# ui/custom_visualizer.py

import math
import random
import time
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
import cairo

ORANGE = (1.0, 0.42, 0.08)
RED = (1.0, 0.27, 0.22)
MAGENTA = (0.85, 0.30, 0.75)
BLUE = (0.18, 0.62, 1.0)
CYAN = (0.35, 0.85, 1.0)


def _mix(c1, c2, t):
    return tuple(a + (b - a) * t for a, b in zip(c1, c2))


def _bar_color(t):
    if t < 0.5:
        return _mix(ORANGE, MAGENTA, t * 2.0)
    return _mix(MAGENTA, BLUE, (t - 0.5) * 2.0)


def _glow_sprite(color, radius):
    size = int(radius * 2) + 2
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    c = size / 2.0
    grad = cairo.RadialGradient(c, c, 0, c, c, radius)
    grad.add_color_stop_rgba(0.0, color[0], color[1], color[2], 0.95)
    grad.add_color_stop_rgba(0.35, color[0], color[1], color[2], 0.55)
    grad.add_color_stop_rgba(1.0, color[0], color[1], color[2], 0.0)
    cr.set_source(grad)
    cr.arc(c, c, radius, 0, 2 * math.pi)
    cr.fill()
    return surface


class CustomVisualizer(Gtk.DrawingArea):
    BAR_COUNT = 64
    SPIKE_COUNT = 72
    BOKEH_COUNT = 46
    MIN_FREQ = 40.0
    MAX_FREQ = 16000.0
    NYQUIST = 24000.0
    FLOOR_DB = -62.0
    CEIL_DB = -12.0

    def __init__(self):
        super().__init__()
        self.bands = self.BAR_COUNT
        self.min_db = self.FLOOR_DB
        self.levels = [0.0] * self.BAR_COUNT
        self.peaks = [0.0] * self.BAR_COUNT
        self.bass = 0.0
        self.energy = 0.0
        self._band_ranges = None
        self._band_ranges_for = 0
        self._cache_size = None
        self._background = None
        self._sphere = None
        self._sprites = {}
        self._start_time = time.monotonic()
        rng = random.Random(7)
        self._bokeh = [
            (rng.uniform(0, 2 * math.pi), rng.random(), rng.uniform(0.006, 0.024), rng.uniform(0.6, 1.4),
             rng.choice((BLUE, BLUE, CYAN, RED, ORANGE)), rng.uniform(0.25, 0.6), rng.randrange(self.BAR_COUNT))
            for _ in range(self.BOKEH_COUNT)
        ]
        self._flow = 0.0
        self._last_draw = None
        self._spike_jitter = [rng.uniform(0.75, 1.25) for _ in range(self.SPIKE_COUNT)]
        self.set_draw_func(self.on_draw)
        self.set_visible(False)
        self.set_can_target(False)

    def _ranges_for(self, bin_count):
        if self._band_ranges_for == bin_count and self._band_ranges:
            return self._band_ranges
        hz_per_bin = self.NYQUIST / bin_count
        ratio = self.MAX_FREQ / self.MIN_FREQ
        ranges = []
        for i in range(self.BAR_COUNT):
            lo_hz = self.MIN_FREQ * ratio ** (i / self.BAR_COUNT)
            hi_hz = self.MIN_FREQ * ratio ** ((i + 1) / self.BAR_COUNT)
            lo = min(bin_count - 1, int(lo_hz / hz_per_bin))
            hi = min(bin_count, max(lo + 1, int(math.ceil(hi_hz / hz_per_bin))))
            centre = math.sqrt(lo_hz * hi_hz)
            tilt = 3.0 * math.log2(centre / 1000.0)
            ranges.append((lo, hi, tilt))
        self._band_ranges = ranges
        self._band_ranges_for = bin_count
        return ranges

    def update_magnitudes(self, new_mags):
        if not new_mags:
            return
        span = self.CEIL_DB - self.FLOOR_DB
        for i, (lo, hi, tilt) in enumerate(self._ranges_for(len(new_mags))):
            db = max(new_mags[lo:hi]) + tilt
            target = max(0.0, min(1.0, (db - self.FLOOR_DB) / span)) ** 1.4
            current = self.levels[i]
            if target > current:
                current = current * 0.25 + target * 0.75
            else:
                current = current * 0.82 + target * 0.18
            self.levels[i] = current
            if current >= self.peaks[i]:
                self.peaks[i] = current
            else:
                self.peaks[i] = max(current, self.peaks[i] - 0.012)
        low = self.levels[:8]
        self.bass = self.bass * 0.6 + (sum(low) / len(low)) * 0.4
        self.energy = self.energy * 0.7 + (sum(self.levels) / self.BAR_COUNT) * 0.3
        self.queue_draw()

    def reset(self):
        self.levels = [0.0] * self.BAR_COUNT
        self.peaks = [0.0] * self.BAR_COUNT
        self.bass = 0.0
        self.energy = 0.0
        self.queue_draw()

    def _sprite(self, color, radius):
        key = (color, int(radius))
        sprite = self._sprites.get(key)
        if sprite is None:
            sprite = _glow_sprite(color, max(2, int(radius)))
            self._sprites[key] = sprite
        return sprite

    def _build_cache(self, width, height):
        self._cache_size = (width, height)
        self._background = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        cr = cairo.Context(self._background)
        cx, cy = width / 2.0, height / 2.0
        grad = cairo.RadialGradient(cx, cy, 0, cx, cy, max(width, height) * 0.75)
        grad.add_color_stop_rgb(0.0, 0.03, 0.05, 0.12)
        grad.add_color_stop_rgb(0.55, 0.01, 0.02, 0.05)
        grad.add_color_stop_rgb(1.0, 0.0, 0.0, 0.01)
        cr.set_source(grad)
        cr.paint()
        radius = min(width, height) * 0.24
        size = int(radius * 2.4)
        self._sphere = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        cr = cairo.Context(self._sphere)
        c = size / 2.0
        halo = cairo.RadialGradient(c, c, radius * 0.7, c, c, radius * 1.15)
        halo.add_color_stop_rgba(0.0, BLUE[0], BLUE[1], BLUE[2], 0.0)
        halo.add_color_stop_rgba(0.85, BLUE[0], BLUE[1], BLUE[2], 0.18)
        halo.add_color_stop_rgba(1.0, BLUE[0], BLUE[1], BLUE[2], 0.0)
        cr.set_source(halo)
        cr.paint()
        rng = random.Random(11)
        dots = int(radius * 32)
        for _ in range(dots):
            u = rng.random()
            r = radius * (u ** 0.35)
            a = rng.uniform(0, 2 * math.pi)
            x = c + r * math.cos(a)
            y = c + r * math.sin(a)
            edge = r / radius
            color = RED if rng.random() < 0.07 else (CYAN if edge > 0.85 else BLUE)
            alpha = 0.15 + 0.75 * edge ** 2
            cr.set_source_rgba(color[0], color[1], color[2], alpha)
            cr.arc(x, y, rng.uniform(0.5, 1.3) * (0.5 + edge * 0.7), 0, 2 * math.pi)
            cr.fill()
        shade = cairo.RadialGradient(c, c, 0, c, c, radius)
        shade.add_color_stop_rgba(0.0, 0.0, 0.0, 0.02, 0.55)
        shade.add_color_stop_rgba(0.75, 0.0, 0.0, 0.02, 0.2)
        shade.add_color_stop_rgba(1.0, 0.0, 0.0, 0.02, 0.0)
        cr.set_source(shade)
        cr.arc(c, c, radius, 0, 2 * math.pi)
        cr.fill()
        self._sprites = {}

    def _controls_top(self, height):
        parent = self.get_parent()
        child = parent.get_child() if parent is not None and hasattr(parent, "get_child") else None
        controls = getattr(child, "controls", None)
        if controls is None or not controls.get_mapped():
            return height
        ok, bounds = controls.compute_bounds(self)
        if not ok:
            return height
        top = int(bounds.get_y())
        return top if 0 < top < height else height

    def on_draw(self, area, cr, width, height):
        height = self._controls_top(height)
        if width < 20 or height < 20:
            return
        if self._cache_size != (width, height):
            self._build_cache(width, height)
        now = time.monotonic() - self._start_time
        cx, cy = width / 2.0, height / 2.0
        base = min(width, height)
        radius = base * 0.24 * (1.0 + 0.07 * self.bass)
        cr.rectangle(0, 0, width, height)
        cr.clip()
        cr.set_source_surface(self._background, 0, 0)
        cr.paint()
        self._draw_bokeh(cr, width, height, now)
        self._draw_spikes(cr, cx, cy, radius, base)
        self._draw_sphere(cr, cx, cy, radius, now)
        self._draw_wave(cr, cx, cy, radius)

    def _draw_bokeh(self, cr, width, height, now):
        if self._last_draw is not None:
            dt = min(0.1, max(0.0, now - self._last_draw))
            self._flow += dt * (0.025 + self.energy * 0.22 + self.bass * 0.12)
        self._last_draw = now
        cx, cy = width / 2.0, height / 2.0
        reach = math.hypot(cx, cy)
        small = min(width, height)
        for angle, start, size, speed, color, alpha, band in self._bokeh:
            travel = (start + self._flow * speed) % 1.0
            dist = reach * (0.18 + 0.85 * travel)
            x = cx + math.cos(angle) * dist
            y = cy + math.sin(angle) * dist
            level = self.levels[band]
            fade = min(1.0, travel * 6.0) * min(1.0, (1.0 - travel) * 4.0)
            r = size * small * (0.8 + 1.4 * level + 0.4 * travel)
            sprite = self._sprite(color, r)
            cr.set_source_surface(sprite, x - sprite.get_width() / 2, y - sprite.get_height() / 2)
            cr.paint_with_alpha(min(1.0, (alpha * 0.45 + level * 0.9) * fade))

    def _draw_spikes(self, cr, cx, cy, radius, base):
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for k in range(self.SPIKE_COUNT):
            angle = (k / self.SPIKE_COUNT) * 2 * math.pi - math.pi / 2
            band = (k * 37) % self.BAR_COUNT
            level = self.levels[band]
            length = base * (0.03 + 0.24 * level * self._spike_jitter[k])
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            x1, y1 = cx + cos_a * radius * 1.02, cy + sin_a * radius * 1.02
            x2, y2 = cx + cos_a * (radius + length), cy + sin_a * (radius + length)
            color = ORANGE if cos_a < -0.15 else (BLUE if cos_a > 0.15 else MAGENTA)
            if k % 3 == 1:
                color = RED if cos_a < 0 else CYAN
            grad = cairo.LinearGradient(x1, y1, x2, y2)
            grad.add_color_stop_rgba(0.0, color[0], color[1], color[2], 0.05)
            grad.add_color_stop_rgba(1.0, color[0], color[1], color[2], 0.85)
            cr.set_source(grad)
            cr.set_line_width(max(1.0, base * 0.0025))
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()
            tip = self._sprite(color, base * (0.008 + 0.012 * level))
            cr.set_source_surface(tip, x2 - tip.get_width() / 2, y2 - tip.get_height() / 2)
            cr.paint()

    def _draw_sphere(self, cr, cx, cy, radius, now):
        sphere = self._sphere
        scale = radius / (min(self._cache_size) * 0.24)
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(now * 0.08)
        cr.scale(scale, scale)
        cr.set_source_surface(sphere, -sphere.get_width() / 2, -sphere.get_height() / 2)
        cr.paint()
        cr.restore()

    def _draw_wave(self, cr, cx, cy, radius):
        width = radius * 2.1
        left = cx - width / 2
        slot = width / self.BAR_COUNT
        bar_w = max(1.0, slot * 0.55)
        max_h = radius * 0.5
        glow = cairo.LinearGradient(left, cy, left + width, cy)
        glow.add_color_stop_rgba(0.0, ORANGE[0], ORANGE[1], ORANGE[2], 0.0)
        glow.add_color_stop_rgba(0.08, ORANGE[0], ORANGE[1], ORANGE[2], 0.9)
        glow.add_color_stop_rgba(0.5, MAGENTA[0], MAGENTA[1], MAGENTA[2], 0.9)
        glow.add_color_stop_rgba(0.92, BLUE[0], BLUE[1], BLUE[2], 0.9)
        glow.add_color_stop_rgba(1.0, BLUE[0], BLUE[1], BLUE[2], 0.0)
        cr.set_source(glow)
        cr.rectangle(left, cy - 1, width, 2)
        cr.fill()
        for i in range(self.BAR_COUNT):
            t = i / (self.BAR_COUNT - 1)
            edge = math.sin(math.pi * (0.08 + 0.84 * t))
            h = max(1.5, self.levels[i] * max_h * edge)
            x = left + i * slot + (slot - bar_w) / 2
            r, g, b = _bar_color(t)
            cr.set_source_rgba(r, g, b, 0.95)
            cr.rectangle(x, cy - h, bar_w, h * 2)
            cr.fill()
            p = self.peaks[i] * max_h * edge
            if p > h + 2:
                cr.set_source_rgba(r, g, b, 0.6)
                cr.rectangle(x, cy - p - 1.5, bar_w, 1.5)
                cr.rectangle(x, cy + p, bar_w, 1.5)
                cr.fill()

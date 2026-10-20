# ui/epg_detail_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GdkPixbuf, Gdk, Pango
import gettext
import logging
import urllib.request
from core.config import APP_USER_AGENT

from background import image_download_pool

_ = gettext.gettext

POSTER_WIDTH = 220
POSTER_HEIGHT = 250


class EPGDetailDialog(Adw.MessageDialog):
    def __init__(self, parent, program_data, tmdb_data=None):
        super().__init__(transient_for=parent)
        self.add_css_class("epg-detail-dialog")
        self.set_property("heading-use-markup", True)
        start_time = program_data['start'].astimezone().strftime('%H:%M')
        stop_time = program_data['stop'].astimezone().strftime('%H:%M')
        title_markup = f"<span weight='bold' size='large'>{GLib.markup_escape_text(program_data['title'])}</span>\n<span size='small'>({start_time} - {stop_time})</span>"
        self.set_heading(title_markup)
        self.set_default_size(560, 420)
        outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.set_extra_child(outer_box)
        self.poster_picture = None
        poster_url = program_data.get('poster_url')
        if poster_url:
            self.poster_picture = Gtk.Picture()
            self.poster_picture.set_halign(Gtk.Align.START)
            self.poster_picture.set_valign(Gtk.Align.START)
            self.poster_picture.set_visible(False)
            outer_box.append(self.poster_picture)
            self._load_poster_async(poster_url)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, hexpand=True)
        outer_box.append(content_box)
        if tmdb_data:
            extra_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            content_box.append(extra_info_box)
            year = tmdb_data.get('release_date', '????').split('-')[0]
            rating = tmdb_data.get('rating', 0)
            extra_info_box.append(Gtk.Label(label=f"{_('Year')}: {year}   •   {_('TMDb Rating')}: {rating:.1f}/10", xalign=0, css_classes=["caption"]))
            extra_info_box.append(Gtk.Label(label=f"{_('Director')}: {tmdb_data.get('director', 'N/A')}", xalign=0, css_classes=["caption"]))
            cast_label = Gtk.Label(label=f"{_('Cast')}: {tmdb_data.get('cast', 'N/A')}", xalign=0, wrap=True, css_classes=["caption"])
            extra_info_box.append(cast_label)
        scrolled_window = Gtk.ScrolledWindow(vexpand=True)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content_box.append(scrolled_window)
        desc_view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 left_margin=6, right_margin=6, top_margin=6, bottom_margin=6)
        desc_view.get_buffer().set_text(program_data.get('desc', _("Description not found.")))
        scrolled_window.set_child(desc_view)
        self.add_response("close", _("Close"))
        self.set_close_response("close")
        self.connect("response", lambda d, r: self.destroy())

    def _load_poster_async(self, url):
        def thread_func():
            pixbuf = None
            try:
                headers = {"User-Agent": APP_USER_AGENT}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = resp.read()
                loader = GdkPixbuf.PixbufLoader.new()
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()
            except Exception as e:
                logging.warning(f"[EPG Detail] Failed to load poster '{url}': {e}")
            if pixbuf:
                GLib.idle_add(self._apply_poster, pixbuf)
        image_download_pool.submit(thread_func)

    def _apply_poster(self, pixbuf):
        if self.poster_picture and pixbuf:
            src_w = pixbuf.get_width()
            src_h = pixbuf.get_height()
            src_ratio = src_w / src_h
            target_ratio = POSTER_WIDTH / POSTER_HEIGHT
            if src_ratio > target_ratio:
                crop_w = max(1, int(src_h * target_ratio))
                x_offset = max(0, (src_w - crop_w) // 2)
                pixbuf = pixbuf.new_subpixbuf(x_offset, 0, crop_w, src_h)
            elif src_ratio < target_ratio:
                crop_h = max(1, int(src_w / target_ratio))
                y_offset = max(0, (src_h - crop_h) // 2)
                pixbuf = pixbuf.new_subpixbuf(0, y_offset, src_w, crop_h)
            scaled_pixbuf = pixbuf.scale_simple(POSTER_WIDTH, POSTER_HEIGHT, GdkPixbuf.InterpType.BILINEAR)
            texture = Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
            self.poster_picture.set_paintable(texture)
            self.poster_picture.set_visible(True)
        return False

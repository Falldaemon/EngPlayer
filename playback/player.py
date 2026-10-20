# playback/player.py

import os
if os.name == 'nt':
    os.environ.setdefault("GST_GL_API", "opengl3")
    os.environ.setdefault("GST_GL_PLATFORM", "wgl")
import gi
import time
import logging
import database
from core.config import PROVIDER_USER_AGENT
import re
import gettext
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GObject, GLib
Gst.init(None)
_ = gettext.gettext

_get_structure = Gst.Caps.get_structure

def _get_structure_compat(self, index):
    structure = _get_structure(self, index)
    if not hasattr(structure, "get_name") and hasattr(structure, "__enter__"):
        return structure.__enter__()
    return structure


Gst.Caps.get_structure = _get_structure_compat
_audioconvert_probe = Gst.ElementFactory.make("audioconvert", None)
_AUDIOCONVERT_REORDERS = _audioconvert_probe is None or _audioconvert_probe.find_property("input-channels-reorder-mode") is not None
from playback import ac3_output
from utils.teletext import TeletextSubtitleDecoder

_MP4_SUBTITLE_HANDLERS = (b"sbtl", b"text", b"subt")

_DVB_REINJECTING_PADS = set()


def _widen_dvb_regions(data):
    if len(data) < 2 or data[0] != 0x20 or data[1] != 0x00:
        return False
    changed = False
    pos = 2
    while pos + 6 <= len(data) and data[pos] == 0x0F:
        length = (data[pos + 4] << 8) | data[pos + 5]
        if data[pos + 1] == 0x11 and length >= 6 and pos + 10 <= len(data):
            width = (data[pos + 8] << 8) | data[pos + 9]
            if 0 < width < 8192:
                width += 1
                data[pos + 8] = width >> 8
                data[pos + 9] = width & 0xFF
                changed = True
        pos += 6 + length
    return changed


def _mp4_boxes(data, start, end):
    pos = start
    while pos + 8 <= end:
        size, kind, header = int.from_bytes(data[pos:pos + 4], "big"), data[pos + 4:pos + 8], 8
        if size == 1:
            size, header = int.from_bytes(data[pos + 8:pos + 16], "big"), 16
        elif size == 0:
            size = end - pos
        if size < header:
            return
        yield kind, pos + header, min(pos + size, end)
        pos += size


def mp4_subtitle_counts(moov):
    counts = {}
    for kind, start, end in _mp4_boxes(moov, 8, len(moov)):
        if kind != b"trak":
            continue
        track_id = handler = count = None
        for child, s1, e1 in _mp4_boxes(moov, start, end):
            if child == b"tkhd":
                track_id = int.from_bytes(moov[s1 + 20:s1 + 24] if moov[s1] == 1 else moov[s1 + 12:s1 + 16], "big")
            elif child == b"mdia":
                for box, s2, e2 in _mp4_boxes(moov, s1, e1):
                    if box == b"hdlr":
                        handler = bytes(moov[s2 + 8:s2 + 12])
                    elif box == b"minf":
                        for stbl, s3, e3 in _mp4_boxes(moov, s2, e2):
                            if stbl == b"stbl":
                                for table, s4, _e4 in _mp4_boxes(moov, s3, e3):
                                    if table in (b"stsz", b"stz2"):
                                        count = int.from_bytes(moov[s4 + 8:s4 + 12], "big")
        if handler in _MP4_SUBTITLE_HANDLERS and track_id is not None and count:
            counts[track_id] = count
    return counts


class Mp4MoovCapture:

    def __init__(self):
        self.next_box = 0
        self.boxes = 0
        self.header = b""
        self.moov = None
        self.moov_start = 0
        self.ranges = []

    def feed(self, offset, size, read):
        end = offset + size
        while self.moov is None:
            want = self.next_box + len(self.header)
            if not offset <= want < end:
                return None
            self.header += read(want - offset, min(16 - len(self.header), end - want))
            if len(self.header) < 8 or (self.header[:4] == b"\x00\x00\x00\x01" and len(self.header) < 16):
                if len(self.header) >= 16 or want + len(self.header) >= end:
                    return None if len(self.header) < 16 else False
                continue
            header, self.header = self.header, b""
            box_size, kind = int.from_bytes(header[:4], "big"), header[4:8]
            if box_size == 1:
                box_size = int.from_bytes(header[8:16], "big")
            self.boxes += 1
            if box_size < 8 or self.boxes > 16:
                return False
            if kind == b"moov":
                if box_size > 32 * 1024 * 1024:
                    return False
                self.moov = bytearray(box_size)
                self.moov_start = self.next_box
                self.moov[:len(header)] = header[:box_size]
                self.ranges = [(self.moov_start, self.moov_start + min(len(header), box_size))]
            else:
                self.next_box += box_size
        lo, hi = max(offset, self.moov_start), min(end, self.moov_start + len(self.moov))
        if lo >= hi:
            return None
        self.moov[lo - self.moov_start:hi - self.moov_start] = read(lo - offset, hi - lo)
        self.ranges.append((lo, hi))
        self.ranges.sort()
        merged = []
        for a, b in self.ranges:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        self.ranges = merged
        if merged == [(self.moov_start, self.moov_start + len(self.moov))]:
            return mp4_subtitle_counts(self.moov)
        return None

def _video_overlay_call(sink, func_name, *args):
    method = getattr(sink, func_name.replace("gst_video_overlay_", ""), None)
    if callable(method):
        method(*args)
        return
    import ctypes
    get_ptr = ctypes.pythonapi.PyCapsule_GetPointer
    get_ptr.restype = ctypes.c_void_p
    get_ptr.argtypes = [ctypes.py_object, ctypes.c_char_p]
    ptr = get_ptr(sink.__gpointer__, None)
    lib = ctypes.CDLL("libgstvideo-1.0-0.dll")
    fn = getattr(lib, func_name)
    fn.restype = None
    fn.argtypes = [ctypes.c_void_p] + [ctypes.c_size_t] * len(args)
    fn(ptr, *args)

class Player(GObject.Object):
    __gsignals__ = {
        "stream-started": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "tracks-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "about-to-finish": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "playback-error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "paintable-changed": (GObject.SignalFlags.RUN_FIRST, None, (GObject.Object,)),
        "playback-finished": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "seek-accumulated": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "spectrum-update": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "ac3-output-unavailable": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "teletext-cue": (GObject.SignalFlags.RUN_FIRST, None, (float, str)),
        "embedded-cue": (GObject.SignalFlags.RUN_FIRST, None, (float, float, str, bool)),
        "live-subtitles-reset": (GObject.SignalFlags.RUN_FIRST, None, ())
    }
    TELETEXT_TRACK_BASE = 1000

    def __init__(self, audio_output=True):
        super().__init__()
        self.audio_output = audio_output
        self.player = None
        self.video_balance = None
        self.paintable = None
        self.equalizer = None
        self.current_uri = None
        self.audio_tracks = []
        self.subtitle_tracks = []
        self._teletext_decoder = None
        self._teletext_pages = []
        self._teletext_page = None
        self._subtitle_counts = {}
        self._text_cues = {}
        self._selected_text_index = -1
        self._last_audio_log = None
        self.total_bytes = 0
        self.last_bitrate = 0
        self.last_time = time.time()
        self.current_rate = 1.0
        self.seek_accumulator_ns = 0
        self.seek_timer_id = None
        self.base_seek_pos_ns = None
        self.bus = None
        self._hw_pipeline_active = False
        self._retry_without_hw = False
        self._ac3_active = False
        self._ac3_failed = False
        self._ac3_notified = False
        self._ac3_volume = None
        self._layout_filter = None
        self._volume = None
        self._window_handle_provider = None
        self._native_active_cb = None
        self.native_sink = None
        self._native_size = None          
        self._aspect_mode = "contain"  

    def set_window_handle_provider(self, provider, on_active=None):
        self._window_handle_provider = provider
        self._native_active_cb = on_active

    def _notify_native_active(self, active):
        logging.debug(f"Player: native video output {'started' if active else 'stopping'}.")
        if self._native_active_cb:
            try:
                self._native_active_cb(active)
            except Exception as e:
                logging.debug(f"Native video active callback failed: {e}")

    def expose_native(self, width=None, height=None):
        if width and height:
            self._native_size = (int(width), int(height))
        if self.native_sink:
            self._apply_native_aspect()
            try:
                _video_overlay_call(self.native_sink, "gst_video_overlay_expose")
            except Exception as e:
                logging.debug(f"d3d11videosink expose failed: {e}")

    def set_aspect_mode(self, mode):
        self._aspect_mode = mode
        self._apply_native_aspect()

    def _native_video_size(self):
        try:
            pad = self.native_sink.get_static_pad("sink")
            caps = pad.get_current_caps() if pad else None
            if not caps:
                return None
            s = caps.get_structure(0)
            ok_w, w = s.get_int("width")
            ok_h, h = s.get_int("height")
            if not (ok_w and ok_h) or w <= 0 or h <= 0:
                return None
            ok_par, par_n, par_d = s.get_fraction("pixel-aspect-ratio")
            if ok_par and par_n > 0 and par_d > 0:
                w = w * par_n / par_d
            return (w, h)
        except Exception:
            return None

    def _set_render_rectangle(self, x, y, w, h):
        import ctypes
        get_ptr = ctypes.pythonapi.PyCapsule_GetPointer
        get_ptr.restype = ctypes.c_void_p
        get_ptr.argtypes = [ctypes.py_object, ctypes.c_char_p]
        ptr = get_ptr(self.native_sink.__gpointer__, None)
        fn = ctypes.CDLL("libgstvideo-1.0-0.dll").gst_video_overlay_set_render_rectangle
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        fn(ptr, int(x), int(y), int(w), int(h))

    def _apply_native_aspect(self):
        if not self.native_sink:
            return
        mode = self._aspect_mode
        logging.info(f"Native aspect: mode={mode}, window={self._native_size}, video={self._native_video_size()}")
        try:
            self.native_sink.set_property("force-aspect-ratio", mode != "fill")
            rect = None
            if mode == "cover" and self._native_size:
                vsize = self._native_video_size()
                if vsize:
                    ww, wh = self._native_size
                    vw, vh = vsize
                    scale = max(ww / vw, wh / vh)
                    rw, rh = vw * scale, vh * scale
                    rect = ((ww - rw) / 2, (wh - rh) / 2, rw, rh)
            if rect:
                logging.info(f"Native aspect: render rectangle {tuple(int(v) for v in rect)}")
                self._set_render_rectangle(*rect)
            else:
                self._set_render_rectangle(0, 0, -1, -1) 
        except Exception:
            logging.exception(f"Could not apply aspect mode '{mode}' to d3d11videosink")

    def _setup_native_video_sink(self, hwnd):
        sink = Gst.ElementFactory.make("d3d11videosink", None)
        if not sink:
            logging.warning("d3d11videosink not available, falling back to the GTK sink.")
            return False
        try:
            _video_overlay_call(sink, "gst_video_overlay_set_window_handle", hwnd)
        except Exception as e:
            logging.error(f"Could not attach d3d11videosink to HWND {hwnd:#x}: {e}. Falling back to the GTK sink.")
            return False
        self._set_hardware_priority(not self._retry_without_hw)
        sink.set_property("force-aspect-ratio", True)
        self.player.set_property("video-sink", sink)
        self.native_sink = sink
        self.paintable = None
        self.video_balance = None
        self._hw_pipeline_active = not self._retry_without_hw
        logging.info(f"Native D3D11 video sink active (HWND {hwnd:#x}). Color balance not available on this path yet.")
        return True

    def _set_hardware_priority(self, use_hw):
        registry = Gst.Registry.get()
        hw_decoders = ["d3d11h265dec", "d3d11h264dec", "d3d11vp9dec", "d3d11av1dec"]
        sw_decoders = ["avdec_h264", "avdec_h265", "avdec_hevc"]
        found_hw = False
        for dec_name in hw_decoders:
            feature = registry.find_feature(dec_name, Gst.ElementFactory)
            if feature:
                feature.set_rank(Gst.Rank.PRIMARY + 256 if use_hw else Gst.Rank.NONE)
                found_hw = True
        for sw_name in sw_decoders:
            feature = registry.find_feature(sw_name, Gst.ElementFactory)
            if feature:
                feature.set_rank(Gst.Rank.MARGINAL if use_hw else Gst.Rank.PRIMARY)
        if found_hw:
            logging.info(f">>> Hardware decode priority set to: {use_hw}")
        else:
            logging.info("No D3D11 hardware decoder found on this system; using default decoder ranking.")
        return found_hw

    def _setup_player(self):
        self._spectrum_generation = getattr(self, "_spectrum_generation", 0) + 1
        self._spectrum_latency_ns = 0
        self._spectrum_latency_checked = 0.0
        if self.native_sink:
            self._notify_native_active(False)
        if self.player:
            if self.bus:
                self.bus.remove_signal_watch()
                self.bus = None
            self.player.set_state(Gst.State.NULL)
            self.player = None
            self.paintable = None
            self.video_balance = None
        self.native_sink = None
        self._teletext_decoder = None
        self._teletext_pages = []
        self._teletext_page = None
        self._subtitle_counts = {}
        self._text_cues = {}
        self._selected_text_index = -1
        self._last_audio_log = None
        self.player = Gst.ElementFactory.make("playbin", None)
        self.player.connect("element-setup", self._on_element_setup)
        if not self.player:
            raise Exception("Failed to create GStreamer 'playbin' element.")
        flags = self.player.get_property("flags")
        TEXT_FLAG = 4
        flags &= ~TEXT_FLAG
        self.player.set_property("flags", flags)
        self.player.set_property("current-text", -1)
        self.audio_filter_bin = None
        saved_vis = database.get_config_value('visualizer_type') or "custom"
        if saved_vis == "custom":
            try:
                bin_desc = "equalizer-10bands name=eq ! spectrum bands=512 threshold=-80 post-messages=true interval=30000000 name=spec"
                self.audio_filter_bin = Gst.parse_bin_from_description(bin_desc, True)
                self.equalizer = self.audio_filter_bin.get_by_name("eq")
                logging.info("Custom Visualizer (Spectrum + Equalizer) loaded.")
            except Exception as e:
                logging.error(f"Error creating custom visualizer bin: {e}")
                self.equalizer = None
                self.audio_filter_bin = None
        else:
            try:
                self.audio_filter_bin = Gst.ElementFactory.make("equalizer-10bands", "equalizer")
                self.equalizer = self.audio_filter_bin
            except Exception as e:
                logging.error(f"Error creating equalizer: {e}")
                self.equalizer = None
                self.audio_filter_bin = None
            if saved_vis != "none":
                visualizer = None
                if os.name != 'nt':
                    try:
                        visualizer = Gst.parse_bin_from_description(
                            f"{saved_vis} ! videoconvert ! capsfilter caps=video/x-raw,format=RGBx", True)
                    except Exception as e:
                        logging.warning(f"Could not wrap visualizer '{saved_vis}', using it directly: {e}")
                if visualizer is None:
                    visualizer = Gst.ElementFactory.make(saved_vis, "visualizer")
                if visualizer:
                    self.player.set_property("vis-plugin", visualizer)
                    logging.info(f"Built-in Visualizer '{saved_vis}' loaded.")
                else:
                    logging.warning(f"GStreamer '{saved_vis}' plugin not found.")
        if self.equalizer:
            for i in range(10):
                band_value = database.get_config_value(f"eq_band_{i}")
                if band_value is not None:
                    self.set_equalizer_band(i, float(band_value))
        self._ac3_active = False
        self._ac3_volume = None
        self._layout_filter = None
        self._layout_matrix_size = None
        use_ac3 = self.audio_output and ac3_output.is_enabled() and not self._ac3_failed
        ac3_sink = ac3_output.create_sink() if use_ac3 else None
        if use_ac3 and ac3_sink is None and not self._ac3_notified:
            self._ac3_notified = True
            self.emit("ac3-output-unavailable")
        scaletempo = Gst.ElementFactory.make("scaletempo", None)
        if not self.audio_output:
            self.player.set_property("audio-sink", Gst.ElementFactory.make("fakesink", None))
            logging.info("Audio output disabled for this player (muted secondary view).")
        elif ac3_sink:
            self.player.set_property("audio-sink", ac3_sink)
            self._ac3_active = True
            self._ac3_volume = ac3_sink.get_by_name(ac3_output.VOLUME_NAME)
            if self._ac3_volume is not None and self._volume is not None:
                self._ac3_volume.set_property("volume", self._volume ** 3)
            logging.info("Dolby Digital (AC-3) audio output enabled.")
        elif scaletempo:
            try:
                layout_convert = "" if _AUDIOCONVERT_REORDERS else "audioconvert name=layout_convert ! "
                audio_sink_bin = Gst.parse_bin_from_description(
                    f"{layout_convert}capsfilter name=layout_filter ! audioconvert ! scaletempo ! autoaudiosink", True)
                self._layout_filter = audio_sink_bin.get_by_name("layout_filter")
                layout_convert_element = audio_sink_bin.get_by_name("layout_convert")
                if layout_convert_element is not None:
                    layout_convert_element.get_static_pad("sink").add_probe(
                        Gst.PadProbeType.EVENT_DOWNSTREAM | Gst.PadProbeType.QUERY_DOWNSTREAM, self._layout_matrix_probe)
                self.player.set_property("audio-sink", audio_sink_bin)
                logging.info("Scaletempo enabled for pitch correction during speed changes.")
            except Exception as e:
                logging.error(f"Error setting up scaletempo audio sink: {e}")
        else:
            logging.warning("GStreamer 'scaletempo' plugin not found. Pitch correction disabled.")
        if self._volume is not None and self.audio_output and not self._ac3_active:
            self.player.set_property("volume", self._volume ** 3)
        c = float(database.get_config_value("video_contrast") or 1.0)
        b = float(database.get_config_value("video_brightness") or 0.0)
        s = float(database.get_config_value("video_saturation") or 1.0)
        h = float(database.get_config_value("video_hue") or 0.0)
        native_handle = None
        if os.name == 'nt' and self._window_handle_provider:
            try:
                native_handle = self._window_handle_provider()
            except Exception as e:
                logging.warning(f"Native window handle unavailable, using GTK sink: {e}")
        if native_handle and self._setup_native_video_sink(native_handle):
            pass
        else:
            try:
                use_hw = False
                if os.name == 'nt':
                    hw_found = self._set_hardware_priority(not self._retry_without_hw)
                    use_hw = hw_found and not self._retry_without_hw
                if use_hw:
                    pipeline_str = (
                        "d3d11download ! queue max-size-buffers=3 ! "
                        "glupload ! glcolorconvert ! "
                        "gtk4paintablesink name=gtksink"
                    )
                else:
                    pipeline_str = (
                        "glupload ! glcolorconvert ! glcolorscale ! "
                        "glcolorbalance name=video_correction ! "
                        "gtk4paintablesink name=gtksink"
                    )
                sink_bin = Gst.parse_bin_from_description(pipeline_str, True)
                self.player.set_property("video-sink", sink_bin)
                real_sink = sink_bin.get_by_name("gtksink")
                self.paintable = real_sink.get_property("paintable")
                self.video_balance = sink_bin.get_by_name("video_correction")
                self._hw_pipeline_active = use_hw
                if self.video_balance:
                    self.video_balance.set_property("contrast", c)
                    self.video_balance.set_property("brightness", b)
                    self.video_balance.set_property("saturation", s)
                    self.video_balance.set_property("hue", h)
                    logging.info("GPU Color Balance (glcolorbalance) active.")
                elif use_hw:
                    logging.info("Hardware decode bridge active - color balance disabled (matches v0.1.4 pipeline).")
                logging.info(f"GPU Sink initialized successfully. (Hardware decode bridge: {use_hw})")
            except Exception as e:
                self._hw_pipeline_active = False
                logging.error(f"GPU Sink error: {e}. Switching to Software Fallback.")
                try:
                    gtk_sink = Gst.ElementFactory.make("gtk4paintablesink", None)
                    self.player.set_property("video-sink", gtk_sink)
                    self.paintable = gtk_sink.get_property("paintable")
                    filter_bin = Gst.parse_bin_from_description(
                        "videoconvert ! videobalance name=video_correction ! videoconvert", True
                    )
                    self.video_balance = filter_bin.get_by_name("video_correction")
                    if self.video_balance:
                        self.video_balance.set_property("contrast", c)
                        self.video_balance.set_property("brightness", b)
                        self.video_balance.set_property("saturation", s)
                        self.video_balance.set_property("hue", h)
                        self.player.set_property("video-filter", filter_bin)
                        logging.info("Software Color Balance (videobalance) active.")
                except Exception as ex:
                    logging.error(f"Software Fallback error: {ex}")
                    self.video_balance = None
        bus = self.player.get_bus()
        self.bus = bus
        bus.add_signal_watch()
        bus.connect("message::error", self.on_bus_error)
        bus.connect("message::eos", self.on_eos)
        bus.connect("message::state-changed", self.on_bus_state_changed)
        bus.connect("message::application", self.on_application_message)
        bus.connect("message::element", self.on_element_message)

    def set_video_correction(self, setting_type, value):
        if self.video_balance:
            try:
                self.video_balance.set_property(setting_type, float(value))
            except Exception as e:
                logging.error(f"Failed to apply video setting ({setting_type}): {e}")

    def _on_element_setup(self, playbin, element):
        if element.find_property("user-agent") is not None:
            element.set_property("user-agent", PROVIDER_USER_AGENT)
            factory_name = element.get_factory().get_name() if element.get_factory() else element.get_name()
            logging.debug(f"User-Agent set on {factory_name}: {PROVIDER_USER_AGENT}")
        factory = element.get_factory()
        if factory:
            klass = factory.get_metadata("klass")
            if klass and "Decoder" in klass and "Video" in klass:
                logging.info(f">>> VIDEO DECODER SELECTED: {factory.get_name()}")
            if factory.get_name() == "audioconvert" and element.find_property("input-channels-reorder-mode") is not None:
                Gst.util_set_object_arg(element, "input-channels-reorder-mode", "unpositioned")
            if factory.get_name() == "dvbsuboverlay":
                text_pad = element.get_static_pad("text_sink")
                if text_pad:
                    if hasattr(Gst.PadProbeInfo, "writable_object"):
                        text_pad.add_probe(Gst.PadProbeType.BUFFER, self._dvb_subtitle_region_probe)
                        logging.info("DVB subtitle region workaround attached.")
                    else:
                        text_pad.add_probe(Gst.PadProbeType.BUFFER, self._dvb_subtitle_region_probe_copy)
                        logging.info("DVB subtitle region workaround attached (copy mode).")
            if factory.get_name() == "tsdemux":
                element.connect("pad-added", self._on_ts_pad_added)
            if factory.get_name() == "input-selector":
                element.connect("pad-added", self._on_selector_pad_added, playbin)
            if factory.get_name() == "textoverlay":
                text_pad = element.get_static_pad("text_sink")
                if text_pad:
                    if element.find_property("wait-text") is not None:
                        element.set_property("wait-text", False)
                    text_pad.add_probe(Gst.PadProbeType.BUFFER, lambda pad, info: Gst.PadProbeReturn.DROP)
                    logging.info("Embedded text subtitles routed to the subtitle label.")
            if factory.get_name() == "qtdemux":
                demux_pad = element.get_static_pad("sink")
                if demux_pad:
                    demux_pad.add_probe(Gst.PadProbeType.BUFFER, self._mp4_header_probe, (playbin, Mp4MoovCapture()))
            if klass and "Source" in klass:
                pad = element.get_static_pad("src")
                if pad:
                    pad.add_probe(Gst.PadProbeType.BUFFER, self._bitrate_probe_cb)

    def _on_ts_pad_added(self, demux, pad):
        caps = pad.get_current_caps() or pad.query_caps(None)
        if not caps or caps.get_size() == 0 or caps.get_structure(0).get_name() != "application/x-teletext":
            return
        if self._teletext_decoder is None:
            self._teletext_decoder = TeletextSubtitleDecoder()
        pad.add_probe(Gst.PadProbeType.BUFFER, self._teletext_probe, self._teletext_decoder)
        logging.info("Teletext stream found, looking for subtitle pages.")

    def _teletext_probe(self, pad, info, decoder):
        buf = info.get_buffer()
        if buf is None or buf.pts == Gst.CLOCK_TIME_NONE:
            return Gst.PadProbeReturn.OK
        try:
            events = decoder.feed(buf.extract_dup(0, buf.get_size()), buf.pts)
            if events:
                event = pad.get_sticky_event(Gst.EventType.SEGMENT, 0)
                segment = event.parse_segment() if event else None
                for page, pts, text in events:
                    position = segment.to_stream_time(Gst.Format.TIME, pts) if segment else pts
                    if position == Gst.CLOCK_TIME_NONE or position < 0:
                        continue
                    GLib.idle_add(self._on_teletext_event, decoder, page, position / Gst.MSECOND, text)
        except Exception as e:
            logging.debug(f"Teletext decode skipped: {e}")
        return Gst.PadProbeReturn.OK

    def _on_teletext_event(self, decoder, page, start_ms, text):
        if decoder is not self._teletext_decoder:
            return GLib.SOURCE_REMOVE
        if page not in self._teletext_pages:
            self._teletext_pages.append(page)
            logging.info(f"Teletext subtitle page found: {page}")
            self._discover_tracks()
        if page == self._teletext_page:
            self.emit("teletext-cue", start_ms, text)
        return GLib.SOURCE_REMOVE

    _FALLBACK_CHANNEL_MASKS = {3: 0xb, 4: 0x33, 5: 0x37, 6: 0x3f, 7: 0x13f, 8: 0xc3f}

    def _on_selector_pad_added(self, selector, pad, playbin):
        if pad.direction == Gst.PadDirection.SINK:
            pad.add_probe(Gst.PadProbeType.BUFFER, self._text_cue_probe, playbin)
            pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, self._audio_layout_probe)

    def _audio_layout_probe(self, pad, info):
        event = info.get_event()
        if event is None or event.type != Gst.EventType.CAPS:
            return Gst.PadProbeReturn.OK
        caps = event.parse_caps()
        if not caps or caps.get_size() == 0 or caps.get_structure(0).get_name() != "audio/x-raw":
            return Gst.PadProbeReturn.REMOVE
        ok, channels = caps.get_structure(0).get_int("channels")
        mask = self._FALLBACK_CHANNEL_MASKS.get(channels) if ok else None
        text = caps.to_string()
        layout_filter = self._layout_filter
        if mask is None or layout_filter is None:
            return Gst.PadProbeReturn.OK
        if "channel-mask" in text and "channel-mask=(bitmask)0x0000000000000000" not in text:
            return Gst.PadProbeReturn.OK
        layout_filter.set_property("caps", Gst.Caps.from_string(
            f"audio/x-raw, channels=(int){channels}, channel-mask=(bitmask)0x{mask:x}; "
            f"audio/x-raw, channels=(int)[1, {channels - 1}]; audio/x-raw, channels=(int)[{channels + 1}, 64]"))
        logging.info(f"Audio has {channels} channels without a layout; using the standard channel order.")
        return Gst.PadProbeReturn.OK

    def _layout_matrix_probe(self, pad, info):
        caps = None
        if info.type & Gst.PadProbeType.EVENT_DOWNSTREAM:
            event = info.get_event()
            if event is not None and event.type == Gst.EventType.CAPS:
                caps = event.parse_caps()
        elif info.type & Gst.PadProbeType.QUERY_DOWNSTREAM:
            query = info.get_query()
            if query is not None and query.type == Gst.QueryType.ACCEPT_CAPS:
                caps = query.parse_accept_caps()
        if not caps or caps.get_size() == 0 or not caps.is_fixed():
            return Gst.PadProbeReturn.OK
        text = caps.to_string()
        ok, channels = caps.get_structure(0).get_int("channels")
        unpositioned = ok and channels in self._FALLBACK_CHANNEL_MASKS and (
            "channel-mask" not in text or "channel-mask=(bitmask)0x0000000000000000" in text)
        size = channels if unpositioned else 0
        if self._layout_matrix_size != size:
            self._layout_matrix_size = size
            rows = [", ".join("(float)1.0" if i == j else "(float)0.0" for j in range(size)) for i in range(size)]
            Gst.util_set_object_arg(pad.get_parent_element(), "mix-matrix", "<" + ", ".join(f"<{row}>" for row in rows) + ">")
            logging.debug(f"Audio layout matrix {'set for %d channels' % size if size else 'cleared'}.")
        return Gst.PadProbeReturn.OK

    def _text_cue_probe(self, pad, info, playbin):
        caps = pad.get_current_caps()
        if not caps or caps.get_size() == 0:
            return Gst.PadProbeReturn.OK
        if caps.get_structure(0).get_name() != "text/x-raw":
            return Gst.PadProbeReturn.REMOVE
        buf = info.get_buffer()
        if buf is None or buf.pts == Gst.CLOCK_TIME_NONE:
            return Gst.PadProbeReturn.OK
        try:
            is_markup = caps.get_structure(0).get_string("format") == "pango-markup"
            text = buf.extract_dup(0, buf.get_size()).decode("utf-8", "replace").replace("\x00", "").strip()
            event = pad.get_sticky_event(Gst.EventType.SEGMENT, 0)
            segment = event.parse_segment() if event else None
            start = segment.to_stream_time(Gst.Format.TIME, buf.pts) if segment else buf.pts
            if text and 0 <= start != Gst.CLOCK_TIME_NONE:
                duration = buf.duration if buf.duration != Gst.CLOCK_TIME_NONE else 5 * Gst.SECOND
                GLib.idle_add(self._on_text_cue, playbin, pad, start / Gst.MSECOND,
                              (start + duration) / Gst.MSECOND, text, is_markup)
        except Exception as e:
            logging.debug(f"Embedded subtitle skipped: {e}")
        return Gst.PadProbeReturn.OK

    def _on_text_cue(self, playbin, pad, start_ms, end_ms, text, is_markup):
        if playbin is not self.player:
            return GLib.SOURCE_REMOVE
        cue = (start_ms, end_ms, text, is_markup)
        if pad not in self._text_cues:
            logging.info(f"Subtitle track {self._text_pad_index(pad)}: first cue received at {start_ms / 1000:.1f}s.")
        self._text_cues.setdefault(pad, {})[(round(start_ms), text)] = cue
        if pad == self._active_text_pad():
            self.emit("embedded-cue", *cue)
        return GLib.SOURCE_REMOVE

    def _active_text_pad(self):
        if self._teletext_page is not None or self._selected_text_index < 0:
            return None
        return self.player.emit("get-text-pad", self._selected_text_index)

    def _replay_text_cues(self, playbin, index):
        if playbin is not self.player or self._selected_text_index != index:
            logging.info(f"Subtitle track {index}: replay skipped, track {self._selected_text_index} is now selected.")
            return GLib.SOURCE_REMOVE
        pad = self._active_text_pad()
        ok, position = self.player.query_position(Gst.Format.TIME)
        position_ms = position / Gst.MSECOND if ok else 0
        replayed = 0
        for cue in list(self._text_cues.get(pad, {}).values()) if pad else []:
            if cue[1] >= position_ms:
                self.emit("embedded-cue", *cue)
                replayed += 1
        logging.info(f"Subtitle track {index}: replayed {replayed} cached cues from {position_ms / 1000:.1f}s.")
        return GLib.SOURCE_REMOVE

    def _text_pad_index(self, pad):
        for i in range(self.player.get_property("n-text")):
            if self.player.emit("get-text-pad", i) == pad:
                return i
        return -1

    def _log_subtitle_cache(self):
        parts = []
        for i in range(self.player.get_property("n-text")):
            cues = self._text_cues.get(self.player.emit("get-text-pad", i), {})
            last = max((cue[0] for cue in cues.values()), default=None)
            parts.append(f"{i}: {len(cues)} cues" + (f", last at {last / 1000:.1f}s" if last is not None else ""))
        ok, position = self.player.query_position(Gst.Format.TIME)
        where = f"{position / Gst.SECOND:.1f}s" if ok else "unknown"
        logging.info(f"Subtitle cache at {where}: " + ("; ".join(parts) or "no text tracks"))

    def _log_audio_input(self, reason):
        try:
            index = max(self.player.get_property("current-audio"), 0)
            pad = self.player.emit("get-audio-pad", index)
            caps = pad.get_current_caps() if pad else None
            if not caps or caps.get_size() == 0:
                return
            structure = caps.get_structure(0)
            tags = self.player.emit("get-audio-tags", index)
            codec = tags.get_string(Gst.TAG_AUDIO_CODEC)[1] if tags and tags.get_string(Gst.TAG_AUDIO_CODEC)[0] else "unknown codec"
            mask = re.search(r"channel-mask=\(bitmask\)(0x[0-9a-f]+)", caps.to_string())
            output = "Dolby Digital (AC-3)" if self._ac3_active else "normal"
            mask_text = f"channel-mask {int(mask.group(1), 16):#x}" if mask else "no channel-mask"
            message = (f"track {index}, {codec}, {structure.get_int('channels')[1]} ch, {mask_text}, "
                       f"{structure.get_int('rate')[1]} Hz, output: {output}")
            if message != self._last_audio_log:
                self._last_audio_log = message
                logging.info(f"Audio ({reason}): {message}.")
        except Exception as e:
            logging.debug(f"Could not log audio input: {e}")

    @staticmethod
    def _dvb_subtitle_region_probe(pad, info):
        try:
            with info.writable_object() as buf:
                with buf.map(Gst.MapFlags.READ | Gst.MapFlags.WRITE) as mapped:
                    data = mapped.data
                    if len(data) < 2 or data[0] != 0x20 or data[1] != 0x00:
                        return Gst.PadProbeReturn.OK
                    pos = 2
                    while pos + 6 <= len(data) and data[pos] == 0x0F:
                        length = (data[pos + 4] << 8) | data[pos + 5]
                        if data[pos + 1] == 0x11 and length >= 6 and pos + 10 <= len(data):
                            width = (data[pos + 8] << 8) | data[pos + 9]
                            if 0 < width < 8192:
                                width += 1
                                data[pos + 8] = width >> 8
                                data[pos + 9] = width & 0xFF
                        pos += 6 + length
        except Exception as e:
            logging.debug(f"DVB subtitle region workaround skipped: {e}")
        return Gst.PadProbeReturn.OK

    @staticmethod
    def _dvb_subtitle_region_probe_copy(pad, info):
        if pad in _DVB_REINJECTING_PADS:
            return Gst.PadProbeReturn.OK
        try:
            buf = info.get_buffer()
            data = bytearray(buf.extract_dup(0, buf.get_size()))
            if not _widen_dvb_regions(data):
                return Gst.PadProbeReturn.OK
            patched = Gst.Buffer.new_wrapped(bytes(data))
            patched.pts, patched.dts, patched.duration = buf.pts, buf.dts, buf.duration
            _DVB_REINJECTING_PADS.add(pad)
            try:
                pad.chain(patched)
            finally:
                _DVB_REINJECTING_PADS.discard(pad)
            return Gst.PadProbeReturn.DROP
        except Exception as e:
            logging.debug(f"DVB subtitle region workaround skipped: {e}")
        return Gst.PadProbeReturn.OK

    def _on_source_setup(self, playbin, source):
        pad = source.get_static_pad("src")
        if pad:
            pad.add_probe(Gst.PadProbeType.BUFFER, self._bitrate_probe_cb)

    def _bitrate_probe_cb(self, pad, info):
        buffer = info.get_buffer()
        if buffer:
            self.total_bytes += buffer.get_size()
        return Gst.PadProbeReturn.OK

    def play_url(self, url, media_type="video", _hw_retry=False, flags=None, audio_filter=None):
        if not _hw_retry:
            self._retry_without_hw = False
            self._last_start_flags = flags
            self._last_audio_filter = audio_filter
        else:
            flags = getattr(self, "_last_start_flags", None)
            audio_filter = getattr(self, "_last_audio_filter", None)
        self._last_media_type = media_type
        self._setup_player()
        is_remote = url.startswith("http") or url.startswith("https")
        if media_type == "music" and not is_remote:
            try:
                self.player.set_property("buffer-duration", 200 * Gst.MSECOND)
                self.player.set_property("ring-buffer-max-size", 0)
                logging.info("Local Music Mode: Buffer set to 200ms for instant Audio FX response.")
            except Exception as e:
                logging.warning(f"Could not set music buffer: {e}")
        else:
            try:
                saved_buffer = database.get_config_value('stream_buffer_duration')
                logging.info(f"[BUFFER] Raw value read from DB: '{saved_buffer}'")
                if saved_buffer and str(saved_buffer).isdigit():
                    buffer_seconds = int(saved_buffer)
                    logging.info(f"[BUFFER] User setting found. Using: {buffer_seconds} seconds.")
                else:
                    buffer_seconds = 4
                    logging.info(f"[BUFFER] No setting found or invalid. Using default: {buffer_seconds} seconds.")
                nano_seconds = buffer_seconds * Gst.SECOND
                self.player.set_property("buffer-duration", nano_seconds)
                ring_size = 100 * 1024 * 1024 if media_type == "iptv" else 0
                self.player.set_property("ring-buffer-max-size", ring_size)
                logging.info(f"[BUFFER] SUCCESS: Buffer set to {buffer_seconds}s ({nano_seconds} ns), ring buffer {'on' if ring_size else 'off'}.")
            except Exception as e:
                logging.error(f"[BUFFER] CRITICAL ERROR: Could not set buffer! Detail: {e}")
                self.player.set_property("buffer-duration", 4 * Gst.SECOND)
        self.emit("paintable-changed", self.paintable)
        self.current_uri = url
        self.player.set_property("uri", url)
        if flags is not None:
            self.player.set_property("flags", flags)
        if audio_filter is not None:
            self.player.set_property("audio-filter", self.audio_filter_bin if audio_filter else None)
        self.player.set_state(Gst.State.PAUSED)

    def on_bus_error(self, bus, message):
        if self.native_sink:
            self._notify_native_active(False)
        err, debug = message.parse_error()
        error_message = f"GStreamer Error: {err.message} ({debug})"
        if "Proxy Authentication Required" in error_message:
            logging.debug(error_message)
            self.emit("playback-error", err.message)
            self.player.set_state(Gst.State.NULL)
            return
        if self._ac3_active and ac3_output.is_ac3_error(message, error_message):
            logging.warning(f"Dolby Digital output failed, falling back to normal audio. Detail: {error_message}")
            self._ac3_failed = True
            retry_uri = self.current_uri
            self.player.set_state(Gst.State.NULL)
            self.emit("ac3-output-unavailable")
            if retry_uri:
                GLib.idle_add(self._retry_play, retry_uri)
            return
        is_resource_error = err.domain == GLib.quark_to_string(Gst.ResourceError.quark())
        src_factory = message.src.get_factory() if isinstance(message.src, Gst.Element) else None
        is_source_error = bool(src_factory) and src_factory.get_name().endswith("src")
        is_no_data = (err.domain == GLib.quark_to_string(Gst.StreamError.quark())
                      and err.code == int(Gst.StreamError.TYPE_NOT_FOUND))
        if (getattr(self, "_hw_pipeline_active", False) and not self._retry_without_hw
                and not is_resource_error and not is_source_error and not is_no_data):
            logging.warning(f"Hardware decode pipeline failed, retrying with software pipeline. Detail: {error_message}")
            self._retry_without_hw = True
            retry_uri = self.current_uri
            self.player.set_state(Gst.State.NULL)
            if retry_uri:
                GLib.idle_add(self._retry_play, retry_uri)
            return
        logging.error(error_message)
        self.emit("playback-error", err.message)
        self.player.set_state(Gst.State.NULL)

    def _retry_play(self, uri):
        self.play_url(uri, media_type=getattr(self, "_last_media_type", "video"), _hw_retry=True)
        self.play()
        return GLib.SOURCE_REMOVE

    def reset_ac3_fallback(self):
        self._ac3_failed = False
        self._ac3_notified = False

    def _log_ac3_input(self):
        try:
            pad = self.player.get_property("audio-sink").get_static_pad("sink")
            caps = pad.get_current_caps() if pad else None
            if caps:
                s = caps.get_structure(0)
                logging.info(f"AC-3 output: encoding {s.get_int('channels')[1]} channels at {s.get_int('rate')[1]} Hz.")
        except Exception as e:
            logging.debug(f"AC-3 output: could not read input caps: {e}")

    def on_bus_state_changed(self, bus, message):
        if not self.player or message.src != self.player:
            return
        old_state, new_state, pending_state = message.parse_state_changed()
        flags = self.player.get_property("flags")
        current_text = self.player.get_property("current-text")
        if new_state == Gst.State.PLAYING:
            if self._ac3_active:
                self._log_ac3_input()
            if self.native_sink:
                self._apply_native_aspect() 
                self._notify_native_active(True)
            self.emit("stream-started")
            self._log_audio_input("playing")
            self._discover_tracks()
            self.apply_subtitle_font()

    def on_application_message(self, bus, message):
        if message.get_structure().get_name() == 'stream-info':
            self._discover_tracks()

    def _discover_tracks(self):
        if not self.player: return
        self.audio_tracks.clear()
        self.subtitle_tracks.clear()
        num_audio = self.player.get_property("n-audio")
        seen_audio_labels = {}
        for i in range(num_audio):
            tags = self.player.emit("get-audio-tags", i)
            lang_code = (tags.get_string(Gst.TAG_LANGUAGE_CODE)[1] if tags and tags.get_string(Gst.TAG_LANGUAGE_CODE)[0] else _("Track {number}").format(number=i+1))
            title = tags.get_string(Gst.TAG_TITLE)[1] if tags and tags.get_string(Gst.TAG_TITLE)[0] else ""
            short_title = self._short_subtitle_title(title, lang_code)
            label = f"{lang_code} — {short_title}" if short_title else lang_code
            audio_format = self._audio_format(i, tags)
            if audio_format:
                label = f"{label} ({audio_format})"
            seen_audio_labels[label] = seen_audio_labels.get(label, 0) + 1
            if seen_audio_labels[label] > 1:
                label = f"{label} {seen_audio_labels[label]}"
            self.audio_tracks.append({"index": i, "name": lang_code, "label": label})
        num_text = self.player.get_property("n-text")
        text_tracks = []
        for i in range(num_text):
            tags = self.player.emit("get-text-tags", i)
            lang_code = (tags.get_string(Gst.TAG_LANGUAGE_CODE)[1] if tags and tags.get_string(Gst.TAG_LANGUAGE_CODE)[0] else _("Subtitle {number}").format(number=i+1))
            title = tags.get_string(Gst.TAG_TITLE)[1] if tags and tags.get_string(Gst.TAG_TITLE)[0] else ""
            track_id = tags.get_string("container-specific-track-id")[1] if tags and tags.get_string("container-specific-track-id")[0] else ""
            count = self._subtitle_counts.get(int(track_id)) if track_id.isdigit() else None
            text_tracks.append((i, lang_code, title, count))
        largest = {}
        for _index, lang_code, _title, count in text_tracks:
            largest[lang_code] = max(largest.get(lang_code, 0), count or 0)
        seen_labels = {}
        for i, lang_code, title, count in text_tracks:
            forced = "forced" in title.lower() or (count is not None and count < largest[lang_code] * 0.15)
            short_title = self._short_subtitle_title(title, lang_code)
            label = f"{lang_code} — {short_title}" if short_title else lang_code
            if forced and "forced" not in label.lower():
                label = f"{label} — {_('Forced')}"
            subtitle_format = self._subtitle_format(i)
            if subtitle_format:
                label = f"{label} ({subtitle_format})"
            seen_labels[label] = seen_labels.get(label, 0) + 1
            if seen_labels[label] > 1:
                label = f"{label} {seen_labels[label]}"
            self.subtitle_tracks.append({"index": i, "name": lang_code, "label": label, "forced": forced})
        for page in self._teletext_pages:
            self.subtitle_tracks.append({"index": self.TELETEXT_TRACK_BASE + page,
                                         "name": _("Teletext {page}").format(page=page)})
        if self._teletext_decoder and self.audio_tracks:
            current_audio = max(0, min(self.player.get_property("current-audio"), len(self.audio_tracks) - 1))
            self._teletext_decoder.language = self.audio_tracks[current_audio]["name"]
        self.emit("tracks-changed")

    _SUBTITLE_FORMATS = {"text/x-raw": "Text", "application/x-ass": "ASS", "application/x-ssa": "SSA",
                         "subpicture/x-dvb": "DVB", "subpicture/x-pgs": "PGS", "subpicture/x-dvd": "VobSub"}
    _RELEASE_NAME = re.compile(r"\b(\d{3,4}p|S\d{1,2}E\d{1,2}|WEB-?DL|WEB-?Rip|BluRay|BDRip|HDTV|[xh]\.?26[45]|HEVC|DDP?\d|AAC|AMZN|NF|DSNP)\b",
                               re.IGNORECASE)

    @classmethod
    def _short_subtitle_title(cls, title, lang_code):
        title = (title or "").strip()
        if not title or title.lower() == lang_code.lower() or cls._RELEASE_NAME.search(title):
            return ""
        return title if len(title) <= 20 else title[:19] + "…"

    def _mp4_header_probe(self, pad, info, data):
        playbin, capture = data
        buf = info.get_buffer()
        if buf is None:
            return Gst.PadProbeReturn.OK
        if buf.offset == Gst.BUFFER_OFFSET_NONE:
            return Gst.PadProbeReturn.REMOVE
        try:
            counts = capture.feed(buf.offset, buf.get_size(), lambda start, length: buf.extract_dup(start, length))
        except Exception as e:
            logging.debug(f"Subtitle line counts unavailable: {e}")
            return Gst.PadProbeReturn.REMOVE
        if counts is None:
            return Gst.PadProbeReturn.OK
        if counts:
            GLib.idle_add(self._on_subtitle_counts, playbin, counts)
        return Gst.PadProbeReturn.REMOVE

    def _on_subtitle_counts(self, playbin, counts):
        if playbin is self.player:
            self._subtitle_counts = counts
            logging.info(f"Subtitle line counts read for {len(counts)} tracks.")
            self._discover_tracks()
        return GLib.SOURCE_REMOVE

    _AUDIO_CODECS = (("E-AC-3", "E-AC-3"), ("AC-3", "AC-3"), ("TrueHD", "TrueHD"), ("DTS", "DTS"),
                     ("AAC", "AAC"), ("Layer 3", "MP3"), ("MP3", "MP3"), ("Layer 2", "MP2"),
                     ("Opus", "Opus"), ("FLAC", "FLAC"), ("Vorbis", "Vorbis"), ("PCM", "PCM"))
    _AUDIO_LAYOUTS = {1: "Mono", 2: "Stereo", 6: "5.1", 8: "7.1"}

    def _audio_format(self, index, tags):
        codec = tags.get_string(Gst.TAG_AUDIO_CODEC)[1] if tags and tags.get_string(Gst.TAG_AUDIO_CODEC)[0] else ""
        codec = next((short for key, short in self._AUDIO_CODECS if key.lower() in codec.lower()), codec)
        channels = 0
        try:
            pad = self.player.emit("get-audio-pad", index)
            caps = pad.get_current_caps() if pad else None
            if caps and caps.get_size():
                channels = caps.get_structure(0).get_int("channels")[1]
        except Exception as e:
            logging.debug(f"Could not read audio channels: {e}")
        layout = self._AUDIO_LAYOUTS.get(channels, f"{channels} ch" if channels else "")
        return " ".join(part for part in (codec, layout) if part)

    def _subtitle_format(self, index):
        try:
            pad = self.player.emit("get-text-pad", index)
            caps = pad.get_current_caps() if pad else None
            if caps and caps.get_size():
                return self._SUBTITLE_FORMATS.get(caps.get_structure(0).get_name(), "")
        except Exception as e:
            logging.debug(f"Could not read subtitle format: {e}")
        return ""

    def is_subtitle_track_active(self, index):
        if not self.player:
            return False
        if index >= self.TELETEXT_TRACK_BASE:
            return self._teletext_page == index - self.TELETEXT_TRACK_BASE
        return self._teletext_page is None and self._selected_text_index == index

    def get_audio_tracks(self):
        return self.audio_tracks

    def get_subtitle_tracks(self):
        return self.subtitle_tracks

    def set_audio_track(self, index):
        if self.player:
            self.player.set_property("current-audio", index)
            self._log_audio_input("track changed")

    def apply_subtitle_font(self, font_string=None):
        if not self.player: return
        try:
            if font_string is None: font_string = database.get_config_value("subtitle_font") or "Sans 12"
            self.player.set_property('subtitle-font-desc', font_string)
        except Exception as e: logging.error(f"Could not set embedded subtitle font: {e}")

    def set_subtitle_track(self, index):
        if not self.player: return
        if index >= self.TELETEXT_TRACK_BASE:
            self._teletext_page = index - self.TELETEXT_TRACK_BASE
            index = -1
        else:
            self._teletext_page = None
        TEXT_FLAG = 4
        flags = self.player.get_property("flags")
        was_active = index >= 0 and self._selected_text_index == index
        if index == -1:
            flags &= ~TEXT_FLAG
        else:
            flags |= TEXT_FLAG
        self.player.set_property("flags", flags)
        self.player.set_property("current-text", index)
        self._selected_text_index = index
        if self._teletext_page is not None:
            logging.info(f"Subtitle selected: teletext page {self._teletext_page}.")
        elif index == -1:
            logging.info("Subtitles turned off.")
        else:
            label = next((t.get("label", t["name"]) for t in self.subtitle_tracks if t["index"] == index), "?")
            logging.info(f"Subtitle selected: track {index} ({label}), already active: {was_active}.")
            self._log_subtitle_cache()
        if index == -1:
            self.emit("live-subtitles-reset")
        elif not was_active:
            GLib.idle_add(self._replay_text_cues, self.player, index)

    def play(self):
        if self.player: self.player.set_state(Gst.State.PLAYING)

    def pause(self):
        if self.player: self.player.set_state(Gst.State.PAUSED)

    def toggle_play_pause(self):
        if not self.player: return
        state = self.player.get_state(0).state
        if state == Gst.State.PLAYING:
            self.pause()
        elif state == Gst.State.PAUSED:
            self.play()

    def set_volume(self, value):
        self._volume = value
        if self._ac3_active and self._ac3_volume is not None:
            self._ac3_volume.set_property("volume", value ** 3)
        elif self.player:
            self.player.set_property("volume", value ** 3)

    def get_volume(self):
        if self._ac3_active and self._volume is not None:
            return self._volume
        return self.player.get_property("volume") ** (1/3) if self.player else 0.0

    def seek_forward(self, s=10):
        self._seek_relative(s * Gst.SECOND)

    def seek_backward(self, s=10):
        self._seek_relative(-s * Gst.SECOND)

    def _seek_relative(self, amount_ns):
        if not self.player: return
        if self.base_seek_pos_ns is None:
            ok, pos_ns = self.player.query_position(Gst.Format.TIME)
            if ok:
                self.base_seek_pos_ns = pos_ns
            else:
                return
        self.seek_accumulator_ns += amount_ns
        seconds = int(self.seek_accumulator_ns / Gst.SECOND)
        self.emit("seek-accumulated", seconds)
        if self.seek_timer_id:
            GLib.source_remove(self.seek_timer_id)
        self.seek_timer_id = GLib.timeout_add(400, self._execute_accumulated_seek)

    def _execute_accumulated_seek(self):
        if not self.player or self.base_seek_pos_ns is None:
            self.seek_timer_id = None
            return GLib.SOURCE_REMOVE
        target_ns = self.base_seek_pos_ns + self.seek_accumulator_ns
        target_ns = max(0, target_ns)
        rate = getattr(self, 'current_rate', 1.0)
        if rate == 1.0:
            self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, target_ns)
        else:
            self.player.seek(
                rate, Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                Gst.SeekType.SET, target_ns, Gst.SeekType.SET, -1
            )
        self.seek_accumulator_ns = 0
        self.seek_timer_id = None
        self.base_seek_pos_ns = None
        self.emit("seek-accumulated", 0)
        return GLib.SOURCE_REMOVE

    def shutdown(self):
        if self.native_sink:
            self._notify_native_active(False)
            self.native_sink = None
        if self.player:
            if self.bus:
                self.bus.remove_signal_watch()
                self.bus = None
            self.player.set_state(Gst.State.NULL)
            self.player = None

    def get_duration(self):
        if not self.player: return 0
        ok, duration_ns = self.player.query_duration(Gst.Format.TIME)
        return duration_ns if ok else 0

    def get_position(self):
        if not self.player: return 0
        ok, position_ns = self.player.query_position(Gst.Format.TIME)
        return position_ns if ok else 0

    def get_seek_range(self):
        if not self.player: return None, None
        query = Gst.Query.new_seeking(Gst.Format.TIME)
        if self.player.query(query):
            _format, seekable, start, end = query.parse_seeking()
            if seekable and end != Gst.CLOCK_TIME_NONE: return start, end
        return None, None

    def seek_to_seconds(self, seconds):
        if not self.player or seconds is None: return
        target_ns = int(seconds * Gst.SECOND)
        rate = getattr(self, 'current_rate', 1.0)
        if rate == 1.0:
            self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, target_ns)
        else:
            self.player.seek(
                rate,
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                Gst.SeekType.SET,
                target_ns,
                Gst.SeekType.SET,
                -1
            )

    def set_playback_rate(self, rate=1.0):
        if not self.player:
            return
        self.current_rate = rate
        ok, position_ns = self.player.query_position(Gst.Format.TIME)
        if not ok:
            position_ns = 0
        try:
            self.player.seek(
                rate,
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                Gst.SeekType.SET,
                position_ns,
                Gst.SeekType.SET,
                -1
            )
            logging.info(f"Playback rate changed to: {rate}x")
        except Exception as e:
            logging.error(f"Error changing playback rate: {e}")

    def get_stream_info(self):
        if not self.player: return "-", "-"
        video_text = f'{_("Video")}: -'; audio_text = f'{_("Audio")}: -'
        try:
            video_sink = self.player.get_property("video-sink")
            if video_sink:
                video_pad = video_sink.get_static_pad("sink")
                if video_pad and (caps := video_pad.get_current_caps()) and (s := caps.get_structure(0)):
                    width, height = s.get_int("width")[1], s.get_int("height")[1]
                    success, fr_num, fr_den = s.get_fraction("framerate")
                    framerate = fr_num / fr_den if success and fr_den > 0 else 0
                    video_text = f'{_("Video")}: {width}x{height} @ {framerate:.2f}fps'
        except Exception as e: logging.debug(f"Could not retrieve video stream info: {e}")
        try:
            audio_index = max(self.player.get_property("current-audio"), 0)
            audio_pad = self.player.emit("get-audio-pad", audio_index)
            if audio_pad and (caps := audio_pad.get_current_caps()) and (s := caps.get_structure(0)) \
                    and s.has_field("rate") and s.has_field("channels"):
                rate, channels = s.get_int("rate")[1], s.get_int("channels")[1]
                ch_desc = {
                    1: _("Mono"),
                    2: _("Stereo"),
                    6: "5.1",
                    8: "7.1"
                }.get(channels, _("{count} ch").format(count=channels))
                audio_text = f'{_("Audio")}: {ch_desc}, {rate/1000:.1f} kHz'
        except Exception as e: logging.debug(f"Could not retrieve audio stream info: {e}")
        return video_text, audio_text

    def get_detailed_stats(self):
        now = time.time()
        elapsed = now - self.last_time
        if elapsed >= 1.0:
            self.last_bitrate = (self.total_bytes * 8) / elapsed
            self.total_bytes = 0
            self.last_time = now
        safe_url = "-"
        if self.current_uri:
            url_pattern = re.compile(r'(https?://[^/]+/(?:series|movie|timeshift|live)?/?(?:[a-zA-Z0-9_-]+/)?)([^/]+)/([^/]+)(/[0-9a-zA-Z._-]+)')
            def mask_url(match):
                base = match.group(1)
                stream_id = match.group(4)
                return f"{base}***/****{stream_id}"
            safe_url = url_pattern.sub(mask_url, self.current_uri)
        stats = {
            "video_codec": "-", "audio_codec": "-", "resolution": "-",
            "fps": "-", "format": "-", "channels": "-", "sample_rate": "-",
            "profile": "-", "level": "-", "language": "-",
            "bitrate": self.last_bitrate,
            "url": self.current_uri or "-",
            "safe_url": safe_url
        }
        if not self.player:
            return stats
        v_pad = self.player.emit("get-video-pad", 0)
        if v_pad:
            caps = v_pad.get_current_caps()
            if caps:
                s = caps.get_structure(0)
                stats["resolution"] = f"{s.get_int('width')[1]}x{s.get_int('height')[1]}"
                stats["format"] = s.get_string("format")
                stats["profile"] = s.get_string("profile") if s.has_field("profile") else "-"
                stats["level"] = s.get_string("level") if s.has_field("level") else "-"
                success, fn, fd = s.get_fraction("framerate")
                if success and fd > 0:
                    stats["fps"] = f"{fn / fd:.2f}"
            tags = self.player.emit("get-video-tags", 0)
            if tags:
                success, codec = tags.get_string("video-codec")
                if success: stats["video_codec"] = codec
        a_pad = self.player.emit("get-audio-pad", 0)
        if a_pad:
            caps = a_pad.get_current_caps()
            if caps:
                s = caps.get_structure(0)
                stats["channels"] = str(s.get_int("channels")[1]) if s.has_field("channels") else "-"
                rate = s.get_int("rate")[1] if s.has_field("rate") else "-"
                stats["sample_rate"] = f"{rate} Hz" if rate != "-" else "-"
            a_tags = self.player.emit("get-audio-tags", 0)
            if a_tags:
                success, a_codec = a_tags.get_string("audio-codec")
                if success: stats["audio_codec"] = a_codec
                success, lang = a_tags.get_string("language-code")
                stats["language"] = lang if success else "-"
        return stats

    def on_eos(self, bus, message):
        logging.info("Playback finished (EOS).")
        self.player.set_state(Gst.State.PAUSED)
        self.emit("playback-finished")

    def set_equalizer_band(self, band_index, value):
        if self.equalizer:
            prop_name = f"band{band_index}"
            clamped_value = max(-24.0, min(value, 12.0))
            self.equalizer.set_property(prop_name, clamped_value)

    def get_equalizer_band_labels(self):
        labels = [
            "31\nHz",
            "62\nHz",
            "125\nHz",
            "250\nHz",
            "500\nHz",
            "1\nkHz",
            "2\nkHz",
            "4\nkHz",
            "8\nkHz",
            "16\nkHz"
        ]
        return labels

    def enable_equalizer(self):
        if self.player and self.audio_filter_bin:
            logging.info("Audio Filter (EQ/Spectrum) ENABLED.")
            self.player.set_property("audio-filter", self.audio_filter_bin)

    def disable_equalizer(self):
        if self.player:
            logging.info("Audio Filter DISABLED.")
            self.player.set_property("audio-filter", None)

    def on_player_about_to_finish(self, playbin):
        logging.debug("Player: 'about-to-finish' signal received from GStreamer.")
        self.emit("about-to-finish")

    def on_element_message(self, bus, message):
        if message.get_structure() and message.get_structure().get_name() == "spectrum":
            struct_str = message.get_structure().to_string()
            start_marker = "magnitude=(float){"
            start_idx = struct_str.find(start_marker)
            if start_idx != -1:
                start_idx += len(start_marker)
                end_idx = struct_str.find("}", start_idx)
                if end_idx != -1:
                    mags_raw = struct_str[start_idx:end_idx]
                    mags = [float(x.strip()) for x in mags_raw.split(',') if x.strip()]
                    if mags:
                        delay_ms = self._spectrum_delay_ms(message.get_structure())
                        if delay_ms > 5:
                            GLib.timeout_add(delay_ms, self._emit_spectrum, mags, self._spectrum_generation)
                        else:
                            self.emit("spectrum-update", mags)

    def _emit_spectrum(self, mags, generation):
        if generation == self._spectrum_generation:
            self.emit("spectrum-update", mags)
        return GLib.SOURCE_REMOVE

    def _spectrum_delay_ms(self, structure):
        try:
            if not self.player:
                return 0
            clock = self.player.get_clock()
            running_time = structure.get_value("running-time")
            if clock is None or running_time is None:
                return 0
            now = time.monotonic()
            if now - self._spectrum_latency_checked > 2.0:
                self._spectrum_latency_checked = now
                query = Gst.Query.new_latency()
                if self.player.query(query):
                    _live, min_latency, _max_latency = query.parse_latency()
                    self._spectrum_latency_ns = min_latency
            render_at = self.player.get_base_time() + running_time + self._spectrum_latency_ns
            delay_ns = render_at - clock.get_time()
            return int(max(0, min(delay_ns, 3 * Gst.SECOND)) // Gst.MSECOND)
        except Exception:
            return 0

# playback/player.py

import gi
import time
import logging
import database
import gettext
gi.require_version("Gst", "1.0")
from gi.repository import Gst, GObject
Gst.init(None)
_ = gettext.gettext
class Player(GObject.Object):
    __gsignals__ = {
        "stream-started": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "tracks-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "about-to-finish": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "playback-error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "paintable-changed": (GObject.SignalFlags.RUN_FIRST, None, (GObject.Object,)),
        "playback-finished": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self):
        super().__init__()
        self.player = None
        self.video_balance = None
        self.paintable = None
        self.equalizer = None
        self.current_uri = None
        self.audio_tracks = []
        self.subtitle_tracks = []
        self.total_bytes = 0
        self.last_bitrate = 0
        self.last_time = time.time()

    def _setup_player(self):
        """Creates a clean player and linked elements each time."""
        if self.player:
            self.player.set_state(Gst.State.NULL)
            self.player = None
            self.paintable = None
            self.video_balance = None
        self.player = Gst.ElementFactory.make("playbin", None)
        self.player.connect("element-setup", self._on_element_setup)
        if not self.player:
            raise Exception("Failed to create GStreamer 'playbin' element.")
        flags = self.player.get_property("flags")
        TEXT_FLAG = 4
        flags &= ~TEXT_FLAG
        self.player.set_property("flags", flags)
        self.player.set_property("current-text", -1)
        try:
            self.equalizer = Gst.ElementFactory.make("equalizer-10bands", "equalizer")
            if self.equalizer:
                logging.info("10-band equalizer successfully linked to player.")
                for i in range(10):
                    band_value = database.get_config_value(f"eq_band_{i}")
                    if band_value is not None:
                        self.set_equalizer_band(i, float(band_value))
            else:
                logging.warning("GStreamer 'equalizer-10band' plugin not found. Equalizer disabled.")
                self.equalizer = None
        except Exception as e:
            logging.error(f"Error creating equalizer: {e}")
            self.equalizer = None
        visualizer = Gst.ElementFactory.make("goom", "visualizer")
        if visualizer:
            self.player.set_property("vis-plugin", visualizer)
        else:
            logging.warning("GStreamer 'goom' plugin not found. Visualizer disabled.")
        c = float(database.get_config_value("video_contrast") or 1.0)
        b = float(database.get_config_value("video_brightness") or 0.0)
        s = float(database.get_config_value("video_saturation") or 1.0)
        h = float(database.get_config_value("video_hue") or 0.0)
        try:
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
            if self.video_balance:
                self.video_balance.set_property("contrast", c)
                self.video_balance.set_property("brightness", b)
                self.video_balance.set_property("saturation", s)
                self.video_balance.set_property("hue", h)
                logging.info("GPU Color Balance (glcolorbalance) active.")
            logging.info("GPU Sink initialized successfully.")
        except Exception as e:
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
        bus.add_signal_watch()
        bus.connect("message::error", self.on_bus_error)
        bus.connect("message::eos", self.on_eos)
        bus.connect("message::state-changed", self.on_bus_state_changed)
        bus.connect("message::application", self.on_application_message)
        
    def set_video_correction(self, setting_type, value):
        if self.video_balance:
            try:
                self.video_balance.set_property(setting_type, float(value))
            except Exception as e:
                logging.error(f"Failed to apply video setting ({setting_type}): {e}")        

    def _on_element_setup(self, playbin, element):
        factory = element.get_factory()
        if factory:
            klass = factory.get_metadata("klass")
            if klass and "Source" in klass:
                pad = element.get_static_pad("src")
                if pad:
                    pad.add_probe(Gst.PadProbeType.BUFFER, self._bitrate_probe_cb)

    def _on_source_setup(self, playbin, source):
        pad = source.get_static_pad("src")
        if pad:
            pad.add_probe(Gst.PadProbeType.BUFFER, self._bitrate_probe_cb)

    def _bitrate_probe_cb(self, pad, info):
        buffer = info.get_buffer()
        if buffer:
            self.total_bytes += buffer.get_size()
        return Gst.PadProbeReturn.OK        

    def play_url(self, url, media_type="video"):
        """Destroys the old player, sets up a new one, and puts playback in the PAUSED state."""
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
                self.player.set_property("ring-buffer-max-size", 100 * 1024 * 1024)               
                logging.info(f"[BUFFER] SUCCESS: Buffer set to {buffer_seconds}s ({nano_seconds} ns).")
            except Exception as e:
                logging.error(f"[BUFFER] CRITICAL ERROR: Could not set buffer! Detail: {e}")
                self.player.set_property("buffer-duration", 4 * Gst.SECOND)
        self.emit("paintable-changed", self.paintable)
        self.current_uri = url
        self.player.set_property("uri", url)
        self.player.set_state(Gst.State.PAUSED)

    def on_bus_error(self, bus, message):
        err, debug = message.parse_error()
        error_message = f"GStreamer Error: {err.message} ({debug})"
        if "Proxy Authentication Required" in error_message:
            logging.debug(error_message)
        else:
            logging.error(error_message)
        self.emit("playback-error", err.message)
        self.player.set_state(Gst.State.NULL)

    def on_bus_state_changed(self, bus, message):
        if not self.player or message.src != self.player:
            return
        old_state, new_state, pending_state = message.parse_state_changed()
        flags = self.player.get_property("flags")
        current_text = self.player.get_property("current-text")
        if new_state == Gst.State.PLAYING:
            self.emit("stream-started")
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
        for i in range(num_audio):
            tags = self.player.emit("get-audio-tags", i)
            lang_code = (tags.get_string(Gst.TAG_LANGUAGE_CODE)[1] if tags and tags.get_string(Gst.TAG_LANGUAGE_CODE)[0] else _("Track {number}").format(number=i+1))
            self.audio_tracks.append({"index": i, "name": lang_code})
        num_text = self.player.get_property("n-text")
        for i in range(num_text):
            tags = self.player.emit("get-text-tags", i)
            lang_code = (tags.get_string(Gst.TAG_LANGUAGE_CODE)[1] if tags and tags.get_string(Gst.TAG_LANGUAGE_CODE)[0] else _("Subtitle {number}").format(number=i+1))
            self.subtitle_tracks.append({"index": i, "name": lang_code})
        self.emit("tracks-changed")

    def get_audio_tracks(self):
        return self.audio_tracks

    def get_subtitle_tracks(self):
        return self.subtitle_tracks

    def set_audio_track(self, index):
        if self.player: self.player.set_property("current-audio", index)

    def apply_subtitle_font(self, font_string=None):
        if not self.player: return
        try:
            if font_string is None: font_string = database.get_config_value("subtitle_font") or "Sans 12"
            self.player.set_property('subtitle-font-desc', font_string)
        except Exception as e: logging.error(f"Could not set embedded subtitle font: {e}")

    def set_subtitle_track(self, index):
        if not self.player: return
        TEXT_FLAG = 4
        flags = self.player.get_property("flags")
        if index == -1:
            flags &= ~TEXT_FLAG
        else:
            flags |= TEXT_FLAG
        self.player.set_property("flags", flags)
        self.player.set_property("current-text", index)
        flags_after = self.player.get_property("flags")
        current_text_after = self.player.get_property("current-text")

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
        if self.player: self.player.set_property("volume", value ** 3)

    def get_volume(self):
        return self.player.get_property("volume") ** (1/3) if self.player else 0.0

    def seek_forward(self, s=10):
        self._seek_relative(s * Gst.SECOND)

    def seek_backward(self, s=10):
        self._seek_relative(-s * Gst.SECOND)

    def _seek_relative(self, amount_ns):
        if not self.player: return
        ok, pos_ns = self.player.query_position(Gst.Format.TIME)
        if ok:
            new_pos = pos_ns + amount_ns
            self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, new_pos if new_pos > 0 else 0)

    def shutdown(self):
        if self.player:
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
        self.player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE, target_ns)

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
            audio_sink = self.player.get_property("audio-sink")
            if audio_sink:
                audio_pad = audio_sink.get_static_pad("sink")
                if audio_pad and (caps := audio_pad.get_current_caps()) and (s := caps.get_structure(0)):
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
        stats = {
            "video_codec": "-", "audio_codec": "-", "resolution": "-",
            "fps": "-", "format": "-", "channels": "-", "sample_rate": "-",
            "profile": "-", "level": "-", "language": "-",
            "bitrate": self.last_bitrate,
            "url": self.current_uri or "-"
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
        """Runs when the end of the video is reached and emits a signal."""
        logging.info("Playback finished (EOS).")
        self.player.set_state(Gst.State.PAUSED)
        self.emit("playback-finished")

    def set_equalizer_band(self, band_index, value):
        """Sets the value of a specific equalizer band."""
        if self.equalizer:
            prop_name = f"band{band_index}"
            clamped_value = max(-24.0, min(value, 12.0))
            self.equalizer.set_property(prop_name, clamped_value)

    def get_equalizer_band_labels(self):
        """Returns the standard frequency labels for the equalizer bands."""
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
        """Sets the equalizer as the audio filter."""
        if self.player and self.equalizer:
            logging.info("Equalizer ENABLED.")
            self.player.set_property("audio-filter", self.equalizer)

    def disable_equalizer(self):
        """Disables the equalizer by removing the audio filter."""
        if self.player:
            logging.info("Equalizer DISABLED.")
            self.player.set_property("audio-filter", None)

    def on_player_about_to_finish(self, playbin):
        """Emits our own signal when the 'about-to-finish' signal is received from GStreamer."""
        logging.debug("Player: 'about-to-finish' signal received from GStreamer.")
        self.emit("about-to-finish")
      

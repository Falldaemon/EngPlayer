# utils/subtitle_manager.py

import re, logging
from gi.repository import GLib, Gst, Gdk, Pango
import database
import gettext
_ = gettext.gettext

def parse_srt(srt_content):
    subs = []
    try:
        try:
            decoded_content = srt_content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                decoded_content = srt_content.decode('cp1254')
            except UnicodeDecodeError:
                decoded_content = srt_content.decode('iso-8859-9', errors='ignore')
            except Exception as decode_err_inner:
                 logging.error(f"SRT decode error (inner): {decode_err_inner}")
                 decoded_content = srt_content.decode('utf-8', errors='ignore')
        lines = re.split(r'\r?\n\r?\n', decoded_content.strip())
        logging.debug(f"parse_srt: Found {len(lines)} blocks to parse.")
        for block in lines:
            parts = block.strip().split('\n')
            if len(parts) >= 3:
                time_line = parts[1]
                time_match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})', time_line)
                if time_match:
                    h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, time_match.groups())
                    start_time_ms = (h1 * 3600 + m1 * 60 + s1) * 1000 + ms1
                    end_time_ms = (h2 * 3600 + m2 * 60 + s2) * 1000 + ms2
                    text = "\n".join(parts[2:])
                    text = re.sub(r'<[^>]+>', '', text)
                    subs.append({'start': start_time_ms, 'end': end_time_ms, 'text': text})
                else:
                     logging.warning(f"parse_srt: Skipping invalid time format: {time_line}")
        logging.debug(f"parse_srt: Successfully parsed {len(subs)} subtitle lines.")
        return subs
    except Exception as e:
        logging.exception(f"Unexpected error in parse_srt: {e}")
        return []

class SubtitleManager:
    def __init__(self, player, overlay_label):
        self.player = player
        self.label = overlay_label
        self.subtitles = []
        self.timer_id = None
        self.last_markup = None
        self.delay_ms = 0
        self._debug_counter = 0

    def load_from_file(self, filepath):
        self.clear()
        logging.info(f"Loading subtitle file: {filepath}")
        try:
            with open(filepath, 'rb') as f:
                content_bytes = f.read()
            logging.debug(f"File read, {len(content_bytes)} bytes. Calling parse_srt...")
            parsed_subs = parse_srt(content_bytes)
            self.subtitles = parsed_subs
            if self.subtitles:
                logging.info(f"Successfully loaded {len(self.subtitles)} subtitle lines.")
                for i, sub in enumerate(self.subtitles[:3]):
                    logging.debug(f"  -> Line {i+1}: Start={sub['start']}, End={sub['end']}, Text='{sub['text'][:50]}...'")
                self.start()
                return True
            else:
                logging.warning("Could not parse subtitle file or file is empty.")
                return False
        except FileNotFoundError:
             logging.error(f"Subtitle file not found: {filepath}")
             return False
        except Exception as e:
            logging.exception(f"Error reading/processing subtitle file: {filepath} - {e}")
            return False

    def clear(self):
        self.stop()
        self.subtitles = []
        if self.label:
            GLib.idle_add(self.label.set_markup, "")
            GLib.idle_add(self.label.hide)
        self.last_markup = None
        logging.debug("SubtitleManager cleared.")

    def start(self):
        self.stop()
        if self.subtitles:
            logging.debug("Starting SubtitleManager timer.")
            self.timer_id = GLib.timeout_add(100, self._update)
        else:
             logging.warning("Subtitle list is empty, timer not started.")

    def stop(self):
        if self.timer_id:
            logging.debug("Stopping SubtitleManager timer.")
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def _update(self):
        self._debug_counter = (self._debug_counter + 1) % 10
        log_this_time = (self._debug_counter == 0)
        if not self.subtitles or not self.player or not self.player.player:
             return False
        try:
             _ret, state, _pending = self.player.player.get_state(0)
             if state != Gst.State.PLAYING: return True
             ok, current_pos_ns = self.player.player.query_position(Gst.Format.TIME)
             if not ok: return True
        except Exception as gst_err:
             logging.error(f"SubtitleManager update: Could not get GStreamer state/position: {gst_err}")
             return False
        current_pos_ms = current_pos_ns / 1_000_000
        adjusted_pos_ms = current_pos_ms - self.delay_ms
        if log_this_time:
            logging.debug(f"SubtitleManager Update: Delay={self.delay_ms}ms | CurrentPos={current_pos_ms:.0f}ms | AdjustedPos={adjusted_pos_ms:.0f}ms")
        found_sub = next((sub for sub in self.subtitles if sub['start'] <= adjusted_pos_ms < sub['end']), None)
        if log_this_time and found_sub:
            logging.debug(f"  -> Sub Found: Start={found_sub['start']}ms | End={found_sub['end']}ms | Text='{found_sub['text'][:20]}...'")
        elif log_this_time and not found_sub:
            logging.debug(f"  -> Sub Not Found for AdjustedPos={adjusted_pos_ms:.0f}ms")
        if found_sub:
            try:
                font_desc = database.get_config_value("subtitle_font") or "Sans 12"
                color_str = database.get_config_value("subtitle_color") or "rgba(255,255,255,1.0)"
                bgcolor_str = database.get_config_value("subtitle_bgcolor") or "rgba(0,0,0,0.6)"
                bgopacity_str = database.get_config_value("subtitle_bgopacity") or "0.6"
                fg_rgba = Gdk.RGBA(); fg_rgba.parse(color_str)
                font_color_hex = f'#{int(fg_rgba.red*255):02x}{int(fg_rgba.green*255):02x}{int(fg_rgba.blue*255):02x}'
                bg_rgba = Gdk.RGBA(); bg_rgba.parse(bgcolor_str)
                try: bg_alpha_val = max(0.1, min(1.0, float(bgopacity_str)))
                except ValueError: bg_alpha_val = 0.6
                bg_color_hex = f'#{int(bg_rgba.red*255):02x}{int(bg_rgba.green*255):02x}{int(bg_rgba.blue*255):02x}{int(bg_alpha_val*255):02x}'
                escaped_text = GLib.markup_escape_text(found_sub['text'])
                markup = (f"<span font_desc='{font_desc}' "
                          f"foreground='{font_color_hex}' "
                          f"background='{bg_color_hex}'>"
                          f" {escaped_text} "
                          f"</span>")
                if self.last_markup != markup:
                    if log_this_time: logging.debug(f"  -> Updating Label (Markup Changed)")
                    self.label.set_markup(markup)
                    self.last_markup = markup
                if not self.label.get_visible():
                    if log_this_time: logging.debug(f"  -> Showing Label")
                    self.label.show()
            except Exception as label_err:
                 logging.error(f"Error setting subtitle label: {label_err}")
                 return False
        else:
            if self.label.get_visible():
                if log_this_time: logging.debug(f"  -> Hiding Label")
                self.label.hide()
            self.last_markup = None
        return True

    def set_delay(self, delay_ms):
        """Called by MainWindow to set the delay."""
        logging.debug(f"SubtitleManager: Delay set -> {delay_ms} ms")
        self.delay_ms = delay_ms
        self.last_markup = None

# ui/player_controls.py

import gi
import os
import gettext
import logging
import threading
import urllib.request
from gi.repository import Gtk, GLib, GdkPixbuf, Gdk, GObject, Gio
from .placeholder_icon import PlaceholderIcon
from utils.theme_utils import get_icon_theme_folder
gi.require_version("Gtk", "4.0")
_ = gettext.gettext
class PlayerControls(Gtk.Box):
    __gsignals__ = {
        "audio-track-selected": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "subtitle-button-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "record-button-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "catch-up-button-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "seek-value-changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        "stop-trailer-clicked": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4, **kwargs)
        self.is_fullscreen = False
        self.add_css_class("player-controls")
        self.volume_popover_timer = None
        self.buttons = {}
        self.seek_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, hexpand=True, valign=Gtk.Align.CENTER)
        self.append(self.seek_box)
        self.time_label_current = Gtk.Label(label="00:00", css_classes=["caption"])
        self.seek_box.append(self.time_label_current)
        self.progress_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.progress_slider.set_draw_value(False)
        self.progress_slider.set_hexpand(True)
        self.progress_slider.connect("change-value", self.on_slider_value_changed)
        self.seek_box.append(self.progress_slider)
        self.time_label_duration = Gtk.Label(label="00:00", css_classes=["caption"])
        self.seek_box.append(self.time_label_duration)
        controls_center_box = Gtk.CenterBox()
        controls_center_box.set_valign(Gtk.Align.CENTER)
        self.append(controls_center_box)
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls_center_box.set_start_widget(left_box)
        self.channel_icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, width_request=50, height_request=50, valign=Gtk.Align.CENTER)
        left_box.append(self.channel_icon_box)
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, valign=Gtk.Align.CENTER)
        left_box.append(info_box)
        self.video_info_label = Gtk.Label(label=f'{_("Video")}: -', xalign=0, css_classes=["caption"])
        self.audio_info_label = Gtk.Label(label=f'{_("Audio")}: -', xalign=0, css_classes=["caption"])
        info_box.append(self.video_info_label)
        info_box.append(self.audio_info_label)
        media_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0, halign=Gtk.Align.CENTER)
        controls_center_box.set_center_widget(media_box)
        stop_trailer_icon = "back.svg"
        self.buttons["stop_trailer"] = self._create_icon_button(stop_trailer_icon)
        self.buttons["stop_trailer"].set_tooltip_text(_("Stop Trailer and Go Back"))
        self.buttons["stop_trailer"].add_css_class("destructive-action")
        self.buttons["stop_trailer"].connect("clicked", lambda b: self.emit("stop-trailer-clicked"))
        self.buttons["stop_trailer"].set_visible(False)
        media_icons = {
            "seek-backward": "media-seek-backward.svg",
            "play-pause": "media-playback-start.svg",
            "seek-forward": "media-seek-forward.svg",
            "record": "media-record.svg",
            "catch-up": "folder-recent.svg"
        }
        tooltips = {
            "seek-backward": _("Seek Backward (or Previous Track)"),
            "play-pause": _("Play/Pause"),
            "seek-forward": _("Seek Forward (or Next Track)"),
            "record": _("Record"),
            "catch-up": _("Past Broadcasts (Archive)"),
            "stop_trailer": _("Stop Trailer and Go Back")
        }
        for key, icon_name in media_icons.items():
            btn = self._create_icon_button(icon_name)
            btn.set_tooltip_text(tooltips.get(key, ""))
            self.buttons[key] = btn
            media_box.append(btn)
            if key == "seek-forward":
                 media_box.append(self.buttons["stop_trailer"])
        self.buttons["record"].connect("clicked", self.on_record_clicked)
        self.buttons["catch-up"].connect("clicked", lambda b: self.emit("catch-up-button-clicked"))
        self.buttons["catch-up"].set_visible(False)
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        right_box.set_valign(Gtk.Align.CENTER)
        controls_center_box.set_end_widget(right_box)
        right_icons = {
            "equalizer": "equalizer.svg",
            "audio-track": "language.svg",
            "subtitles": "media-show-subtitles.svg",
            "volume": "audio-speakers.svg",
            "info": "info.svg",
            "fullscreen": "view-fullscreen.svg"
        }
        for key, icon_name in right_icons.items():
            btn = self._create_icon_button(icon_name)
            self.buttons[key] = btn
            right_box.append(btn)
        self.buttons["equalizer"].set_tooltip_text(_("Audio Equalizer"))
        self.buttons["audio-track"].set_tooltip_text(_("Select Audio Track"))
        self.buttons["subtitles"].set_tooltip_text(_("Subtitle Options"))
        self.buttons["volume"].set_tooltip_text(_("Volume Control"))
        self.buttons["info"].set_tooltip_text(_("Stream Information"))
        self.buttons["fullscreen"].set_tooltip_text(_("Toggle Fullscreen"))    
        self.audio_popover = Gtk.PopoverMenu()
        self.buttons["audio-track"].connect("clicked", lambda btn: self.audio_popover.popup())
        self.audio_popover.set_parent(self.buttons["audio-track"])
        self.volume_popover = Gtk.Popover()
        self.volume_popover.add_css_class("volume-popover")
        self.volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, 0.0, 1.0, 0.05)
        self.volume_scale.set_draw_value(False)
        self.volume_scale.set_inverted(True)
        self.volume_scale.set_size_request(20, 120)
        self.volume_popover.set_child(self.volume_scale)
        volume_button = self.buttons["volume"]
        self.volume_popover.set_parent(volume_button)
        volume_button.connect("clicked", self.on_volume_button_clicked)
        self.volume_scale.connect("value-changed", self._start_volume_popover_timer)
        self.volume_popover.connect("closed", self._on_volume_popover_closed)
        self.buttons["subtitles"].connect("clicked", lambda btn: self.emit("subtitle-button-clicked"))

    def set_catchup_button_visibility(self, visible):
        """Shows or hides the Catch-up button."""
        self.set_button_visibility("catch-up", visible)

    def update_info_labels(self, video_text, audio_text):
        self.video_info_label.set_text(video_text)
        self.audio_info_label.set_text(audio_text)

    def _clear_icon_box(self):
        child = self.channel_icon_box.get_first_child()
        if child: self.channel_icon_box.remove(child)

    def _replace_main_placeholder(self, pixbuf):
        self._clear_icon_box()
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        image = Gtk.Image.new_from_paintable(texture)
        image.add_css_class("channel-logo-image")
        image.set_pixel_size(50)
        center_box = Gtk.CenterBox()
        center_box.set_center_widget(image)
        self.channel_icon_box.append(center_box)
        return GLib.SOURCE_REMOVE

    def _set_main_placeholder(self):
        self._clear_icon_box()
        placeholder = PlaceholderIcon()
        placeholder.set_size_request(62, 50)
        center_box = Gtk.CenterBox()
        center_box.set_center_widget(placeholder)
        self.channel_icon_box.append(center_box)

    def update_channel_icon(self, logo_path_or_url):
        self._set_main_placeholder()
        if logo_path_or_url and logo_path_or_url.strip():
            def thread_func():
                try:
                    if logo_path_or_url.lower().startswith("http"):
                        headers = {"User-Agent": "Mozilla/5.0"}; req = urllib.request.Request(logo_path_or_url, headers=headers)
                        with urllib.request.urlopen(req, timeout=5) as resp: data = resp.read()
                    else:
                        with open(logo_path_or_url, "rb") as f: data = f.read()
                    if data:
                        loader = GdkPixbuf.PixbufLoader.new(); loader.write(data); loader.close()
                        pixbuf = loader.get_pixbuf()
                        GLib.idle_add(self._replace_main_placeholder, pixbuf)
                except Exception as e:
                    if "404" in str(e):
                        logging.debug(f"Main icon not found (404): {logo_path_or_url}")
                    else:
                        logging.warning(f"Failed to load main icon '{logo_path_or_url}': {e}")
            threading.Thread(target=thread_func, daemon=True).start()

    def on_volume_button_clicked(self, button):
        if self.is_fullscreen:
            return
        self.volume_popover.popup()
        self._start_volume_popover_timer()

    def on_record_clicked(self, button):
        """Emits the 'record-button-clicked' signal when the record button is clicked."""
        self.emit("record-button-clicked")

    def set_button_visibility(self, key, visible):
        if key in self.buttons: self.buttons[key].set_visible(visible)
        else: logging.warning(f"Attempted to set visibility for a non-existent button key: {key}")

    def _create_icon_button(self, icon_name):
        btn = Gtk.Button()
        btn.add_css_class("flat-button")
        box = Gtk.CenterBox()
        box.add_css_class("control-button-box")
        box.set_size_request(32, 32)
        theme_folder = get_icon_theme_folder()
        image_path = os.path.join("resources", "icons", theme_folder, icon_name)
        if os.path.exists(image_path):
            icon = Gtk.Image.new_from_file(image_path)
            icon.set_pixel_size(22)
            box.set_center_widget(icon)
        else:
            label = Gtk.Label(label=icon_name.split('.')[0])
            box.set_center_widget(label)
            logging.warning(f"Control panel icon not found: {image_path}")
        btn.set_child(box)
        return btn

    def set_channel_icon_visibility(self, visible):
        """Shows or hides the channel icon box on the left."""
        self.channel_icon_box.set_visible(visible)

    def update_audio_tracks_menu(self, tracks):
        """Populates the audio track selection menu with the given tracks."""
        audio_button = self.buttons.get("audio-track")
        if not audio_button:
            return
        if not tracks or len(tracks) <= 1:
            audio_button.set_visible(False)
            if hasattr(self, 'audio_popover') and self.audio_popover:
                 self.audio_popover.set_menu_model(None)
            return
        audio_button.set_visible(True)
        menu_model = Gio.Menu()
        action_group = Gio.SimpleActionGroup()
        for track in tracks:
            action_name = f"set_audio_{track['index']}"
            menu_model.append(track['name'], f"track.{action_name}")
            action = Gio.SimpleAction.new(action_name, None)
            action.connect("activate", lambda a, v, index=track['index']: self.emit("audio-track-selected", index))
            action_group.add_action(action)
        self.audio_popover.set_menu_model(menu_model)
        try:
            audio_button.insert_action_group("track", action_group)
        except Exception as e:
            logging.error(f"Unexpected error while adding audio track action group: {e}")
            try:
                audio_button.insert_action_group("track", action_group)
            except Exception as inner_e:
                 logging.error(f"insert_action_group failed even on retry: {inner_e}")

    def set_recording_state(self, is_recording):
        """Updates the visual state (icon, style, tooltip) of the record button."""
        record_button = self.buttons.get("record")
        if not record_button:
            return
        center_box = record_button.get_child()
        theme_folder = get_icon_theme_folder()
        icon_path = ""
        if is_recording:
            icon_path = os.path.join("resources", "icons", theme_folder, "record-stop.svg")
            center_box.add_css_class("recording-active")
            record_button.set_tooltip_text(_("Stop Recording"))
        else:
            icon_path = os.path.join("resources", "icons", theme_folder, "media-record.svg")
            center_box.remove_css_class("recording-active")
            record_button.set_tooltip_text(_("Start Recording"))
        if os.path.exists(icon_path):
            new_icon = Gtk.Image.new_from_file(icon_path)
            new_icon.set_pixel_size(22)
            center_box.set_center_widget(new_icon)
        else:
            logging.warning(f"Recording icon not found: {icon_path}")

    def on_slider_value_changed(self, scale, scroll_type, value):
        """Runs when the user moves the slider."""
        if scale.get_property("has-focus"):
            self.emit("seek-value-changed", value)

    def set_seek_controls_visibility(self, visible):
        """Shows or hides the slider and time labels."""
        self.seek_box.set_visible(visible)
        self.set_button_visibility("seek-forward", visible)
        self.set_button_visibility("seek-backward", visible)

    def set_mode(self, mode):
        """Switches the interface to 'video' or 'audio' mode."""
        is_video_mode = (mode == 'video')
        self.set_button_visibility("subtitles", is_video_mode)
        self.set_button_visibility("fullscreen", is_video_mode)
        self.video_info_label.set_visible(is_video_mode)

    def _start_volume_popover_timer(self, *args):
        """Cancels the existing timer and starts a new one."""
        if self.volume_popover_timer:
            GLib.source_remove(self.volume_popover_timer)
        self.volume_popover_timer = GLib.timeout_add_seconds(3, self._close_volume_popover_timeout)

    def _close_volume_popover_timeout(self):
        """Closes the volume popover when the timer expires."""
        self.volume_popover.popdown()
        self.volume_popover_timer = None
        return GLib.SOURCE_REMOVE

    def _on_volume_popover_closed(self, popover):
        """Clears the timer when the popover is manually closed."""
        if self.volume_popover_timer:
            GLib.source_remove(self.volume_popover_timer)
            self.volume_popover_timer = None

    def set_playing_state(self, is_playing):
        """Updates the Play/Pause button icon based on the playback state."""
        play_pause_button = self.buttons.get("play-pause")
        if not play_pause_button:
            return
        center_box = play_pause_button.get_child()
        theme_folder = get_icon_theme_folder()
        icon_name = "media-playback-pause.svg" if is_playing else "media-playback-start.svg"
        icon_path = os.path.join("resources", "icons", theme_folder, icon_name)
        if os.path.exists(icon_path):
            new_icon = Gtk.Image.new_from_file(icon_path)
            new_icon.set_pixel_size(22)
            center_box.set_center_widget(new_icon)
        else:
            logging.warning(f"Play/Pause icon not found: {icon_path}")
            label = Gtk.Label(label=">" if not is_playing else "||")
            center_box.set_center_widget(label)

    def show_volume_popover_transiently(self):
        """Shows the volume popover and starts/resets the auto-hide timer."""
        if self.is_fullscreen:
            return
        if not self.volume_popover.is_visible():
            self.volume_popover.popup()
        self._start_volume_popover_timer()

    def set_fullscreen_mode(self, is_fullscreen):
        """Sets the fullscreen state from the main window."""
        self.is_fullscreen = is_fullscreen

    def set_stop_trailer_button_visibility(self, visible):
        """Shows or hides the 'Stop Trailer' button."""
        self.set_button_visibility("stop_trailer", visible)

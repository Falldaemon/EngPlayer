# ui/standalone_player_window.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk
import gettext
import logging
import os
from datetime import timedelta

_ = gettext.gettext

from playback.player import Player
from .player_controls import PlayerControls
from .playback_speed_manager import PlaybackSpeedManager
from .aspect_ratio_manager import AspectRatioManager
from .media_info_dialog import MediaInfoDialog
from .subtitle_dialog import SubtitleDialog
from .subtitle_results_dialog import SubtitleResultsDialog
from .equalizer_window import EqualizerWindow
from ui.custom_visualizer import CustomVisualizer
from ui.theme_manager import ThemeManager
from utils.sleep_inhibitor import SleepInhibitor
from utils.subtitle_manager import SubtitleManager
from utils import subtitle_searcher
from utils import title_parser
from background import image_download_pool
import database

NS_PER_SECOND = 1_000_000_000


class StandalonePlayerWindow(Adw.ApplicationWindow):
    def __init__(self, application, file_path, **kwargs):
        super().__init__(application=application, **kwargs)
        self.set_default_size(960, 600)
        self.set_title(os.path.basename(file_path))
        self.file_path = file_path
        self._is_playing = False
        AUDIO_EXTENSIONS = (".mp3", ".flac", ".ogg", ".wav", ".aac", ".m4a", ".wma", ".opus", ".aiff")
        self.media_type = "music" if file_path.lower().endswith(AUDIO_EXTENSIONS) else "video"
        self.equalizer_window = None
        self.is_immersive_fullscreen = False
        self.last_mouse_x = -1
        self.last_mouse_y = -1
        self.hide_panels_timer = None
        self.active_dialog_open = False
        saved_theme = database.get_config_value('app_theme') or "default"
        ThemeManager.apply_theme(saved_theme)
        self.inhibitor = SleepInhibitor(application)
        self.player = Player()
        self.player.connect("stream-started", self._on_stream_started)
        self.player.connect("paintable-changed", self._on_paintable_changed)
        self.player.connect("tracks-changed", self._on_tracks_changed)
        self.player.connect("seek-accumulated", self._on_seek_accumulated)
        self.player.connect("spectrum-update", self._on_spectrum_update)
        self.seek_toast = None
        toast_overlay = Adw.ToastOverlay()
        self.set_content(toast_overlay)
        self.toast_overlay = toast_overlay
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toast_overlay.set_child(root_box)
        self.root_box = root_box
        header = Adw.HeaderBar()
        root_box.append(header)
        self.header = header
        video_overlay = Gtk.Overlay(vexpand=True, hexpand=True)
        root_box.append(video_overlay)
        self.native_host = None
        self._osd = video_overlay
        if os.name == 'nt' and self.media_type == "video":
            from .native_video_host import NativeVideoHost
            self.native_host = NativeVideoHost(video_overlay)
            self._osd = self.native_host.osd_overlay
        black_background = Gtk.Box(css_classes=["black"])
        black_background.set_hexpand(True)
        black_background.set_vexpand(True)
        video_overlay.set_child(black_background)
        self.video_frame = Gtk.AspectFrame(ratio=16 / 9, obey_child=False, hexpand=True, vexpand=True)
        self.picture_widget = Gtk.Picture()
        self.video_frame.set_child(self.picture_widget)
        video_overlay.add_overlay(self.video_frame)
        self.subtitle_label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.subtitle_label.set_valign(Gtk.Align.END)
        self.subtitle_label.set_halign(Gtk.Align.CENTER)
        self.subtitle_label.set_margin_bottom(20)
        self.subtitle_label.hide()
        self._osd.add_overlay(self.subtitle_label)
        self.video_view = video_overlay
        self.custom_visualizer = CustomVisualizer()
        self._osd.add_overlay(self.custom_visualizer)
        self.subtitle_manager = SubtitleManager(self.player, self.subtitle_label)
        self.subtitle_delay_ms = 0
        self.subtitles_visible = False
        self.is_external_subtitle_active = False
        self.current_subtitle_track = -1
        self.last_selected_embedded_track = 0
        self.controls = PlayerControls()
        root_box.append(self.controls)
        for key in ("record", "catch-up", "go-live", "backup-link", "series-episodes", "epg"):
            btn = self.controls.buttons.get(key)
            if btn:
                btn.set_visible(False)
        self.controls.set_button_visibility("equalizer", self.media_type == "music")
        self.controls.buttons["equalizer"].connect("clicked", self._on_equalizer_button_clicked)
        self.controls.set_channel_icon_visibility(False)
        self.controls.buttons["play-pause"].connect("clicked", self._on_play_pause_clicked)
        self.controls.buttons["fullscreen"].connect("clicked", self._on_fullscreen_clicked)
        self.controls.buttons["seek-backward"].connect("clicked", self._on_seek_backward_clicked)
        self.controls.buttons["seek-forward"].connect("clicked", self._on_seek_forward_clicked)
        self.controls.progress_slider.connect("change-value", self._on_seek)
        self.controls.volume_scale.connect("value-changed", self._on_volume_changed)
        self.controls.volume_scale.set_value(0.8)
        self.controls.connect("audio-track-selected", self._on_audio_track_selected)
        self.last_volume_before_mute = 0.8
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)
        self.controls.buttons["subtitles"].connect("clicked", self._on_subtitle_button_clicked)
        self.playback_speed_manager = PlaybackSpeedManager(self, self.player)
        self.aspect_ratio_manager = AspectRatioManager(self)
        info_action = Gio.SimpleAction.new("show_media_info", None)
        info_action.connect("activate", self._on_show_media_info_action)
        self.add_action(info_action)
        self.more_menu_model = Gio.Menu()
        self.more_menu_model.append(_("Media Info"), "win.show_media_info")
        speed_menu = self.playback_speed_manager.build_submenu()
        self.more_menu_model.append_submenu(_("Playback Speed"), speed_menu)
        ar_menu = self.aspect_ratio_manager.build_submenu()
        self.more_menu_model.append_submenu(_("Aspect Ratio"), ar_menu)
        self.controls.more_popover.set_menu_model(self.more_menu_model)
        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("motion", self._on_mouse_motion)
        self.add_controller(motion_controller)
        self._progress_timer_id = GLib.timeout_add_seconds(1, self._update_progress)
        self.connect("close-request", self._on_close_request)
        if self.native_host:
            self.player.set_window_handle_provider(self.native_host.get_window_handle,
                                                   on_active=self.native_host.set_video_active)
            self.native_host.key_forward = self._on_key_pressed
            self.native_host.motion_forward = self._on_mouse_motion
            self.native_host.resized_callback = self.player.expose_native
            self._map_handler_id = self.connect("map", self._on_first_map)
        else:
            self._start_playback()

    def _on_first_map(self, window):
        self.disconnect(self._map_handler_id)
        GLib.idle_add(self._start_playback)

    def _start_playback(self):
        self.player.play_url(self.file_path, media_type=self.media_type)
        if self.media_type == "music":
            self.player.enable_equalizer()
            saved_vis = database.get_config_value('visualizer_type') or "custom"
            self.custom_visualizer.set_visible(saved_vis == "custom")
        self.player.play()
        return GLib.SOURCE_REMOVE
        
    def show_toast(self, text):
        self.toast_overlay.add_toast(Adw.Toast.new(text))

    def _on_stream_started(self, player):
        self._is_playing = True
        self.controls.set_playing_state(True)
        self.inhibitor.inhibit()

    def _on_tracks_changed(self, player):
        tracks = self.player.get_audio_tracks() or []
        self.controls.update_audio_tracks_menu(tracks)

    def _on_paintable_changed(self, player, new_paintable):
        self.picture_widget.set_paintable(new_paintable)

    def _on_spectrum_update(self, player, mags):
        if self.custom_visualizer.get_visible():
            self.custom_visualizer.update_magnitudes(mags)

    def _on_play_pause_clicked(self, button):
        self.player.toggle_play_pause()
        self._is_playing = not self._is_playing
        self.controls.set_playing_state(self._is_playing)

    def _on_fullscreen_clicked(self, button):
        if self.is_fullscreen():
            self.is_immersive_fullscreen = False
            self.unfullscreen()
            if self.hide_panels_timer:
                GLib.source_remove(self.hide_panels_timer)
                self.hide_panels_timer = None
            self.get_surface().set_cursor(None)
            self._disable_fullscreen_overlay_mode()
        else:
            self.is_immersive_fullscreen = True
            self.fullscreen()
            self._enable_fullscreen_overlay_mode()

    def _enable_fullscreen_overlay_mode(self):
        self.header.set_visible(False)
        self.root_box.remove(self.controls)
        self.controls.remove_css_class("player-controls")
        self.controls.add_css_class("fullscreen-controls")
        self.controls.set_valign(Gtk.Align.END)
        self.controls.set_halign(Gtk.Align.FILL)
        self.controls.set_margin_bottom(30)
        self.controls.set_margin_start(30)
        self.controls.set_margin_end(30)
        self.controls.set_visible(True)
        self._osd.add_overlay(self.controls)

    def _disable_fullscreen_overlay_mode(self):
        self.header.set_visible(True)
        self._osd.remove_overlay(self.controls)
        self.controls.remove_css_class("fullscreen-controls")
        self.controls.add_css_class("player-controls")
        self.controls.set_margin_bottom(0)
        self.controls.set_margin_start(0)
        self.controls.set_margin_end(0)
        self.root_box.insert_child_after(self.controls, self.video_view)
        self.controls.set_visible(True)

    def _on_mouse_motion(self, controller, x, y):
        if not self.is_immersive_fullscreen:
            return
        if abs(x - self.last_mouse_x) < 1 and abs(y - self.last_mouse_y) < 1:
            return
        self.last_mouse_x = x
        self.last_mouse_y = y
        self.get_surface().set_cursor(None)
        if not self.controls.get_visible():
            self.controls.set_visible(True)
        if self.hide_panels_timer:
            GLib.source_remove(self.hide_panels_timer)
        self.hide_panels_timer = GLib.timeout_add_seconds(3, self._hide_panels_callback)

    def _hide_panels_callback(self):
        if self.controls.more_popover.get_visible() or self.controls.audio_popover.get_visible() or self.active_dialog_open:
            return True
        if self.is_immersive_fullscreen:
            self.controls.set_visible(False)
            self.get_surface().set_cursor(Gdk.Cursor.new_from_name("none", None))
        self.hide_panels_timer = None
        return False

    def _on_seek_backward_clicked(self, button):
        self.player.seek_backward()

    def _on_seek_forward_clicked(self, button):
        self.player.seek_forward()

    def _on_seek_accumulated(self, player, seconds):
        if seconds == 0:
            if self.seek_toast:
                self.seek_toast.dismiss()
                self.seek_toast = None
            return
        if seconds > 0:
            msg = f"⏩ +{seconds} {_('Seconds')}"
        else:
            msg = f"⏪ {seconds} {_('Seconds')}"
        if self.seek_toast:
            self.seek_toast.set_title(msg)
        else:
            self.seek_toast = Adw.Toast.new(msg)
            self.seek_toast.set_timeout(5)
            def on_dismissed(toast):
                if self.seek_toast == toast:
                    self.seek_toast = None
            self.seek_toast.connect("dismissed", on_dismissed)
            self.toast_overlay.add_toast(self.seek_toast)

    def _on_seek(self, scale, scroll_type, value):
        duration_ns = self.player.get_duration()
        if duration_ns:
            duration_seconds = duration_ns / NS_PER_SECOND
            target_seconds = duration_seconds * (value / 100.0)
            self.player.seek_to_seconds(target_seconds)
        return False

    def _on_volume_changed(self, scale):
        self.player.set_volume(scale.get_value())

    def _change_volume(self, delta):
        scale = self.controls.volume_scale
        new_value = max(0.0, min(1.0, scale.get_value() + delta))
        scale.set_value(new_value)
        if not self.is_immersive_fullscreen and hasattr(self.controls, "show_volume_popover_transiently"):
            self.controls.show_volume_popover_transiently()

    def _toggle_mute(self):
        scale = self.controls.volume_scale
        current_volume = scale.get_value()
        if current_volume > 0.01:
            self.last_volume_before_mute = current_volume
            scale.set_value(0.0)
        else:
            scale.set_value(self.last_volume_before_mute)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        key_name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval))
        if key_name == "Escape":
            if self.is_immersive_fullscreen:
                self._on_fullscreen_clicked(None)
                return True
        if key_name == "F11" or key_name == "f":
            self._on_fullscreen_clicked(None)
            return True
        if key_name == "space":
            self._on_play_pause_clicked(None)
            return True
        elif key_name == "Right":
            self._change_volume(0.05)
            return True
        elif key_name == "Left":
            self._change_volume(-0.05)
            return True
        elif key_name == "Up":
            self._on_seek_forward_clicked(None)
            return True
        elif key_name == "Down":
            self._on_seek_backward_clicked(None)
            return True
        elif key_name == "m":
            self._toggle_mute()
            return True
        return False

    def _on_audio_track_selected(self, controls, index):
        self.player.set_audio_track(index)

    def _on_subtitle_button_clicked(self, button):
        embedded_tracks = self.player.get_subtitle_tracks()
        dialog = SubtitleDialog(
            self,
            embedded_tracks,
            current_state=self.subtitles_visible,
            current_track_index=self.current_subtitle_track
        )
        dialog.connect("online-search-requested", self._on_online_subtitle_search_requested)
        dialog.connect('sync-adjust-requested', self._on_subtitle_sync_adjust)
        dialog.connect("subtitle-toggled", self._on_subtitle_toggled)
        dialog.connect("load-external-requested", self._on_load_external_subtitle)
        dialog.connect("track-selected", self._on_embedded_subtitle_selected)
        dialog.update_sync_label(self.subtitle_delay_ms)
        self.active_dialog_open = True
        dialog.connect("close-request", self._on_dialog_closed)
        dialog.present()

    def _on_online_subtitle_search_requested(self, dialog):
        dialog.close()
        api_key = database.get_config_value("opensubtitles_api_key")
        if not api_key:
            self.show_toast(_("Please enter your OpenSubtitles API key from Settings first."))
            return
        raw_name = os.path.basename(self.file_path)
        search_title, search_year = title_parser.parse_title_for_search(raw_name)
        if not search_title:
            search_title = raw_name
        self.show_toast(_("Searching for subtitles for '{}'...").format(search_title))
        image_download_pool.submit(
            subtitle_searcher.search_subtitles_online,
            self.file_path,
            search_title,
            api_key,
            self._on_subtitle_search_results_received,
            tmdb_id=None,
            year=search_year
        )

    def _on_subtitle_search_results_received(self, results, error):
        if error:
            self.show_toast(error)
            return
        if not results:
            self.show_toast(_("No subtitles found."))
            return
        results_dialog = SubtitleResultsDialog(self, results)
        results_dialog.connect('subtitle-selected', self._on_subtitle_result_selected)
        results_dialog.present()

    def _on_subtitle_result_selected(self, dialog, selected_subtitle_data):
        file_name = selected_subtitle_data.get('file_name', 'N/A')
        file_id = selected_subtitle_data.get('file_id')
        if not file_id:
            self.show_toast(_("Error: Could not retrieve file ID for selected subtitle."))
            return
        api_key = database.get_config_value("opensubtitles_api_key")
        if not api_key:
            self.show_toast(_("Error: API key not found for download."))
            return
        self.show_toast(_("Downloading '{0}'...").format(file_name))
        image_download_pool.submit(
            subtitle_searcher.download_subtitle_file,
            file_id,
            api_key,
            self._on_subtitle_downloaded
        )

    def _on_subtitle_downloaded(self, temp_file_path, error):
        if error:
            self.show_toast(error)
            return
        if temp_file_path and os.path.exists(temp_file_path):
            self.player.set_subtitle_track(-1)
            self.current_subtitle_track = -1
            self.subtitles_visible = False
            success = self.subtitle_manager.load_from_file(temp_file_path)
            if success:
                self.is_external_subtitle_active = True
                self.subtitles_visible = True
                self.show_toast(_("Subtitle loaded and enabled successfully."))
            else:
                self.is_external_subtitle_active = False
                self.show_toast(_("Error: Downloaded subtitle file could not be loaded."))
                try: os.remove(temp_file_path)
                except OSError: pass
        else:
            self.show_toast(_("Error: Downloaded subtitle file not found."))

    def _on_subtitle_sync_adjust(self, dialog, adjustment_ms):
        self.subtitle_delay_ms += adjustment_ms
        dialog.update_sync_label(self.subtitle_delay_ms)
        self.subtitle_manager.set_delay(self.subtitle_delay_ms)

    def _on_subtitle_toggled(self, dialog, is_active):
        if is_active and self.is_external_subtitle_active:
            return
        self.subtitles_visible = is_active
        if is_active:
            self.subtitle_manager.clear()
            self.is_external_subtitle_active = False
            track_to_activate = self.last_selected_embedded_track
            self.player.set_subtitle_track(track_to_activate)
            self.current_subtitle_track = track_to_activate
        else:
            self.subtitle_manager.clear()
            self.is_external_subtitle_active = False
            self.player.set_subtitle_track(-1)
            self.current_subtitle_track = -1

    def _on_load_external_subtitle(self, dialog):
        dialog.close()
        chooser = Gtk.FileChooserDialog(
            title=_("Select External Subtitle File"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN
        )
        chooser.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Select"), Gtk.ResponseType.ACCEPT
        )
        chooser.set_modal(True)
        filter_subs = Gtk.FileFilter()
        filter_subs.set_name(_("Subtitle Files"))
        for pattern in ["*.srt", "*.vtt", "*.ass", "*.sub", "*.smi", "*.txt"]:
            filter_subs.add_pattern(pattern)
        chooser.add_filter(filter_subs)
        filter_all = Gtk.FileFilter()
        filter_all.set_name(_("All Files"))
        filter_all.add_pattern("*")
        chooser.add_filter(filter_all)

        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                gfile = d.get_file()
                if gfile:
                    file_path = gfile.get_path()
                    self.player.set_subtitle_track(-1)
                    success = self.subtitle_manager.load_from_file(file_path)
                    if success:
                        self.subtitles_visible = True
                        self.is_external_subtitle_active = True
                        self.current_subtitle_track = -1
                        self.show_toast(_("External subtitle loaded."))
                    else:
                        self.is_external_subtitle_active = False
                        self.show_toast(_("Could not load subtitle file."))
            d.hide()
            def _safe_destroy():
                d.destroy()
                return GLib.SOURCE_REMOVE
            GLib.idle_add(_safe_destroy)
        chooser.connect("response", on_response)
        chooser.present()

    def _on_embedded_subtitle_selected(self, dialog, track_index):
        self.subtitle_manager.clear()
        self.is_external_subtitle_active = False
        self.player.set_subtitle_track(track_index)
        self.current_subtitle_track = track_index
        self.last_selected_embedded_track = track_index
        self.subtitles_visible = True

    def _on_equalizer_button_clicked(self, button):
        if not self.equalizer_window:
            self.equalizer_window = EqualizerWindow(self, self.player)
        self.equalizer_window.present()

    def _on_show_media_info_action(self, action, param):
        dialog = MediaInfoDialog(self, self.player)
        self.active_dialog_open = True
        dialog.connect("close-request", self._on_dialog_closed)
        dialog.present()

    def _on_dialog_closed(self, dialog):
        self.active_dialog_open = False
        return False

    def _update_progress(self):
        duration_ns = self.player.get_duration()
        position_ns = self.player.get_position()
        if duration_ns:
            percent = (position_ns / duration_ns) * 100.0
            self.controls.progress_slider.set_value(percent)
            position_sec = int(position_ns / NS_PER_SECOND)
            duration_sec = int(duration_ns / NS_PER_SECOND)
            self.controls.time_label_current.set_text(str(timedelta(seconds=position_sec)))
            self.controls.time_label_duration.set_text(str(timedelta(seconds=duration_sec)))
        video_text, audio_text = self.player.get_stream_info()
        self.controls.update_info_labels(video_text, audio_text)
        return True

    def _on_close_request(self, window):
        if self._progress_timer_id:
            GLib.source_remove(self._progress_timer_id)
            self._progress_timer_id = None
        self.inhibitor.uninhibit()
        if self.player:
            self.player.shutdown()
        return False

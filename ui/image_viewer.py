# ui/image_viewer.py

import gi
import threading
gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gtk, GObject, GLib, Gio, Gst, GdkPixbuf
Gst.init(None)
import gettext
_ = gettext.gettext

class ImageViewer(Gtk.Overlay):
    __gsignals__ = {
        "back-requested": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self.add_css_class("black")
        self.image_list = []
        self.current_index = 0
        self.slideshow_timer_id = None
        self.is_playing = False
        self.audio_player = Gst.ElementFactory.make("playbin", None)
        bus = self.audio_player.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self._on_music_finished)
        frame = Gtk.AspectFrame(ratio=16/9, obey_child=False, xalign=0.5, yalign=0.5)
        self.picture = Gtk.Picture(vexpand=True, hexpand=True, can_shrink=True)
        frame.set_child(self.picture)
        self.set_child(frame)
        self.controls_box = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER, valign=Gtk.Align.END, margin_bottom=12)
        self.controls_box.add_css_class("player-controls")
        self.add_overlay(self.controls_box)
        self.btn_left_arrow = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self.btn_left_arrow.set_halign(Gtk.Align.START); self.btn_left_arrow.set_valign(Gtk.Align.CENTER)
        self.btn_left_arrow.add_css_class("flat-button"); self.add_overlay(self.btn_left_arrow)
        self.btn_right_arrow = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self.btn_right_arrow.set_halign(Gtk.Align.END); self.btn_right_arrow.set_valign(Gtk.Align.CENTER)
        self.btn_right_arrow.add_css_class("flat-button"); self.add_overlay(self.btn_right_arrow)
        btn_back = Gtk.Button(label=_("Back"), icon_name="go-up-symbolic")
        btn_back.add_css_class("transparent-button")
        btn_back.connect("clicked", lambda w: self.emit("back-requested"))
        self.btn_prev = Gtk.Button.new_from_icon_name("media-skip-backward-symbolic")
        self.btn_prev.add_css_class("transparent-button")
        self.btn_slideshow = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
        self.btn_slideshow.add_css_class("transparent-button")
        self.btn_next = Gtk.Button.new_from_icon_name("media-skip-forward-symbolic")
        self.btn_next.add_css_class("transparent-button")
        btn_music = Gtk.Button.new_from_icon_name("audio-x-generic-symbolic")
        btn_music.add_css_class("transparent-button")
        btn_music.set_tooltip_text(_("Select music for slideshow"))
        btn_music.connect("clicked", self._on_music_button_clicked)
        self.speed_combo = Gtk.ComboBoxText()
        self.speed_combo.add_css_class("transparent-button")
        self.speed_combo.append("3000", _("3 Seconds")); self.speed_combo.append("5000", _("5 Seconds"))
        self.speed_combo.append("10000", _("10 Seconds")); self.speed_combo.set_active(1)
        self.controls_box.append(btn_back); self.controls_box.append(self.btn_prev)
        self.controls_box.append(self.btn_slideshow); self.controls_box.append(self.btn_next)
        self.controls_box.append(btn_music); self.controls_box.append(self.speed_combo)
        self.btn_next.connect("clicked", self._on_next_clicked)
        self.btn_right_arrow.connect("clicked", self._on_next_clicked)
        self.btn_prev.connect("clicked", self._on_prev_clicked)
        self.btn_left_arrow.connect("clicked", self._on_prev_clicked)
        self.btn_slideshow.connect("clicked", self._on_slideshow_toggled)

    def set_images(self, image_list, start_index):
        self.image_list = image_list; self.current_index = start_index
        self._show_current_image()

    def _show_current_image(self):
        """
        Loads the next image in the background and displays it
        on the main thread when loaded. (TO PREVENT AUDIO STUTTERING)
        """
        if not self.image_list:
            return
        image_path = self.image_list[self.current_index].props.path_or_url

        def _update_picture_on_main_thread(pixbuf):
            if pixbuf:
                self.picture.set_pixbuf(pixbuf)
            else:
                self.picture.set_from_icon_name("image-missing-symbolic")
            return GLib.SOURCE_REMOVE

        def _load_image_in_background():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
                GLib.idle_add(_update_picture_on_main_thread, pixbuf)
            except GLib.Error:
                GLib.idle_add(_update_picture_on_main_thread, None)
        thread = threading.Thread(target=_load_image_in_background)
        thread.start()

    def _on_next_clicked(self, widget):
        if not self.image_list: return
        self.current_index = (self.current_index + 1) % len(self.image_list)
        self._show_current_image()

    def _on_prev_clicked(self, widget):
        if not self.image_list: return
        self.current_index = (self.current_index - 1 + len(self.image_list)) % len(self.image_list)
        self._show_current_image()

    def _on_slideshow_toggled(self, widget):
        if self.is_playing:
            self._pause_playback()
        else:
            self._start_playback()

    def _start_playback(self):
        if self.is_playing: return
        self.is_playing = True
        self.btn_slideshow.set_icon_name("media-playback-pause-symbolic")
        interval = int(self.speed_combo.get_active_id())
        self.slideshow_timer_id = GLib.timeout_add(interval, self._on_slideshow_tick)
        self._on_slideshow_tick()
        self.audio_player.set_state(Gst.State.PLAYING)

    def _pause_playback(self):
        if not self.is_playing: return
        self.is_playing = False
        self.btn_slideshow.set_icon_name("media-playback-start-symbolic")
        if self.slideshow_timer_id:
            GLib.source_remove(self.slideshow_timer_id)
            self.slideshow_timer_id = None
        self.audio_player.set_state(Gst.State.PAUSED)

    def _on_slideshow_tick(self):
        self._on_next_clicked(None)
        return True

    def _on_music_button_clicked(self, widget):
        """
        Opens a GTK FileChooserDialog to select background music.
        Updated to match the consistent style (Portal Bypass) and prevent segfaults.
        """
        chooser = Gtk.FileChooserDialog(
            title=_("Select Background Music"),
            transient_for=self.get_root(),
            action=Gtk.FileChooserAction.OPEN
        )
        chooser.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Select"), Gtk.ResponseType.ACCEPT
        )
        chooser.set_modal(True)
        filter_audio = Gtk.FileFilter()
        filter_audio.set_name(_("Audio Files"))
        for pattern in ["*.mp3", "*.ogg", "*.wav", "*.flac", "*.m4a", "*.aac", "*.wma"]:
            filter_audio.add_pattern(pattern)
        chooser.add_filter(filter_audio)
        filter_all = Gtk.FileFilter()
        filter_all.set_name(_("All Files"))
        filter_all.add_pattern("*")
        chooser.add_filter(filter_all)

        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                gfile = d.get_file()
                if gfile:
                    path = gfile.get_path()
                    self.audio_player.set_state(Gst.State.NULL)
                    self.audio_player.set_property("uri", f"file://{path}")
                    if self.is_playing:
                        self.audio_player.set_state(Gst.State.PLAYING)
            d.hide()
            def _safe_destroy():
                d.destroy()
                return GLib.SOURCE_REMOVE
            GLib.idle_add(_safe_destroy)
        chooser.connect("response", on_response)
        chooser.present()
        
    def _on_music_finished(self, bus, message):
        self.audio_player.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, 0)

    def stop_all_activity(self):
        self._pause_playback()
        self.audio_player.set_state(Gst.State.NULL)

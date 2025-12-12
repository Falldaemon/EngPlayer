# ui/video_view.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Pango, GLib
from .player_controls import PlayerControls
import gettext
import os
from utils.theme_utils import get_icon_theme_folder
_ = gettext.gettext
class VideoView(Gtk.Box):
    __gsignals__ = {
        "video-area-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "epg-item-activated": (GObject.SignalFlags.RUN_FIRST, None, (object,))
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_hexpand(True)
        self.set_vexpand(True)
        overlay = Gtk.Overlay(vexpand=True, hexpand=True)
        self.append(overlay)
        black_background = Gtk.Box(css_classes=["black"])
        overlay.set_child(black_background)
        self.video_frame = Gtk.AspectFrame(ratio=16/9, obey_child=False, hexpand=True, vexpand=True)
        self.picture_widget = Gtk.Picture()
        self.video_frame.set_child(self.picture_widget)
        overlay.add_overlay(self.video_frame)
        self.subtitle_label = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, justify=Gtk.Justification.CENTER)
        self.subtitle_label.set_vexpand(True)
        self.subtitle_label.set_halign(Gtk.Align.CENTER)
        self.subtitle_label.set_valign(Gtk.Align.END)
        self.subtitle_label.set_margin_bottom(20)
        self.subtitle_label.hide()
        overlay.add_overlay(self.subtitle_label)
        self.controls = PlayerControls()
        self.append(self.controls)
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("pressed", self._on_video_frame_pressed)
        self.video_frame.add_controller(click_gesture)
        self.epg_listbox = Gtk.ListBox()
        self.epg_listbox.connect("row-activated", self.on_epg_row_activated)
        self.epg_scroll = Gtk.ScrolledWindow(css_classes=["epg-panel"])
        self.epg_scroll.set_child(self.epg_listbox)
        self.epg_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.epg_scroll.set_min_content_height(100)
        self.next_episode_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            halign=Gtk.Align.END,
            valign=Gtk.Align.END,
            margin_bottom=80,
            margin_end=20,
            css_classes=["osd", "box"]
        )
        self.next_episode_box.set_opacity(0.9)
        self.next_episode_box.set_visible(False)
        self.next_episode_label = Gtk.Label(xalign=1)
        self.next_episode_box.append(self.next_episode_label)
        self.next_episode_skip_button = Gtk.Button(label=_("Skip Now"))
        self.next_episode_skip_button.add_css_class("suggested-action")
        self.next_episode_box.append(self.next_episode_skip_button)
        self.next_episode_cancel_button = Gtk.Button(label=_("Cancel"))
        self.next_episode_box.append(self.next_episode_cancel_button)
        overlay.add_overlay(self.next_episode_box)
        self.append(self.epg_scroll)

    def on_epg_row_activated(self, listbox, row):
        if hasattr(row, 'program_data'):
            self.emit("epg-item-activated", row.program_data)

    def update_epg(self, program_infos):
        while (child := self.epg_listbox.get_first_child()):
            self.epg_listbox.remove(child)
        if not program_infos:
            label = Gtk.Label(label=_("No program information found for this channel."), xalign=0, margin_start=10, css_classes=["caption"])
            self.epg_listbox.append(label)
        else:
            for info in program_infos:
                program = info["data"]
                is_current = info["is_current"]
                row = Gtk.ListBoxRow()
                row.program_data = program
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_start=10, margin_end=10)
                start_time = program['start'].astimezone().strftime('%H:%M')
                display_text = f"{start_time}   {program['title']}"
                label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
                label.set_hexpand(True)
                if is_current:
                    escaped_text = GLib.markup_escape_text(display_text)
                    label.set_markup(f"<b>{escaped_text}</b>")
                else:
                    label.set_text(display_text)
                hbox.append(label)
                theme_folder = get_icon_theme_folder()
                icon_path = os.path.join("resources", "icons", theme_folder, "info.svg")
                info_icon = Gtk.Image.new_from_file(icon_path)
                info_icon.set_pixel_size(16)
                info_icon.set_opacity(0.7)
                hbox.append(info_icon)
                row.set_child(hbox)
                self.epg_listbox.append(row)

    def set_paintable(self, paintable):
        self.picture_widget.set_paintable(paintable)

    def set_epg_visibility(self, visible):
        self.epg_scroll.set_visible(visible)

    def set_mode(self, mode):
        """Switches the interface to 'video' or 'audio' mode."""
        is_video_mode = (mode == 'video')
        self.video_frame.set_visible(is_video_mode)

    def _on_video_frame_pressed(self, gesture, n_press, x, y):
        """Emits the signal only when the video area is double-clicked."""
        if n_press == 2:
            self.emit("video-area-clicked")

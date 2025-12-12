# ui/track_list_view.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject, Pango, GLib
import logging

class TrackListView(Gtk.Box):
    __gsignals__ = {
        'track-activated': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'track-right-clicked': (GObject.SignalFlags.RUN_FIRST, None, (object, Gtk.Widget,)),
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.current_tracks = []
        self.album_art_image = Gtk.Image(icon_name="audio-x-generic-symbolic", pixel_size=256, margin_bottom=12)
        self.album_title_label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12, margin_bottom=12)
        header_box.append(self.album_art_image)
        header_box.append(self.album_title_label)
        self.append(header_box)
        self.track_listbox = Gtk.ListBox()
        self.track_listbox.connect("row-activated", self._on_row_activated)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.track_listbox)
        scrolled_window.set_vexpand(True)
        self.append(scrolled_window)

    def populate_tracks(self, album_data, tracks):
        """Displays the track list and album info in the UI."""
        self.current_tracks = tracks
        self.album_title_label.set_markup(f"<big><b>{GLib.markup_escape_text(album_data['album_name'])}</b></big>\n{GLib.markup_escape_text(album_data['artist_name'])}")
        if album_data['album_art_path']:
            self.album_art_image.set_from_file(album_data['album_art_path'])
        else:
            self.album_art_image.set_from_icon_name("audio-x-generic-symbolic")
        while (child := self.track_listbox.get_first_child()):
            self.track_listbox.remove(child)
        for track in tracks:
            row = Gtk.ListBoxRow()
            row.track_data = track
            label_text = f"{track['track_number']}. {track['title']}"
            row.set_child(Gtk.Label(label=label_text, xalign=0, margin_start=12, margin_end=12))
            right_click_gesture = Gtk.GestureClick.new()
            right_click_gesture.set_button(3)
            right_click_gesture.connect("pressed", self._on_row_right_clicked, row)
            row.add_controller(right_click_gesture)
            self.track_listbox.append(row)

    def _on_row_activated(self, listbox, row):
        if hasattr(row, 'track_data'):
            self.emit('track-activated', row.track_data)

    def _on_row_right_clicked(self, gesture, n_press, x, y, row):
        """Emits the signal when a track row is right-clicked."""
        if hasattr(row, 'track_data'):
            self.emit('track-right-clicked', row.track_data, row)
        else:
            logging.warning("TrackListView: Right-click detected but 'track_data' not found on the row.")

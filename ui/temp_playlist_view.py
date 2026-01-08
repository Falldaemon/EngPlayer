#ui/temp_playlist_view.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject, Pango, GLib
import gettext

_ = gettext.gettext

class TempPlaylistView(Gtk.Box):
    __gsignals__ = {
        "channel-selected": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "close-clicked": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, **kwargs)       
        self.loading_process_id = None 
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header_box.set_margin_top(6)
        header_box.set_margin_start(6)
        header_box.set_margin_end(6)
        self.close_button = Gtk.Button(icon_name="window-close-symbolic")
        self.close_button.set_tooltip_text(_("Close Playlist"))
        self.close_button.connect("clicked", self._on_close_clicked)
        header_box.append(self.close_button)       
        self.title_label = Gtk.Label(label=_("Network Playlist"))
        self.title_label.set_hexpand(True)
        self.title_label.set_xalign(0)
        self.title_label.add_css_class("heading")
        header_box.append(self.title_label)       
        self.append(header_box)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Filter channels..."))
        self.search_entry.set_margin_start(6)
        self.search_entry.set_margin_end(6)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.append(self.search_entry)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        self.append(scrolled_window)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self._on_row_activated)
        self.listbox.set_filter_func(self._filter_func)
        scrolled_window.set_child(self.listbox)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_visible(False)
        self.append(self.progress_bar)

    def populate(self, channel_list):
        if self.loading_process_id:
            GLib.source_remove(self.loading_process_id)
            self.loading_process_id = None
        while True:
            row = self.listbox.get_first_child()
            if not row: break
            self.listbox.remove(row)
        total_channels = len(channel_list)
        self.title_label.set_text(_("Playlist ({})").format(total_channels))       
        if total_channels == 0:
            return
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_visible(True)
        self.loading_process_id = GLib.idle_add(self._batch_load, channel_list, 0, 50, total_channels)

    def _batch_load(self, all_channels, current_index, batch_size, total_count):
        if not self.get_root():
            return False
        end_index = min(current_index + batch_size, total_count)       
        for i in range(current_index, end_index):
            name, url = all_channels[i]
            self._create_row(name, url)
        progress = end_index / total_count
        self.progress_bar.set_fraction(progress)
        if end_index >= total_count:
            self.progress_bar.set_visible(False)
            self.loading_process_id = None
            return False         
        GLib.idle_add(self._batch_load, all_channels, end_index, batch_size, total_count)
        return False 

    def _create_row(self, name, url):
        row = Gtk.ListBoxRow()
        row.channel_url = url
        row.channel_name = name      
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(4) 
        box.set_margin_bottom(4)
        box.set_margin_start(8)
        box.set_margin_end(8)      
        icon = Gtk.Image.new_from_icon_name("tv-symbolic")
        box.append(icon)       
        lbl = Gtk.Label(label=name)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_xalign(0)
        box.append(lbl)       
        row.set_child(box)
        self.listbox.append(row)

    def _on_close_clicked(self, btn):
        if self.loading_process_id:
            GLib.source_remove(self.loading_process_id)
            self.loading_process_id = None
        self.emit("close-clicked")

    def _on_row_activated(self, listbox, row):
        if row:
            self.emit("channel-selected", row.channel_url, row.channel_name)

    def _on_search_changed(self, entry):
        self.listbox.invalidate_filter()

    def _filter_func(self, row):
        text = self.search_entry.get_text().lower()
        if not text: return True
        return text in row.channel_name.lower()

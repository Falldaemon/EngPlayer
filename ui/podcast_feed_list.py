#ui/podcast_feed_list.py

import gi
import threading
import urllib.request
import os
import hashlib
gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GObject, Pango, GLib, GdkPixbuf, Gdk
import gettext
import database

_ = gettext.gettext

class PodcastFeedList(Gtk.Box):
    __gsignals__ = {
        "back-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "podcast-selected": (GObject.SignalFlags.RUN_FIRST, None, (int, str, str)),
        "podcast-right-clicked": (GObject.SignalFlags.RUN_FIRST, None, (int, str, Gtk.Widget))
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, **kwargs)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header_box.set_margin_top(6)
        header_box.set_margin_start(6)
        header_box.set_margin_end(6)       
        self.back_button = Gtk.Button(icon_name="go-previous-symbolic")
        self.back_button.set_tooltip_text(_("Back to Media Menu"))
        self.back_button.connect("clicked", self._on_back_clicked)
        header_box.append(self.back_button)      
        title_label = Gtk.Label(label=_("Podcasts"))
        title_label.set_hexpand(True)
        title_label.set_xalign(0)
        title_label.add_css_class("heading")
        header_box.append(title_label)     
        self.append(header_box)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Search podcasts..."))
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
        self.all_podcasts = []
        self.cache_dir = os.path.join(database.get_cache_path(), "podcasts")
        os.makedirs(self.cache_dir, exist_ok=True)

    def populate(self, podcast_list):
        while True:
            row = self.listbox.get_first_child()
            if not row: break
            self.listbox.remove(row)      
        self.all_podcasts = podcast_list
        for pod in podcast_list:
            pod_id = pod[0]
            title = pod[1]
            url = pod[2]
            image_url = pod[5] if len(pod) > 5 else None          
            row = Gtk.ListBoxRow()
            row.podcast_id = pod_id
            row.podcast_title = title
            row.podcast_url = url
            gesture = Gtk.GestureClick.new()
            gesture.set_button(3)
            gesture.connect("pressed", self._on_row_right_clicked, row)
            row.add_controller(gesture)            
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(8)
            box.set_margin_end(8)
            icon = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
            icon.set_pixel_size(32)
            row.icon_widget = icon
            box.append(icon)
            if image_url:
                self._load_image_threaded(image_url, icon)
            lbl = Gtk.Label(label=title)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_xalign(0)
            box.append(lbl)           
            row.set_child(box)
            self.listbox.append(row)

    def _load_image_threaded(self, url, icon_widget):
        thread = threading.Thread(target=self._download_image_task, args=(url, icon_widget), daemon=True)
        thread.start()

    def _download_image_task(self, url, icon_widget):
        try:
            filename = hashlib.md5(url.encode()).hexdigest() + ".jpg"
            local_path = os.path.join(self.cache_dir, filename)           
            if not os.path.exists(local_path):
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = response.read()
                    with open(local_path, 'wb') as f:
                        f.write(data)
            GLib.idle_add(self._update_icon_on_ui, icon_widget, local_path)           
        except Exception as e:
            pass

    def _update_icon_on_ui(self, icon_widget, local_path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(local_path, 32, 32, True)
            icon_widget.set_from_pixbuf(pixbuf)
        except Exception:
            pass
        return False

    def _on_back_clicked(self, btn):
        self.search_entry.set_text("")
        self.emit("back-clicked")

    def _on_row_activated(self, listbox, row):
        if row:
            self.emit("podcast-selected", row.podcast_id, row.podcast_title, row.podcast_url)

    def _on_row_right_clicked(self, gesture, n_press, x, y, row):
        self.emit("podcast-right-clicked", row.podcast_id, row.podcast_title, row)

    def _on_search_changed(self, entry):
        self.listbox.invalidate_filter()

    def _filter_func(self, row):
        search_text = self.search_entry.get_text().lower()
        if not search_text: return True
        return search_text in row.podcast_title.lower()

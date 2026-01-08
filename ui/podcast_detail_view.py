#ui/podcast_detail_view.py

import gi
import threading
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject, Pango, GLib, GdkPixbuf
from utils.image_loader import load_image_async
import gettext

_ = gettext.gettext

class PodcastDetailView(Gtk.Box):
    __gsignals__ = {
        "episode-clicked": (GObject.SignalFlags.RUN_FIRST, None, (str, str))
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        self.info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.info_box.set_margin_top(12)
        self.info_box.set_margin_bottom(12)
        self.info_box.set_margin_start(12)
        self.info_box.set_margin_end(12)       
        self.cover_image = Gtk.Picture()
        self.cover_image.set_size_request(80, 80)
        self.cover_image.set_content_fit(Gtk.ContentFit.COVER)
        self.info_box.append(self.cover_image)      
        labels_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        labels_box.set_valign(Gtk.Align.CENTER)       
        self.podcast_title_label = Gtk.Label()
        self.podcast_title_label.add_css_class("title-1")
        self.podcast_title_label.set_xalign(0)
        labels_box.append(self.podcast_title_label)      
        self.episode_count_label = Gtk.Label()
        self.episode_count_label.add_css_class("caption")
        self.episode_count_label.set_xalign(0)
        labels_box.append(self.episode_count_label)      
        self.info_box.append(labels_box)
        self.append(self.info_box)      
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_vexpand(True)
        self.append(self.scrolled_window)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self._on_row_activated)
        self.listbox.add_css_class("navigation-sidebar")
        self.scrolled_window.set_child(self.listbox)        
        self.loading_spinner = Gtk.Spinner()
        self.loading_spinner.set_size_request(32, 32)
        self.loading_spinner.set_halign(Gtk.Align.CENTER)
        self.loading_spinner.set_valign(Gtk.Align.CENTER)

    def show_loading(self):
        self.scrolled_window.set_child(self.loading_spinner)
        self.loading_spinner.start()
        self.info_box.set_visible(False)

    def show_content(self):
        self.loading_spinner.stop()
        self.scrolled_window.set_child(self.listbox)
        self.info_box.set_visible(True)

    def populate(self, podcast_data):
        while True:
            row = self.listbox.get_first_child()
            if not row: break
            self.listbox.remove(row)          
        if not podcast_data:
            return
        self.podcast_title_label.set_text(podcast_data.get("title", "Unknown Podcast"))
        episodes = podcast_data.get("episodes", [])
        self.episode_count_label.set_text(_("{} Episodes").format(len(episodes)))
        image_url = podcast_data.get("image")
        if image_url:
            load_image_async(image_url, self.cover_image, width=80, height=80)
        for ep in episodes:
            row = Gtk.ListBoxRow()
            row.audio_url = ep.get("audio_url")
            row.title = ep.get("title")
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(10)
            box.set_margin_end(10)
            icon = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic") 
            icon.set_pixel_size(32)
            box.append(icon)
            lbl = Gtk.Label(label=ep.get("title", "Unknown Episode"))
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_xalign(0)
            lbl.set_hexpand(True)
            box.append(lbl)          
            row.set_child(box)
            self.listbox.append(row)          
        self.show_content()

    def _on_row_activated(self, listbox, row):
        if row and row.audio_url:
            self.emit("episode-clicked", row.audio_url, row.title)

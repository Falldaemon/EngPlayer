#ui/podcast_episode_list.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject, Pango
import gettext
import database 

_ = gettext.gettext

class PodcastEpisodeList(Gtk.Box):
    __gsignals__ = {
        "back-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "episode-selected": (GObject.SignalFlags.RUN_FIRST, None, (str, str))
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, **kwargs)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header_box.set_margin_top(6)
        header_box.set_margin_start(6)
        header_box.set_margin_end(6)      
        back_btn = Gtk.Button(icon_name="go-previous-symbolic")
        back_btn.set_tooltip_text(_("Back to Podcast List"))
        back_btn.connect("clicked", lambda b: self.emit("back-clicked"))
        header_box.append(back_btn)       
        self.title_label = Gtk.Label(label=_("Episodes"))
        self.title_label.add_css_class("heading")
        header_box.append(self.title_label)
        self.append(header_box)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.append(scrolled)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.add_css_class("navigation-sidebar")
        self.listbox.connect("row-activated", self._on_row_activated)
        scrolled.set_child(self.listbox)
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_valign(Gtk.Align.CENTER)

    def show_loading(self):
        self.listbox.set_visible(False)
        self.append(self.spinner)
        self.spinner.start()

    def populate(self, podcast_title, episodes):
        self.spinner.stop()
        if self.spinner.get_parent():
            self.remove(self.spinner)           
        self.listbox.set_visible(True)
        self.title_label.set_text(podcast_title)
        while True:
            row = self.listbox.get_first_child()
            if not row: break
            self.listbox.remove(row)
        for ep in episodes:
            row = Gtk.ListBoxRow()
            audio_url = ep["audio_url"]
            row.audio_url = audio_url
            row.title = ep["title"]
            is_finished = False
            try:
                is_finished = database.is_content_finished(audio_url)
            except AttributeError:
                pass
            except Exception as e:
                print(f"DB Error in Podcast List: {e}")
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(8)
            box.set_margin_end(8)
            icon_name = "object-select-symbolic" if is_finished else "audio-x-generic-symbolic"
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(16)
            if is_finished:
                icon.add_css_class("success")             
            box.append(icon)          
            lbl = Gtk.Label(label=ep["title"])
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_xalign(0)
            if is_finished:
                lbl.set_opacity(0.6)               
            box.append(lbl)          
            row.set_child(box)
            self.listbox.append(row)

    def _on_row_activated(self, listbox, row):
        if row:
            self.emit("episode-selected", row.audio_url, row.title)

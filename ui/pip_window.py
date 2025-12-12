# ui/pip_window.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GObject
import gettext
import logging
_ = gettext.gettext
class PipWindow(Gtk.Window):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("Picture-in-Picture"))
        self.set_default_size(320, 180)
        self.set_resizable(True)
        self.set_decorated(True)
        main_box = Gtk.Box()
        main_box.add_css_class("black")
        self.set_child(main_box)
        self.aspect_frame = Gtk.AspectFrame(ratio=16/9, obey_child=False, xalign=0.5, yalign=0.5)
        main_box.append(self.aspect_frame)
        self.picture_widget = Gtk.Picture(hexpand=True, vexpand=True, can_shrink=True)
        self.aspect_frame.set_child(self.picture_widget)

    def set_paintable(self, paintable):
        if self.picture_widget:
            self.picture_widget.set_paintable(paintable)

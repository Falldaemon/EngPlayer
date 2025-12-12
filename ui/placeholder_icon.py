# ui/placeholder_icon.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
class PlaceholderIcon(Gtk.Box):
    """
    A custom widget that displays a simple, stylish placeholder box.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_css_class("placeholder-icon")

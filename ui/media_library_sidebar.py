# ui/media_library_sidebar.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
import gettext
_ = gettext.gettext
class MediaLibrarySidebar(Gtk.Box):
    """
    A widget containing the navigation buttons for the media library
    (e.g., Videos, Pictures, Music) and control buttons.
    """
    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, **kwargs)
        self.set_margin_top(6)
        self.set_margin_start(6)
        self.set_margin_end(6)
        self.buttons = {}
        library_types = {
            "videos": _("Video Library"),
            "pictures": _("Picture Library"),
            "music": _("Music Library")
        }
        for key, label in library_types.items():
            btn = Gtk.Button(label=label)
            self.buttons[key] = btn
            self.append(btn)
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_top=6, margin_bottom=6)
        self.append(separator)
        refresh_button = Gtk.Button(label=_("Refresh Library"))
        self.buttons["refresh_library"] = refresh_button
        self.append(refresh_button)
        add_button = Gtk.Button(label=_("Add Source..."))
        self.buttons["add_source"] = add_button
        self.append(add_button)

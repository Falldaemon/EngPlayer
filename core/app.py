# core/app.py

import gi
import os
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, Gio
from ui.profile_window import ProfileWindow
import database
import gettext
_ = gettext.gettext

class MediaCenterApplication(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(flags=Gio.ApplicationFlags.HANDLES_OPEN, **kwargs)
        self.connect('activate', self.on_activate)

    def do_open(self, files, n_files, hint):
        self.activate()

    def do_startup(self):
        """This method runs once on application startup."""
        try:
            saved_theme = database.get_config_value('app_theme')
            style_manager = Adw.StyleManager.get_default()
            if saved_theme == "force_light":
                style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            elif saved_theme == "force_dark":
                style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            else:
                style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)
        except Exception as e:
            print(f"ERROR APPLYING SAVED THEME: {e}")
        Adw.Application.do_startup(self)
        css_provider = Gtk.CssProvider()
        css_file_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'css', 'style.css')
        try:
            css_provider.load_from_path(css_file_path)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        except Exception as e:
            print(f"ERROR LOADING CSS: {e}")

    def on_activate(self, app):
        if hasattr(self, 'win') and self.win:
            self.win.present()
            return
        self.win = ProfileWindow(application=app)
        self.win.present()

# ui/aspect_ratio_manager.py

import gi
gi.require_version('Gio', '2.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk
import gettext
import logging

_ = gettext.gettext

class AspectRatioManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.current_mode = "contain"
        variant_type = GLib.VariantType.new("s")
        initial_state = GLib.Variant("s", "contain")      
        self.ar_action = Gio.SimpleAction.new_stateful(
            "set_aspect_ratio", 
            variant_type, 
            initial_state
        )
        self.ar_action.connect("change-state", self._on_mode_change_requested)
        self.main_window.add_action(self.ar_action)

    def build_submenu(self):
        ar_menu = Gio.Menu()
        modes = [
            (_("Original (Fit)"), "contain"),
            (_("Stretch (Fill Screen)"), "fill"),
            (_("Zoom (Crop Edges)"), "cover")
        ]       
        for label, mode_str in modes:
            detailed_action = f"win.set_aspect_ratio::{mode_str}"
            ar_menu.append(label, detailed_action)          
        return ar_menu

    def _on_mode_change_requested(self, action, value):
        action.set_state(value)
        mode_str = value.get_string()
        self._apply_mode(mode_str)

    def _apply_mode(self, mode_str):
        self.current_mode = mode_str
        picture_widget = self._find_picture_widget(self.main_window.video_view)
        if not picture_widget:
            logging.error("Gtk.Picture widget not found in VideoView!")
            return          
        if mode_str == "contain":
            picture_widget.set_content_fit(Gtk.ContentFit.CONTAIN)
            self.main_window.show_toast(_("Aspect Ratio: Original (Fit)"))
        elif mode_str == "fill":
            picture_widget.set_content_fit(Gtk.ContentFit.FILL)
            self.main_window.show_toast(_("Aspect Ratio: Stretch to Fill"))
        elif mode_str == "cover":
            picture_widget.set_content_fit(Gtk.ContentFit.COVER)
            self.main_window.show_toast(_("Aspect Ratio: Zoom to Fit"))

    def _find_picture_widget(self, widget):
        if isinstance(widget, Gtk.Picture):
            return widget       
        child = widget.get_first_child()
        while child:
            found = self._find_picture_widget(child)
            if found:
                return found
            child = child.get_next_sibling()           
        return None

    def reset_mode(self):
        if self.current_mode != "contain":
            normal_state = GLib.Variant("s", "contain")
            self.ar_action.set_state(normal_state)
            self._apply_mode("contain")

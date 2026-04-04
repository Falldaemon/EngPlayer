# ui/playback_speed_manager.py

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
import gettext
import logging

_ = gettext.gettext

class PlaybackSpeedManager:
    def __init__(self, main_window, player):
        self.main_window = main_window
        self.player = player
        self.current_rate = 1.0
        variant_type = GLib.VariantType.new("s")
        initial_state = GLib.Variant("s", "1.0")       
        self.speed_action = Gio.SimpleAction.new_stateful(
            "set_playback_speed", 
            variant_type, 
            initial_state
        )
        self.speed_action.connect("change-state", self._on_speed_change_requested)
        self.main_window.add_action(self.speed_action)

    def build_submenu(self):
        speed_menu = Gio.Menu()
        speeds = [
            ("0.3x", "0.3"),
            ("0.4x", "0.4"),
            ("0.5x", "0.5"),
            ("0.6x", "0.6"),
            (_("Normal (1.0x)"), "1.0"),
            ("1.25x", "1.25"),
            ("1.5x", "1.5"),
            ("2.0x", "2.0")
        ]      
        for label, rate_str in speeds:
            detailed_action = f"win.set_playback_speed::{rate_str}"
            speed_menu.append(label, detailed_action)           
        return speed_menu

    def _on_speed_change_requested(self, action, value):
        action.set_state(value)       
        rate_str = value.get_string()
        rate = float(rate_str)       
        self._apply_speed(rate)

    def _apply_speed(self, rate):
        if self.current_rate == rate:
            return            
        self.current_rate = rate
        if hasattr(self.player, 'set_playback_rate'):
            self.player.set_playback_rate(rate)
            if rate == 1.0:
                self.main_window.show_toast(_("Playback speed restored to Normal"))
            else:
                self.main_window.show_toast(_("Playback speed set to {}x").format(rate))
        else:
            logging.error("Function 'set_playback_rate' not found in player module!")

    def reset_speed(self):
        if self.current_rate != 1.0:
            normal_state = GLib.Variant("s", "1.0")
            self.speed_action.set_state(normal_state)
            self._apply_speed(1.0)
            
    def set_enabled(self, enabled):
        self.speed_action.set_enabled(enabled)            

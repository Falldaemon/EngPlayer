# ui/sleep_timer_manager.py

import time
import logging
import gettext
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib

_ = gettext.gettext

class SleepTimerManager:
    def __init__(self, main_window):
        self.win = main_window
        self.sleep_timer_id = None
        self.sleep_target_time = 0
        self.sleep_at_end_of_media = False
        self.sleep_warning_shown = False
        self.sleep_warning_dialog = None
        self._setup_actions()

    def _setup_actions(self):
        self.sleep_timer_action = Gio.SimpleAction.new_stateful(
            "sleep_timer", 
            GLib.VariantType.new("s"), 
            GLib.Variant.new_string("off")
        )
        self.sleep_timer_action.connect("change-state", self._on_sleep_timer_change_state)
        self.win.add_action(self.sleep_timer_action)

    def build_submenu(self):
        timer_menu = Gio.Menu()
        timer_menu.append(_("Off"), "win.sleep_timer::off")
        timer_menu.append(_("15 Minutes"), "win.sleep_timer::15")
        timer_menu.append(_("30 Minutes"), "win.sleep_timer::30")
        timer_menu.append(_("60 Minutes"), "win.sleep_timer::60")
        timer_menu.append(_("90 Minutes"), "win.sleep_timer::90")
        timer_menu.append(_("120 Minutes"), "win.sleep_timer::120")
        timer_menu.append(_("Custom Time..."), "win.sleep_timer::custom")
        timer_menu.append(_("End of Media"), "win.sleep_timer::end")
        return timer_menu

    def _on_sleep_timer_change_state(self, action, value):
        action.set_state(value)
        selected_value = value.get_string()      
        if selected_value == "off":
            self.cancel_sleep_timer()
        elif selected_value == "custom":
            self._show_custom_time_dialog()
        elif selected_value == "end":
            self.win.show_toast(_("Timer set to close at the End of Media."))
            self._set_end_of_media_timer()
        else:
            minutes = int(selected_value)
            self._start_sleep_timer(minutes)

    def _show_custom_time_dialog(self):
        dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading=_("Custom Sleep Timer"),
            body=_("Please select the sleep timer duration:")
        )
        dialog.add_css_class("custom-timer-dialog")       
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(16)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)      
        self.timer_value_label = Gtk.Label(label="45 " + _("Minutes"))
        self.timer_value_label.add_css_class("title-1")       
        slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 180, 1)
        slider.set_value(45) 
        slider.set_draw_value(False) 
        slider.set_hexpand(True)
        
        def on_slider_changed(range_widget):
            val = int(range_widget.get_value())
            self.timer_value_label.set_text(f"{val} " + _("Minutes"))          
        slider.connect("value-changed", on_slider_changed)       
        box.append(self.timer_value_label)
        box.append(slider)
        dialog.set_extra_child(box)      
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("start", _("Start Timer"))
        dialog.set_default_response("start")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("start", Adw.ResponseAppearance.SUGGESTED)      
        dialog.connect("response", self._on_custom_time_response, slider)
        dialog.present()

    def _on_custom_time_response(self, dialog, response_id, slider):
        if response_id == "start":
            minutes = int(slider.get_value())
            self._start_sleep_timer(minutes)
        else:
            self.sleep_timer_action.set_state(GLib.Variant.new_string("off"))
        dialog.close()

    def _start_sleep_timer(self, minutes):
        if getattr(self, 'sleep_timer_id', None):
            GLib.source_remove(self.sleep_timer_id)
            self.sleep_timer_id = None       
        self.sleep_target_time = time.time() + (minutes * 60)
        self.sleep_warning_shown = False
        self.sleep_at_end_of_media = False      
        self.sleep_timer_id = GLib.timeout_add_seconds(1, self._sleep_timer_tick)
        self.win.show_toast(_("Sleep timer set for {} minutes.").format(minutes))
        state_val = str(minutes) if minutes in [15, 30, 60, 90, 120] else "custom"
        self.sleep_timer_action.set_state(GLib.Variant.new_string(state_val))

    def cancel_sleep_timer(self):
        if getattr(self, 'sleep_timer_id', None):
            GLib.source_remove(self.sleep_timer_id)
            self.sleep_timer_id = None           
        if getattr(self, 'sleep_warning_dialog', None):
            self.sleep_warning_dialog.close()
            self.sleep_warning_dialog = None
        self.sleep_target_time = 0
        self.sleep_warning_shown = False
        self.sleep_at_end_of_media = False
        self.sleep_timer_action.set_state(GLib.Variant.new_string("off"))

    def _set_end_of_media_timer(self):
        self.cancel_sleep_timer()
        self.sleep_at_end_of_media = True
        self.sleep_timer_action.set_state(GLib.Variant.new_string("end"))

    def _sleep_timer_tick(self):
        remaining = self.sleep_target_time - time.time()      
        if remaining <= 0:
            self.execute_sleep_action()
            return GLib.SOURCE_REMOVE           
        if remaining <= 60 and not self.sleep_warning_shown:
            self._show_sleep_warning_dialog()
            self.sleep_warning_shown = True          
        if self.sleep_warning_shown and getattr(self, 'sleep_warning_dialog', None):
            self.sleep_warning_label.set_markup(
                f"<span size='xx-large' weight='900'>{int(remaining)}</span>\n" + 
                _("seconds before playback stops.")
            )
        return GLib.SOURCE_CONTINUE

    def _show_sleep_warning_dialog(self):
        self.sleep_warning_dialog = Adw.MessageDialog(
            transient_for=self.win,
            heading=_("Sleep Timer Finishing"),
        )
        self.sleep_warning_dialog.add_css_class("custom-timer-dialog")       
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        self.sleep_warning_label = Gtk.Label(label="60")
        self.sleep_warning_label.set_use_markup(True)
        box.append(self.sleep_warning_label)
        self.sleep_warning_dialog.set_extra_child(box)      
        self.sleep_warning_dialog.add_response("cancel", _("Cancel Timer"))
        self.sleep_warning_dialog.add_response("add_15", "+15 " + _("Min"))
        self.sleep_warning_dialog.add_response("add_30", "+30 " + _("Min"))
        self.sleep_warning_dialog.add_response("add_45", "+45 " + _("Min"))
        self.sleep_warning_dialog.add_response("add_60", "+60 " + _("Min"))       
        self.sleep_warning_dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DESTRUCTIVE)
        self.sleep_warning_dialog.set_default_response("add_15")       
        self.sleep_warning_dialog.connect("response", self._on_sleep_warning_response)
        self.sleep_warning_dialog.present()

    def _on_sleep_warning_response(self, dialog, response_id):
        if response_id == "cancel":
            self.cancel_sleep_timer()
            self.win.show_toast(_("Sleep timer cancelled."))
        elif response_id.startswith("add_"):
            add_mins = int(response_id.split("_")[1])
            self.sleep_target_time += (add_mins * 60)
            self.sleep_warning_shown = False 
            self.sleep_warning_dialog = None
            self.win.show_toast(_("Added {} minutes to sleep timer.").format(add_mins))
            self.sleep_timer_action.set_state(GLib.Variant.new_string("custom"))
        dialog.close()

    def execute_sleep_action(self):
        logging.info("Sleep timer triggered. Closing the application completely.")
        self.cancel_sleep_timer()
        if hasattr(self.win, 'player') and self.win.player:
            self.win.player.shutdown()
        if hasattr(self.win, 'inhibitor') and self.win.inhibitor:
            self.win.inhibitor.uninhibit()
        self.win.close()
        
    def is_any_dialog_open(self):
        if hasattr(self, 'custom_timer_dialog') and self.custom_timer_dialog and self.custom_timer_dialog.get_visible():
            return True
        if hasattr(self, 'sleep_warning_dialog') and self.sleep_warning_dialog and self.sleep_warning_dialog.get_visible():
            return True          
        return False        

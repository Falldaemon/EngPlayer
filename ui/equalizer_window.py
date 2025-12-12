# ui/equalizer_window.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import gettext
import database
_ = gettext.gettext

PRESETS = {
    "flat": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "hiphop": [5.0, 4.0, 3.0, -1.0, -2.0, 1.0, 2.0, 1.5, 2.0, 2.5],
    "pop": [3.0, 2.5, 1.5, 0.5, -1.0, -1.0, 0.5, 1.5, 2.5, 3.0],
    "rock": [5.0, 4.0, 2.5, -1.0, -3.0, -3.0, -1.0, 2.0, 4.0, 5.0],
    "jazz": [2.5, 2.0, 1.0, 0.5, -0.5, -0.5, 0.5, 1.5, 2.0, 2.0],
    "classical": [2.0, 1.5, 0.5, -1.0, -1.5, -1.5, 0.5, 2.0, 3.0, 4.0],
    "vocal": [-3.5, -3.0, -1.0, 2.0, 4.0, 4.5, 3.5, 1.0, -2.0, -3.0]
}

class EqualizerWindow(Gtk.Window):
    def __init__(self, parent, player, **kwargs):
        super().__init__(transient_for=parent, **kwargs)
        self.player = player
        self.is_applying_preset = False
        self.set_title(_("Audio Equalizer"))
        self.set_default_size(500, 450)
        self.set_hide_on_close(True)
        self.set_modal(True)
        self.add_css_class("equalizer-window")
        header = Adw.HeaderBar()
        self.set_titlebar(header)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.set_child(main_box)
        preset_row = Adw.ActionRow(title=_("Presets"))
        main_box.append(preset_row)
        self.preset_combo = Gtk.ComboBoxText()
        preset_row.add_suffix(self.preset_combo)
        preset_row.set_activatable_widget(self.preset_combo)
        self.preset_combo.append("custom", _("Custom"))
        self.preset_combo.append("flat", _("Reset (Flat)"))
        self.preset_combo.append("hiphop", _("Hip-Hop"))
        self.preset_combo.append("pop", _("Pop"))
        self.preset_combo.append("rock", _("Rock"))
        self.preset_combo.append("jazz", _("Jazz"))
        self.preset_combo.append("classical", _("Classical"))
        self.preset_combo.append("vocal", _("Vocal"))
        self.preset_combo.connect("changed", self._on_preset_changed)
        self.sliders = []
        grid = Gtk.Grid(column_spacing=12, row_spacing=6, vexpand=True, halign=Gtk.Align.CENTER)
        main_box.append(grid)
        band_labels = self.player.get_equalizer_band_labels()
        for i in range(10):
            slider = Gtk.Scale(orientation=Gtk.Orientation.VERTICAL, inverted=True, digits=1, value_pos=Gtk.PositionType.BOTTOM)
            slider.set_range(-24, 12)
            saved_value = database.get_config_value(f"eq_band_{i}")
            slider.set_value(float(saved_value) if saved_value is not None else 0)
            slider.set_size_request(-1, 150)
            slider.connect("value-changed", self.on_band_changed, i)
            label = Gtk.Label(label=band_labels[i] if i < len(band_labels) else f"B{i}")
            grid.attach(slider, i, 0, 1, 1)
            grid.attach(label, i, 1, 1, 1)
            self.sliders.append(slider)
        reset_button = Gtk.Button(label=_("Reset"), halign=Gtk.Align.END, margin_top=10)
        reset_button.connect("clicked", self._on_reset_clicked)
        main_box.append(reset_button)
        self._check_current_settings()

    def _check_current_settings(self):
        """Checks which preset matches the current slider settings when the window is opened."""
        current_values = []
        for i in range(10):
            saved_value = database.get_config_value(f"eq_band_{i}")
            current_values.append(float(saved_value) if saved_value is not None else 0.0)
        found_preset_id = "custom"
        for preset_id, values in PRESETS.items():
            if all(abs(current_values[i] - values[i]) < 0.1 for i in range(10)):
                found_preset_id = preset_id
                break
        self.is_applying_preset = True
        self.preset_combo.set_active_id(found_preset_id)
        self.is_applying_preset = False

    def _on_preset_changed(self, combo):
        """Updates the sliders and the player when a preset is selected from the ComboBox."""
        if self.is_applying_preset:
            return
        active_id = combo.get_active_id()
        if not active_id or active_id == "custom":
            return
        values = PRESETS.get(active_id)
        if not values:
            return
        self.is_applying_preset = True
        for i in range(10):
            val = values[i]
            self.sliders[i].set_value(val)
            self.player.set_equalizer_band(i, val)
            database.set_config_value(f"eq_band_{i}", f"{val:.2f}")
        self.is_applying_preset = False

    def on_band_changed(self, slider, band_index):
        """Runs when a slider is manually moved."""
        if self.is_applying_preset:
            return
        value = slider.get_value()
        self.player.set_equalizer_band(band_index, value)
        database.set_config_value(f"eq_band_{band_index}", f"{value:.2f}")
        if self.preset_combo.get_active_id() != "custom":
            self.is_applying_preset = True
            self.preset_combo.set_active_id("custom")
            self.is_applying_preset = False

    def _on_reset_clicked(self, button):
        """The reset button now selects the 'flat' preset."""
        self.preset_combo.set_active_id("flat")

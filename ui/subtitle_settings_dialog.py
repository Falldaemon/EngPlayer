# ui/subtitle_settings_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk
import gettext
import database
_ = gettext.gettext
class SubtitleSettingsDialog(Adw.PreferencesWindow):

    def __init__(self, parent):
        super().__init__(transient_for=parent)
        self.set_title(_("Subtitle Settings"))
        self.set_default_size(500, 500)
        self.set_modal(True)
        self.set_search_enabled(False)
        self.add_css_class("subtitle-settings-dialog")
        self._load_settings()
        page = Adw.PreferencesPage()
        self.add(page)
        font_group = Adw.PreferencesGroup(title=_("Font"))
        page.add(font_group)
        self.font_row = Adw.ActionRow(title=_("Subtitle Font and Size"))
        font_group.add(self.font_row)
        self.font_row.set_subtitle(self.font_setting_str)
        change_button = Gtk.Button(label=_("Change..."), valign=Gtk.Align.CENTER)
        change_button.connect("clicked", self._on_font_change_clicked)
        self.font_row.add_suffix(change_button)
        self.font_row.set_activatable_widget(change_button)
        color_group = Adw.PreferencesGroup(title=_("Colors"))
        page.add(color_group)
        self.color_button = Gtk.ColorButton(valign=Gtk.Align.CENTER)
        self.color_button.set_rgba(self.font_color)
        self.color_button.connect("color-set", self._on_color_setting_changed)
        color_row = Adw.ActionRow(title=_("Font Color"))
        color_row.add_suffix(self.color_button)
        color_row.set_activatable_widget(self.color_button)
        color_group.add(color_row)
        bg_group = Adw.PreferencesGroup(title=_("Background"))
        page.add(bg_group)
        self.bg_color_button = Gtk.ColorButton(valign=Gtk.Align.CENTER)
        self.bg_color_button.set_rgba(self.bg_color)
        self.bg_color_button.connect("color-set", self._on_bg_color_changed)
        bg_color_row = Adw.ActionRow(title=_("Background Color"))
        bg_color_row.add_suffix(self.bg_color_button)
        bg_color_row.set_activatable_widget(self.bg_color_button)
        bg_group.add(bg_color_row)
        self.opacity_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.opacity_scale.set_value(self.bg_opacity * 100)
        self.opacity_scale.set_draw_value(True)
        self.opacity_scale.set_hexpand(True)
        self.opacity_scale.connect("value-changed", self._on_opacity_changed)
        opacity_row = Adw.ActionRow(title=_("Background Opacity"))
        opacity_row.add_suffix(self.opacity_scale)
        bg_group.add(opacity_row)

    def _load_settings(self):
        """Loads settings from the database."""
        self.font_setting_str = database.get_config_value("subtitle_font") or "Sans 12"
        color_setting_str = database.get_config_value("subtitle_color") or "rgba(255,255,255,1.0)"
        self.font_color = Gdk.RGBA()
        self.font_color.parse(color_setting_str)
        bg_color_str = database.get_config_value("subtitle_bgcolor") or "rgba(0,0,0,1.0)"
        self.bg_color = Gdk.RGBA()
        self.bg_color.parse(bg_color_str)
        opacity_str = database.get_config_value("subtitle_bgopacity") or "0.5"
        self.bg_opacity = float(opacity_str)
        self.bg_color.alpha = self.bg_opacity

    def _on_font_change_clicked(self, button):
        font_dialog = Gtk.FontChooserDialog(title=_("Select Font"), transient_for=self)
        font_dialog.set_font(self.font_setting_str)
        font_dialog.connect("response", self._on_font_dialog_response)
        font_dialog.present()

    def _on_font_dialog_response(self, dialog, response_id):
        """Handles the response from the font chooser dialog."""
        if response_id == Gtk.ResponseType.OK:
            new_font_name = dialog.get_font()
            database.set_config_value("subtitle_font", new_font_name)
            self.font_setting_str = new_font_name
            self.font_row.set_subtitle(self.font_setting_str)
            main_window = self.get_transient_for()
            if main_window and hasattr(main_window, 'player'):
                main_window.player.apply_subtitle_font(new_font_name)
            self._show_toast(_("Subtitle font set!"))
        dialog.destroy()

    def _on_color_setting_changed(self, color_button):
        """Saves the color setting to the database when changed."""
        color = color_button.get_rgba()
        database.set_config_value("subtitle_color", color.to_string())
        self._show_toast(_("Subtitle color saved!"))

    def _on_bg_color_changed(self, color_button):
        """Saves the background color to the database when changed."""
        color = color_button.get_rgba()
        database.set_config_value("subtitle_bgcolor", color.to_string())
        self._show_toast(_("Background color saved!"))

    def _on_opacity_changed(self, scale):
        """Saves the background opacity to the database when changed."""
        opacity = scale.get_value() / 100.0
        database.set_config_value("subtitle_bgopacity", str(opacity))
        color = self.bg_color_button.get_rgba()
        color.alpha = opacity
        self.bg_color_button.set_rgba(color)

    def _show_toast(self, message):
        main_window = self.get_transient_for()
        if main_window and hasattr(main_window, 'show_toast'):
             main_window.show_toast(message)

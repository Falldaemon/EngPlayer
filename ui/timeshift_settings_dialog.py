# ui/timeshift_settings_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import database
import gettext
import os

_ = gettext.gettext

class TimeshiftSettingsDialog(Adw.MessageDialog):
    def __init__(self, parent_window):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_heading(_("Timeshift Settings (BETA)"))
        self.add_css_class("timeshift-settings-dialog")
        self.ts_enabled = database.get_config_value('timeshift_enabled') == '1'
        self.ts_quota = database.get_config_value('timeshift_quota_mb') or '1024'
        self.ts_path = database.get_config_value('timeshift_path') or ""
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content_box.set_margin_top(16)
        content_box.set_margin_bottom(16)
        content_box.set_margin_start(16)
        content_box.set_margin_end(16)
        description_text = _(
            "Timeshift allows you to pause live TV and resume from where you left off. "
            "The broadcast is temporarily recorded to your selected folder.\n\n"
            "<b>📊 Estimated Storage Usage (Per Hour):</b>\n"
            "  • <b>HD (720p):</b> ~1.2 GB\n"
            "  • <b>Full HD (1080p):</b> ~2.5 GB\n"
            "  • <b>4K (UHD):</b> ~6.0 GB+\n\n"
            "💡 <b>Tip:</b> To save internal disk space and prevent wear on your system's SSD, "
            "it is highly recommended to select an external USB drive or HDD as your Timeshift folder.\n\n"
            "⚠️ <b>Note:</b> Recording stops automatically if the quota is reached. "
            "The temporary buffer is safely cleared when you change channels or return to live TV."
        )       
        self.description_label = Gtk.Label()
        self.description_label.set_markup(description_text)
        self.description_label.set_wrap(True)
        self.description_label.set_xalign(0)
        self.description_label.add_css_class("caption")
        content_box.append(self.description_label)       
        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        content_box.append(listbox)
        self.enable_switch = Adw.SwitchRow(title=_("Enable Timeshift"))
        self.enable_switch.set_active(self.ts_enabled)
        listbox.append(self.enable_switch)
        self.folder_row = Adw.ActionRow(title=_("Timeshift Folder"))
        subtitle_text = self.ts_path if self.ts_path else _("Default (Cache Folder)")
        self.folder_row.set_subtitle(subtitle_text)
        self.folder_row.set_activatable(True)
        self.folder_row.connect("activated", self._on_folder_row_activated)
        suffix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.reset_path_btn = Gtk.Button(icon_name="edit-clear-symbolic")
        self.reset_path_btn.set_valign(Gtk.Align.CENTER)
        self.reset_path_btn.add_css_class("flat")
        self.reset_path_btn.set_tooltip_text(_("Reset to Default"))
        self.reset_path_btn.connect("clicked", self._on_reset_path_clicked)
        self.reset_path_btn.set_visible(bool(self.ts_path)) 
        folder_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")      
        suffix_box.append(self.reset_path_btn)
        suffix_box.append(folder_icon)      
        self.folder_row.add_suffix(suffix_box)
        listbox.append(self.folder_row)
        self.quota_row = Adw.ActionRow(title=_("Storage Quota"))
        self.quota_combo = Gtk.ComboBoxText()
        self.quota_combo.append("500", "500 MB")
        self.quota_combo.append("1024", "1 GB")
        self.quota_combo.append("2048", "2 GB")
        self.quota_combo.append("5120", "5 GB")
        self.quota_combo.append("custom", _("Custom..."))
        self.quota_combo.set_valign(Gtk.Align.CENTER)
        self.quota_row.add_suffix(self.quota_combo)
        listbox.append(self.quota_row)
        self.custom_row = Adw.ActionRow(title=_("Custom Quota (MB)"))
        self.custom_row.set_subtitle(_("Enter value in Megabytes (e.g. 1500)"))
        self.custom_spin = Gtk.SpinButton.new_with_range(100, 50000, 100) 
        self.custom_spin.set_valign(Gtk.Align.CENTER)
        self.custom_row.add_suffix(self.custom_spin)
        listbox.append(self.custom_row)      
        if self.ts_quota in ["500", "1024", "2048", "5120"]:
            self.quota_combo.set_active_id(self.ts_quota)
            self.custom_row.set_visible(False)
        else:
            self.quota_combo.set_active_id("custom")
            self.custom_spin.set_value(float(self.ts_quota))
            self.custom_row.set_visible(True)
        self.quota_combo.connect("changed", self._on_combo_changed)
        self.enable_switch.connect("notify::active", self._on_switch_changed)
        self._on_switch_changed(self.enable_switch, None)        
        self.set_extra_child(content_box)
        self.add_response("cancel", _("Cancel"))
        self.add_response("save", _("Save"))
        self.set_default_response("save")
        self.set_close_response("cancel")
        self.connect("response", self._on_response)

    def _on_reset_path_clicked(self, button):
        self.ts_path = ""
        self.folder_row.set_subtitle(_("Default (Cache Folder)"))
        self.reset_path_btn.set_visible(False)

    def _on_folder_row_activated(self, row):
        dialog = Gtk.FileChooserDialog(
            title=_("Select Timeshift Folder"),
            transient_for=self.get_transient_for(),
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Select"), Gtk.ResponseType.ACCEPT
        )
        dialog.set_modal(True)
        
        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                gfile = d.get_file()
                if gfile:
                    selected_path = gfile.get_path()
                    self.ts_path = selected_path
                    self.folder_row.set_subtitle(selected_path)
                    self.reset_path_btn.set_visible(True)
            d.hide()
            GLib.idle_add(d.destroy)
        dialog.connect("response", on_response)
        dialog.present()

    def _on_combo_changed(self, combo):
        is_custom = combo.get_active_id() == "custom"
        self.custom_row.set_visible(is_custom)
        
    def _on_switch_changed(self, switch, pspec):
        is_active = switch.get_active()
        self.quota_row.set_sensitive(is_active)
        self.custom_row.set_sensitive(is_active)
        self.folder_row.set_sensitive(is_active)

    def _on_response(self, dialog, response_id):
        if response_id == "save":
            is_enabled = self.enable_switch.get_active()
            database.set_config_value('timeshift_enabled', '1' if is_enabled else '0')          
            selected_quota = self.quota_combo.get_active_id()
            if selected_quota == "custom":
                final_quota = str(int(self.custom_spin.get_value()))
            else:
                final_quota = selected_quota               
            database.set_config_value('timeshift_quota_mb', final_quota)
            database.set_config_value('timeshift_path', self.ts_path)           
            self.get_transient_for().show_toast(_("Timeshift settings saved!"))           
        self.close()

#ui/password_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
import gettext
import database
_ = gettext.gettext
class PasswordDialog(Adw.MessageDialog):
    def __init__(self, parent, toast_overlay):
        super().__init__()
        self.add_css_class("password-dialog")
        self.toast_overlay = toast_overlay
        self.set_transient_for(parent)
        self.set_modal(True)
        self.password_is_set = database.get_config_value('app_password') is not None
        if self.password_is_set:
            self.set_heading(_("Change Application Password"))
            self.set_body(_("Please enter your old password and a new one."))
        else:
            self.set_heading(_("Set Application Password"))
            self.set_body(_("Please enter a new password. This will be used to lock and unlock items."))
        self.add_response("cancel", _("Cancel"))
        self.add_response("save", _("Save"))
        self.set_default_response("save")
        self.set_close_response("cancel")
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.old_pass_entry = None
        if self.password_is_set:
            self.old_pass_entry = Gtk.PasswordEntry()
            self.old_pass_entry.set_property("placeholder-text", _("Old Password"))
            content_box.append(self.old_pass_entry)
        self.pass_entry = Gtk.PasswordEntry()
        self.pass_entry.set_property("placeholder-text", _("New Password"))
        self.confirm_entry = Gtk.PasswordEntry()
        self.confirm_entry.set_property("placeholder-text", _("Confirm New Password"))
        content_box.append(self.pass_entry)
        content_box.append(self.confirm_entry)
        self.set_extra_child(content_box)
        self.connect("response", self.on_response)

    def on_response(self, dialog, response_id):
        if response_id == "save":
            if self.password_is_set:
                old_pass = self.old_pass_entry.get_text()
                if not database.check_password(old_pass):
                    self.get_transient_for().show_toast(_("Old password is not correct!"))
                    return
            pass1 = self.pass_entry.get_text()
            pass2 = self.confirm_entry.get_text()
            if not pass1:
                self.get_transient_for().show_toast(_("New password cannot be empty!"))
                return
            if pass1 == pass2:
                database.set_password(pass1)
                self.get_transient_for().show_toast(_("Password saved successfully!"))
            else:
                self.get_transient_for().show_toast(_("New passwords do not match!"))

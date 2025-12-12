#ui/password_prompt_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
import gettext
_ = gettext.gettext
class PasswordPromptDialog(Adw.MessageDialog):
    """
    A simple dialog to prompt the user for the application password.
    """

    def __init__(self, parent):
        super().__init__()
        self.add_css_class("password-prompt-dialog")
        self.set_transient_for(parent)
        self.set_default_size(400, -1)
        self.set_heading(_("Password Required"))
        self.set_body(_("This item is locked. Please enter the password to continue."))
        self.add_response("cancel", _("Cancel"))
        self.add_response("ok", _("OK"))
        self.set_default_response("ok")
        self.set_close_response("cancel")
        self.password_entry = Gtk.PasswordEntry()
        self.password_entry.set_property("placeholder-text", _("Password"))
        self.password_entry.set_property("activates-default", True)
        self.set_extra_child(self.password_entry)

    def get_password(self):
        """Returns the text entered in the password entry."""
        return self.password_entry.get_text()

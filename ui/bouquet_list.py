# ui/bouquet_list.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, GdkPixbuf, Gio, Gdk, Adw, Pango
import gettext
import os
import database
import logging
from utils.theme_utils import get_icon_theme_folder
from .password_prompt_dialog import PasswordPromptDialog
from .password_dialog import PasswordDialog
_ = gettext.gettext
class BouquetList(Gtk.Box):
    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.search_entry = Gtk.SearchEntry(
            placeholder_text=_("Search bouquet..."),
            margin_start=6,
            margin_end=6,
            margin_top=6,
            margin_bottom=6
        )
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.append(self.search_entry)
        self.show_locked_button = Gtk.CheckButton(label=_("Show Locked Items"))
        self.show_locked_button.set_halign(Gtk.Align.CENTER)
        self.show_locked_button.set_margin_top(6)
        self.show_locked_button.set_margin_bottom(6)
        self.show_locked_button.set_margin_start(12)
        self.show_locked_button.set_margin_end(12)
        self.append(self.show_locked_button)
        self.bouquet_listbox = Gtk.ListBox()
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.bouquet_listbox)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        self.append(scrolled_window)
        self.active_row = None
        self.all_bouquet_names = []

    def clear_list(self):
        """Clears the listbox completely."""
        while (child := self.bouquet_listbox.get_first_child()):
            self.bouquet_listbox.remove(child)

    def populate_bouquets_async(self, bouquet_names):
        """
        Populates the bouquet list incrementally without freezing the UI.
        """
        self.clear_list()
        self.all_bouquet_names = bouquet_names
        show_locked = database.get_show_locked_bouquets_status()
        if show_locked:
            bouquets_to_display = bouquet_names
        else:
            bouquets_to_display = [
                name for name in bouquet_names
                if not database.get_bouquet_lock_status(name)
            ]
        bouquets_generator = (name for name in sorted(bouquets_to_display))
        GLib.idle_add(self._populate_chunk, bouquets_generator)

    def _populate_chunk(self, bouquets_generator):
        """
        Takes a certain number (e.g., 20) of items from the generator and adds them to the list.
        """
        chunk_size = 20
        try:
            for _ in range(chunk_size):
                bouquet_name = next(bouquets_generator)
                self._add_row_to_listbox(bouquet_name)
            return True
        except StopIteration:
            logging.info("Incremental population of the bouquet list is complete.")
            return False

    def _add_row_to_listbox(self, name):
        """Creates a single ListBoxRow for the given name and adds it to the list."""
        row = Gtk.ListBoxRow()
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox.set_margin_start(10); hbox.set_margin_end(10)
        row.set_child(hbox)
        label = Gtk.Label(label=name, xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_hexpand(True)
        hbox.append(label)
        theme_folder = get_icon_theme_folder()
        row.lock_icon = Gtk.Image.new_from_file(os.path.join("resources", "icons", theme_folder, "lock-icon.svg"))
        row.lock_icon.set_pixel_size(16)
        hbox.append(row.lock_icon)
        is_locked = database.get_bouquet_lock_status(name)
        row.lock_icon.set_visible(is_locked)
        row.bouquet_name = name
        right_click_gesture = Gtk.GestureClick.new()
        right_click_gesture.set_button(0)
        right_click_gesture.connect("pressed", self._on_row_right_clicked, row)
        row.add_controller(right_click_gesture)
        self.bouquet_listbox.append(row)

    def populate_bouquets(self, bouquet_names):
        logging.warning("Synchronous populate_bouquets called. Please use the async version.")
        self.populate_bouquets_async(bouquet_names)

    def _on_row_right_clicked(self, gesture, n_press, x, y, listbox_row):
        if gesture.get_current_button() == 3:
            self.active_row = listbox_row
            menu_model = self._build_menu_for_bouquet(listbox_row.bouquet_name)
            popover = Gtk.PopoverMenu.new_from_model(menu_model)
            popover.set_parent(listbox_row)
            popover.popup()

    def _build_menu_for_bouquet(self, bouquet_name):
        main_menu = Gio.Menu()
        is_locked = database.get_bouquet_lock_status(bouquet_name)
        lock_label = _("Unlock") if is_locked else _("Lock")
        main_menu.append(lock_label, "row.toggle_lock")
        action_group = Gio.SimpleActionGroup()
        toggle_lock_action = Gio.SimpleAction.new("toggle_lock", None)
        toggle_lock_action.connect("activate", self._on_toggle_lock_activated)
        action_group.add_action(toggle_lock_action)
        if self.active_row:
            self.active_row.insert_action_group("row", action_group)
        return main_menu

    def _on_toggle_lock_activated(self, action, value):
        if not self.active_row: return
        name = self.active_row.bouquet_name
        is_currently_locked = database.get_bouquet_lock_status(name)
        if is_currently_locked:
            prompt = PasswordPromptDialog(self.get_root())
            prompt.connect("response", self._on_password_prompt_response_for_unlock)
            prompt.present()
        else:
            password_is_set = database.get_config_value('app_password') is not None
            if password_is_set:
                database.set_bouquet_lock_status(name, True)
                self.populate_bouquets_async(self.all_bouquet_names)
            else:
                self.show_set_password_dialog()

    def _on_password_prompt_response_for_unlock(self, dialog, response_id):
        if response_id == "ok":
            if database.check_password(dialog.get_password()):
                name = self.active_row.bouquet_name
                database.set_bouquet_lock_status(name, False)
                self.populate_bouquets_async(self.all_bouquet_names)
            else:
                toast = Adw.Toast.new(_("Wrong Password!"))
                self.get_root().toast_overlay.add_toast(toast)

    def show_set_password_dialog(self):
        """Dialog that shows the 'password not set' warning."""
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading=_("Password Not Set"),
            body=_("To lock items, you must first set a master password for the application."),
            modal=True
        )
        dialog.add_css_class("set-password-warning-dialog")
        dialog.add_response("close", _("Close"))
        dialog.add_response("set-password", _("Set Password"))
        dialog.set_default_response("set-password")
        dialog.connect("response", self._on_set_password_dialog_response)
        dialog.present()

    def _on_set_password_dialog_response(self, dialog, response_id):
        """Runs when the 'Set Password' button in the warning dialog is pressed."""
        if response_id == "set-password":
            password_dialog = PasswordDialog(self.get_root(), self.get_root().toast_overlay)
            password_dialog.present()

    def _on_search_changed(self, entry):
        """Manually filters the list as the search bar changes."""
        search_text = entry.get_text().lower().strip()
        current_row = self.bouquet_listbox.get_first_child()
        while current_row:
            if hasattr(current_row, 'bouquet_name'):
                row_text = current_row.bouquet_name.lower()
                if search_text in row_text:
                    current_row.set_visible(True)
                else:
                    current_row.set_visible(False)
            current_row = current_row.get_next_sibling()

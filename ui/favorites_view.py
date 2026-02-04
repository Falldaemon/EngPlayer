# ui/favorites_view.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GObject, Pango
import gettext
import os
import database
from utils.theme_utils import get_icon_theme_folder
from .channel_list import ChannelList
from .password_prompt_dialog import PasswordPromptDialog
from .password_dialog import PasswordDialog
from .move_list_dialog import MoveListDialog
_ = gettext.gettext
class FavoritesView(Gtk.Box):
    __gsignals__ = {
        "favorites-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "playlist-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,))
    }

    def __init__(self, all_channels_map, toast_overlay, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.all_channels_map = all_channels_map
        self.toast_overlay = toast_overlay
        self.active_fav_list_row = None
        self.fav_list_search_entry = Gtk.SearchEntry(
            placeholder_text=_("Search favorite list..."),
            margin_start=6, margin_end=6, margin_top=6, margin_bottom=6
        )
        self.fav_list_search_entry.connect("search-changed", self._on_fav_list_search_changed)
        self.append(self.fav_list_search_entry)
        self.favorites_stack = Gtk.Stack()
        self.favorites_stack.set_vexpand(True)
        self.append(self.favorites_stack)
        self.favorite_lists_listbox = Gtk.ListBox()
        self.favorite_lists_listbox.connect("row-activated", self._on_favorite_list_selected)
        fav_list_scrolled = Gtk.ScrolledWindow()
        fav_list_scrolled.set_child(self.favorite_lists_listbox)
        self.favorites_stack.add_titled(fav_list_scrolled, "lists", "Favorite Lists")
        self.favorite_channels_list = ChannelList()
        self.favorites_stack.add_titled(self.favorite_channels_list, "channels", "Favorite Channels")
        self.favorites_stack.set_visible_child_name("lists")

    def get_favorite_channels_list_widget(self):
        return self.favorite_channels_list.channel_listbox

    def reset_view(self):
        """Resets the view to the initial state showing the favorite lists."""
        self.favorites_stack.set_visible_child_name("lists")
        self.fav_list_search_entry.set_visible(True)
        if hasattr(self.favorite_channels_list, 'search_entry'):
             self.favorite_channels_list.search_entry.set_visible(False)
        self.fav_list_search_entry.set_text("")
        if hasattr(self.favorite_channels_list, 'search_entry'):
            self.favorite_channels_list.search_entry.set_text("")

    def refresh_lists(self):
        while (child := self.favorite_lists_listbox.get_first_child()):
            self.favorite_lists_listbox.remove(child)
        show_locked = database.get_show_locked_bouquets_status()
        all_fav_lists = database.get_all_favorite_lists()
        if show_locked:
            lists_to_display = all_fav_lists
        else:
            lists_to_display = [
                fav_list for fav_list in all_fav_lists
                if not database.get_favorite_list_lock_status(fav_list["list_id"])
            ]
        for fav_list in lists_to_display:
            row = Gtk.ListBoxRow()
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hbox.set_margin_start(10); hbox.set_margin_end(10)
            row.set_child(hbox)
            label = Gtk.Label(label=fav_list["list_name"], xalign=0)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_hexpand(True)
            hbox.append(label)
            theme_folder = get_icon_theme_folder()
            row.lock_icon = Gtk.Image.new_from_file(os.path.join("resources", "icons", theme_folder, "lock-icon.svg"))
            row.lock_icon.set_pixel_size(16)
            hbox.append(row.lock_icon)
            is_locked = database.get_favorite_list_lock_status(fav_list["list_id"])
            row.lock_icon.set_visible(is_locked)
            row.list_id = fav_list["list_id"]
            row.list_name = fav_list["list_name"]
            right_click_gesture = Gtk.GestureClick.new()
            right_click_gesture.set_button(3)
            right_click_gesture.connect("pressed", self._on_fav_list_row_right_clicked, row)
            row.add_controller(right_click_gesture)
            self.favorite_lists_listbox.append(row)

    def _on_favorite_list_selected(self, listbox, row):
        if not row: return
        self.fav_list_search_entry.set_text("")
        list_id = row.list_id
        password_is_set = database.get_config_value('app_password') is not None
        list_is_locked = database.get_favorite_list_lock_status(list_id)
        if password_is_set and list_is_locked:
            prompt = PasswordPromptDialog(self.get_root())
            prompt.connect("response", self._on_password_prompt_response_fav_list, list_id)
            prompt.present()
        else:
            self._show_channels_for_favorite_list(list_id)

    def _show_channels_for_favorite_list(self, list_id):
        channel_urls = database.get_channels_in_list(list_id)
        channels_to_display = [self.all_channels_map.get(url) for url in channel_urls if self.all_channels_map.get(url)]
        self.emit("playlist-selected", channels_to_display)
        self.favorite_channels_list.active_list_id = list_id
        self.favorite_channels_list.populate_channels_async(channels_to_display)
        self.favorites_stack.set_visible_child_name("channels")
        self.fav_list_search_entry.set_visible(False)
        if hasattr(self.favorite_channels_list, 'search_entry'):
             self.favorite_channels_list.search_entry.set_visible(True)
             self.favorite_channels_list.search_entry.set_text("")

    def _on_password_prompt_response_fav_list(self, dialog, response_id, list_id):
        if response_id == "ok":
            if database.check_password(dialog.get_password()):
                self._show_channels_for_favorite_list(list_id)
            else:
                self.get_root().show_toast(_("Wrong Password!"))

    def _on_fav_list_row_right_clicked(self, gesture, n_press, x, y, listbox_row):
        if gesture.get_current_button() == 3:
            self.active_fav_list_row = listbox_row
            menu_model = self._build_menu_for_fav_list(listbox_row.list_id)
            popover = Gtk.PopoverMenu.new_from_model(menu_model)
            popover.set_parent(listbox_row)
            popover.popup()

    def _build_menu_for_fav_list(self, list_id):
        main_menu = Gio.Menu()
        is_locked = database.get_favorite_list_lock_status(list_id)
        lock_label = _("Unlock") if is_locked else _("Lock")
        main_menu.append(lock_label, "row.toggle_lock")
        main_menu.append_section(None, Gio.Menu())
        main_menu.append(_("Move..."), "row.move_list")
        main_menu.append_section(None, Gio.Menu())
        main_menu.append(_("Delete List"), "row.delete_list")
        action_group = Gio.SimpleActionGroup()
        toggle_lock_action = Gio.SimpleAction.new("toggle_lock", None)
        action_group.add_action(toggle_lock_action)
        toggle_lock_action.connect("activate", lambda a, v, l_id=list_id: self._on_toggle_fav_list_lock_activated(l_id))
        move_action = Gio.SimpleAction.new("move_list", None)
        action_group.add_action(move_action)
        move_action.connect("activate", self._on_move_list_activated)
        delete_action = Gio.SimpleAction.new("delete_list", None)
        action_group.add_action(delete_action)
        delete_action.connect("activate", lambda a, v, l_id=list_id: self._on_delete_fav_list_activated(l_id))
        if self.active_fav_list_row:
            self.active_fav_list_row.insert_action_group("row", action_group)
        return main_menu

    def _on_toggle_fav_list_lock_activated(self, list_id):
        if not self.active_fav_list_row: return
        is_currently_locked = database.get_favorite_list_lock_status(list_id)
        if is_currently_locked:
            prompt = PasswordPromptDialog(self.get_root())
            prompt.connect("response", self._on_password_prompt_response_for_unlock_fav_list, list_id)
            prompt.present()
        else:
            password_is_set = database.get_config_value('app_password') is not None
            if password_is_set:
                database.set_favorite_list_lock_status(list_id, True)
                self.refresh_lists()
            else:
                self.show_set_password_dialog()

    def _on_password_prompt_response_for_unlock_fav_list(self, dialog, response_id, list_id):
        if response_id == "ok":
            if database.check_password(dialog.get_password()):
                database.set_favorite_list_lock_status(list_id, False)
                self.refresh_lists()
            else:
                self.get_root().show_toast(_("Wrong Password!"))

    def _on_delete_fav_list_activated(self, list_id):
        dialog = Adw.MessageDialog(transient_for=self.get_root(), heading=_("Confirm Deletion"),
            body=_("Are you sure you want to delete this favorite list? This action cannot be undone."), modal=True)
        dialog.add_css_class("delete-confirm-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_delete_list_confirm_response, list_id)
        dialog.present()

    def _on_delete_list_confirm_response(self, dialog, response_id, list_id):
        if response_id == "delete":
            database.delete_favorite_list(list_id)
            self.refresh_lists()
            self.emit("favorites-changed")

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

    def _on_fav_list_search_changed(self, entry):
        """Filters the favorite list as the search bar changes."""
        search_text = entry.get_text().lower().strip()
        current_row = self.favorite_lists_listbox.get_first_child()
        while current_row:
            if hasattr(current_row, 'list_name'):
                list_name = getattr(current_row, 'list_name', "")
                row_text = list_name.lower()
                if search_text in row_text:
                    current_row.set_visible(True)
                else:
                    current_row.set_visible(False)
            current_row = current_row.get_next_sibling()

    def _on_move_list_activated(self, action, value):
        """Opens the MoveListDialog when the menu item is clicked."""
        if not self.active_fav_list_row:
            return
        dialog = MoveListDialog(self.get_root(), self.active_fav_list_row, self)
        dialog.present()

    def move_list_up(self, row_to_move):
        """Moves the favorite list row UP."""
        if not row_to_move:
            return False
        current_index = row_to_move.get_index()
        if current_index <= 0:
            return False
        target_index = current_index - 1
        target_row = self.favorite_lists_listbox.get_row_at_index(target_index)
        if not target_row:
            return False
        success = database.swap_favorite_list_order(
            row_to_move.list_id,
            target_row.list_id
        )
        if success:
            self.favorite_lists_listbox.remove(row_to_move)
            self.favorite_lists_listbox.insert(row_to_move, target_index)
            self.favorite_lists_listbox.select_row(row_to_move)
            return True
        return False

    def move_list_down(self, row_to_move):
        """Moves the favorite list row DOWN."""
        if not row_to_move:
            return False
        current_index = row_to_move.get_index()
        target_row = row_to_move.get_next_sibling()
        if not target_row:
            return False
        target_index = current_index + 1
        success = database.swap_favorite_list_order(
            row_to_move.list_id,
            target_row.list_id
        )
        if success:
            self.favorite_lists_listbox.remove(row_to_move)
            self.favorite_lists_listbox.insert(row_to_move, target_index)
            self.favorite_lists_listbox.select_row(row_to_move)
            return True
        return False

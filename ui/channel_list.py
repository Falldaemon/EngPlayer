# ui/channel_list.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, GdkPixbuf, Gio, Gdk, Adw, Pango, GObject
from .placeholder_icon import PlaceholderIcon
from .password_prompt_dialog import PasswordPromptDialog
from .password_dialog import PasswordDialog
from .move_channel_dialog import MoveChannelDialog
import gettext
import re
import unicodedata
import threading
import urllib.request
import logging
import os
import database
from utils.theme_utils import get_icon_theme_folder
from background import image_download_pool
try:
    from thefuzz import fuzz, process
    logging.info("Loaded 'thefuzz' library for smart searching.")
    FUZZ_AVAILABLE = True
except ImportError:
    try:
        from fuzzywuzzy import fuzz, process
        logging.info("Loaded fallback 'fuzzywuzzy' library for smart searching.")
        FUZZ_AVAILABLE = True
    except ImportError:
        logging.warning("Smart search library ('thefuzz' or 'fuzzywuzzy') not found!")
        logging.warning("'Fuzzy' search will be skipped for Logo/EPG/TMDb matching.")
        logging.warning("For better results, install 'python3-thefuzz' (Debian/Ubuntu) or 'python3-fuzzywuzzy' (Fedora) package.")
        fuzz = None
        process = None
        FUZZ_AVAILABLE = False
_ = gettext.gettext

class ChannelList(Gtk.Box):
    __gsignals__ = {
        'pip-requested': (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, **kwargs)
        self.active_list_id = None
        self.search_entry = Gtk.SearchEntry(
            placeholder_text=_("Search channel..."),
            margin_start=6, margin_end=6, margin_top=6, margin_bottom=6
        )
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.append(self.search_entry)
        self.spinner = Gtk.Spinner(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, vexpand=True)
        self.channel_listbox = Gtk.ListBox()
        scrolled_window = Gtk.ScrolledWindow()
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-released", self._on_list_key_released)
        self.channel_listbox.add_controller(key_controller)
        scrolled_window.set_child(self.channel_listbox)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_size_request(300, -1)
        self.view_stack = Gtk.Stack()
        self.view_stack.add_named(scrolled_window, "list")
        self.view_stack.add_named(self.spinner, "loading")
        self.append(self.view_stack)
        self.active_row = None

    def populate_channels_async(self, channels, icon_path=""):
        while (child := self.channel_listbox.get_first_child()):
            self.channel_listbox.remove(child)
        self.view_stack.set_visible_child_name("loading")
        self.spinner.start()
        favorite_urls_set = database.get_all_favorite_channel_urls()
        locked_urls_set = database.get_all_locked_channel_urls()
        logo_map = {}
        main_window = self.get_ancestor(Gtk.Window)
        if main_window and hasattr(main_window, 'logo_map'):
            if isinstance(main_window.logo_map, dict):
                logo_map = main_window.logo_map
                logging.debug(f"ChannelList: Received logo map with {len(logo_map)} entries from main window.")
            else:
                logging.error(f"ChannelList: 'logo_map' found in main window but it is not a dict! Type: {type(main_window.logo_map)}")
        else:
            logging.warning("ChannelList: Logo map (logo_map) could not be retrieved from main window.")
        channel_generator = (channel for channel in channels)
        GLib.idle_add(
            self._populate_chunk,
            channel_generator,
            logo_map,
            favorite_urls_set,
            locked_urls_set
        )

    def _populate_chunk(self, channel_generator, logo_map, favorite_urls, locked_urls):
        chunk_size = 50
        try:
            for _ in range(chunk_size):
                channel = next(channel_generator)
                is_fav = channel["url"] in favorite_urls
                is_locked = channel["url"] in locked_urls
                self._add_row_to_listbox(channel, logo_map, is_fav, is_locked)
            return True
        except StopIteration:
            self.spinner.stop()
            self.view_stack.set_visible_child_name("list")
            logging.info("Incremental population of the channel list is complete.")
            return False
        except Exception as e:
            logging.exception(f"Error in _populate_chunk (ChannelList): {e}")
            return True

    def _add_row_to_listbox(self, channel, logo_map, is_fav, is_locked):
        row = Gtk.ListBoxRow()
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_start(10); hbox.set_margin_end(10)
        row.set_child(hbox)
        placeholder = PlaceholderIcon()
        placeholder.set_size_request(36, 36)
        hbox.append(placeholder)
        logo_to_load = self._find_logo_path(channel, logo_map)
        row.correct_logo_path = logo_to_load
        if logo_to_load and logo_to_load.strip():
            self._load_logo_and_replace(logo_to_load, placeholder)
        label = Gtk.Label(label=channel["name"], xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END); label.set_hexpand(True)
        hbox.append(label)
        theme_folder = get_icon_theme_folder()
        row.fav_icon = Gtk.Image.new_from_file(os.path.join("resources", "icons", theme_folder, "favorite-icon.svg"))
        row.fav_icon.set_pixel_size(16); hbox.append(row.fav_icon)
        row.lock_icon = Gtk.Image.new_from_file(os.path.join("resources", "icons", theme_folder, "lock-icon.svg"))
        row.lock_icon.set_pixel_size(16); hbox.append(row.lock_icon)
        row.fav_icon.set_visible(is_fav)
        row.lock_icon.set_visible(is_locked)
        row.channel_data = channel
        right_click_gesture = Gtk.GestureClick.new(); right_click_gesture.set_button(3)
        right_click_gesture.connect("pressed", self._on_row_right_clicked, row)
        row.add_controller(right_click_gesture)
        self.channel_listbox.append(row)

    def _on_row_right_clicked(self, gesture, n_press, x, y, listbox_row):
        if gesture.get_current_button() == 3:
            self.active_row = listbox_row
            menu_model = self._build_dynamic_menu_for_channel(listbox_row.channel_data)
            popover = Gtk.PopoverMenu.new_from_model(menu_model)
            popover.add_css_class("channel-action-popover")
            popover.set_parent(listbox_row)
            popover.popup()

    def _build_dynamic_menu_for_channel(self, channel_data):
        main_menu = Gio.Menu()
        fav_submenu = Gio.Menu()
        all_lists = database.get_all_favorite_lists()
        url = channel_data["url"]
        action_group = Gio.SimpleActionGroup()
        for list_id, list_name in all_lists:
            if database.is_channel_in_list(url, list_id):
                action_name = f"row.remove_from_list_{list_id}"
                fav_submenu.append(f'{_("Remove from")} "{list_name}"', action_name)
                action = Gio.SimpleAction.new(f"remove_from_list_{list_id}", None)
                action.connect("activate", lambda a, p, l_id=list_id: self._on_remove_from_list_activated(l_id))
            else:
                action_name = f"row.add_to_list_{list_id}"
                fav_submenu.append(f'{_("Add to")} "{list_name}"', action_name)
                action = Gio.SimpleAction.new(f"add_to_list_{list_id}", None)
                action.connect("activate", lambda a, p, l_id=list_id: self._on_add_to_list_activated(l_id))
            action_group.add_action(action)
        fav_submenu.append_section(None, Gio.Menu())
        fav_submenu.append(_("New List..."), "row.create_new_list")
        new_list_action = Gio.SimpleAction.new("create_new_list", None)
        new_list_action.connect("activate", self._on_create_new_list_activated)
        action_group.add_action(new_list_action)
        main_menu.append_submenu(_("Add to Favorites"), fav_submenu)
        is_locked = database.get_channel_lock_status(url)
        lock_label = _("Unlock") if is_locked else _("Lock")
        main_menu.append(lock_label, "row.toggle_lock")
        toggle_lock_action = Gio.SimpleAction.new("toggle_lock", None)
        toggle_lock_action.connect("activate", self._on_toggle_lock_activated)
        action_group.add_action(toggle_lock_action)
        if self.active_list_id is not None:
            main_menu.append_section(None, Gio.Menu())
            main_menu.append(_("Move..."), "row.move_interactive")
            move_action = Gio.SimpleAction.new("move_interactive", None)
            move_action.connect("activate", self._on_move_interactive_activated)
            action_group.add_action(move_action)
        main_menu.append_section(None, Gio.Menu())
        main_menu.append(_("Play as Picture-in-Picture"), "row.play_pip")
        play_pip_action = Gio.SimpleAction.new("play_pip", None)
        play_pip_action.connect("activate", self._on_play_pip_activated)
        action_group.add_action(play_pip_action)
        if self.active_row:
             self.active_row.insert_action_group("row", action_group)
        return main_menu

    def _on_play_pip_activated(self, action, value):
        """Runs when the 'Play as Picture-in-Picture' menu item is selected."""
        if not self.active_row or not self.active_row.channel_data:
            logging.warning("PiP requested but no active row or channel data found.")
            return
        channel_url = self.active_row.channel_data.get("url")
        if channel_url:
            logging.info(f"PiP requested for URL: {channel_url}")
            self.emit("pip-requested", channel_url)
        else:
            logging.warning("PiP requested but channel URL is missing.")

    def _clean_key(self, text):
        """
        Creates a consistent cleaning key for logo map keys and channel names.
        (v2 - Fixed Sorting)
        """
        if not text:
            return None
        name = text.lower().strip()
        try:
            name = unicodedata.normalize("NFKD", name)
            name = "".join([c for c in name if not unicodedata.combining(c)])
        except Exception:
             pass
        name = re.sub(r'(\(.*\))|(\[.*?\])|(".*?")|(\=.*)', ' ', name)
        name = re.sub(r'\b(HD|FHD|UHD|4K|8K|SD)\b', ' ', name, flags=re.IGNORECASE)
        name = re.sub(r'[^\w\d\s]+', ' ', name)
        name = re.sub(
            r'\b(tr|de|us|uk|fr|it|es|ru|br|ar|mx|ca|cn|jp|kr|nl|pl|pt|gr|se|no|dk|fi|in|ir|iq|sa|ae|az|kz|by|ro|bg|hu|cz|sk|si|hr|ch|be|at|ua|lt|lv|ee|rs|ba|me|mk|al)\b',
            ' ', name, flags=re.IGNORECASE
        )
        name = re.sub(r'(\d+)\s*(hd|sd|uhd|fhd|4k|8k)', r'\1', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+', '', name)
        return name.strip().lower()

    def _find_logo_path(self, channel_data, logo_map):
        """
        Performs a 4-step search in the logo map for the given channel data.
        Returns the original 'logo' URL from M3U if not found.
        """
        fallback_logo_url = channel_data.get("logo")
        if not logo_map:
            return fallback_logo_url
        channel_name = channel_data.get("name")
        channel_tvg_id = channel_data.get("tvg-id")
        if channel_tvg_id:
            key_from_tvg_id = self._clean_key(channel_tvg_id)
            if key_from_tvg_id and key_from_tvg_id in logo_map:
                logging.debug(f"Logo Found (Step 1: TVG-ID): '{channel_name}' ({channel_tvg_id}) -> '{key_from_tvg_id}'")
                return logo_map[key_from_tvg_id]
        if channel_name:
            key_from_name = self._clean_key(channel_name)
            if key_from_name and key_from_name in logo_map:
                logging.debug(f"Logo Found (Step 2: Channel Name): '{channel_name}' -> '{key_from_name}'")
                return logo_map[key_from_name]
        if FUZZ_AVAILABLE and channel_name:
            key_from_name_clean = self._clean_key(channel_name)
            if key_from_name_clean:
                best_match, score = process.extractOne(key_from_name_clean, logo_map.keys())
                if score > 90:
                    logging.debug(f"Logo Found (Step 3: Fuzzy %{score}): '{channel_name}' -> '{best_match}'")
                    return logo_map[best_match]
        logging.debug(f"Logo not found (Step 4: Fallback): M3U logo ('{fallback_logo_url}') will be used for '{channel_name}'.")
        return fallback_logo_url

    def _on_add_to_list_activated(self, list_id):
        if not self.active_row: return
        url = self.active_row.channel_data["url"]
        database.add_channel_to_list(url, list_id)
        self.active_row.fav_icon.set_visible(True)
        main_window = self.get_ancestor(Gtk.Window)
        if main_window and hasattr(main_window, 'favorites_view'):
             main_window.favorites_view.emit("favorites-changed")

    def _on_remove_from_list_activated(self, list_id):
        if not self.active_row: return
        row_to_remove = self.active_row
        url = row_to_remove.channel_data["url"]
        database.remove_channel_from_list(url, list_id)
        if self.active_list_id == list_id:
            listbox = row_to_remove.get_parent()
            if listbox:
                listbox.remove(row_to_remove)
        elif not database.is_channel_in_any_favorite(url):
            row_to_remove.fav_icon.set_visible(False)
        main_window = self.get_ancestor(Gtk.Window)
        if main_window and hasattr(main_window, 'favorites_view'):
             main_window.favorites_view.emit("favorites-changed")

    def _on_create_new_list_activated(self, action, value):
        dialog = Adw.MessageDialog.new(self.get_root(), _("New Favorite List"), _("Please enter the name for the new list:"))
        dialog.add_css_class("new-list-dialog")
        entry = Gtk.Entry(); dialog.set_extra_child(entry)
        dialog.add_response("ok", _("Create")); dialog.set_default_response("ok"); dialog.set_close_response("cancel")
        dialog.connect("response", lambda d, res: self._on_new_list_dialog_response(d, res, entry)); dialog.present()

    def _on_new_list_dialog_response(self, dialog, response_id, entry):
        if response_id == "ok":
            list_name = entry.get_text().strip()
            if list_name:
                success = database.create_favorite_list(list_name)
                if success:
                     main_window = self.get_ancestor(Gtk.Window)
                     if main_window and hasattr(main_window, 'favorites_view'):
                         main_window.favorites_view.emit("favorites-changed")

    def _on_toggle_lock_activated(self, action, value):
        if not self.active_row: return
        url = self.active_row.channel_data["url"]
        is_currently_locked = database.get_channel_lock_status(url)
        if is_currently_locked:
            prompt = PasswordPromptDialog(self.get_root())
            prompt.connect("response", self._on_password_prompt_response_for_unlock); prompt.present()
        else:
            password_is_set = database.get_config_value('app_password') is not None
            if password_is_set:
                database.set_channel_lock_status(url, True)
                self.active_row.lock_icon.set_visible(True)
            else:
                self.show_set_password_dialog()

    def _on_password_prompt_response_for_unlock(self, dialog, response_id):
        if response_id == "ok":
            if database.check_password(dialog.get_password()):
                url = self.active_row.channel_data["url"]
                database.set_channel_lock_status(url, False); self.active_row.lock_icon.set_visible(False)
            else:
                self.get_root().show_toast(_("Wrong Password!"))

    def _replace_placeholder_with_image(self, placeholder, pixbuf):
        if not placeholder or not placeholder.get_parent(): return
        parent = placeholder.get_parent()
        image = Gtk.Image.new_from_pixbuf(pixbuf); image.set_pixel_size(36)
        parent.remove(placeholder)
        parent.insert_child_after(image, None)

    def _load_logo_and_replace(self, url, placeholder_widget):
        if not placeholder_widget or not placeholder_widget.get_ancestor(Gtk.ListBoxRow):
             return
        def thread_func():
            pixbuf = None
            try:
                if url.lower().startswith("http"):
                    headers = {"User-Agent": "Mozilla/5.0"}; req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as resp: data = resp.read()
                else:
                    if os.path.exists(url):
                         with open(url, "rb") as f: data = f.read()
                    else: data = None
                if data:
                    loader = GdkPixbuf.PixbufLoader.new(); loader.write(data); loader.close()
                    pixbuf = loader.get_pixbuf()
            except Exception as e:
                 logging.warning(f"Failed to load channel logo '{url}': {e}")
            if pixbuf:
                GLib.idle_add(self._check_and_replace_placeholder, placeholder_widget, pixbuf)
        image_download_pool.submit(thread_func)

    def _check_and_replace_placeholder(self, placeholder, pixbuf):
        if placeholder and placeholder.get_ancestor(Gtk.ListBoxRow):
            parent = placeholder.get_parent()
            if parent:
                image = Gtk.Image.new_from_pixbuf(pixbuf)
                image.add_css_class("channel-logo-image")
                image.set_pixel_size(36)
                parent.remove(placeholder)
                parent.prepend(image)
            else: logging.warning("Main thread (logo): Placeholder has no parent!")
        else: logging.warning("Main thread (logo): Placeholder is not valid, image not replaced.")
        return GLib.SOURCE_REMOVE

    def show_set_password_dialog(self):
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading=_("Password Not Set"),
            body=_("To lock items, you must first set a master password for the application from the settings menu."),
            modal=True)
        dialog.add_css_class("set-password-warning-dialog")
        dialog.add_response("close", _("Close")); dialog.add_response("set-password", _("Set Password")); dialog.set_default_response("set-password")
        dialog.connect("response", self._on_set_password_dialog_response); dialog.present()

    def _on_set_password_dialog_response(self, dialog, response_id):
        if response_id == "set-password":
            password_dialog = PasswordDialog(self.get_root(), self.get_root().toast_overlay)
            password_dialog.present()

    def _on_list_key_released(self, controller, keyval, keycode, state):
        key_name = Gdk.keyval_name(keyval)
        if key_name in ("Up", "Down"):
            GLib.idle_add(self._activate_selected_row)

    def _activate_selected_row(self):
        selected_row = self.channel_listbox.get_selected_row()
        if selected_row:
            self.channel_listbox.emit("row-activated", selected_row)
        return GLib.SOURCE_REMOVE

    def _on_search_changed(self, entry):
        search_text = entry.get_text().lower().strip()
        current_row = self.channel_listbox.get_first_child()
        while current_row:
            if hasattr(current_row, 'channel_data'):
                channel_name = current_row.channel_data.get("name", "")
                row_text = channel_name.lower()
                current_row.set_visible(search_text in row_text)
            current_row = current_row.get_next_sibling()

    def _on_move_interactive_activated(self, action, value):
        """Opens the new dialog when the 'Move...' menu item is selected."""
        if not self.active_row:
            return
        dialog = MoveChannelDialog(self.get_root(), self.active_row, self)
        dialog.present()

    def move_row_up(self, row_to_move):
        """Public method called by the dialog, moves the row ONE UP."""
        if not row_to_move or self.active_list_id is None:
            return
        current_index = row_to_move.get_index()
        if current_index <= 0:
            return
        target_index = current_index - 1
        target_row = self.channel_listbox.get_row_at_index(target_index)
        if not target_row:
            return
        success = database.swap_favorite_channel_order(
            self.active_list_id,
            row_to_move.channel_data["url"],
            target_row.channel_data["url"]
        )
        if success:
            self.channel_listbox.remove(row_to_move)
            self.channel_listbox.insert(row_to_move, target_index)
            self.channel_listbox.select_row(row_to_move)
        return success

    def move_row_down(self, row_to_move):
        """Public method called by the dialog, moves the row ONE DOWN."""
        if not row_to_move or self.active_list_id is None:
            return
        current_index = row_to_move.get_index()
        target_index = current_index + 1
        target_row = self.channel_listbox.get_row_at_index(target_index)
        if not target_row:
            return
        success = database.swap_favorite_channel_order(
            self.active_list_id,
            row_to_move.channel_data["url"],
            target_row.channel_data["url"]
        )
        if success:
            self.channel_listbox.remove(row_to_move)
            self.channel_listbox.insert(row_to_move, target_index)
            self.channel_listbox.select_row(row_to_move)
        return success

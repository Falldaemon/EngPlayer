import logging
from gi.repository import Gtk, Adw
from ui.channel_row import ChannelRow
from ui.password_prompt_dialog import PasswordPromptDialog
import database

import gettext
_ = gettext.gettext

logger = logging.getLogger(__name__)

class FavoritesPanel(Gtk.Box):
    def __init__(self, fav_manager, app_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.fav_manager = fav_manager
        self.app_window = app_window       
        self.selected_channel_url = None
        self.selected_bucket = None
        self._next_open_bucket = None
        self._is_refreshing_ui = False
        self._build_ui()

    def _build_ui(self):
        self.fav_toolbar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)        
        self.add_bucket_btn = Gtk.Button(label=_("+ New Favorite Bucket"))
        self.add_bucket_btn.connect("clicked", self._on_add_bucket_clicked)
        self.fav_toolbar.append(self.add_bucket_btn)
        self.move_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)      
        self.move_up_btn = Gtk.Button()
        self.move_up_btn.set_child(Adw.ButtonContent(icon_name="go-up-symbolic", label=_("Up")))
        self.move_up_btn.set_hexpand(True)
        self.move_up_btn.set_tooltip_text(_("Move Channel Up (Alt+Up)"))
        self.move_up_btn.connect("clicked", lambda b: self.move_selected_channel(-1))
        self.move_toolbar.append(self.move_up_btn)
        self.move_down_btn = Gtk.Button()
        self.move_down_btn.set_child(Adw.ButtonContent(icon_name="go-down-symbolic", label=_("Down")))
        self.move_down_btn.set_hexpand(True)
        self.move_down_btn.set_tooltip_text(_("Move Channel Down (Alt+Down)"))
        self.move_down_btn.connect("clicked", lambda b: self.move_selected_channel(1))
        self.move_toolbar.append(self.move_down_btn)
        self.fav_toolbar.append(self.move_toolbar)
        self.append(self.fav_toolbar)      
        self.fav_list_box = Gtk.ListBox()
        self.fav_list_box.add_css_class("boxed-list")       
        self.fav_list_box.set_selection_mode(Gtk.SelectionMode.NONE)       
        fav_scroll = Gtk.ScrolledWindow(child=self.fav_list_box, vexpand=True)
        bg_click_ctrl = Gtk.GestureClick.new()
        bg_click_ctrl.connect("pressed", self._on_favorites_bg_clicked)
        fav_scroll.add_controller(bg_click_ctrl)
        self.append(fav_scroll)

    def move_selected_channel(self, direction):
        if not self.selected_channel_url or not self.selected_bucket:
            return
        channels = self.fav_manager.favorites.get(self.selected_bucket, [])
        idx = next((i for i, ch in enumerate(channels) if ch.get("url") == self.selected_channel_url), -1)       
        if idx == -1:
            return
        new_idx = idx + direction       
        if 0 <= new_idx < len(channels):
            channels[idx], channels[new_idx] = channels[new_idx], channels[idx]
            self.fav_manager.save()
            logger.info(f"Moved channel {'up' if direction == -1 else 'down'}")
            self.refresh_ui()
            self.update_selection_ui()

    def _on_favorites_bg_clicked(self, gesture, n_press, x, y):
        if getattr(self, "_ignore_bg_click", False):
            self._ignore_bg_click = False
            return
        if self.selected_channel_url is not None:
            self.selected_channel_url = None
            self.selected_bucket = None
            self.update_selection_ui()

    def _on_add_bucket_clicked(self, button):
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading=_("New Favorite Bucket"),
            body=_("Enter a name for the new favorite bucket:")
        )
        dialog.add_css_class("new-bucket-dialog")
        dialog.add_css_class("new-bucket-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("add", _("Add"))
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        entry = Gtk.Entry()
        entry.set_margin_top(10)
        dialog.set_extra_child(entry)
        dialog.connect("response", self._on_add_bucket_response, entry)
        dialog.present()

    def _on_add_bucket_response(self, dialog, response, entry):
        if response == "add":
            name = entry.get_text()
            if name:
                logger.info(f"Creating new bucket: {name}")
                self.fav_manager.add_bucket(name)
                self._next_open_bucket = name 
                self.refresh_ui()

    def _on_right_expander_changed(self, expander, param):
        if self._is_refreshing_ui:
            return 
        if expander.get_expanded():
            row = self.fav_list_box.get_first_child()
            while row is not None:
                other_expander = row.get_child()
                if isinstance(other_expander, Gtk.Expander) and other_expander != expander:
                    other_expander.set_expanded(False)
                row = row.get_next_sibling()
        self.app_window.refresh_left_checkboxes()

    def get_active_bucket(self):
        row = self.fav_list_box.get_first_child()
        while row is not None:
            expander = row.get_child()
            if isinstance(expander, Gtk.Expander) and expander.get_expanded():
                if hasattr(expander, 'bucket_name'):
                    return expander.bucket_name
            row = row.get_next_sibling()
        return None

    def update_selection_ui(self):
        row = self.fav_list_box.get_first_child()
        while row is not None:
            expander = row.get_child()
            if isinstance(expander, Gtk.Expander):
                inner_box = expander.get_child()
                if inner_box:
                    child = inner_box.get_first_child()
                    while child is not None:
                        if isinstance(child, ChannelRow):
                            is_sel = (child.data.get("url") == self.selected_channel_url and child.bucket_name == self.selected_bucket)
                            child.set_selected(is_sel)
                        child = child.get_next_sibling()
            row = row.get_next_sibling()

    def _on_channel_selected(self, url, bucket_name):
        self._ignore_bg_click = True
        self.selected_channel_url = url
        self.selected_bucket = bucket_name
        self.update_selection_ui()

    def refresh_ui(self):
        self._is_refreshing_ui = True 
        expanded_folders = []
        if self._next_open_bucket:
            expanded_folders.append(self._next_open_bucket)
            self._next_open_bucket = None
        else:
            row = self.fav_list_box.get_first_child()
            while row is not None:
                expander = row.get_child()
                if isinstance(expander, Gtk.Expander) and expander.get_expanded():
                    if hasattr(expander, 'bucket_name'):
                        expanded_folders.append(expander.bucket_name)
                row = row.get_next_sibling()
        while self.fav_list_box.get_first_child():
            self.fav_list_box.remove(self.fav_list_box.get_first_child())          
        for bucket_name, channels in self.fav_manager.favorites.items():
            if bucket_name == "Default":
                continue             
            expander = Gtk.Expander()
            expander.bucket_name = bucket_name 
            expander.connect("notify::expanded", self._on_right_expander_changed)
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)           
            label_text = f"📁 {bucket_name}"
            header_label = Gtk.Label(label=label_text, hexpand=True, xalign=0)
            header_box.append(header_label)
            list_id = self._get_list_id_by_name(bucket_name)
            is_locked = False
            if list_id is not None:
                is_locked = database.get_favorite_list_lock_status(list_id)              
            lock_icon_name = "changes-prevent-symbolic" if is_locked else "changes-allow-symbolic"          
            lock_btn = Gtk.Button(icon_name=lock_icon_name)
            lock_btn.add_css_class("flat")
            lock_btn.set_tooltip_text(_("Unlock") if is_locked else _("Lock"))
            lock_btn.connect("clicked", self._on_lock_bucket_clicked, bucket_name, is_locked, list_id)
            header_box.append(lock_btn)
            delete_btn = Gtk.Button(icon_name="user-trash-symbolic")
            delete_btn.add_css_class("flat")
            delete_btn.add_css_class("error")
            delete_btn.set_tooltip_text(_("Delete List"))
            delete_btn.connect("clicked", self._on_delete_bucket_clicked, bucket_name)
            header_box.append(delete_btn)           
            expander.set_label_widget(header_box)            
            if bucket_name in expanded_folders:
                expander.set_expanded(True)               
            inner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)           
            for ch in channels:
                is_this_channel_selected = (ch.get("url") == self.selected_channel_url and bucket_name == self.selected_bucket)               
                row_widget = ChannelRow(
                    channel_data=ch, 
                    is_checked=True, 
                    buckets_text="", 
                    on_toggled_cb=lambda cd, ic, bn=bucket_name: self.app_window._on_right_channel_toggled(cd, ic, bn),
                    is_selectable=True, 
                    bucket_name=bucket_name,
                    on_select_cb=self._on_channel_selected,
                    on_edit_cb=self.app_window._on_edit_channel_clicked
                )           
                row_widget.set_selected(is_this_channel_selected)
                inner_box.append(row_widget)               
            expander.set_child(inner_box)
            self.fav_list_box.append(expander)          
        self._is_refreshing_ui = False
        
    def _on_delete_bucket_clicked(self, button, bucket_name):
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading=_("Confirm Deletion"),
            body=_("Are you sure you want to delete this favorite list? This action cannot be undone.")
        )
        dialog.add_css_class("delete-confirm-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(d, response_id):
            if response_id == "delete":
                if bucket_name in self.fav_manager.favorites:
                    del self.fav_manager.favorites[bucket_name]
                    if self.selected_bucket == bucket_name:
                        self.selected_bucket = None
                        self.selected_channel_url = None
                    self.fav_manager.save()
                    self.app_window.refresh_left_checkboxes() 
                    self.refresh_ui()
        dialog.connect("response", on_response)
        dialog.present()   
        
    def _on_lock_bucket_clicked(self, button, bucket_name, is_locked, list_id):
        if list_id is None:
            self.app_window.get_root().show_toast(_("Please click 'Save Changes' to save this folder to the database before locking it."))
            return
        password_is_set = database.get_config_value('app_password') is not None
        if not password_is_set:
            dialog = Adw.MessageDialog(
                transient_for=self.app_window.get_root(),
                heading=_("Password Not Set"),
                body=_("To lock items, you must first set a master password for the application from the settings menu."),
                modal=True
            )
            dialog.add_css_class("set-password-warning-dialog")
            dialog.add_response("close", _("Close"))
            dialog.add_response("set-password", _("Set Password"))
            dialog.set_default_response("set-password")
            
            def on_set_pass_response(d, response_id):
                if response_id == "set-password":
                    from ui.password_dialog import PasswordDialog
                    toast_overlay = getattr(self.app_window.get_root(), 'toast_overlay', None)
                    password_dialog = PasswordDialog(self.app_window.get_root(), toast_overlay)
                    password_dialog.present()                   
            dialog.connect("response", on_set_pass_response)
            dialog.present()
            return
        if is_locked:
            from ui.password_prompt_dialog import PasswordPromptDialog
            prompt = PasswordPromptDialog(self.app_window.get_root())
            
            def on_password_response(dialog, response_id):
                if response_id == "ok":
                    if database.check_password(dialog.get_password()):
                        database.set_favorite_list_lock_status(list_id, False)
                        self.refresh_ui()
                    else:
                        self.app_window.get_root().show_toast(_("Wrong Password!"))         
            prompt.connect("response", on_password_response)
            prompt.present()
        else:
            database.set_favorite_list_lock_status(list_id, True)
            self.refresh_ui() 
            
    def _get_list_id_by_name(self, bucket_name):
        all_lists = database.get_all_favorite_lists()
        for list_id, list_name in all_lists:
            if list_name == bucket_name:
                return list_id
        return None                     

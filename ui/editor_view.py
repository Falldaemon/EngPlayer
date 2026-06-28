import logging
import threading
import json
import os
import sys
import database
from gi.repository import Gtk, Adw, Pango, Gdk, GLib, GObject

import gettext
_ = gettext.gettext

from data_providers.playlist_parser import PlaylistParser
from data_providers.favorites import FavoritesManager
from ui.channel_row import ChannelRow
from ui.favorites_panel import FavoritesPanel
from ui.channel_editor import ChannelEditor

logger = logging.getLogger(__name__)

class EditorView(Gtk.Box):
    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, hexpand=True, vexpand=True, **kwargs)       
        self._setup_custom_css()       
        self.fav_manager = FavoritesManager()
        self.all_channels = [] 
        self.original_grouped = {} 
        self.current_sort_state = 0 
        self.url_to_buckets = {} 
        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)
        self.toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.toolbar.set_margin_top(8)
        self.toolbar.set_margin_bottom(8)
        self.toolbar.set_margin_start(12)
        self.toolbar.set_margin_end(12)
        self.append(self.toolbar)
        self.main_save_btn = Gtk.Button()
        self.main_save_btn.set_child(Adw.ButtonContent(icon_name="document-save-symbolic", label=_("Save Changes")))
        self.main_save_btn.set_tooltip_text(_("Save modifications to database"))
        self.main_save_btn.add_css_class("suggested-action")
        self.main_save_btn.connect("clicked", self._on_main_save_clicked)
        self.toolbar.append(self.main_save_btn)
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.set_position(420)
        self.paned.set_vexpand(True) 
        self.append(self.paned)
        self.left_stack = Gtk.Stack()
        self.left_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.left_stack.set_transition_duration(250)
        self.paned.set_start_child(self.left_stack)
        self.loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.loading_box.set_valign(Gtk.Align.CENTER)
        self.loading_box.set_halign(Gtk.Align.CENTER)        
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(40, 40)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(200, -1)
        self.progress_bar.set_show_text(True) 
        self.loading_box.append(self.spinner)
        self.loading_box.append(self.progress_bar)      
        self.left_stack.add_named(self.loading_box, "loading")      
        self.empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.empty_box.set_valign(Gtk.Align.CENTER)
        self.empty_box.set_halign(Gtk.Align.CENTER)
        empty_icon = Gtk.Image(icon_name="document-open-symbolic")
        empty_icon.set_pixel_size(64)
        empty_icon.add_css_class("dim-label")
        empty_label = Gtk.Label(label=_("Please import an M3U file to start."))
        empty_label.add_css_class("dim-label")
        self.empty_box.append(empty_icon)
        self.empty_box.append(empty_label)
        self.left_stack.add_named(self.empty_box, "empty")
        self.bouquet_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.bouquet_view.set_margin_start(10); self.bouquet_view.set_margin_end(0)
        self.bouquet_view.set_margin_top(10); self.bouquet_view.set_margin_bottom(10)
        self.bouquet_search_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.bouquet_search_toolbar.set_margin_end(10)      
        self.bouquet_search_entry = Gtk.SearchEntry(placeholder_text=_("Search categories..."))
        self.bouquet_search_entry.set_hexpand(True)
        self.bouquet_search_entry.connect("search-changed", self._on_bouquet_search_changed)
        self.bouquet_search_toolbar.append(self.bouquet_search_entry)      
        self.sort_btn = Gtk.Button(icon_name="view-list-symbolic")
        self.sort_btn.add_css_class("flat")
        self.sort_btn.set_tooltip_text(_("Sort Categories"))
        self.sort_btn.connect("clicked", self._on_sort_btn_clicked)
        self.bouquet_search_toolbar.append(self.sort_btn)       
        self.bouquet_view.append(self.bouquet_search_toolbar)
        self.sort_popover = Gtk.Popover()
        self.sort_popover.set_parent(self.sort_btn)
        sort_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        sort_vbox.set_margin_start(10); sort_vbox.set_margin_end(10)
        sort_vbox.set_margin_top(10); sort_vbox.set_margin_bottom(10)
        lbl_sort = Gtk.Label(label=_("Sort By:"))
        lbl_sort.add_css_class("dim-label")
        sort_vbox.append(lbl_sort)
        btn_default = Gtk.Button(label=_("Default Order"))
        btn_default.add_css_class("flat")
        btn_default.connect("clicked", self._apply_sort, 0)
        sort_vbox.append(btn_default)
        btn_az = Gtk.Button(label=_("A-Z (Ascending)"))
        btn_az.add_css_class("flat")
        btn_az.connect("clicked", self._apply_sort, 1)
        sort_vbox.append(btn_az)
        btn_za = Gtk.Button(label=_("Z-A (Descending)"))
        btn_za.add_css_class("flat")
        btn_za.connect("clicked", self._apply_sort, 2)
        sort_vbox.append(btn_za)
        self.sort_popover.set_child(sort_vbox)
        self.bouquet_list_box = Gtk.ListBox()
        self.bouquet_list_box.add_css_class("boxed-list")
        self.bouquet_list_box.set_margin_end(15)
        self.bouquet_list_box.connect("row-activated", self._on_bouquet_row_activated)     
        self.bouquet_scroll = Gtk.ScrolledWindow(child=self.bouquet_list_box, vexpand=True)
        self.bouquet_view.append(self.bouquet_scroll)
        self.left_stack.add_named(self.bouquet_view, "bouquets")
        self.channel_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.channel_view.set_margin_start(10); self.channel_view.set_margin_end(0)
        self.channel_view.set_margin_top(10); self.channel_view.set_margin_bottom(10)
        channel_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        channel_header_box.set_margin_end(10)     
        back_to_bouquets_btn = Gtk.Button(icon_name="go-previous-symbolic")
        back_to_bouquets_btn.add_css_class("flat")
        back_to_bouquets_btn.set_tooltip_text(_("Back to Categories"))
        back_to_bouquets_btn.connect("clicked", self._on_back_to_bouquets_clicked)
        channel_header_box.append(back_to_bouquets_btn)      
        self.channel_header_label = Gtk.Label(label="", hexpand=True, xalign=0)
        self.channel_header_label.add_css_class("title-4")
        self.channel_header_label.set_ellipsize(Pango.EllipsizeMode.END)
        channel_header_box.append(self.channel_header_label)
        self.channel_view.append(channel_header_box)
        self.channel_search_entry = Gtk.SearchEntry(placeholder_text=_("Search channels..."))
        self.channel_search_entry.set_margin_end(10)
        self.channel_search_entry.connect("search-changed", self._on_channel_search_changed)
        self.channel_view.append(self.channel_search_entry)      
        self.channel_list_box = Gtk.ListBox()
        self.channel_list_box.add_css_class("boxed-list")
        self.channel_list_box.set_margin_end(15)      
        self.channel_scroll = Gtk.ScrolledWindow(child=self.channel_list_box, vexpand=True)
        self.channel_view.append(self.channel_scroll)
        self.left_stack.add_named(self.channel_view, "channels")
        self.left_stack.set_visible_child_name("empty")
        self.right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.right_box.set_margin_start(10); self.right_box.set_margin_end(10)
        self.right_box.set_margin_top(10); self.right_box.set_margin_bottom(10)
        self.right_stack = Gtk.Stack()
        self.right_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.right_stack.set_transition_duration(300)
        self.favorites_panel = FavoritesPanel(self.fav_manager, self)
        self.right_stack.add_named(self.favorites_panel, "favorites")
        self.channel_editor = ChannelEditor(
            on_back_cb=self._on_editor_back_clicked,
            on_save_cb=self._on_editor_save_clicked,
            on_delete_cb=self._on_editor_delete_clicked
        )
        self.right_stack.add_named(self.channel_editor, "editor")
        self.right_box.append(self.right_stack)
        self.paned.set_end_child(self.right_box)
        self.favorites_panel.refresh_ui()

    def load_active_profile_data(self, bouquets_data):
        if not bouquets_data:
            return
        self.left_stack.set_visible_child_name("loading")
        self.spinner.start()
        self.progress_bar.set_fraction(0.5)
        self.progress_bar.set_text(_("Loading channels from active profile..."))
        if database.CURRENT_PROFILE_DB_FILE:
            self.fav_manager.load_for_m3u(database.CURRENT_PROFILE_DB_FILE)
        hidden_bouquets = database.get_hidden_bouquets()
        self.all_channels = []
        self.original_grouped = {}
        while self.bouquet_list_box.get_first_child():
            self.bouquet_list_box.remove(self.bouquet_list_box.get_first_child())
        while self.channel_list_box.get_first_child():
            self.channel_list_box.remove(self.channel_list_box.get_first_child())
        for bouquet_name, channels in bouquets_data.items():
            if bouquet_name.startswith("⭐") or bouquet_name in hidden_bouquets:
                continue               
            self.original_grouped[bouquet_name] = []
            for ch in channels:
                editor_channel = {
                    "name": ch.get("name", "Unknown"),
                    "group": bouquet_name,
                    "url": ch.get("url", ""),
                    "logo": ch.get("logo", ""),
                    "stream_id": ch.get("stream_id", ""),
                    "tvg-id": ch.get("tvg-id", ""),     
                    "tvg-logo": ch.get("tvg-logo", "")  
                }
                self.original_grouped[bouquet_name].append(editor_channel)
                self.all_channels.append(editor_channel)
        db_lists = database.get_all_favorite_lists()
        if db_lists:
            url_to_channel_map = {ch["url"]: ch for ch in self.all_channels if ch.get("url")}
            has_new_import = False
            for list_id, list_name in db_lists:
                if list_name not in self.fav_manager.favorites:
                    self.fav_manager.favorites[list_name] = []
                db_channel_urls = database.get_channels_in_list(list_id)
                for url in db_channel_urls:
                    already_in_editor = any(e_ch.get("url") == url for e_ch in self.fav_manager.favorites[list_name])
                    if not already_in_editor and url in url_to_channel_map:
                        self.fav_manager.favorites[list_name].append(url_to_channel_map[url])
                        has_new_import = True
            if has_new_import:
                self.fav_manager.save()
        self._build_bouquet_list(self.all_channels, self.original_grouped, True)
        self.favorites_panel.refresh_ui()
        self.spinner.stop()
        self.left_stack.set_visible_child_name("bouquets")

    def _setup_custom_css(self):
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
        .channel-selected {
            background-color: alpha(@accent_bg_color, 0.25);
            border-radius: 6px;
        }
        .badge-pill {
            background-color: alpha(@accent_color, 0.15);
            color: @accent_color;
            border: 1px solid alpha(@accent_color, 0.3);
            border-radius: 12px;
            padding: 4px 12px;
            font-weight: bold;
            font-size: 0.9em;
        }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), 
            css_provider, 
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if state & Gdk.ModifierType.ALT_MASK:
            if keyval == Gdk.KEY_Up:
                self.favorites_panel.move_selected_channel(-1)
                return True
            elif keyval == Gdk.KEY_Down:
                self.favorites_panel.move_selected_channel(1)
                return True
        return False

    def _on_edit_channel_clicked(self, channel_data, bucket_name):
        channel_url = channel_data.get("url")
        self._rebuild_url_map()
        in_buckets = self.url_to_buckets.get(channel_url, [])
        if not in_buckets and bucket_name:
            in_buckets = [bucket_name]
        self.channel_editor.set_channel(channel_data, bucket_name, in_buckets)
        self.favorites_panel.selected_channel_url = channel_url
        self.favorites_panel.selected_bucket = bucket_name
        self.favorites_panel.update_selection_ui()
        self.right_stack.set_visible_child_name("editor")

    def _on_editor_back_clicked(self):
        self.right_stack.set_visible_child_name("favorites")

    def _on_editor_save_clicked(self, channel_data, bucket_name, new_name, new_url, new_logo, new_epg, is_locked, is_hidden):
        logger.info(f"Save triggered for channel: {new_name}")
        old_url = channel_data.get("url")
        for ch in self.all_channels:
            if ch.get("url") == old_url:
                ch["name"] = new_name
                ch["url"] = new_url
                ch["logo"] = new_logo
                ch["tvg-logo"] = new_logo
                ch["tvg-id"] = new_epg
                ch["stream_id"] = new_epg
                break       
        for group, ch_list in self.original_grouped.items():
            for ch in ch_list:
                if ch.get("url") == old_url:
                    ch["name"] = new_name
                    ch["url"] = new_url
                    ch["logo"] = new_logo
                    ch["tvg-logo"] = new_logo
                    ch["tvg-id"] = new_epg
                    ch["stream_id"] = new_epg
                    break
        if bucket_name and bucket_name in self.fav_manager.favorites:
            for b_name, channels in self.fav_manager.favorites.items():
                for ch in channels:
                    if ch.get("url") == old_url:
                        ch["name"] = new_name
                        ch["url"] = new_url
                        ch["logo"] = new_logo
                        ch["tvg-logo"] = new_logo
                        ch["tvg-id"] = new_epg
                        ch["stream_id"] = new_epg
            self.fav_manager.save()
        database.set_channel_lock_status(new_url, is_locked)
        database.set_channel_hidden_status(new_url, is_hidden)
        database.save_custom_channel_edit(new_url, new_name, bucket_name or channel_data.get("group"), new_logo, new_epg)
        self._update_channel_row_names(self.channel_list_box, old_url, new_name, is_hidden, is_locked)
        self.favorites_panel.refresh_ui() 
        self._rebuild_url_map()
        self.right_stack.set_visible_child_name("favorites")

    def _on_editor_delete_clicked(self, channel_data, bucket_name):
        if bucket_name and bucket_name in self.fav_manager.favorites:
            self.fav_manager.favorites[bucket_name] = [
                ch for ch in self.fav_manager.favorites[bucket_name] 
                if ch.get("url") != channel_data.get("url")
            ]
            self.fav_manager.save()
            self.refresh_left_checkboxes()
            self.favorites_panel.refresh_ui()
        self.right_stack.set_visible_child_name("favorites")

    def _update_progress(self, text, fraction):
        if text:
            self.progress_bar.set_text(f"{text} (%{int(fraction * 100)})")
        self.progress_bar.set_fraction(fraction)

    def _rebuild_url_map(self):
        self.url_to_buckets.clear()
        for b_name, channels in self.fav_manager.favorites.items():
            if b_name == "Default":
                continue
            for ch in channels:
                url = ch.get("url")
                if url:
                    if url not in self.url_to_buckets:
                        self.url_to_buckets[url] = []
                    if b_name not in self.url_to_buckets[url]:
                        self.url_to_buckets[url].append(b_name)

    def _update_checkboxes_in_list(self, container, fav_urls):
        current = container.get_first_child()
        while current is not None:
            widget = current.get_child() if isinstance(current, Gtk.ListBoxRow) else current
            if isinstance(widget, ChannelRow):
                url = widget.data.get("url")
                is_in = url in fav_urls
                b_list = self.url_to_buckets.get(url, [])
                b_text = f"[{', '.join(b_list)}]" if b_list else ""
                widget.update_state(is_in, b_text)
            current = current.get_next_sibling()
            
    def _update_channel_row_names(self, container, url, new_name, is_hidden=None, is_locked=None):
        current = container.get_first_child()
        while current is not None:
            widget = current.get_child() if isinstance(current, Gtk.ListBoxRow) else current
            if isinstance(widget, ChannelRow):
                if widget.data.get("url") == url:
                    widget.update_channel_info(new_name)
                    if hasattr(widget, 'update_editor_icons'):
                        widget.update_editor_icons(is_hidden, is_locked)
            current = current.get_next_sibling()          

    def refresh_left_checkboxes(self):
        self._rebuild_url_map()
        active_bucket = self.favorites_panel.get_active_bucket()
        fav_urls = set()
        if active_bucket:
            fav_urls = {ch.get("url") for ch in self.fav_manager.favorites.get(active_bucket, []) if ch.get("url")}
        self._update_checkboxes_in_list(self.channel_list_box, fav_urls)

    def _on_left_channel_toggled(self, channel_data, is_checked):
        active_bucket = self.favorites_panel.get_active_bucket()
        if not active_bucket:
            logger.warning("No bucket is currently opened/selected!")
            return           
        if is_checked:
            self.fav_manager.add_to_bucket(active_bucket, channel_data)
        else:
            self.fav_manager.favorites[active_bucket] = [
                ch for ch in self.fav_manager.favorites[active_bucket] 
                if ch.get("url") != channel_data.get("url")
            ]
            self.fav_manager.save()         
        self.favorites_panel.refresh_ui()
        self.refresh_left_checkboxes() 

    def _on_right_channel_toggled(self, channel_data, is_checked, bucket_name):
        if not is_checked:
            self.fav_manager.favorites[bucket_name] = [
                ch for ch in self.fav_manager.favorites[bucket_name] 
                if ch.get("url") != channel_data.get("url")
            ]
            self.fav_manager.save()
            self.favorites_panel.refresh_ui()
            self.refresh_left_checkboxes()

    def _on_export_clicked(self, button):
        dialog = Gtk.FileChooserNative(
            title=_("Export M3U"),
            action=Gtk.FileChooserAction.SAVE,
            accept_label=_("Save"),
            cancel_label=_("Cancel")
        )
        dialog.set_current_name("favorites.m3u")
        dialog.connect("response", self._on_export_response)
        dialog.show()

    def _on_export_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            file_path = file.get_path()
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("#EXTM3U\n")
                    for bucket_name, channels in self.fav_manager.favorites.items():
                        if bucket_name == "Default" or not channels:
                            continue
                        for ch in channels:
                            name = ch.get("name", _("Unknown"))
                            url = ch.get("url", "")
                            f.write(f'#EXTINF:-1 group-title="{bucket_name}",{name}\n')
                            f.write(f"{url}\n")
                logger.info(f"Successfully exported to {file_path}")
                msg = Adw.MessageDialog(transient_for=self, heading=_("Export Successful"), body=_("Your favorites have been successfully exported to the M3U file."))
                msg.add_response("ok", _("OK"))
                msg.present()
            except Exception as e:
                logger.error(f"Failed to export M3U: {e}")
                msg = Adw.MessageDialog(transient_for=self, heading=_("Export Error"), body=f"Error details: {e}")
                msg.add_response("ok", _("OK"))
                msg.present()
        dialog.destroy()
        
    def _on_main_save_clicked(self, button):
        try:
            self.fav_manager.save()
            if hasattr(self.fav_manager, 'favorites'):
                fav_data = self.fav_manager.favorites
            else:
                fav_data = self.fav_manager.load_for_m3u(database.CURRENT_PROFILE_DB_FILE)             
            database.save_editor_favorites_to_db(fav_data)           
            logger.info("All changes and favorites saved to database.")
            msg = Adw.MessageDialog(
                transient_for=self.get_root(), 
                heading=_("Restart Required"), 
                body=_("Your playlist edits and favorites have been successfully saved. The application needs to restart to apply them.")
            )
            msg.add_css_class("editor-save-dialog")          
            msg.add_response("restart", _("Restart Now"))
            msg.set_response_appearance("restart", Adw.ResponseAppearance.SUGGESTED)
            msg.connect("response", self._on_restart_response)
            msg.present()           
        except Exception as e:
            logger.error(f"Failed to save changes: {e}")
            msg = Adw.MessageDialog(
                transient_for=self.get_root(), 
                heading=_("Save Error"), 
                body=f"An error occurred while saving: {e}"
            )
            msg.add_css_class("editor-save-dialog")
            msg.add_response("ok", _("OK"))
            msg.present()       

    def _on_restart_response(self, dialog, response_id):
        if response_id == "restart":
            if hasattr(self.get_root(), "restart_app"):
                self.get_root().restart_app()
            else:
                os.execl(sys.executable, sys.executable, *sys.argv)     

    def _on_open_file_clicked(self, button):
        dialog = Gtk.FileChooserNative(action=Gtk.FileChooserAction.OPEN)
        dialog.connect("response", self._on_file_response)
        dialog.show()

    def _on_file_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            file_path = file.get_path()
            self._open_m3u_file(file_path)
        dialog.destroy()
        
    def _open_m3u_file(self, file_path):
        logger.info(f"Loading M3U file: {file_path}")     
        self.left_stack.set_visible_child_name("loading")      
        while self.bouquet_list_box.get_first_child(): 
            self.bouquet_list_box.remove(self.bouquet_list_box.get_first_child())
        while self.channel_list_box.get_first_child():
            self.channel_list_box.remove(self.channel_list_box.get_first_child())          
        self.all_channels.clear()
        self.original_grouped.clear()
        self.bouquet_search_entry.set_text("")
        self.channel_search_entry.set_text("")
        self.favorites_panel.selected_channel_url = None
        self.favorites_panel.selected_bucket = None      
        self.fav_manager.load_for_m3u(file_path)
        self.favorites_panel.refresh_ui()      
        self.spinner.start()
        self.progress_bar.set_fraction(0.1)
        self.progress_bar.set_text(_("Reading file..."))     
        threading.Thread(target=self._parse_file_thread, args=(file_path,), daemon=True).start()
       
    def _parse_file_thread(self, file_path):
        GLib.idle_add(self._update_progress, _("Parsing channels..."), 0.4)
        parser = PlaylistParser()
        channels = parser.parse_m3u(file_path)       
        GLib.idle_add(self._update_progress, _("Organizing categories..."), 0.8)
        grouped = {}
        for ch in channels:
            group = ch.get("group", _("Uncategorized"))
            if group not in grouped: 
                grouped[group] = []
            grouped[group].append(ch)         
        GLib.idle_add(self._build_bouquet_list, channels, grouped, True)

    def _build_bouquet_list(self, all_channels, grouped, is_initial_load=False):
        if is_initial_load:
            self.all_channels = all_channels
            self.original_grouped = grouped
            self.current_sort_state = 0
            self.sort_btn.set_icon_name("view-list-symbolic")
            self._update_progress(_("Building interface..."), 0.9)
        for group in grouped.keys():
            row = Gtk.ListBoxRow()           
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_start(10); box.set_margin_end(10)
            box.set_margin_top(12); box.set_margin_bottom(12)          
            icon = Gtk.Image(icon_name="folder-symbolic")
            icon.add_css_class("dim-label")
            box.append(icon)          
            lbl = Gtk.Label(label=group, xalign=0, hexpand=True)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            box.append(lbl)         
            arrow = Gtk.Image(icon_name="go-next-symbolic")
            arrow.add_css_class("dim-label")
            box.append(arrow)          
            row.set_child(box)
            row.group_name = group
            self.bouquet_list_box.append(row)           
        if is_initial_load:
            self.spinner.stop()
            self.left_stack.set_visible_child_name("bouquets")
            self.progress_bar.set_fraction(1.0)
            logger.info(f"Successfully loaded {len(all_channels)} channels into the new stack architecture.")

    def _on_bouquet_row_activated(self, listbox, row):
        if not row: return
        group_name = getattr(row, "group_name", "")       
        self.channel_header_label.set_text(group_name)
        self.channel_search_entry.set_text("")       
        while self.channel_list_box.get_first_child():
            self.channel_list_box.remove(self.channel_list_box.get_first_child())           
        channels = self.original_grouped.get(group_name, [])
        active_bucket = self.favorites_panel.get_active_bucket()
        fav_urls = {ch.get("url") for ch in self.fav_manager.favorites.get(active_bucket, []) if ch.get("url")} if active_bucket else set()
        self._rebuild_url_map()       
        for ch in channels:
            url = ch.get("url")
            is_checked = url in fav_urls
            b_list = self.url_to_buckets.get(url, [])
            b_text = f"[{', '.join(b_list)}]" if b_list else ""          
            ch_row = ChannelRow(
                channel_data=ch, 
                is_checked=is_checked, 
                buckets_text=b_text, 
                on_toggled_cb=self._on_left_channel_toggled,
                on_edit_cb=self._on_edit_channel_clicked
            )
            self.channel_list_box.append(ch_row)           
        self.left_stack.set_visible_child_name("channels")

    def _on_back_to_bouquets_clicked(self, btn):
        self.channel_search_entry.set_text("")
        self.left_stack.set_visible_child_name("bouquets")

    def _on_sort_btn_clicked(self, button):
        self.sort_popover.popup()

    def _apply_sort(self, button, sort_state):
        self.sort_popover.popdown()
        if not self.original_grouped:
            return
        self.current_sort_state = sort_state
        sorted_grouped = {}
        if sort_state == 1:
            self.sort_btn.set_icon_name("view-sort-ascending-symbolic")
            sorted_keys = sorted(self.original_grouped.keys(), key=lambda x: x.lower())
            for k in sorted_keys:
                sorted_grouped[k] = sorted(self.original_grouped[k], key=lambda x: x.get("name", "").lower())
        elif sort_state == 2:
            self.sort_btn.set_icon_name("view-sort-descending-symbolic") 
            sorted_keys = sorted(self.original_grouped.keys(), key=lambda x: x.lower(), reverse=True)
            for k in sorted_keys:
                sorted_grouped[k] = sorted(self.original_grouped[k], key=lambda x: x.get("name", "").lower(), reverse=True)
        else:
            self.sort_btn.set_icon_name("view-list-symbolic")
            sorted_grouped = self.original_grouped           
        while self.bouquet_list_box.get_first_child():
            self.bouquet_list_box.remove(self.bouquet_list_box.get_first_child())          
        self._build_bouquet_list(self.all_channels, sorted_grouped, is_initial_load=False)
        self.left_stack.set_visible_child_name("bouquets")

    def _on_bouquet_search_changed(self, entry):
        if getattr(self, '_bouquet_search_timer_id', None) is not None:
            GLib.source_remove(self._bouquet_search_timer_id)
        search_text = entry.get_text().lower().strip()
        self._bouquet_search_timer_id = GLib.timeout_add(200, self._perform_bouquet_search, search_text)

    def _perform_bouquet_search(self, search_text):
        self._bouquet_search_timer_id = None
        row = self.bouquet_list_box.get_first_child()
        while row is not None:
            if hasattr(row, 'group_name'):
                if search_text in row.group_name.lower():
                    row.set_visible(True)
                else:
                    row.set_visible(False)
            row = row.get_next_sibling()
        return GLib.SOURCE_REMOVE

    def _on_channel_search_changed(self, entry):
        if getattr(self, '_channel_search_timer_id', None) is not None:
            GLib.source_remove(self._channel_search_timer_id)
        search_text = entry.get_text().lower().strip()
        self._channel_search_timer_id = GLib.timeout_add(200, self._perform_channel_search, search_text)

    def _perform_channel_search(self, search_text):
        self._channel_search_timer_id = None
        row = self.channel_list_box.get_first_child()
        while row is not None:
            widget = row.get_child() if isinstance(row, Gtk.ListBoxRow) else row
            if isinstance(widget, ChannelRow):
                ch_name = widget.data.get("name", "").lower()
                if search_text in ch_name:
                    row.set_visible(True)
                else:
                    row.set_visible(False)
            row = row.get_next_sibling()
        return GLib.SOURCE_REMOVE
        
    def reset_state(self):
        if hasattr(self, 'all_channels') and self.all_channels:
            self.left_stack.set_visible_child_name("bouquets")
        else:
            self.left_stack.set_visible_child_name("empty")
        self.right_stack.set_visible_child_name("favorites")
        self.bouquet_search_entry.set_text("")
        self.channel_search_entry.set_text("")
        self.favorites_panel.selected_channel_url = None
        self.favorites_panel.selected_bucket = None
        self.channel_header_label.set_text("")        

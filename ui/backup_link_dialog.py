# ui/backup_link_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import gettext
import logging
import threading
import database
from utils.profile_manager import load_profiles
from data_providers import xtream_client
from data_providers.m3u_provider import parse_m3u_content

_ = gettext.gettext

class BackupLinkDialog(Adw.MessageDialog):
    def __init__(self, main_window, current_channel_data):
        super().__init__()
        self.set_transient_for(main_window)
        self.main_window = main_window
        self.current_channel_data = current_channel_data
        self.channel_name = current_channel_data.get("name", _("Channel"))
        self.grouped_channels = {}
        self.selected_profile = None
        self.current_bouquet_name = None
        self.add_css_class("backup-link-dialog")
        self.set_default_size(500, 550)
        self.set_heading(_("Add Backup Link — {}").format(self.channel_name))
        self.add_response("cancel", _("Cancel"))
        self.set_default_response("cancel")
        self.set_close_response("cancel")
        self.connect("response", lambda d, r: self.destroy())
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.set_extra_child(self.stack)
        profile_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        profile_page.set_margin_top(10)
        profile_page.set_margin_bottom(10)
        profile_page.set_margin_start(10)
        profile_page.set_margin_end(10)
        profile_page.append(Gtk.Label(
            label=_("Which profile do you want to add this from?"),
            halign=Gtk.Align.START,
            wrap=True
        ))
        self.profile_list_box = Gtk.ListBox()
        self.profile_list_box.add_css_class("boxed-list")
        self.profile_list_box.connect("row-activated", self._on_profile_row_activated)
        profile_scroll = Gtk.ScrolledWindow(child=self.profile_list_box, vexpand=True)
        profile_page.append(profile_scroll)
        self.stack.add_named(profile_page, "profiles")
        bouquet_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        bouquet_page.set_margin_top(10)
        bouquet_page.set_margin_bottom(10)
        bouquet_page.set_margin_start(10)
        bouquet_page.set_margin_end(10)
        bouquet_back_btn = Gtk.Button(icon_name="go-previous-symbolic", halign=Gtk.Align.START)
        bouquet_back_btn.add_css_class("flat")
        bouquet_back_btn.connect("clicked", lambda b: self.stack.set_visible_child_name("profiles"))
        bouquet_page.append(bouquet_back_btn)
        self.bouquet_search_entry = Gtk.SearchEntry(placeholder_text=_("Search categories..."))
        self.bouquet_search_entry.connect("search-changed", self._on_bouquet_search_changed)
        bouquet_page.append(self.bouquet_search_entry)
        self.bouquet_list_box = Gtk.ListBox()
        self.bouquet_list_box.add_css_class("boxed-list")
        self.bouquet_list_box.connect("row-activated", self._on_bouquet_row_activated)
        bouquet_scroll = Gtk.ScrolledWindow(child=self.bouquet_list_box, vexpand=True)
        bouquet_page.append(bouquet_scroll)
        self.stack.add_named(bouquet_page, "bouquets")
        channel_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        channel_page.set_margin_top(10)
        channel_page.set_margin_bottom(10)
        channel_page.set_margin_start(10)
        channel_page.set_margin_end(10)
        channel_back_btn = Gtk.Button(icon_name="go-previous-symbolic", halign=Gtk.Align.START)
        channel_back_btn.add_css_class("flat")
        channel_back_btn.connect("clicked", lambda b: self.stack.set_visible_child_name("bouquets"))
        channel_page.append(channel_back_btn)
        self.channel_search_entry = Gtk.SearchEntry(placeholder_text=_("Search channels..."))
        self.channel_search_entry.connect("search-changed", self._on_channel_search_changed)
        channel_page.append(self.channel_search_entry)
        self.channel_list_box = Gtk.ListBox()
        self.channel_list_box.add_css_class("boxed-list")
        self.channel_list_box.connect("row-activated", self._on_channel_row_activated)
        channel_scroll = Gtk.ScrolledWindow(child=self.channel_list_box, vexpand=True)
        channel_page.append(channel_scroll)
        self.stack.add_named(channel_page, "channels")
        self.loading_page = Adw.StatusPage(title=_("Loading channels..."))
        if hasattr(Adw, "Spinner"):
            self._loading_spinner = Adw.Spinner(width_request=32, height_request=32, halign=Gtk.Align.CENTER)
            self._loading_spinner.start = self._loading_spinner.stop = lambda: None
        else:
            self._loading_spinner = Gtk.Spinner(width_request=32, height_request=32, halign=Gtk.Align.CENTER)
        self.loading_page.set_child(self._loading_spinner)
        self.stack.add_named(self.loading_page, "loading")
        self.stack.set_visible_child_name("profiles")
        self._populate_profile_list()

    def _populate_profile_list(self):
        all_profiles = load_profiles()
        current_id = self.main_window.profile_data.get("id")
        other_profiles = [p for p in all_profiles if p.get("id") != current_id]
        if not other_profiles:
            empty_row = Gtk.ListBoxRow(selectable=False, activatable=False)
            empty_row.set_child(Gtk.Label(
                label=_("No other profiles found."),
                margin_top=10, margin_bottom=10
            ))
            self.profile_list_box.append(empty_row)
            return
        for profile in other_profiles:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_start(10)
            box.set_margin_end(10)
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            icon = Gtk.Image(icon_name="network-server-symbolic")
            box.append(icon)
            label = Gtk.Label(label=profile.get("name", "?"), xalign=0, hexpand=True)
            box.append(label)
            arrow = Gtk.Image(icon_name="go-next-symbolic")
            arrow.add_css_class("dim-label")
            box.append(arrow)
            row.set_child(box)
            row.profile_data = profile
            self.profile_list_box.append(row)

    def _on_profile_row_activated(self, listbox, row):
        profile = getattr(row, "profile_data", None)
        if not profile:
            return
        self.selected_profile = profile
        self.stack.set_visible_child_name("loading")
        self._loading_spinner.start()
        threading.Thread(target=self._fetch_channels_thread, args=(profile,), daemon=True).start()

    def _fetch_channels_thread(self, profile):
        grouped = {}
        try:
            if profile.get("type") == "xtream":
                categories = xtream_client.get_live_categories(profile)
                streams = xtream_client.get_live_streams(profile)
                cat_map = {c.get("category_id"): c.get("category_name", "?") for c in categories}
                for s in streams:
                    cat_name = cat_map.get(s.get("category_id"), _("Uncategorized"))
                    grouped.setdefault(cat_name, []).append({
                        "name": s.get("name"),
                        "stream_id": s.get("stream_id"),
                    })
            elif profile.get("type") in ("m3u_url", "m3u_file"):
                import requests
                if profile.get("type") == "m3u_url":
                    resp = requests.get(profile.get("url"), timeout=20)
                    resp.raise_for_status()
                    lines = resp.text.splitlines()
                else:
                    with open(profile.get("path"), 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.read().splitlines()
                channels, _vod, _epg = parse_m3u_content(lines)
                grouped = channels
        except Exception as e:
            logging.error(f"[BackupLink] Error fetching channels for profile '{profile.get('name')}': {e}")
        GLib.idle_add(self._on_channels_fetched, grouped)

    def _on_channels_fetched(self, grouped):
        self._loading_spinner.stop()
        if not grouped:
            self.main_window.show_toast(_("Could not load channels from this profile."))
            self.stack.set_visible_child_name("profiles")
            return False
        self.grouped_channels = grouped
        self._build_bouquet_list(grouped)
        self.stack.set_visible_child_name("bouquets")
        return False

    def _build_bouquet_list(self, grouped, filter_text=""):
        while self.bouquet_list_box.get_first_child():
            self.bouquet_list_box.remove(self.bouquet_list_box.get_first_child())
        filter_lower = filter_text.lower()
        for bouquet_name in grouped.keys():
            if filter_lower and filter_lower not in bouquet_name.lower():
                continue
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_start(10)
            box.set_margin_end(10)
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            icon = Gtk.Image(icon_name="folder-symbolic")
            icon.add_css_class("dim-label")
            box.append(icon)
            label = Gtk.Label(label=bouquet_name, xalign=0, hexpand=True)
            box.append(label)
            arrow = Gtk.Image(icon_name="go-next-symbolic")
            arrow.add_css_class("dim-label")
            box.append(arrow)
            row.set_child(box)
            row.bouquet_name = bouquet_name
            self.bouquet_list_box.append(row)

    def _on_bouquet_search_changed(self, entry):
        self._build_bouquet_list(self.grouped_channels, entry.get_text())

    def _on_bouquet_row_activated(self, listbox, row):
        bouquet_name = getattr(row, "bouquet_name", None)
        if bouquet_name is None:
            return
        self.current_bouquet_name = bouquet_name
        self.channel_search_entry.set_text("")
        self._build_channel_list(self.grouped_channels.get(bouquet_name, []))
        self.stack.set_visible_child_name("channels")

    def _build_channel_list(self, channels, filter_text=""):
        while self.channel_list_box.get_first_child():
            self.channel_list_box.remove(self.channel_list_box.get_first_child())
        filter_lower = filter_text.lower()
        for ch in channels:
            name = ch.get("name", "?")
            if filter_lower and filter_lower not in name.lower():
                continue
            row = Gtk.ListBoxRow()
            label = Gtk.Label(
                label=name, xalign=0,
                margin_start=10, margin_end=10, margin_top=10, margin_bottom=10
            )
            row.set_child(label)
            row.channel_data = ch
            self.channel_list_box.append(row)

    def _on_channel_search_changed(self, entry):
        channels = self.grouped_channels.get(self.current_bouquet_name, [])
        self._build_channel_list(channels, entry.get_text())

    def _on_channel_row_activated(self, listbox, row):
        channel_data = getattr(row, "channel_data", None)
        if not channel_data:
            return
        backup_url = self._build_backup_url(self.selected_profile, channel_data)
        if not backup_url:
            self.main_window.show_toast(_("Could not build a playable URL for this channel."))
            return
        primary_url = self.current_channel_data.get("url")
        database.save_channel_backup_url(primary_url, backup_url)
        logging.info(f"[Backup Link] Saved for '{self.channel_name}' -> profile '{self.selected_profile.get('name')}', backup URL: {backup_url}")
        self.main_window.show_toast(
            _("Backup link added: {} – {}").format(self.selected_profile.get("name"), channel_data.get("name"))
        )
        if hasattr(self.main_window, "_update_backup_link_button_visibility"):
            self.main_window._update_backup_link_button_visibility()
        self.close()

    def _build_backup_url(self, profile, channel_data):
        if profile.get("type") == "xtream":
            host = profile.get("host")
            username = profile.get("username")
            password = profile.get("password")
            stream_id = channel_data.get("stream_id")
            if not (host and username and password and stream_id):
                return None
            return f"{host}/live/{username}/{password}/{stream_id}.ts"
        else:
            return channel_data.get("url")

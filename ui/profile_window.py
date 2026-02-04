# ui/profile_window.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk

import threading
import requests
import time
import logging
import uuid
import gettext
import os
import hashlib
import database
import json
from datetime import datetime
from utils.profile_manager import load_profiles, save_profiles, update_profile_dates
from data_providers.m3u_provider import load_from_file, parse_m3u_content
from core.window import MainWindow
from data_providers import epg_provider, xtream_client
_ = gettext.gettext

class ProfileWindow(Gtk.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        last_id = database.get_config_value('last_active_profile_id')
        is_auto_login = bool(last_id)
        if is_auto_login:
            self.set_decorated(False)
            self.set_default_size(340, 240)
            self.add_css_class("splash-window") 
        else:
            self.set_title(_("Profile Selection"))
            self.set_default_size(500, 450)
            header = Adw.HeaderBar()
            self.set_titlebar(header)
            self.add_css_class("profile-window")
        self.toast_overlay = Adw.ToastOverlay()
        self.set_child(self.toast_overlay)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)       
        if is_auto_login:
            main_box.add_css_class("splash-content")
            main_box.set_valign(Gtk.Align.CENTER)
            main_box.set_halign(Gtk.Align.CENTER)
        else:
            main_box.set_margin_top(12)
            main_box.set_margin_bottom(12)
            main_box.set_margin_start(12)
            main_box.set_margin_end(12)           
        self.toast_overlay.set_child(main_box)
        if not is_auto_login:
            main_box.append(Gtk.Label(label=_("Please select a profile or create a new one."), margin_bottom=10, halign=Gtk.Align.START))
        self.list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.list_box)
        scrolled_window.set_vexpand(True)        
        self.button_box = Gtk.Box(spacing=6)
        self.btn_add = Gtk.Button(label=_("Add New"))
        self.btn_edit = Gtk.Button(label=_("Edit"))
        self.btn_delete = Gtk.Button(label=_("Delete"))
        self.btn_open = Gtk.Button(label=_("Open Selected Profile"), css_classes=["suggested-action"])       
        self.btn_add.connect("clicked", self.on_add_profile_clicked)
        self.btn_edit.connect("clicked", self.on_edit_profile_clicked)
        self.btn_delete.connect("clicked", self.on_delete_profile_clicked)
        self.btn_open.connect("clicked", self.on_open_profile)      
        self.button_box.append(self.btn_add)
        self.button_box.append(self.btn_edit)
        self.button_box.append(self.btn_delete)
        self.button_box.append(Gtk.Box(hexpand=True))
        self.button_box.append(self.btn_open)
        self.status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        brand_label = Gtk.Label(label="EngPlayer", css_classes=["splash-title"])
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(48, 48)
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.status_label = Gtk.Label(label=_("Starting..."), css_classes=["splash-status"])      
        self.status_box.append(brand_label)
        self.status_box.append(self.spinner)
        self.status_box.append(self.status_label)
        if not is_auto_login:
            main_box.append(scrolled_window)
            main_box.append(self.status_box) 
            main_box.append(self.button_box)
            self.status_box.set_visible(False)
            self.populate_profiles()
        else:
            main_box.append(self.status_box)
            self.status_box.set_visible(True)
            self.spinner.start()
            self.start_auto_login_process()
        saved_color = database.get_config_value("app_accent_color")
        default_color = "#3584e4"
        self.apply_accent_color(saved_color if saved_color else default_color)

    def show_toast(self, message):
        timeout_sec = 3
        toast = Adw.Toast.new(message)
        toast.set_timeout(timeout_sec)
        if hasattr(self, "current_active_toast") and self.current_active_toast:
            try:
                self.current_active_toast.dismiss()
            except:
                pass
        self.current_active_toast = toast
        toast.connect("dismissed", lambda t: setattr(self, "current_active_toast", None))
        self.toast_overlay.add_toast(toast)

    def _get_cache_path(self, profile_id, cache_type):
        extension = 'm3u' if cache_type == 'm3u_cache' else 'xml'
        safe_id = hashlib.md5(profile_id.encode()).hexdigest()
        base_cache_dir = database.get_cache_path()
        cache_dir = os.path.join(base_cache_dir, cache_type)
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, f"{safe_id}.{extension}")

    def _get_xtream_cache_path(self, profile_id, data_type):
        safe_id = hashlib.md5(profile_id.encode()).hexdigest()
        base_cache_dir = database.get_cache_path()
        cache_dir = os.path.join(base_cache_dir, "xtream_cache")
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, f"{safe_id}_{data_type}.json")

    def _update_profile_timestamp(self, profile_id, key):
        profiles = load_profiles()
        for p in profiles:
            if p.get("id") == profile_id:
                p[key] = time.time()
                break
        save_profiles(profiles)

    def on_open_profile(self, widget):
        selected_row = self.list_box.get_selected_row()
        if not selected_row: return
        profile = selected_row.profile_data
        database.set_config_value('last_active_profile_id', profile['id'])
        try:
            database.set_active_profile_db(profile['id'])
        except Exception as e:
            logging.error(f"CRITICAL ERROR setting database path: {e}")
        try:
            database.set_active_profile_db(profile['id'])
        except Exception as e:
            logging.error(f"CRITICAL ERROR setting database path: {e}")
            dialog = Adw.MessageDialog(transient_for=self,
                                       heading=_("Critical Database Error"),
                                       body=_("Could not set profile database: {e}").format(e=e))
            dialog.add_response("ok", _("OK"))
            dialog.present()
            return
        self.set_sensitive(False)
        self.status_label.set_text(_("Loading profile '{}'...").format(profile['name']))
        self.status_box.set_visible(True)
        self.spinner.start()
        thread = threading.Thread(target=self._master_load_thread, args=(profile,), daemon=True)
        thread.start()

    def _master_load_thread(self, profile):
        """Loads data from the selected profile, including EPG."""

        def _transform_streams_to_bouquets(streams, categories, stream_type='live'):
            category_map = {cat['category_id']: cat['category_name'] for cat in categories}
            bouquets = {}
            base_url = f"{profile.get('host')}/{stream_type}/{profile.get('username')}/{profile.get('password')}"
            for stream in streams:
                cat_id = str(stream.get('category_id'))
                cat_name = category_map.get(cat_id, _("Other"))
                stream_data = {
                    "name": stream.get('name'),
                    "url": f"{base_url}/{stream.get('stream_id')}.ts",
                    "logo": stream.get('stream_icon'),
                    "tvg-id": stream.get('epg_channel_id'),
                    "rating": stream.get('rating'),
                    "added": stream.get('added'),
                    "stream_id": stream.get('stream_id'),
                    "series_id": stream.get('series_id'),
                    "youtube_trailer": stream.get('trailer') or stream.get('youtube_trailer'),
                    "tmdb_id": stream.get('tmdb_id') or stream.get('tmdb')
                }
                tv_archive_val = stream.get('tv_archive')
                tv_archive_duration_val = stream.get('tv_archive_duration')
                if tv_archive_val is not None:
                    stream_data["tv_archive"] = str(tv_archive_val)
                if tv_archive_duration_val is not None:
                    stream_data["tv_archive_duration"] = str(tv_archive_duration_val)
                if cat_name not in bouquets:
                    bouquets[cat_name] = []
                bouquets[cat_name].append(stream_data)
            return bouquets
        try:
            profile_type = profile.get("type")
            channels = {}
            vod = {}
            epg_data = {}
            if profile_type == "xtream":
                logging.info("Profile type is Xtream. Checking cache...")
                channels_cache_path = self._get_xtream_cache_path(profile['id'], 'channels')
                vod_cache_path = self._get_xtream_cache_path(profile['id'], 'vod')
                xtream_ttl = 86400
                last_xtream_update = profile.get('last_xtream_update', 0)
                xtream_is_stale = (time.time() - last_xtream_update) > xtream_ttl
                dates_are_missing = not profile.get("created_at") or not profile.get("exp_date")
                if dates_are_missing:
                    logging.info("Dates missing, calling 'get_user_authentication'...")
                    user_info = xtream_client.get_user_authentication(profile)
                    if user_info and isinstance(user_info, dict):
                        start_ts = user_info.get("created_at")
                        exp_ts = user_info.get("exp_date")
                        if (start_ts and str(start_ts).isdigit()) or (exp_ts and str(exp_ts).isdigit()):
                            update_profile_dates(profile['id'], start_ts, exp_ts)
                if os.path.exists(channels_cache_path) and os.path.exists(vod_cache_path) and not xtream_is_stale:
                    logging.info("Fresh Xtream cache found. Reading from disk.")
                    try:
                        with open(channels_cache_path, 'r', encoding='utf-8') as f:
                            channels = json.load(f)
                        with open(vod_cache_path, 'r', encoding='utf-8') as f:
                            vod = json.load(f)
                    except (json.JSONDecodeError, IOError):
                        channels, vod = {}, {}
                if not channels or not vod:
                    live_categories = xtream_client.get_live_categories(profile)
                    live_streams = xtream_client.get_live_streams(profile)
                    if live_streams is not None and live_categories is not None:
                         channels = _transform_streams_to_bouquets(live_streams, live_categories, 'live')
                    vod_categories = xtream_client.get_vod_categories(profile)
                    vod_streams = xtream_client.get_vod_streams(profile)
                    if vod_streams is not None and vod_categories is not None:
                         vod = _transform_streams_to_bouquets(vod_streams, vod_categories, 'movie')
                    if channels or vod:
                        try:
                            if channels:
                                with open(channels_cache_path, 'w', encoding='utf-8') as f:
                                    json.dump(channels, f, ensure_ascii=False)
                            if vod:
                                with open(vod_cache_path, 'w', encoding='utf-8') as f:
                                    json.dump(vod, f, ensure_ascii=False)
                            if channels or vod:
                                 self._update_profile_timestamp(profile['id'], 'last_xtream_update')
                        except IOError as e:
                            logging.error(f"Could not write Xtream cache to disk: {e}")
            else:
                logging.info("Profile type is M3U. Fetching data from file/URL.")
                m3u_cache_path = self._get_cache_path(profile['id'], 'm3u_cache')
                m3u_ttl = 86400
                last_m3u_update = profile.get('last_m3u_update', 0)
                m3u_is_stale = (time.time() - last_m3u_update) > m3u_ttl
                m3u_content = ""
                if os.path.exists(m3u_cache_path) and not m3u_is_stale:
                    try:
                        with open(m3u_cache_path, 'r', encoding='utf-8', errors='ignore') as f:
                            m3u_content = f.read()
                    except IOError:
                         m3u_content = ""
                else:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    downloaded_text = ""
                    try:
                        if profile_type == "m3u_file":
                            with open(profile["path"], 'r', encoding='utf-8', errors='ignore') as f:
                                downloaded_text = f.read()
                        elif profile_type == "m3u_url":
                            response = requests.get(profile["url"], timeout=30, headers=headers)
                            response.raise_for_status()
                            downloaded_text = response.text
                        if downloaded_text:
                            with open(m3u_cache_path, 'w', encoding='utf-8') as f:
                                f.write(downloaded_text)
                            self._update_profile_timestamp(profile['id'], 'last_m3u_update')
                            m3u_content = downloaded_text
                    except Exception as e:
                         logging.error(f"M3U load error: {e}")
                if m3u_content:
                    channels, vod = parse_m3u_content(m3u_content.splitlines())
            epg_url_or_path = profile.get("epg_url")
            if not epg_url_or_path and profile_type == "xtream":
                host = profile.get("host")
                username = profile.get("username")
                password = profile.get("password")
                if host and username and password:
                    epg_url_or_path = f"{host}/xmltv.php?username={username}&password={password}"
            if epg_url_or_path:
                epg_cache_path = self._get_cache_path(profile['id'], 'epg_cache')
                epg_ttl = 21600
                last_epg_update = profile.get('last_epg_update', 0)
                epg_is_stale = (time.time() - last_epg_update) > epg_ttl
                epg_content = ""
                if os.path.exists(epg_cache_path) and not epg_is_stale:
                    logging.info(f"Fresh EPG cache found: {epg_cache_path}")
                    try:
                        with open(epg_cache_path, 'r', encoding='utf-8', errors='ignore') as f:
                            epg_content = f.read()
                    except IOError:
                         epg_content = ""
                if not epg_content:
                    logging.info("EPG cache missing or stale. Downloading...")
                    epg_content = epg_provider.load_epg_data(epg_url_or_path)
                    if epg_content:
                        try:
                             with open(epg_cache_path, 'w', encoding='utf-8') as f:
                                 f.write(epg_content)
                             self._update_profile_timestamp(profile['id'], 'last_epg_update')
                        except IOError:
                             pass
                if epg_content:
                    epg_data = epg_provider.parse_epg_data(epg_content)
            GLib.idle_add(self._on_loading_complete, profile, channels, vod, epg_data, None)
        except Exception as e:
            error_message = _("An unexpected error occurred while loading profile '{}'.\n\nReason: {}").format(profile['name'], e)
            logging.exception(f"Critical error while loading profile: {profile['name']}")
            GLib.idle_add(self._on_loading_complete, profile, {}, {}, {}, error_message)

    def _on_loading_complete(self, profile, channels, vod, epg_data, error):
        self.spinner.stop()
        self.status_box.set_visible(False)
        self.set_sensitive(True)
        if error:
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=_("Profile Loading Error"),
                body=str(error)
            )
            dialog.add_response("ok", _("OK"))
            dialog.present()
        else:
            logging.info("Loading complete. Creating player window...")
            app = self.get_application()
            player_window = MainWindow(application=app, profile=profile, channels=channels, vod=vod, epg_data=epg_data)
            player_window.present()
            self.close()

    def _format_timestamp(self, ts):
        if not ts or not str(ts).isdigit() or int(ts) == 0:
            return None
        try:
            return datetime.fromtimestamp(int(ts)).strftime('%d.%m.%Y')
        except (ValueError, OSError):
            return None
            
    def check_auto_login(self):
        last_id = database.get_config_value('last_active_profile_id')      
        if not last_id:
            return False
        profiles = load_profiles()
        target_profile = next((p for p in profiles if p['id'] == last_id), None)
        if target_profile:
            logging.info(f"Auto-login: Found last profile '{target_profile['name']}'. Loading directly...")           
            self.set_sensitive(False)
            self.status_label.set_text(_("Loading profile '{}'...").format(target_profile['name']))
            self.status_box.set_visible(True)
            self.spinner.start()           
            try:
                database.set_active_profile_db(target_profile['id'])
                thread = threading.Thread(target=self._master_load_thread, args=(target_profile,), daemon=True)
                thread.start()
                return True 
            except Exception as e:
                logging.error(f"Auto-login failed: {e}")
                database.set_config_value('last_active_profile_id', '')
                self.set_sensitive(True)
                self.status_box.set_visible(False)               
        return False       

    def populate_profiles(self):
        profiles = load_profiles()
        while (child := self.list_box.get_first_child()): self.list_box.remove(child)
        for profile in profiles:
            row = Adw.ActionRow()
            row.profile_data = profile
            row.set_title(profile['name'])
            row.set_activatable(True)
            if profile.get("type") == "xtream":
                start_date_str = self._format_timestamp(profile.get("created_at"))
                exp_date_str = self._format_timestamp(profile.get("exp_date"))
                if start_date_str or exp_date_str:
                    date_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                        halign=Gtk.Align.END,
                                        valign=Gtk.Align.CENTER)
                    if start_date_str:
                        start_label = Gtk.Label(xalign=1)
                        start_label.set_markup(f"<i>{_('Start')}: {start_date_str}</i>")
                        date_vbox.append(start_label)
                    else:
                        if exp_date_str:
                            date_vbox.append(Gtk.Label())
                    if exp_date_str:
                        exp_label = Gtk.Label(xalign=1)
                        exp_label.set_markup(f"<i>{_('End')}: {exp_date_str}</i>")
                        date_vbox.append(exp_label)
                    row.add_suffix(date_vbox)
            self.list_box.append(row)
        if len(profiles) > 0: self.list_box.select_row(self.list_box.get_row_at_index(0))

    def on_edit_profile_clicked(self, widget):
        selected_row = self.list_box.get_selected_row()
        if not selected_row:
            self.show_toast(_("Please select a profile to edit."))
            return
        dialog = self.create_profile_dialog(title=_("Edit Profile"), profile_data=selected_row.profile_data)
        dialog.connect("response", self.on_edit_dialog_response, selected_row.profile_data.get("id"))
        dialog.present()

    def on_add_profile_clicked(self, widget):
        dialog = self.create_profile_dialog(title=_("Add New Profile"), profile_data=None)
        dialog.connect("response", self._on_add_dialog_response); dialog.present()

    def on_delete_profile_clicked(self, widget):
        selected_row = self.list_box.get_selected_row()
        if not selected_row: self.show_toast(_("Please select a profile to delete.")); return
        profile_to_delete = selected_row.profile_data
        dialog = Adw.MessageDialog(transient_for=self, heading=_("Delete profile '{}'?").format(profile_to_delete['name']), body=_("This action cannot be undone."), modal=True)
        dialog.add_response("cancel", _("Cancel")); dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_delete_confirm_response, profile_to_delete.get("id")); dialog.present()

    def _on_delete_confirm_response(self, dialog, response_id, profile_id):
        """
        Runs when profile deletion is confirmed.
        Deletes the profile from JSON, removes all cache files AND the profile database.
        """
        if response_id == "delete":
            profile_name = _("Unknown Profile")
            profiles = load_profiles()
            remaining_profiles = []
            deleted = False
            for p in profiles:
                if p.get("id") == profile_id:
                    profile_name = p.get("name", profile_name)
                    deleted = True
                else:
                    remaining_profiles.append(p)
            if deleted:
                save_profiles(remaining_profiles)
                logging.info(f"Profile '{profile_name}' (ID: {profile_id}) deleted from profiles.json.")
                safe_id = hashlib.md5(profile_id.encode()).hexdigest()
                profile_db_path = os.path.join(database.APP_CONFIG_DIR, f"profile_{safe_id}.db")
                logging.info(f"Deleting database and cache files for profile '{profile_name}'...")
                files_to_delete = [
                    self._get_cache_path(profile_id, 'm3u_cache'),
                    self._get_cache_path(profile_id, 'epg_cache'),
                    self._get_xtream_cache_path(profile_id, 'channels'),
                    self._get_xtream_cache_path(profile_id, 'vod'),
                    profile_db_path
                ]
                deleted_count = 0
                for file_path in files_to_delete:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logging.info(f" -> File deleted: {file_path}")
                            deleted_count += 1
                    except OSError as e:
                        logging.error(f" -> ERROR deleting file: {file_path} | Error: {e}")
                logging.info(f"{deleted_count} related files deleted.")
                self.populate_profiles()
                self.show_toast(_("Profile '{}' and all its data were successfully deleted.").format(profile_name))
            else:
                 logging.warning(f"Profile to be deleted (ID: {profile_id}) not found in profiles.json.")
                 self.show_toast(_("Error: Profile not found or already deleted."))
    def _on_add_dialog_response(self, dialog, response_id):
        if response_id == "save":
            name = dialog.name_entry.get_text().strip()
            if not name: self.show_toast(_("Profile name cannot be empty!")); return
            profile_type = dialog.profile_type_combo.get_active_id()
            new_profile = {"id": str(uuid.uuid4()), "name": name, "type": profile_type}
            if profile_type == "m3u_url": new_profile["url"] = dialog.url_entry.get_text().strip()
            elif profile_type == "m3u_file": new_profile["path"] = dialog.file_path_label.get_text()
            elif profile_type == "xtream":
                new_profile["host"] = dialog.xtream_host_entry.get_text().strip()
                new_profile["username"] = dialog.xtream_user_entry.get_text().strip()
                new_profile["password"] = dialog.xtream_pass_entry.get_text().strip()
            new_profile["epg_url"] = dialog.epg_url_entry.get_text().strip()
            selected_icon_path = dialog.icon_path_label.get_text()
            if os.path.isdir(selected_icon_path):
                new_profile["icon_path"] = selected_icon_path
            else:
                new_profile["icon_path"] = ""
            profiles = load_profiles(); profiles.append(new_profile); save_profiles(profiles)
            self.populate_profiles(); self.show_toast(_("Profile '{}' added.").format(name))

    def on_edit_dialog_response(self, dialog, response_id, profile_id):
        if response_id == "save":
            name = dialog.name_entry.get_text().strip()
            if not name: return
            profiles = load_profiles()
            for p in profiles:
                if p.get("id") == profile_id:
                    p["name"] = name
                    p["type"] = dialog.profile_type_combo.get_active_id()
                    if p["type"] == "m3u_url": p["url"] = dialog.url_entry.get_text().strip()
                    elif p["type"] == "m3u_file": p["path"] = dialog.file_path_label.get_text()
                    elif p["type"] == "xtream":
                        p["host"] = dialog.xtream_host_entry.get_text().strip()
                        p["username"] = dialog.xtream_user_entry.get_text().strip()
                        p["password"] = dialog.xtream_pass_entry.get_text().strip()
                    p["epg_url"] = dialog.epg_url_entry.get_text().strip()
                    selected_icon_path = dialog.icon_path_label.get_text()
                    if os.path.isdir(selected_icon_path):
                        p["icon_path"] = selected_icon_path
                    else:
                        p["icon_path"] = ""
                    p.pop("last_m3u_update", None)
                    p.pop("last_xtream_update", None)
                    p.pop("channels", None)
                    p.pop("vod", None)
                    p.pop("created_at", None)
                    p.pop("exp_date", None)
                    break
            save_profiles(profiles)
            self.populate_profiles()
            self.show_toast(_("Profile '{}' updated.").format(name))

    def create_profile_dialog(self, title, profile_data):
        dialog = Adw.MessageDialog(transient_for=self, heading=title)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12)
        dialog.set_extra_child(content)
        name_entry = Gtk.Entry(placeholder_text=_("Profile Name (e.g., Family IPTV)"))
        content.append(name_entry)
        profile_type_combo = Gtk.ComboBoxText()
        profile_type_combo.append("m3u_url", _("M3U URL"))
        profile_type_combo.append("m3u_file", _("M3U File"))
        profile_type_combo.append("xtream", _("Xtream Codes"))
        content.append(profile_type_combo)
        input_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_UP_DOWN)
        content.append(input_stack)
        url_entry = Gtk.Entry(placeholder_text=_("http://example.com/list.m3u"))
        input_stack.add_named(url_entry, "m3u_url")
        file_box = Gtk.Box(spacing=6)
        file_path_label = Gtk.Label(label=_("No file selected..."), halign=Gtk.Align.START, hexpand=True)
        file_choose_button = Gtk.Button(label=_("Choose File..."))
        file_box.append(file_path_label)
        file_box.append(file_choose_button)
        input_stack.add_named(file_box, "m3u_file")
        xtream_grid = Gtk.Grid(row_spacing=6, column_spacing=6)
        xtream_host_entry = Gtk.Entry(placeholder_text=_("e.g., http://server.com:8080"))
        xtream_user_entry = Gtk.Entry()
        xtream_pass_entry = Gtk.PasswordEntry()
        xtream_grid.attach(Gtk.Label(label=_("Host:"), halign=Gtk.Align.START), 0, 0, 1, 1)
        xtream_grid.attach(xtream_host_entry, 1, 0, 1, 1)
        xtream_grid.attach(Gtk.Label(label=_("Username:"), halign=Gtk.Align.START), 0, 1, 1, 1)
        xtream_grid.attach(xtream_user_entry, 1, 1, 1, 1)
        xtream_grid.attach(Gtk.Label(label=_("Password:"), halign=Gtk.Align.START), 0, 2, 1, 1)
        xtream_grid.attach(xtream_pass_entry, 1, 2, 1, 1)
        input_stack.add_named(xtream_grid, "xtream")
        profile_type_combo.connect("changed", lambda w: input_stack.set_visible_child_name(w.get_active_id()))

        def on_file_choose_clicked(btn):
            chooser = Gtk.FileChooserDialog(
                title=_("Select M3U File"),
                transient_for=self,
                action=Gtk.FileChooserAction.OPEN
            )
            chooser.add_buttons(
                _("Cancel"), Gtk.ResponseType.CANCEL,
                _("Select"), Gtk.ResponseType.ACCEPT
            )
            chooser.set_modal(True)
            filter_m3u = Gtk.FileFilter()
            filter_m3u.set_name("M3U Playlists")
            filter_m3u.add_pattern("*.m3u")
            filter_m3u.add_pattern("*.m3u8")
            chooser.add_filter(filter_m3u)
            filter_all = Gtk.FileFilter()
            filter_all.set_name(_("All Files"))
            filter_all.add_pattern("*")
            chooser.add_filter(filter_all)

            def on_response(d, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    gfile = d.get_file()
                    if gfile:
                        path = gfile.get_path()
                        file_path_label.set_text(path)
                d.hide()
                def _safe_destroy():
                    d.destroy()
                    return GLib.SOURCE_REMOVE
                GLib.idle_add(_safe_destroy)
            chooser.connect("response", on_response)
            chooser.present()
        file_choose_button.connect("clicked", on_file_choose_clicked)
        content.append(Gtk.Separator(margin_top=10, margin_bottom=10))
        epg_url_entry = Gtk.Entry(placeholder_text=_("External EPG URL (XMLTV, optional)"))
        content.append(epg_url_entry)
        icon_folder_box = Gtk.Box(spacing=6)
        icon_path_label = Gtk.Label(label=_("No icon folder selected..."), halign=Gtk.Align.START, hexpand=True)
        icon_choose_button = Gtk.Button(label=_("Choose Folder..."))
        icon_folder_box.append(icon_path_label)
        icon_folder_box.append(icon_choose_button)
        content.append(icon_folder_box)

        def on_icon_folder_choose_clicked(btn):
            chooser = Gtk.FileChooserDialog(
                title=_("Select Channel Icon Folder"),
                transient_for=self,
                action=Gtk.FileChooserAction.SELECT_FOLDER
            )
            chooser.add_buttons(
                _("Cancel"), Gtk.ResponseType.CANCEL,
                _("Select"), Gtk.ResponseType.ACCEPT
            )
            chooser.set_modal(True)

            def on_response(d, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    gfile = d.get_file()
                    if gfile:
                        path = gfile.get_path()
                        icon_path_label.set_text(path)
                d.hide()
                def _safe_destroy():
                    d.destroy()
                    return GLib.SOURCE_REMOVE
                GLib.idle_add(_safe_destroy)
            chooser.connect("response", on_response)
            chooser.present()
        icon_choose_button.connect("clicked", on_icon_folder_choose_clicked)
        if profile_data:
            name_entry.set_text(profile_data.get("name", ""))
            ptype = profile_data.get("type", "m3u_url")
            profile_type_combo.set_active_id(ptype)
            if ptype == "m3u_url":
                url_entry.set_text(profile_data.get("url", ""))
            elif ptype == "m3u_file":
                file_path_label.set_text(profile_data.get("path", _("No file selected...")))
            elif ptype == "xtream":
                xtream_host_entry.set_text(profile_data.get("host", ""))
                xtream_user_entry.set_text(profile_data.get("username", ""))
                xtream_pass_entry.set_text(profile_data.get("password", ""))
            epg_url_entry.set_text(profile_data.get("epg_url", ""))
            icon_path_label.set_text(profile_data.get("icon_path", _("No icon folder selected...")))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save"))
        dialog.name_entry = name_entry
        dialog.profile_type_combo = profile_type_combo
        dialog.url_entry = url_entry
        dialog.file_path_label = file_path_label
        dialog.xtream_host_entry = xtream_host_entry
        dialog.xtream_user_entry = xtream_user_entry
        dialog.xtream_pass_entry = xtream_pass_entry
        dialog.epg_url_entry = epg_url_entry
        dialog.icon_path_label = icon_path_label
        return dialog

    def apply_accent_color(self, color_str):
        if not color_str: return
        css_provider = Gtk.CssProvider()
        css_data = f"""
        @define-color accent_color {color_str}; 
        @define-color accent_bg_color {color_str}; 
        @define-color accent_fg_color #ffffff; 
        """      
        try:
            css_provider.load_from_data(css_data.encode())
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        except Exception as e:
            logging.error(f"Error applying accent color: {e}")
            
    def start_auto_login_process(self):
        last_id = database.get_config_value('last_active_profile_id')
        profiles = load_profiles()
        target_profile = next((p for p in profiles if p['id'] == last_id), None)
        if target_profile:
            logging.info(f"Auto-login: Found last profile '{target_profile['name']}'. Loading directly...")
            try:
                database.set_active_profile_db(target_profile['id'])
                thread = threading.Thread(target=self._master_load_thread, args=(target_profile,), daemon=True)
                thread.start()
            except Exception as e:
                logging.error(f"Auto-login failed: {e}")
        else:
            logging.warning("Auto-login profile not found. Reverting to normal mode.")
            database.set_config_value('last_active_profile_id', '')
           

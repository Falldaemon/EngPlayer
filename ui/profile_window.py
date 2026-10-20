# ui/profile_window.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk, Pango

import threading
import requests
import time
import logging
import uuid
import gettext
import os
import hashlib
import database
from core.config import PROVIDER_USER_AGENT
import json
from datetime import datetime
from utils.profile_manager import load_profiles, save_profiles, update_profile_dates
from data_providers.m3u_provider import load_from_file, parse_m3u_content
from core.window import MainWindow
from data_providers import epg_provider, xtream_client
from ui.theme_manager import ThemeManager

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
            self.add_css_class("dialog")
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
        self.btn_full_restore = Gtk.Button(label=_("Full Restore"))
        self.btn_add.connect("clicked", self.on_add_profile_clicked)
        self.btn_edit.connect("clicked", self.on_edit_profile_clicked)
        self.btn_delete.connect("clicked", self.on_delete_profile_clicked)
        self.btn_open.connect("clicked", self.on_open_profile)      
        self.btn_full_restore.connect("clicked", self.on_full_restore_clicked)
        self.button_box.append(self.btn_add)
        self.button_box.append(self.btn_edit)
        self.button_box.append(self.btn_delete)
        self.button_box.append(self.btn_full_restore)
        self.button_box.append(Gtk.Box(hexpand=True))
        self.button_box.append(self.btn_open)
        self.status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        brand_label = Gtk.Label(label="EngPlayer", css_classes=["splash-title"])
        if hasattr(Adw, "Spinner"):
            self.spinner = Adw.Spinner(width_request=48, height_request=48)
            self.spinner.start = self.spinner.stop = lambda: None
        else:
            self.spinner = Gtk.Spinner()
            self.spinner.set_size_request(48, 48)
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.status_label = Gtk.Label(label=_("Starting..."), css_classes=["splash-status"])  
        if os.name == 'nt':
            self.status_label.set_width_chars(30)
            self.status_label.set_max_width_chars(30)
            self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
        else:
            self.status_label.set_wrap(True)
        self.status_label.set_justify(Gtk.Justification.CENTER)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_margin_top(10)
        self.progress_bar.set_margin_bottom(10)
        self.progress_bar.set_margin_start(40)
        self.progress_bar.set_margin_end(40)
        self.progress_bar.set_show_text(True)    
        self.status_box.append(brand_label)
        self.status_box.append(self.spinner)
        self.status_box.append(self.status_label)
        self.status_box.append(self.progress_bar)
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
        saved_theme = database.get_config_value('app_theme')
        if saved_theme:
            ThemeManager.apply_theme(saved_theme)
        else:
            ThemeManager.apply_theme("default")
        self._check_full_backup_restore_result()

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

    def _check_full_backup_restore_result(self):
        for key, success_msg, error_prefix in [
            ('last_backup_result', _("Backup completed successfully!"), _("Backup failed:")),
            ('last_restore_result', _("Restore completed successfully! Please select a profile."), _("Restore failed:")),
        ]:
            raw = database.get_config_value(key)
            if not raw:
                continue
            try:
                result = json.loads(raw)
            except Exception:
                result = {}
            if result.get("success"):
                self.show_toast(success_msg)
            else:
                self.show_toast(f"{error_prefix} {result.get('error', '?')}")
            database.set_config_value(key, "")

    def on_full_restore_clicked(self, button):
        chooser = Gtk.FileChooserDialog(
            title=_("Select Backup File"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN
        )
        chooser.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Select"), Gtk.ResponseType.ACCEPT
        )
        chooser.set_modal(True)
        filter_backup = Gtk.FileFilter()
        filter_backup.set_name(_("EngPlayer Backup Files"))
        filter_backup.add_pattern("*.tar.gz")
        chooser.add_filter(filter_backup)

        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                gfile = d.get_file()
                if gfile:
                    path = gfile.get_path()
                    self._confirm_full_restore(path)
            d.hide()
            
            def _safe_destroy():
                d.destroy()
                return GLib.SOURCE_REMOVE
            GLib.idle_add(_safe_destroy)
        chooser.connect("response", on_response)
        chooser.present()

    def _confirm_full_restore(self, source_path):
        warning = Adw.MessageDialog(
            transient_for=self,
            heading=_("Full Restore"),
            body=_("This will DELETE ALL your current profiles and settings and replace them with the contents of:\n\n{}\n\nAny profiles or changes made after this backup was taken will be LOST.\n\nThis cannot be undone.\n\nThe app will close now and reopen automatically once the restore is complete — this can take up to 1-2 minutes, so please be patient.").format(source_path),
            modal=True
        )
        warning.add_css_class("restart-dialog")
        warning.add_response("cancel", _("Cancel"))
        warning.add_response("restore", _("Yes, Delete Current Profiles and Restore Backup"))
        warning.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        warning.set_default_response("cancel")
        warning.set_close_response("cancel")
        warning.connect("response", self._on_full_restore_confirmed, source_path)
        warning.present()

    def _on_full_restore_confirmed(self, dialog, response_id, source_path):
        dialog.close()
        if response_id != "restore":
            return
        try:
            request = {"source": source_path, "pid": os.getpid()}
            database.set_config_value('pending_full_restore', json.dumps(request))
            logging.info(f"[Full Restore] Restore requested. Source: {source_path}")
        except Exception as e:
            logging.error(f"[Full Restore] Could not save restore request: {e}")
            self.show_toast(_("Could not start restore."))
            return
        self.show_toast(_("Closing to restore your data. The app will reopen automatically..."))
        GLib.timeout_add(1500, self._quit_for_full_restore)

    def _quit_for_full_restore(self):
        self.get_application().quit()
        return False

    def _get_cache_path(self, profile_id, cache_type, index=None):
        extension = 'm3u' if cache_type == 'm3u_cache' else 'xml'
        safe_id = hashlib.md5(profile_id.encode()).hexdigest()
        base_cache_dir = database.get_cache_path()
        cache_dir = os.path.join(base_cache_dir, cache_type)
        os.makedirs(cache_dir, exist_ok=True)
        suffix = f"_{index}" if index is not None else ""
        return os.path.join(cache_dir, f"{safe_id}{suffix}.{extension}")

    def _get_epg_url_list(self, profile):
        epg_urls = profile.get("epg_urls")
        if epg_urls is None:
            legacy_url = profile.get("epg_url")
            epg_urls = [legacy_url] if legacy_url else []
            profiles = load_profiles()
            for p in profiles:
                if p.get("id") == profile.get("id"):
                    p["epg_urls"] = epg_urls
                    p.pop("epg_url", None)
                    break
            save_profiles(profiles)
            profile["epg_urls"] = epg_urls
            profile.pop("epg_url", None)
            logging.info(f"[EPG] Migrated legacy 'epg_url' field to 'epg_urls' list for profile '{profile.get('name')}'.")
        return [u.strip() for u in epg_urls if u and u.strip()][:3]
        
    def _get_epg_source_cache_path(self, profile_id, source):
        safe_id = hashlib.md5(profile_id.encode()).hexdigest()
        source_hash = hashlib.md5(source.encode('utf-8')).hexdigest()
        base_cache_dir = database.get_cache_path()
        cache_dir = os.path.join(base_cache_dir, 'epg_cache')
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, f"{safe_id}_{source_hash}.xml")        

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
        
    def _update_progress(self, fraction, message):
        def do_update():
            if hasattr(self, 'progress_bar') and self.progress_bar:
                self.progress_bar.set_fraction(fraction)
            if hasattr(self, 'status_label') and self.status_label:
                self.status_label.set_text(message)
            return GLib.SOURCE_REMOVE
        GLib.idle_add(do_update)        

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

        def _transform_streams_to_bouquets(streams, categories, stream_type='live'):
            category_map = {cat['category_id']: cat['category_name'] for cat in categories}
            bouquets = {}
            base_url = f"{profile.get('host')}/{stream_type}/{profile.get('username')}/{profile.get('password')}"
            for stream in streams:
                cat_id = str(stream.get('category_id'))
                cat_name = category_map.get(cat_id, _("Other"))
                stream_data = {
                    "name": stream.get('name') or "",
                    "url": f"{base_url}/{stream.get('stream_id')}.ts",
                    "logo": stream.get('stream_icon'),
                    "tvg-id": stream.get('epg_channel_id'),
                    "rating": stream.get('rating'),
                    "added": stream.get('added'),
                    "stream_id": stream.get('stream_id'),
                    "series_id": stream.get('series_id'),
                    "youtube_trailer": stream.get('trailer') or stream.get('youtube_trailer'),
                    "tmdb_id": stream.get('tmdb_id') or stream.get('tmdb'),
                    "genre": stream.get('genre') if isinstance(stream.get('genre'), str) else None
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
            series = {}
            epg_data = {}
            logging.info(f"[EPG] Activating profile-specific EPG database for '{profile.get('name')}'...")
            database.set_active_epg_db(profile['id'])
            if profile_type == "xtream":
                logging.info("Profile type is Xtream. Checking cache...")
                channels_cache_path = self._get_xtream_cache_path(profile['id'], 'channels')
                series_cache_path = self._get_xtream_cache_path(profile['id'], 'series')
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
                if os.path.exists(channels_cache_path) and os.path.exists(vod_cache_path) and os.path.exists(series_cache_path) and not xtream_is_stale:
                    logging.info("Fresh Xtream cache found. Reading from disk.")
                    try:
                        with open(channels_cache_path, 'r', encoding='utf-8') as f:
                            channels = json.load(f)
                        with open(series_cache_path, 'r', encoding='utf-8') as f:
                            series = json.load(f)    
                        with open(vod_cache_path, 'r', encoding='utf-8') as f:
                            vod = json.load(f)
                        first_vod = next((items[0] for items in vod.values() if items), None) if isinstance(vod, dict) else None
                        if isinstance(first_vod, dict) and "genre" not in first_vod:
                            logging.info("Xtream VOD cache predates genre support. Refreshing it once.")
                            vod = {}
                    except (json.JSONDecodeError, IOError):
                        channels, vod = {}, {}
                if not channels or not vod:
                    self._update_progress(0.1, _("Fetching live channel categories..."))
                    live_categories = xtream_client.get_live_categories(profile)                    
                    self._update_progress(0.2, _("Fetching live streams..."))
                    live_streams = xtream_client.get_live_streams(profile)
                    self._update_progress(0.4, _("Fetching VOD categories..."))
                    vod_categories = xtream_client.get_vod_categories(profile)                  
                    self._update_progress(0.5, _("Fetching VOD streams..."))
                    vod_streams = xtream_client.get_vod_streams(profile)
                    self._update_progress(0.6, _("Fetching series and episodes..."))
                    series_categories = xtream_client.get_series_categories(profile)
                    series_streams = xtream_client.get_series_streams(profile, "all")
                    missing = [kind for kind, streams, cats in (("live", live_streams, live_categories),
                                                                ("vod", vod_streams, vod_categories),
                                                                ("series", series_streams, series_categories))
                               if streams and not cats]
                    if missing:
                        logging.warning(f"Xtream returned no categories for {', '.join(missing)} while streams exist. Retrying once in 9 s...")
                        time.sleep(9)
                        if "live" in missing:
                            live_categories = xtream_client.get_live_categories(profile)
                        if "vod" in missing:
                            vod_categories = xtream_client.get_vod_categories(profile)
                        if "series" in missing:
                            series_categories = xtream_client.get_series_categories(profile)
                    incomplete = {kind for kind, streams, cats in (("live", live_streams, live_categories),
                                                                   ("vod", vod_streams, vod_categories),
                                                                   ("series", series_streams, series_categories))
                                  if streams and not cats}
                    if live_streams is not None and live_categories is not None:
                         channels = _transform_streams_to_bouquets(live_streams, live_categories, 'live')                  
                    if vod_streams is not None and vod_categories is not None:
                         vod = _transform_streams_to_bouquets(vod_streams, vod_categories, 'movie')                        
                    if series_streams is not None and series_categories is not None:
                         series = _transform_streams_to_bouquets(series_streams, series_categories, 'series')     
                    if incomplete:
                        logging.warning(f"Xtream categories still missing for {', '.join(sorted(incomplete))}. "
                                        "Data is shown for this session only and will not be cached.")
                        for kind, path in (("live", channels_cache_path), ("vod", vod_cache_path), ("series", series_cache_path)):
                            if kind in incomplete and os.path.exists(path):
                                try:
                                    os.remove(path)
                                except OSError:
                                    pass
                    if channels or vod:
                        try:
                            if channels and "live" not in incomplete:
                                with open(channels_cache_path, 'w', encoding='utf-8') as f:
                                    json.dump(channels, f, ensure_ascii=False)
                            if vod and "vod" not in incomplete:
                                with open(vod_cache_path, 'w', encoding='utf-8') as f:
                                    json.dump(vod, f, ensure_ascii=False)
                            if series and "series" not in incomplete:
                                with open(series_cache_path, 'w', encoding='utf-8') as f:
                                    json.dump(series, f, ensure_ascii=False)        
                            if (channels or vod) and not incomplete:
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
                    headers = {"User-Agent": PROVIDER_USER_AGENT}
                    downloaded_text = ""
                    try:
                        if profile_type == "m3u_file":
                            with open(profile["path"], 'r', encoding='utf-8', errors='ignore') as f:
                                downloaded_text = f.read()
                        elif profile_type == "m3u_url":
                            response = requests.get(profile["url"], timeout=30, headers=headers)
                            response.raise_for_status()
                            downloaded_text = response.text
                        if downloaded_text and ("#EXTINF" in downloaded_text or "#extinf" in downloaded_text):
                            with open(m3u_cache_path, 'w', encoding='utf-8') as f:
                                f.write(downloaded_text)
                            self._update_profile_timestamp(profile['id'], 'last_m3u_update')
                            m3u_content = downloaded_text
                        elif downloaded_text:
                            logging.warning("M3U content has no #EXTINF entries; not caching it.")
                    except Exception as e:
                         logging.error(f"M3U load error: {e}")                      
                    if not m3u_content and os.path.exists(m3u_cache_path):
                        try:
                            with open(m3u_cache_path, 'r', encoding='utf-8', errors='ignore') as f:
                                m3u_content = f.read()
                            logging.info("M3U download unusable; using the previous cached copy.")
                        except IOError:
                            m3u_content = ""
                    if not m3u_content and downloaded_text:
                        m3u_content = downloaded_text
                extracted_epg_url = None
                if m3u_content:
                    channels, vod, extracted_epg_url = parse_m3u_content(m3u_content.splitlines())                  
            auto_epg_url = None
            if profile_type == "xtream":
                host = profile.get("host")
                username = profile.get("username")
                password = profile.get("password")
                if host and username and password:
                    auto_epg_url = f"{host}/xmltv.php?username={username}&password={password}"
                    logging.info(f"[EPG] Provider (Xtream) EPG URL generated automatically: {auto_epg_url}")
            elif profile_type in ["m3u_url", "m3u_file"] and extracted_epg_url:
                auto_epg_url = extracted_epg_url
                logging.info(f"[EPG] Provider EPG URL auto-detected from M3U header: {auto_epg_url}")
            manual_epg_urls = self._get_epg_url_list(profile)
            epg_sources = ([auto_epg_url] if auto_epg_url else []) + manual_epg_urls
            if len(epg_sources) > 3:
                logging.warning(f"[EPG] {len(epg_sources)} EPG sources configured; only the first 3 (by priority) will be used.")
                epg_sources = epg_sources[:3]
            if epg_sources and not channels:
                logging.warning("[EPG] No channels were loaded; skipping EPG for this launch.")
                epg_sources = []
            if epg_sources:
                total_sources = len(epg_sources)
                logging.info(f"[EPG] {total_sources} EPG source(s) queued for profile '{profile['name']}'.")
                for idx, src in enumerate(epg_sources, start=1):
                    logging.info(f"[EPG]   priority {idx}/{total_sources}: {src}")
                downloaded_contents = []
                for index, source in enumerate(epg_sources):
                    source_num = index + 1
                    epg_cache_path = self._get_epg_source_cache_path(profile['id'], source)
                    source_hash = hashlib.md5(source.encode('utf-8')).hexdigest()
                    epg_ttl = 21600
                    last_epg_update = profile.get(f'last_epg_update_{source_hash}', 0)
                    if os.path.isfile(source):
                        try:
                            file_mtime = os.path.getmtime(source)
                            epg_is_stale = file_mtime > last_epg_update
                        except OSError:
                            epg_is_stale = True
                    else:
                        epg_is_stale = (time.time() - last_epg_update) > epg_ttl
                    epg_content = ""
                    if os.path.exists(epg_cache_path) and not epg_is_stale:
                        logging.info(f"[EPG] Source {source_num}/{total_sources}: fresh cache found, reading from disk ({epg_cache_path}).")
                        try:
                            with open(epg_cache_path, 'r', encoding='utf-8', errors='ignore') as f:
                                epg_content = f.read()
                        except IOError:
                             epg_content = ""
                    if not epg_content:
                        progress_fraction = 0.7 + (0.15 * (index / total_sources))
                        self._update_progress(progress_fraction, _("Downloading EPG source {}/{}...").format(source_num, total_sources))
                        logging.info(f"[EPG] Source {source_num}/{total_sources}: cache missing or stale, downloading from '{source}'...")
                        fresh_content = epg_provider.load_epg_data(source)
                        if fresh_content and "<programme" in fresh_content:
                            epg_content = fresh_content
                            logging.info(f"[EPG] Source {source_num}/{total_sources}: download successful ({len(epg_content)} bytes).")
                            try:
                                 with open(epg_cache_path, 'w', encoding='utf-8') as f:
                                     f.write(epg_content)
                                 self._update_profile_timestamp(profile['id'], f'last_epg_update_{source_hash}')
                            except IOError:
                                 pass
                        else:
                            if fresh_content:
                                logging.warning(f"[EPG] Source {source_num}/{total_sources}: content has no programmes; not caching it ('{source}').")
                            else:
                                logging.warning(f"[EPG] Source {source_num}/{total_sources}: download failed or returned empty content ('{source}').")
                            if os.path.exists(epg_cache_path):
                                try:
                                    with open(epg_cache_path, 'r', encoding='utf-8', errors='ignore') as f:
                                        epg_content = f.read()
                                    logging.info(f"[EPG] Source {source_num}/{total_sources}: using the previous cached copy.")
                                except IOError:
                                    epg_content = ""
                            if not epg_content and fresh_content:
                                epg_content = fresh_content
                    downloaded_contents.append(epg_content)
                self._update_progress(0.9, _("Merging EPG sources into the database..."))
                epg_data = epg_provider.parse_epg_sources(downloaded_contents, profile['id'])
            else:
                logging.info("[EPG] No EPG source configured for this profile (neither provider nor manual).")
            self._update_progress(1.0, _("Loading complete. Preparing player..."))            
            GLib.idle_add(self._on_loading_complete, profile, channels, vod, series, epg_data, None)
        except Exception as e:
            error_message = _("An unexpected error occurred while loading profile '{}'.\n\nReason: {}").format(profile['name'], e)
            logging.exception(f"Critical error while loading profile: {profile['name']}")
            GLib.idle_add(self._on_loading_complete, profile, {}, {}, {}, {}, error_message)

    def _on_loading_complete(self, profile, channels, vod, series, epg_data, error):
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
            player_window = MainWindow(application=app, profile=profile, channels=channels, vod=vod, series=series, epg_data=epg_data)
            player_window.present()
            self._check_and_show_changelog(player_window)
            self.close()

    def _check_and_show_changelog(self, parent_window):
        from core.config import VERSION
        from core.changelog import CHANGELOG
        from ui.changelog_dialog import ChangelogDialog
        last_seen = database.get_config_value('last_seen_changelog_version')
        if last_seen != VERSION and VERSION in CHANGELOG:
            attempts = [0]

            def _present():
                attempts[0] += 1
                if not parent_window.get_mapped() and attempts[0] < 10:
                    return GLib.SOURCE_CONTINUE
                ChangelogDialog(parent_window, VERSION, CHANGELOG).present()
                return GLib.SOURCE_REMOVE
            GLib.timeout_add(500, _present)
            database.set_config_value('last_seen_changelog_version', VERSION)
            
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
        dialog.add_css_class("delete-profile-dialog")
        dialog.add_response("cancel", _("Cancel")); dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_delete_confirm_response, profile_to_delete.get("id")); dialog.present()

    def _on_delete_confirm_response(self, dialog, response_id, profile_id):
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
                epg_db_path = os.path.join(database.get_cache_path(), f"epg_data_{safe_id}.db")
                logging.info(f"Deleting database and cache files for profile '{profile_name}'...")
                files_to_delete = [
                    self._get_cache_path(profile_id, 'm3u_cache'),
                    self._get_cache_path(profile_id, 'epg_cache'),
                    self._get_xtream_cache_path(profile_id, 'channels'),
                    self._get_xtream_cache_path(profile_id, 'vod'),
                    self._get_xtream_cache_path(profile_id, 'series'),
                    profile_db_path,
                    epg_db_path
                ]
                epg_cache_dir = os.path.join(database.get_cache_path(), 'epg_cache')
                if os.path.isdir(epg_cache_dir):
                    for fname in os.listdir(epg_cache_dir):
                        if fname.startswith(f"{safe_id}_"):
                            files_to_delete.append(os.path.join(epg_cache_dir, fname))
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
                new_profile["epg_urls"] = [e.get_text().strip() for e in dialog.epg_url_entries if e.get_text().strip()][:3]
            selected_icon_path = dialog.icon_path_label.get_text()
            if dialog.icon_switch.get_active() and os.path.isdir(selected_icon_path):
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
                    new_epg_urls = [e.get_text().strip() for e in dialog.epg_url_entries if e.get_text().strip()][:3]
                    old_epg_urls = p.get("epg_urls")
                    if old_epg_urls is None:
                        legacy_epg_url = p.get("epg_url")
                        old_epg_urls = [legacy_epg_url] if legacy_epg_url else []
                    removed_epg_urls = [u for u in old_epg_urls if u and u not in new_epg_urls]
                    for removed_url in removed_epg_urls:
                        stale_cache_path = self._get_epg_source_cache_path(profile_id, removed_url)
                        try:
                            if os.path.exists(stale_cache_path):
                                os.remove(stale_cache_path)
                                logging.info(f"[EPG] Removed stale cache file for deleted source: {removed_url}")
                        except OSError as e:
                            logging.warning(f"[EPG] Could not remove stale cache file for '{removed_url}': {e}")
                    p["epg_urls"] = new_epg_urls
                    p.pop("epg_url", None)
                    selected_icon_path = dialog.icon_path_label.get_text()
                    if dialog.icon_switch.get_active() and os.path.isdir(selected_icon_path):
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
        dialog.add_css_class("profile-editor-dialog")
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
        epg_header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        epg_title_label = Gtk.Label(label=_("Manual EPG Sources"), halign=Gtk.Align.START)
        epg_title_label.add_css_class("heading")
        epg_subtitle_label = Gtk.Label(
            label=_("Optional, max 3 — provider EPG always has priority"),
            halign=Gtk.Align.START,
            wrap=True
        )
        epg_subtitle_label.add_css_class("caption")
        epg_subtitle_label.add_css_class("dim-label")
        epg_header_box.append(epg_title_label)
        epg_header_box.append(epg_subtitle_label)
        content.append(epg_header_box)
        epg_urls_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        epg_url_entries = []

        def _add_epg_url_row(initial_text=""):
            if len(epg_url_entries) >= 3:
                return
            row = Gtk.Box(spacing=6)
            entry = Gtk.Entry(placeholder_text=_("External EPG URL (XMLTV)"), hexpand=True)
            entry.set_text(initial_text)
            remove_btn = Gtk.Button(icon_name="list-remove-symbolic")

            def on_remove_clicked(btn):
                epg_urls_box.remove(row)
                epg_url_entries.remove(entry)
                add_epg_row_button.set_sensitive(len(epg_url_entries) < 3)
            remove_btn.connect("clicked", on_remove_clicked)
            row.append(entry)
            row.append(remove_btn)
            epg_urls_box.append(row)
            epg_url_entries.append(entry)
            add_epg_row_button.set_sensitive(len(epg_url_entries) < 3)
        add_epg_row_button = Gtk.Button(label=_("+ Add EPG Source"))
        add_epg_row_button.connect("clicked", lambda btn: _add_epg_url_row())
        content.append(epg_urls_box)
        content.append(add_epg_row_button)
        icon_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_top=6)
        icon_title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        icon_title_label = Gtk.Label(label=_("External Channel Logos"), halign=Gtk.Align.START)
        icon_title_label.add_css_class("heading")
        icon_subtitle_label = Gtk.Label(
            label=_("Optional — use a local folder of logo images matched by channel name"),
            halign=Gtk.Align.START,
            wrap=True
        )
        icon_subtitle_label.add_css_class("caption")
        icon_subtitle_label.add_css_class("dim-label")
        icon_title_box.append(icon_title_label)
        icon_title_box.append(icon_subtitle_label)
        icon_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        icon_header_box.append(icon_title_box)
        icon_header_box.append(icon_switch)
        content.append(icon_header_box)
        icon_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        icon_folder_box = Gtk.Box(spacing=6)
        icon_path_label = Gtk.Label(label=_("No icon folder selected..."), halign=Gtk.Align.START, hexpand=True)
        icon_choose_button = Gtk.Button(label=_("Choose Folder..."))
        icon_folder_box.append(icon_path_label)
        icon_folder_box.append(icon_choose_button)
        icon_revealer.set_child(icon_folder_box)
        content.append(icon_revealer)
        icon_switch.connect("notify::active", lambda sw, p: icon_revealer.set_reveal_child(sw.get_active()))

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
            existing_epg_urls = profile_data.get("epg_urls")
            if existing_epg_urls is None:
                legacy_epg_url = profile_data.get("epg_url", "")
                existing_epg_urls = [legacy_epg_url] if legacy_epg_url else []
            existing_epg_urls = [u for u in existing_epg_urls if u][:3]
            if existing_epg_urls:
                for url in existing_epg_urls:
                    _add_epg_url_row(url)
            else:
                _add_epg_url_row()
            icon_path_label.set_text(profile_data.get("icon_path", _("No icon folder selected...")))
            existing_icon_path = profile_data.get("icon_path", "")
            icon_switch.set_active(bool(existing_icon_path))
            icon_revealer.set_reveal_child(bool(existing_icon_path))
        else:
            _add_epg_url_row()
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save"))
        dialog.name_entry = name_entry
        dialog.profile_type_combo = profile_type_combo
        dialog.url_entry = url_entry
        dialog.file_path_label = file_path_label
        dialog.xtream_host_entry = xtream_host_entry
        dialog.xtream_user_entry = xtream_user_entry
        dialog.xtream_pass_entry = xtream_pass_entry
        dialog.epg_url_entries = epg_url_entries
        dialog.icon_path_label = icon_path_label
        dialog.icon_switch = icon_switch
        return dialog

    def apply_accent_color(self, color_str):
        if not color_str: return
        css_provider = Gtk.CssProvider()
        css_data = f"""
        @define-color accent_color {color_str}; 
        @define-color accent_bg_color {color_str}; 
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
           

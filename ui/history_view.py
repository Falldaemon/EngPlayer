# ui/history_view.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Adw, Pango, GLib, GdkPixbuf
import gettext
import logging
import database
import urllib.request
import os
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlparse
from background import image_download_pool
from ui.placeholder_icon import PlaceholderIcon

_ = gettext.gettext
_failed_logo_hosts = set()
try:
    from thefuzz import fuzz, process
    FUZZ_AVAILABLE = True
except ImportError:
    try:
        from fuzzywuzzy import fuzz, process
        FUZZ_AVAILABLE = True
    except ImportError:
        FUZZ_AVAILABLE = False

class HistoryRow(Gtk.ListBoxRow):
    def __init__(self, channel_data):
        super().__init__()
        self.channel_data = channel_data
        self.correct_logo_path = None
        self.epg_label = None
        self.epg_progress = None       
        self.hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.hbox.set_margin_start(10)
        self.hbox.set_margin_end(10)
        self.hbox.set_margin_top(8)
        self.hbox.set_margin_bottom(8)
        self.set_child(self.hbox)
        self.logo_container = Gtk.Box()
        self.logo_container.set_size_request(46, 46)
        self.logo_container.set_valign(Gtk.Align.CENTER)      
        self.placeholder = PlaceholderIcon()
        self.placeholder.set_size_request(36, 36)
        self.placeholder.set_halign(Gtk.Align.CENTER)
        self.placeholder.set_valign(Gtk.Align.CENTER)
        self.logo_container.append(self.placeholder)
        self.hbox.append(self.logo_container)
        self.label_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.label_vbox.set_hexpand(True)
        self.label_vbox.set_valign(Gtk.Align.CENTER)       
        name = channel_data.get("name", _("Unknown Channel"))
        self.name_label = Gtk.Label(label=name, xalign=0)
        self.name_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.label_vbox.append(self.name_label)       
        self.hbox.append(self.label_vbox)

class HistoryView(Gtk.Box):
    
    __gsignals__ = {
        'channel-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,))
    }

    def __init__(self, main_window=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        self.main_window = main_window 
        self.epg_update_timer_id = None
        self._failed_epg_searches = set()
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(12)
        header_box.set_margin_start(12)
        header_box.set_margin_end(12)       
        self.search_entry = Gtk.SearchEntry(placeholder_text=_("Search History..."))
        self.search_entry.connect("search-changed", self._on_search_changed)
        header_box.append(self.search_entry)      
        self.clear_button = Gtk.Button(label=_("Clear History"))
        self.clear_button.add_css_class("destructive-action") 
        self.clear_button.connect("clicked", self._on_clear_clicked)
        header_box.append(self.clear_button)       
        self.append(header_box)
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_vexpand(True)       
        self.history_listbox = Gtk.ListBox()
        self.history_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.history_listbox.add_css_class("navigation-sidebar")
        self.history_listbox.connect("row-activated", self._on_row_activated)        
        self.scrolled_window.set_child(self.history_listbox)
        self.append(self.scrolled_window)

    def populate(self):
        if self.epg_update_timer_id:
            GLib.source_remove(self.epg_update_timer_id)
            self.epg_update_timer_id = None          
        self.history_listbox.remove_all()
        self._failed_epg_searches.clear()
        history_data = database.get_channel_history()      
        if not history_data:
            placeholder = Gtk.Label(label=_("No history found."))
            placeholder.set_margin_top(20)
            placeholder.add_css_class("dim-label")
            self.history_listbox.append(placeholder)
            self.clear_button.set_sensitive(False)
            return          
        self.clear_button.set_sensitive(True)
        logo_map = {}
        epg_data = None
        epg_clean_map = None
        if self.main_window:
            if hasattr(self.main_window, 'logo_map'): logo_map = self.main_window.logo_map
            if hasattr(self.main_window, 'epg_data'): epg_data = self.main_window.epg_data
            if hasattr(self.main_window, 'epg_clean_map'): epg_clean_map = self.main_window.epg_clean_map
        self._epg_available = bool(epg_data)
        for channel in history_data:
            row = HistoryRow(channel)
            epg_info = self._get_current_program_info(channel, epg_data, epg_clean_map)
            if epg_info:
                row.epg_label = Gtk.Label(label=epg_info['title'], xalign=0)
                row.epg_label.set_ellipsize(Pango.EllipsizeMode.END)
                row.epg_label.add_css_class("caption")
                row.label_vbox.append(row.epg_label)
                if epg_info['progress'] is not None:
                    row.epg_progress = Gtk.ProgressBar()
                    row.epg_progress.set_fraction(epg_info['progress'])
                    row.epg_progress.add_css_class("epg-progress-bar")
                    row.label_vbox.append(row.epg_progress)
            logo_to_load = self._find_logo_path(channel, logo_map)
            row.correct_logo_path = logo_to_load
            if logo_to_load and logo_to_load.strip():
                self._load_logo_and_replace(logo_to_load, row.placeholder)
            self.history_listbox.append(row)
        if self._epg_available:
            self.epg_update_timer_id = GLib.timeout_add_seconds(60, self._update_all_rows_epg)

    def _on_row_activated(self, listbox, row):
        if hasattr(row, 'channel_data'):
            self.emit('channel-selected', row) 

    def _on_search_changed(self, entry):
        search_text = entry.get_text().lower()
        row = self.history_listbox.get_first_child()
        while row:
            if hasattr(row, 'channel_data'):
                name = row.channel_data.get("name", "").lower()
                row.set_visible(search_text in name)
            row = row.get_next_sibling()

    def _on_clear_clicked(self, button):
        if not self.main_window:
            self._perform_clear()
            return          
        dialog = Adw.MessageDialog(
            transient_for=self.main_window,
            heading=_("Clear History"),
            body=_("Are you sure you want to clear your watched channel history?"),
            modal=True
        )
        dialog.add_css_class("delete-confirm-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("clear", _("Clear"))
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_clear_confirm)
        dialog.present()

    def _on_clear_confirm(self, dialog, response_id):
        if response_id == "clear":
            self._perform_clear()

    def _perform_clear(self):
        if database.clear_channel_history():
            self.populate()
            if self.main_window and hasattr(self.main_window, 'show_toast'):
                self.main_window.show_toast(_("History cleared."))
        else:
            if self.main_window and hasattr(self.main_window, 'show_toast'):
                self.main_window.show_toast(_("Error clearing history."))

    def _clean_key(self, text):
        if not text: return None
        name = text.lower().strip()
        match = re.match(r'^([a-z]{2,3})[| \-_]+(.*)', name)
        if match:
            lang_code = match.group(1)
            rest_of_name = match.group(2)
            common_codes = ["tr", "us", "uk", "fr", "de", "it", "es", "pt", "nl", "be", 
                            "ru", "gr", "az", "ch", "at", "pl", "ro", "bg", "hu", "cz", 
                            "sk", "al", "rs", "hr", "ba", "mk", "se", "no", "dk", "fi", 
                            "ie", "ca", "au", "nz", "br", "ar", "mx", "ae", "sa", "eg",
                            "tur", "usa", "gbr", "fra", "deu", "ita", "esp", "prt", "nld", "bel",
                            "rus", "grc", "aze", "che", "aut", "pol", "rou", "bgr", "hun", "cze"]
            if lang_code in common_codes:
                name = f"{rest_of_name}.{lang_code}"
        try:
            name = unicodedata.normalize("NFKD", name)
            name = "".join([c for c in name if not unicodedata.combining(c)])
        except Exception: pass
        name = re.sub(r'(\(.*\))|(\[.*?\])|(".*?")|(\=.*)', ' ', name)
        name = re.sub(r'\b(HD|FHD|UHD|4K|8K|SD)\b', ' ', name, flags=re.IGNORECASE)
        name = re.sub(r'[^\w\d\s.]+', ' ', name)
        name = re.sub(r'\s+', '', name)       
        return name.strip().lower()

    def _check_digits_match(self, str1, str2):
        d1 = "".join(re.findall(r'\d', str1))
        d2 = "".join(re.findall(r'\d', str2))
        return d1 == d2   
        
    def _check_country_match(self, key1, key2):
        if "." in key1 and "." in key2:
            return key1.split(".")[-1] == key2.split(".")[-1]
        if "." in key2:
            epg_suffix = key2.split(".")[-1].lower()
            if 2 <= len(epg_suffix) <= 3:
                channel_prefix = key1[:len(epg_suffix)].lower()               
                if channel_prefix != epg_suffix:
                    common_iso_codes = ["tr", "us", "uk", "fr", "de", "it", "es", "pt", "nl", "be", 
                                        "ru", "gr", "az", "ch", "at", "pl", "ro", "bg", "hu", "cz", 
                                        "sk", "al", "rs", "hr", "ba", "mk", "se", "no", "dk", "fi"]
                    if channel_prefix in common_iso_codes:
                        return False               
        return True             

    def _find_logo_path(self, channel_data, logo_map):
        fallback_logo_url = channel_data.get("logo")
        if not logo_map: return fallback_logo_url
        t_id = (channel_data.get("tvg-id") or "").strip()
        t_name = (channel_data.get("tvg-name") or "").strip()
        name = (channel_data.get("name") or "").strip()
        search_keys = []
        for raw_val in [t_id, t_name, name]:
            if raw_val:
                clean = self._clean_key(raw_val)
                if clean and clean not in search_keys:
                    search_keys.append(clean)
        for clean_key in search_keys:
            if clean_key in logo_map:
                return logo_map[clean_key]
        if FUZZ_AVAILABLE and search_keys:
            primary_key = search_keys[0]
            best_match_tuple = process.extractOne(primary_key, logo_map.keys())           
            if best_match_tuple:
                best_match, score = best_match_tuple
                if score >= 80 and \
                   self._check_digits_match(primary_key, best_match) and \
                   self._check_country_match(primary_key, best_match):
                    len1, len2 = len(primary_key), len(best_match)
                    ratio = max(len1, len2) / min(len1, len2) if min(len1, len2) > 0 else 0
                    first_char_match = primary_key[0] == best_match[0]                   
                    if ratio <= 2.0 and first_char_match:
                        return logo_map[best_match]
        return fallback_logo_url

    def _load_logo_and_replace(self, url, placeholder_widget):
        try:
            host = urlparse(url).netloc
            if host in _failed_logo_hosts: return
        except: pass      
        if not placeholder_widget or not placeholder_widget.get_ancestor(Gtk.ListBoxRow):
             return
             
        def thread_func():
            try:
                host = urlparse(url).netloc
                if host in _failed_logo_hosts: return
            except: pass
            pixbuf = None
            try:
                if url.lower().startswith("http"):
                    headers = {"User-Agent": "Mozilla/5.0"}
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        data = resp.read()
                else:
                    if os.path.exists(url):
                         with open(url, "rb") as f: data = f.read()
                    else: data = None
                if data:
                    loader = GdkPixbuf.PixbufLoader.new()
                    loader.write(data)
                    loader.close()
                    pixbuf = loader.get_pixbuf()
            except Exception as e:
                 try:
                     bad_host = urlparse(url).netloc
                     if bad_host not in _failed_logo_hosts:
                         _failed_logo_hosts.add(bad_host)
                 except: pass
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
        return GLib.SOURCE_REMOVE

    def _get_current_program_info(self, channel, epg_data=None, epg_clean_map=None):
        if not getattr(self, '_epg_available', False):
            return None
        t_id = (channel.get("tvg-id") or "").strip()
        t_name = (channel.get("tvg-name") or "").strip()
        name = (channel.get("name") or "").strip()
        search_key = t_id or t_name or name       
        if not search_key or search_key in self._failed_epg_searches:
            return None    
        programs = database.get_epg_programs(search_key)      
        if not programs:
            clean_id = self._clean_key(search_key)
            if clean_id:
                programs = database.get_epg_programs(clean_id)              
                if not programs and FUZZ_AVAILABLE and process:
                    all_db_keys = database.get_all_epg_channel_ids()
                    if all_db_keys:
                        best_match_tuple = process.extractOne(clean_id, all_db_keys)
                        if best_match_tuple:
                            best_match, score = best_match_tuple
                            if score >= 80 and \
                               self._check_digits_match(clean_id, best_match) and \
                               self._check_country_match(clean_id, best_match):
                                len1, len2 = len(clean_id), len(best_match)
                                ratio = max(len1, len2) / min(len1, len2) if min(len1, len2) > 0 else 0
                                first_char_match = clean_id[0].lower() == best_match[0].lower() if clean_id and best_match else False
                                if ratio <= 2.0 and first_char_match:
                                    programs = database.get_epg_programs(best_match)                                 
                if not programs:
                    soft_id = clean_id.replace("tv.", ".")
                    programs = database.get_epg_programs(soft_id)                      
        if not programs:
            self._failed_epg_searches.add(search_key)
            return None                     
        now = datetime.now(timezone.utc)
        for prog in programs:
            if prog['start'] <= now <= prog['stop']:
                total_duration = (prog['stop'] - prog['start']).total_seconds()
                elapsed_time = (now - prog['start']).total_seconds()
                fraction = max(0.0, min(1.0, elapsed_time / total_duration)) if total_duration > 0 else 0.0
                return {'title': prog['title'], 'progress': fraction}
        return None

    def _update_all_rows_epg(self):
        row = self.history_listbox.get_first_child()      
        while row:
            if hasattr(row, 'channel_data'):
                epg_info = self._get_current_program_info(row.channel_data)
                if epg_info:
                    if not row.epg_label:
                        row.epg_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
                        row.epg_label.add_css_class("caption")
                        row.label_vbox.append(row.epg_label)
                    row.epg_label.set_text(epg_info['title'])                   
                    if epg_info['progress'] is not None:
                        if not row.epg_progress:
                            row.epg_progress = Gtk.ProgressBar()
                            row.epg_progress.add_css_class("epg-progress-bar")
                            row.label_vbox.append(row.epg_progress)
                        row.epg_progress.set_fraction(epg_info['progress'])
                else:
                    if row.epg_label:
                        row.label_vbox.remove(row.epg_label)
                        row.epg_label = None
                    if row.epg_progress:
                        row.label_vbox.remove(row.epg_progress)
                        row.epg_progress = None
            row = row.get_next_sibling()
        return True

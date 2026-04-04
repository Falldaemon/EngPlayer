# ui/global_search_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Pango, Adw
import logging
import gettext

_ = gettext.gettext

class GlobalSearchDialog(Adw.Window):
    def __init__(self, main_window):
        super().__init__(transient_for=main_window)
        self.main_window = main_window
        self.active_category = None 
        self.set_default_size(600, 550)
        self.set_modal(True)
        self.set_hide_on_close(True)
        self.add_css_class("global-search-dialog")       
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)       
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label=_("Global Search"), css_classes=["title"]))
        main_box.append(header)        
        self.root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.root_box.set_margin_top(15)
        self.root_box.set_margin_bottom(15)
        self.root_box.set_margin_start(15)
        self.root_box.set_margin_end(15)
        main_box.append(self.root_box)
        self.button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0, halign=Gtk.Align.CENTER)
        self.button_box.add_css_class("linked") 
        self.root_box.append(self.button_box)
        self.btn_live = Gtk.ToggleButton(label=_("Live TV"))
        self.btn_vod = Gtk.ToggleButton(label=_("VOD"), group=self.btn_live)
        self.btn_series = Gtk.ToggleButton(label=_("Series"), group=self.btn_live)
        self.btn_live.connect("toggled", self.on_category_toggled, "live")
        self.btn_vod.connect("toggled", self.on_category_toggled, "vod")
        self.btn_series.connect("toggled", self.on_category_toggled, "series")
        self.button_box.append(self.btn_live)
        self.button_box.append(self.btn_vod)
        self.button_box.append(self.btn_series)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Please select a category first..."))
        self.search_entry.set_sensitive(False)
        self.root_box.append(self.search_entry)
        self.scrolled_window = Gtk.ScrolledWindow(vexpand=True, min_content_height=350)
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.root_box.append(self.scrolled_window)
        self.results_listbox = Gtk.ListBox()
        self.results_listbox.add_css_class("boxed-list")
        self.results_listbox.connect("row-activated", self.on_result_activated)
        self.scrolled_window.set_child(self.results_listbox)
        self.search_timeout_id = None
        self.search_entry.connect("search-changed", self.on_search_changed)

    def on_category_toggled(self, button, category):
        if button.get_active():
            self.active_category = category
            self.search_entry.set_sensitive(True)
            self.search_entry.set_placeholder_text(_("Search in {}...").format(button.get_label()))
            self.search_entry.grab_focus()
            if self.search_entry.get_text().strip():
                self.on_search_changed(self.search_entry)
        else:
            if not any([self.btn_live.get_active(), self.btn_vod.get_active(), self.btn_series.get_active()]):
                self.active_category = None
                self.search_entry.set_sensitive(False)
                self.search_entry.set_placeholder_text(_("Please select a category first..."))

    def on_search_changed(self, entry):
        if self.search_timeout_id:
            GLib.source_remove(self.search_timeout_id)          
        search_text = entry.get_text().strip()
        if len(search_text) > 2 and self.active_category:
            self.search_timeout_id = GLib.timeout_add(400, self._perform_search, search_text)
        else:
            self._clear_results()

    def _perform_search(self, search_text):
        self.search_timeout_id = None 
        self._clear_results()       
        search_text = search_text.lower().strip()
        search_words = search_text.split()
        results = []
    
        def get_match_score(name_lower):
            if name_lower == search_text:
                return 0 
            elif name_lower.startswith(search_text + " ") or name_lower.startswith(search_text + "-"):
                return 1 
            elif name_lower.startswith(search_text):
                return 2 
            elif f" {search_text} " in name_lower or f"-{search_text} " in name_lower:
                return 3 
            else:
                return 4 
        if self.active_category == "live":
            if hasattr(self.main_window, 'bouquets_data') and self.main_window.bouquets_data:
                for bouquet_name, channels in self.main_window.bouquets_data.items():
                    for channel in channels:
                        name = channel.get('name', '')
                        name_lower = name.lower()
                        if all(word in name_lower for word in search_words):
                            score = get_match_score(name_lower)
                            results.append({'title': name, 'category': bouquet_name, 'type': 'iptv', 'data': channel, 'score': score})
        elif self.active_category == "vod":
            if hasattr(self.main_window, 'vod_data') and self.main_window.vod_data:
                for cat_name, items in self.main_window.vod_data.items():
                    for item in items:
                        name = item.get('name', '')
                        name_lower = name.lower()
                        if all(word in name_lower for word in search_words):
                            score = get_match_score(name_lower)
                            results.append({'title': name, 'category': cat_name, 'type': 'vod', 'data': item, 'score': score})
        elif self.active_category == "series":
            if hasattr(self.main_window, 'series_data') and self.main_window.series_data:
                 for cat_name, items in self.main_window.series_data.items():
                    for item in items:
                        name = item.get('name', '')
                        name_lower = name.lower()
                        if all(word in name_lower for word in search_words):
                            score = get_match_score(name_lower)
                            results.append({'title': name, 'category': cat_name, 'type': 'series', 'data': item, 'score': score})
        results.sort(key=lambda x: (x['score'], x['title'].lower()))      
        self._populate_results(results)
        return GLib.SOURCE_REMOVE

    def _populate_results(self, results):
        if not results:
            empty_label = Gtk.Label(label=_("No results found..."))
            empty_label.set_margin_top(20)
            self.results_listbox.append(empty_label)
            return
        for res in results[:350]:
            row = Gtk.ListBoxRow()
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            hbox.set_margin_top(8)
            hbox.set_margin_bottom(8)
            hbox.set_margin_start(10)
            hbox.set_margin_end(10)                     
            icon_name = "tv-symbolic" if res['type'] == 'iptv' else "video-x-generic-symbolic"
            hbox.append(Gtk.Image.new_from_icon_name(icon_name))                   
            title_label = Gtk.Label(label=res['title'], xalign=0, hexpand=True)
            title_label.set_ellipsize(Pango.EllipsizeMode.END)
            hbox.append(title_label)                   
            cat_label = Gtk.Label(label=f"[{res['category']}]")
            cat_label.add_css_class("dim-label")
            hbox.append(cat_label)                    
            row.set_child(hbox)
            row.result_data = res 
            self.results_listbox.append(row)

    def _clear_results(self):
        while child := self.results_listbox.get_first_child():
            self.results_listbox.remove(child)

    def on_result_activated(self, listbox, row):
        if not hasattr(row, 'result_data'): return
        data = row.result_data
        item_data = data['data']
        res_type = data['type']     
        self.set_visible(False)
        logging.info(f"Global Search: '{data['title']}' selected (Type: {res_type}).")
        if res_type == 'iptv':
            self.main_window._play_channel(item_data)           
        elif res_type == 'vod':
            self.main_window.show_vod_details_from_search(item_data)          
        elif res_type == 'series':
            series_id = item_data.get('series_id') or item_data.get('id')
            if series_id:
                self.main_window.show_series_details_from_search(series_id)
            else:
                logging.warning("Search: Series ID not found!")

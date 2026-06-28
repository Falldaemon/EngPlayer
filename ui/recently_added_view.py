# ui/recently_added_view.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Adw, GLib
import threading
import gettext
import logging
import database

_ = gettext.gettext

class RecentlyAddedView(Gtk.Box):
    
    __gsignals__ = {
        "timeframe-selected": (GObject.SignalFlags.RUN_FIRST, None, (object, str, str))
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_spacing(24)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.status_page = Adw.StatusPage()
        self.status_page.set_title(_("Recently Added"))
        self.status_page.set_description(_("Select a time period to view the latest additions."))
        self.status_page.set_icon_name("document-open-recent-symbolic")
        self.append(self.status_page)
        self.spinner = Gtk.Spinner()
        self.append(self.spinner)
        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_size_request(400, -1)
        self.append(self.listbox)
        self.current_media_type = "vod"
        self._create_ui_rows()
        self._set_ui_state(is_loading=False)

    def _create_ui_rows(self):
        self.row_daily = Adw.ActionRow(title=_("Last 24 Hours"))
        self.row_daily.set_activatable(True)
        self.row_daily.add_prefix(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        self.row_daily.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self.row_daily.connect("activated", lambda r: self._on_timeframe_clicked(1, _("Last 24 Hours")))
        self.listbox.append(self.row_daily)
        self.row_weekly = Adw.ActionRow(title=_("Last 7 Days"))
        self.row_weekly.set_activatable(True)
        self.row_weekly.add_prefix(Gtk.Image.new_from_icon_name("x-office-calendar-symbolic"))
        self.row_weekly.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self.row_weekly.connect("activated", lambda r: self._on_timeframe_clicked(7, _("Last 7 Days")))
        self.listbox.append(self.row_weekly)
        self.row_monthly = Adw.ActionRow(title=_("Last 30 Days"))
        self.row_monthly.set_activatable(True)
        self.row_monthly.add_prefix(Gtk.Image.new_from_icon_name("view-calendar-symbolic"))
        self.row_monthly.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self.row_monthly.connect("activated", lambda r: self._on_timeframe_clicked(30, _("Last 30 Days")))
        self.listbox.append(self.row_monthly)

    def _set_ui_state(self, is_loading):
        if is_loading:
            self.spinner.start()
            self.spinner.set_visible(True)
            self.listbox.set_visible(False)
            self.status_page.set_description(_("Fetching data from database..."))
        else:
            self.spinner.stop()
            self.spinner.set_visible(False)
            self.listbox.set_visible(True)
            self.status_page.set_description(_("Select a time period to view the latest additions."))

    def populate(self, media_type="vod", profile_id="default"):
        self.current_media_type = media_type
        count_daily = database.get_recent_media_count_from_cache(media_type, 1)
        count_weekly = database.get_recent_media_count_from_cache(media_type, 7)
        count_monthly = database.get_recent_media_count_from_cache(media_type, 30)
        item_word = _("Movies") if self.current_media_type == "vod" else _("Series")
        self.row_daily.set_subtitle(f"{count_daily} {item_word}")
        self.row_weekly.set_subtitle(f"{count_weekly} {item_word}")
        self.row_monthly.set_subtitle(f"{count_monthly} {item_word}")
        self.row_daily.set_sensitive(count_daily > 0)
        self.row_weekly.set_sensitive(count_weekly > 0)
        self.row_monthly.set_sensitive(count_monthly > 0)      
        self._set_ui_state(is_loading=False)

    def _on_timeframe_clicked(self, days, title):
        self._set_ui_state(is_loading=True)
        
        def fetch_from_db():
            media_list = database.get_recent_media_from_cache(self.current_media_type, days)
            GLib.idle_add(self._on_db_fetch_finished, media_list, title)          
        threading.Thread(target=fetch_from_db, daemon=True).start()

    def _on_db_fetch_finished(self, media_list, title):
        self._set_ui_state(is_loading=False)
        self.emit("timeframe-selected", media_list, title, self.current_media_type)

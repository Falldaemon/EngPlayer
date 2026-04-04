# ui/category_manager_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import database
import gettext

_ = gettext.gettext

class CategoryManagerDialog(Adw.Window):
    def __init__(self, parent, live_cats, vod_cats, series_cats):
        super().__init__(transient_for=parent, modal=True)
        self.set_default_size(500, 600)
        self.set_title(_("Manage Hidden Categories"))
        self.add_css_class("category-manager-dialog")
        self.switches = {"live": {}, "vod": {}, "series": {}}      
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(content_box)
        header = Adw.HeaderBar()
        content_box.append(header)       
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        info_label = Gtk.Label(label=_("Turn ON the switch to HIDE the category."), css_classes=["dim-label"])
        info_box.append(info_label)
        content_box.append(info_box)      
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_vexpand(True)            
        switcher_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER, margin_bottom=10)
        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self.stack)
        switcher_box.append(switcher)
        content_box.append(switcher_box)
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER, spacing=10, margin_bottom=10)      
        btn_show_all = Gtk.Button(label=_("Show All"))
        btn_show_all.connect("clicked", self._on_show_all_clicked)       
        btn_hide_all = Gtk.Button(label=_("Hide All"))
        btn_hide_all.connect("clicked", self._on_hide_all_clicked)       
        action_box.append(btn_show_all)
        action_box.append(btn_hide_all)
        content_box.append(action_box)        
        content_box.append(self.stack)
        self.hidden_set = database.get_hidden_bouquets()
        self.live_page = self._create_list_page(live_cats, "live")
        self.vod_page = self._create_list_page(vod_cats, "vod")
        self.series_page = self._create_list_page(series_cats, "series")       
        self.stack.add_titled(self.live_page, "live", _("Bouquets"))
        self.stack.add_titled(self.vod_page, "vod", _("VOD"))
        self.stack.add_titled(self.series_page, "series", _("Series"))

    def _create_list_page(self, categories, page_name):
        if not categories:
            empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
            empty_box.append(Gtk.Label(label=_("No categories found."), css_classes=["dim-label"]))
            return empty_box           
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        clamp = Adw.Clamp()
        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        sorted_cats = sorted(categories)            
        for cat_name in sorted_cats:
            row = Adw.ActionRow(title=cat_name)           
            toggle = Gtk.Switch()
            toggle.set_valign(Gtk.Align.CENTER)
            is_hidden = cat_name in self.hidden_set
            toggle.set_active(is_hidden)
            toggle.connect("notify::active", self._on_toggle_changed, cat_name)          
            row.add_suffix(toggle)
            listbox.append(row)
            self.switches[page_name][cat_name] = toggle           
        clamp.set_child(listbox)
        scrolled.set_child(clamp)
        return scrolled

    def _on_toggle_changed(self, switch, pspec, cat_name):
        is_hidden = switch.get_active()
        database.set_bouquet_hidden_status(cat_name, is_hidden)
        
    def _on_hide_all_clicked(self, button):
        current_page = self.stack.get_visible_child_name()
        if current_page and current_page in self.switches:
            for cat_name, switch in self.switches[current_page].items():
                if not switch.get_active():
                    switch.set_active(True)

    def _on_show_all_clicked(self, button):
        current_page = self.stack.get_visible_child_name()
        if current_page and current_page in self.switches:
            for cat_name, switch in self.switches[current_page].items():
                if switch.get_active():
                    switch.set_active(False)

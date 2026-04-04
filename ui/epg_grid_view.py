# ui/epg_grid_view.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Pango, GLib, Gio, Adw
from datetime import datetime, timedelta
import database
import logging
import gettext

_ = gettext.gettext

class EpgGridView(Gtk.Box):
    __gsignals__ = {
        "close-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "channel-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "schedule-recording": (GObject.SignalFlags.RUN_FIRST, None, (str, str, int, int, str))
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.add_css_class("view-bg") 
        self.timer_id = None
        self.now_line = None
        self.selected_channel_data = None       
        self._rendered_grid_rows = {}
        self._rendered_list_cols = {}
        self._grid_scroll_idle_id = None
        self._list_scroll_idle_id = None
        self._grid_data_to_render = []     
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_box.set_margin_top(12); header_box.set_margin_start(12)
        header_box.set_margin_end(12); header_box.set_margin_bottom(12)                   
        back_btn = Gtk.Button(icon_name="go-previous-symbolic")
        back_btn.set_tooltip_text(_("Close and Return"))
        back_btn.add_css_class("flat")
        back_btn.connect("clicked", self._on_back_clicked)
        header_box.append(back_btn)             
        title_label = Gtk.Label(label=_("Advanced EPG"))
        title_label.add_css_class("title-1") 
        title_label.set_hexpand(True)
        title_label.set_xalign(0)
        header_box.append(title_label)     
        self.view_menu_model = Gio.Menu()
        self.view_menu_model.append(_("Grid View"), "epg.view_grid")
        self.view_menu_model.append(_("List View"), "epg.view_list")
        self.view_popover = Gtk.PopoverMenu.new_from_model(self.view_menu_model)             
        self.view_button = Gtk.MenuButton()
        self.view_button.set_icon_name("view-grid-symbolic")
        self.view_button.set_popover(self.view_popover)
        self.view_button.set_tooltip_text(_("Change View"))
        header_box.append(self.view_button)      
        action_group = Gio.SimpleActionGroup()
        grid_action = Gio.SimpleAction.new("view_grid", None)
        grid_action.connect("activate", self._on_view_grid_selected)
        action_group.add_action(grid_action)
        list_action = Gio.SimpleAction.new("view_list", None)
        list_action.connect("activate", self._on_view_list_selected)
        action_group.add_action(list_action)
        self.insert_action_group("epg", action_group)
        self.append(header_box)             
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_content.set_margin_start(20); main_content.set_margin_end(20)
        main_content.set_margin_bottom(20); main_content.set_vexpand(True)
        self.append(main_content)             
        top_panel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        main_content.append(top_panel)             
        self.video_cage = Gtk.ScrolledWindow()
        self.video_cage.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        self.video_cage.set_size_request(400, 230)
        self.video_cage.set_valign(Gtk.Align.START)      
        self.video_frame = Gtk.AspectFrame(ratio=16/9, obey_child=False)
        self.video_frame.add_css_class("card") 
        self.picture_widget = Gtk.Picture()
        self.picture_widget.set_can_shrink(True)
        self.video_frame.set_child(self.picture_widget)
        self.video_cage.set_child(self.video_frame)
        top_panel.append(self.video_cage)              
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        detail_box.set_hexpand(True); detail_box.set_valign(Gtk.Align.CENTER)
        top_panel.append(detail_box)             
        self.detail_channel_name = Gtk.Label(label=_("Channel Name"), xalign=0)
        detail_box.append(self.detail_channel_name)       
        self.detail_title = Gtk.Label(label=_("Select a Program"), xalign=0)
        self.detail_title.set_wrap(True)
        detail_box.append(self.detail_title)       
        self.detail_time = Gtk.Label(label="--:-- / --:--", xalign=0)
        detail_box.append(self.detail_time)             
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(300, -1)
        self.progress_bar.set_margin_top(8); self.progress_bar.set_margin_bottom(8)
        detail_box.append(self.progress_bar)            
        self.desc_scroll = Gtk.ScrolledWindow()
        self.desc_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.desc_scroll.set_size_request(-1, 80) 
        self.desc_scroll.set_propagate_natural_height(False)      
        self.detail_desc = Gtk.Label(label=_("Program details will appear here."), xalign=0, wrap=True)
        self.detail_desc.set_max_width_chars(80)
        self.detail_desc.set_valign(Gtk.Align.START)        
        self.desc_scroll.set_child(self.detail_desc)
        detail_box.append(self.desc_scroll)           
        self.watch_button = Gtk.Button(label=_("Watch Now"))
        self.watch_button.add_css_class("suggested-action")
        self.watch_button.set_margin_top(12); self.watch_button.set_halign(Gtk.Align.START)
        self.watch_button.set_visible(False)
        self.watch_button.connect("clicked", self._on_watch_clicked)
        detail_box.append(self.watch_button)      
        self.timeline_label = Gtk.Label(label=_("Timeline"), xalign=0, css_classes=["caption-heading"])
        main_content.append(self.timeline_label)      
        self.view_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=250)
        self.view_stack.set_vexpand(True)
        main_content.append(self.view_stack)
        self.grid_layout_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header_scroll = Gtk.ScrolledWindow()
        self.header_scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self.header_fixed = Gtk.Fixed()
        self.header_scroll.set_child(self.header_fixed)
        self.grid_layout_box.append(self.header_scroll)      
        self.grid_scroll = Gtk.ScrolledWindow()
        self.grid_scroll.add_css_class("epg-grid-box")
        self.grid_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.grid_scroll.set_vexpand(True)
        self.grid_fixed = Gtk.Fixed()
        self.grid_scroll.set_child(self.grid_fixed)
        self.grid_layout_box.append(self.grid_scroll)     
        hadj_main = self.grid_scroll.get_hadjustment()
        hadj_header = self.header_scroll.get_hadjustment()
        hadj_main.bind_property("value", hadj_header, "value", GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        self.view_stack.add_named(self.grid_layout_box, "grid_view")
        self.list_layout_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.list_header_scroll = Gtk.ScrolledWindow()
        self.list_header_scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self.list_header_fixed = Gtk.Fixed()
        self.list_header_fixed.set_margin_start(16)
        self.list_header_fixed.set_margin_end(16)
        self.list_header_fixed.set_margin_top(16)
        self.list_header_scroll.set_child(self.list_header_fixed)
        self.list_layout_box.append(self.list_header_scroll)      
        self.list_scroll = Gtk.ScrolledWindow()
        self.list_scroll.add_css_class("epg-grid-box")
        self.list_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.list_scroll.set_vexpand(True)
        self.list_fixed = Gtk.Fixed()
        self.list_fixed.set_margin_bottom(20)
        self.list_fixed.set_margin_start(16)
        self.list_fixed.set_margin_end(16)
        self.list_scroll.set_child(self.list_fixed)
        self.list_layout_box.append(self.list_scroll)      
        hadj_list_main = self.list_scroll.get_hadjustment()
        hadj_list_header = self.list_header_scroll.get_hadjustment()
        hadj_list_main.bind_property("value", hadj_list_header, "value", GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        self.view_stack.add_named(self.list_layout_box, "list_view")
        self.grid_scroll.get_vadjustment().connect("value-changed", self._on_grid_scroll)
        self.grid_scroll.get_vadjustment().connect("notify::page-size", self._on_grid_scroll)
        self.list_scroll.get_hadjustment().connect("value-changed", self._on_list_scroll)
        self.list_scroll.get_hadjustment().connect("notify::page-size", self._on_list_scroll)
        saved_view = database.get_config_value("epg_view_mode")
        if saved_view == "list_view":
            self.view_stack.set_visible_child_name("list_view")
            self.view_button.set_icon_name("view-list-symbolic")
            self.timeline_label.set_text(_("Channels"))
        else:
            self.view_stack.set_visible_child_name("grid_view")
            self.view_button.set_icon_name("view-grid-symbolic")
            self.timeline_label.set_text(_("Timeline"))

    def clear_board(self):
        logging.info("[EPG_DEBUG] Clearing EPG board and freeing memory...")
        if getattr(self, "timer_id", None): 
            GLib.source_remove(self.timer_id)
            self.timer_id = None       
        if getattr(self, "_grid_scroll_idle_id", None):
            GLib.source_remove(self._grid_scroll_idle_id)
            self._grid_scroll_idle_id = None
        if getattr(self, "_list_scroll_idle_id", None):
            GLib.source_remove(self._list_scroll_idle_id)
            self._list_scroll_idle_id = None
        for idx, widgets in self._rendered_grid_rows.items():
            for w in widgets:
                if w.get_parent() == self.grid_fixed:
                    self.grid_fixed.remove(w)
        self._rendered_grid_rows.clear()
        for idx, (h_w, m_w) in self._rendered_list_cols.items():
            if h_w.get_parent() == self.list_header_fixed: self.list_header_fixed.remove(h_w)
            if m_w.get_parent() == self.list_fixed: self.list_fixed.remove(m_w)
        self._rendered_list_cols.clear()
        while child := self.header_fixed.get_first_child():
            self.header_fixed.remove(child)           
        if self.now_line and self.now_line.get_parent() == self.grid_fixed:
            self.grid_fixed.remove(self.now_line)
        self._grid_data_to_render = []

    def populate(self, grid_data):
        self.clear_board() 
        if not grid_data: return 
        clean_grid_data = []
        for item in grid_data:
            ch_name = item.get('channel_name', '').strip()
            if ch_name.startswith(('#', '=', '-', '*', '~', '_')):
                continue
            clean_grid_data.append(item)                  
        self._grid_data_to_render = clean_grid_data
        if not self._grid_data_to_render: return            
        now = datetime.now().astimezone()
        self.start_time = now.replace(minute=0, second=0, microsecond=0)
        self.PIXELS_PER_MIN, self.ROW_HEIGHT, self.CHANNEL_WIDTH, self.HEADER_HEIGHT = 4, 50, 160, 40
        self.HOURS_TO_SHOW = 24       
        for i in range(self.HOURS_TO_SHOW + 1):
            time_dt = self.start_time + timedelta(hours=i)
            lbl_text = time_dt.strftime('%a %H:%M') 
            lbl = Gtk.Label(label=lbl_text)
            lbl.add_css_class("caption")
            self.header_fixed.put(lbl, self.CHANNEL_WIDTH + (i * 60 * self.PIXELS_PER_MIN), 10)                 
        total_w = self.CHANNEL_WIDTH + (self.HOURS_TO_SHOW * 60 * self.PIXELS_PER_MIN) + 50
        total_h = len(self._grid_data_to_render) * self.ROW_HEIGHT            
        self.header_fixed.set_size_request(total_w, self.HEADER_HEIGHT) 
        self.now_line = Gtk.Box()
        self.now_line.set_size_request(2, total_h)
        self.now_line.add_css_class("now-indicator-line")
        self.now_line.set_can_target(False)            
        self.timer_id = GLib.timeout_add_seconds(60, self._update_now_line_position)
        self.grid_fixed.set_size_request(total_w, total_h + 50)
        max_progs = 0
        for item in self._grid_data_to_render:
            progs_count = len(item.get('programs', []))
            if progs_count > max_progs: max_progs = progs_count
        list_total_w = len(self._grid_data_to_render) * 292
        list_total_h = max_progs * 60 + 150     
        self.list_fixed.set_size_request(list_total_w, list_total_h)
        self.list_header_fixed.set_size_request(list_total_w, -1)
        GLib.idle_add(self._render_grid_viewport)
        GLib.idle_add(self._render_list_viewport)

    def _on_grid_scroll(self, *args):
        if self._grid_scroll_idle_id is None:
            self._grid_scroll_idle_id = GLib.idle_add(self._render_grid_viewport)

    def _render_grid_viewport(self):
        self._grid_scroll_idle_id = None
        if not self._grid_data_to_render: return False
        v_adj = self.grid_scroll.get_vadjustment()
        y = v_adj.get_value()
        h = v_adj.get_page_size()
        if h <= 0: h = 1080 
        start_idx = max(0, int(y / self.ROW_HEIGHT) - 2)
        end_idx = min(len(self._grid_data_to_render), int((y + h) / self.ROW_HEIGHT) + 3)
        to_remove = []
        for idx in list(self._rendered_grid_rows.keys()):
            if idx < start_idx or idx >= end_idx:
                for widget in self._rendered_grid_rows[idx]:
                    if widget.get_parent() == self.grid_fixed:
                        self.grid_fixed.remove(widget)
                to_remove.append(idx)
        for idx in to_remove:
            del self._rendered_grid_rows[idx]
        added_new = False
        for idx in range(start_idx, end_idx):
            if idx not in self._rendered_grid_rows:
                widgets = self._create_grid_row(idx)
                self._rendered_grid_rows[idx] = widgets
                added_new = True
        if added_new or (self.now_line and self.now_line.get_parent() is None):
            self._update_now_line_position()
        return False

    def _on_list_scroll(self, *args):
        if self._list_scroll_idle_id is None:
            self._list_scroll_idle_id = GLib.idle_add(self._render_list_viewport)

    def _render_list_viewport(self):
        self._list_scroll_idle_id = None
        if not self._grid_data_to_render: return False
        h_adj = self.list_scroll.get_hadjustment()
        x = h_adj.get_value()
        w = h_adj.get_page_size()
        if w <= 0: w = 1920
        COL_WIDTH = 292 
        start_idx = max(0, int(x / COL_WIDTH) - 2)
        end_idx = min(len(self._grid_data_to_render), int((x + w) / COL_WIDTH) + 3)
        to_remove = []
        for idx in list(self._rendered_list_cols.keys()): 
            if idx < start_idx or idx >= end_idx:
                h_widget, m_widget = self._rendered_list_cols[idx]
                if h_widget.get_parent() == self.list_header_fixed: self.list_header_fixed.remove(h_widget)
                if m_widget.get_parent() == self.list_fixed: self.list_fixed.remove(m_widget)
                to_remove.append(idx)
        for idx in to_remove:
            del self._rendered_list_cols[idx]
        for idx in range(start_idx, end_idx):
            if idx not in self._rendered_list_cols:
                h_w, m_w = self._create_list_col(idx)
                self._rendered_list_cols[idx] = (h_w, m_w)
        return False

    def _create_grid_row(self, idx):
        item = self._grid_data_to_render[idx]
        y_pos = idx * self.ROW_HEIGHT
        now = datetime.now().astimezone()
        end_time_limit = self.start_time + timedelta(hours=self.HOURS_TO_SHOW)
        widgets = []
        ch_btn = Gtk.Button()
        ch_btn.set_size_request(self.CHANNEL_WIDTH, self.ROW_HEIGHT - 2)
        ch_btn.add_css_class("card")        
        ch_lbl = Gtk.Label(label=item['channel_name'])
        ch_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        ch_lbl.set_tooltip_text(item['channel_name'])
        ch_lbl.set_xalign(0.0)
        ch_lbl.set_margin_start(8)
        ch_lbl.set_margin_end(8)
        ch_btn.set_child(ch_lbl)
        
        def on_ch_clicked(btn, channel_item=item):
            now_dt = datetime.now().astimezone()
            current_prog = None
            for p in channel_item.get('programs', []):
                if p['start'].astimezone() <= now_dt <= p['stop'].astimezone():
                    current_prog = p
                    break
            if current_prog:
                self.update_detail_panel(channel_item['raw_channel'], current_prog)
            self.emit("channel-selected", channel_item['raw_channel'])                  
        ch_btn.connect("clicked", on_ch_clicked)
        self.grid_fixed.put(ch_btn, 0, y_pos)           
        widgets.append(ch_btn)
        for prog in item.get('programs', []):
            p_start, p_stop = prog.get('start'), prog.get('stop')
            if not p_start or not p_stop: continue
            p_start, p_stop = p_start.astimezone(), p_stop.astimezone()
            if p_stop <= self.start_time or p_start >= end_time_limit: continue                                           
            s_diff = max(0, (p_start - self.start_time).total_seconds() / 60.0)
            width = int((min(self.HOURS_TO_SHOW*60, (p_stop - self.start_time).total_seconds()/60.0) - s_diff) * self.PIXELS_PER_MIN) - 4
            if width <= 2: continue            
            card_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            card_box.set_size_request(width, self.ROW_HEIGHT - 4)
            card_box.add_css_class("suggested-action" if p_start <= now <= p_stop else "card") 
            card_box.set_overflow(Gtk.Overflow.HIDDEN)            
            title_lbl = Gtk.Label(label=prog.get('title', ''))
            title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            title_lbl.set_tooltip_text(prog.get('title', ''))
            title_lbl.set_xalign(0.0)
            title_lbl.set_margin_start(6)
            title_lbl.set_margin_end(12)
            title_lbl.set_valign(Gtk.Align.CENTER)
            card_box.append(title_lbl)                         
            click_gesture = Gtk.GestureClick()
            
            def on_grid_click(gesture, n_press, x, y, ch=item['raw_channel'], pr=prog):
                self._on_program_clicked(None, ch, pr)
            click_gesture.connect("released", on_grid_click)
            card_box.add_controller(click_gesture)          
            if width > 60:
                actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
                actions_box.set_valign(Gtk.Align.CENTER)
                actions_box.set_halign(Gtk.Align.END)
                actions_box.set_hexpand(True)  
                actions_box.set_margin_end(4)              
                if prog.get('is_recorded', False):
                    rec_icon = Gtk.Image.new_from_icon_name("media-record-symbolic")
                    rec_icon.add_css_class("error")
                    actions_box.append(rec_icon)
                more_btn = Gtk.Button()
                more_btn.set_icon_name("view-more-symbolic") 
                more_btn.add_css_class("flat")
                more_btn.set_valign(Gtk.Align.CENTER)
                
                def on_more_clicked_grid(btn, ch_data=item['raw_channel'], prog_data=prog, abox=actions_box):
                    popover = Gtk.Popover()
                    menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)                  
                    rec_btn = Gtk.Button(label=_("Add to Record List"))
                    rec_btn.add_css_class("flat")
                    
                    def on_record_clicked_grid(r_btn):
                        popover.popdown()
                        self._show_record_dialog(ch_data, prog_data, abox)                                        
                    rec_btn.connect("clicked", on_record_clicked_grid)
                    menu_box.append(rec_btn)
                    popover.set_child(menu_box)
                    popover.set_parent(btn)
                    popover.connect("closed", lambda p: p.unparent())
                    popover.popup()                  
                more_btn.connect("clicked", on_more_clicked_grid)
                actions_box.append(more_btn)
                card_box.append(actions_box)
            self.grid_fixed.put(card_box, self.CHANNEL_WIDTH + int(s_diff * self.PIXELS_PER_MIN) + 2, y_pos + 2)              
            widgets.append(card_box)
        return widgets

    def _create_list_col(self, idx):
        item = self._grid_data_to_render[idx]
        x_pos = idx * 292
        now = datetime.now().astimezone()
        end_time_limit = self.start_time + timedelta(hours=self.HOURS_TO_SHOW)
        header_col_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header_col_box.set_size_request(280, -1)
        header_col_box.set_margin_end(12)           
        header_btn = Gtk.Button()
        header_btn.set_halign(Gtk.Align.CENTER)
        header_btn.set_margin_bottom(12)
        header_btn.add_css_class("channel-col-header")            
        header_btn.set_overflow(Gtk.Overflow.HIDDEN)       
        ch_header_lbl = Gtk.Label(label=item['channel_name'])
        ch_header_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        ch_header_lbl.set_tooltip_text(item['channel_name'])
        ch_header_lbl.set_xalign(0.5)
        ch_header_lbl.add_css_class("title-4")             
        header_btn.set_child(ch_header_lbl)

        def on_list_ch_clicked(btn, channel_item=item):
            now_dt = datetime.now().astimezone()
            cur_prog = None
            for prog in channel_item.get('programs', []):
                if prog['start'].astimezone() <= now_dt <= prog['stop'].astimezone():
                    cur_prog = prog
                    break
            if cur_prog:
                self.update_detail_panel(channel_item['raw_channel'], cur_prog)
            self.emit("channel-selected", channel_item['raw_channel'])        
        header_btn.connect("clicked", on_list_ch_clicked)
        header_col_box.append(header_btn)
        self.list_header_fixed.put(header_col_box, x_pos, 0)      
        col_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        col_box.set_size_request(280, -1)
        col_box.set_margin_end(12)
        col_box.set_halign(Gtk.Align.START)            
        current_prog = None
        future_progs = []                  
        for p in item.get('programs', []):
            p_start, p_stop = p['start'].astimezone(), p['stop'].astimezone()
            if p_stop <= now: continue
            if p_start >= end_time_limit: continue
            if p_start <= now <= p_stop:
                current_prog = p
            else:
                future_progs.append(p)                
        if current_prog:
            cur_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            cur_card.add_css_class("card")
            cur_card.add_css_class("current-prog-card")               
            cur_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            cur_vbox.set_hexpand(True)
            cur_vbox.set_margin_top(8); cur_vbox.set_margin_bottom(8)
            cur_vbox.set_margin_start(8); cur_vbox.set_margin_end(8)              
            time_lbl = Gtk.Label(label=f"{current_prog['start'].astimezone().strftime('%a %H:%M')} - {current_prog['stop'].astimezone().strftime('%H:%M')}")
            time_lbl.set_halign(Gtk.Align.START)
            time_lbl.add_css_class("dim-label")
            cur_vbox.append(time_lbl)                                    
            title_lbl_cur = Gtk.Label(label=current_prog.get('title', ''))
            title_lbl_cur.set_ellipsize(Pango.EllipsizeMode.END)
            title_lbl_cur.set_wrap(False)         
            title_lbl_cur.set_width_chars(1)    
            title_lbl_cur.set_max_width_chars(1)  
            title_lbl_cur.set_hexpand(True)     
            title_lbl_cur.set_halign(Gtk.Align.FILL)  
            title_lbl_cur.set_xalign(0.0) 
            title_lbl_cur.add_css_class("accent-label")
            title_lbl_cur.set_tooltip_text(current_prog.get('title', ''))             
            cur_vbox.append(title_lbl_cur)         
            prog_bar = Gtk.ProgressBar()
            prog_bar.set_margin_top(4)
            p_s, p_e = current_prog['start'].astimezone(), current_prog['stop'].astimezone()
            fraction = (now - p_s).total_seconds() / (p_e - p_s).total_seconds()
            prog_bar.set_fraction(max(0.0, min(1.0, fraction)))
            cur_vbox.append(prog_bar)               
            cur_card.append(cur_vbox)         
            click_gesture_cur = Gtk.GestureClick()
            
            def on_cur_click(gesture, n_press, x, y, ch=item['raw_channel'], pr=current_prog):
                self._on_program_clicked(None, ch, pr)
            click_gesture_cur.connect("released", on_cur_click)
            cur_vbox.add_controller(click_gesture_cur)           
            actions_box_cur = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
            actions_box_cur.set_valign(Gtk.Align.CENTER)
            actions_box_cur.set_halign(Gtk.Align.END)
            actions_box_cur.set_hexpand(True)
            actions_box_cur.set_margin_end(4)           
            if current_prog.get('is_recorded', False):
                rec_icon_cur = Gtk.Image.new_from_icon_name("media-record-symbolic")
                rec_icon_cur.add_css_class("error")
                actions_box_cur.append(rec_icon_cur)
            more_btn_cur = Gtk.Button()
            more_btn_cur.set_icon_name("view-more-symbolic") 
            more_btn_cur.add_css_class("flat")
            more_btn_cur.set_valign(Gtk.Align.CENTER)
            
            def on_more_clicked_cur(btn, ch_data=item['raw_channel'], prog_data=current_prog, abox=actions_box_cur):
                popover = Gtk.Popover()
                menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)              
                rec_btn = Gtk.Button(label=_("Add to Record List"))
                rec_btn.add_css_class("flat")
                
                def on_record_clicked_cur(r_btn):
                    popover.popdown()
                    self._show_record_dialog(ch_data, prog_data, abox)                                   
                rec_btn.connect("clicked", on_record_clicked_cur)
                menu_box.append(rec_btn)
                popover.set_child(menu_box)
                popover.set_parent(btn)
                popover.connect("closed", lambda p: p.unparent())
                popover.popup()               
            more_btn_cur.connect("clicked", on_more_clicked_cur)
            actions_box_cur.append(more_btn_cur)
            cur_card.append(actions_box_cur)
            col_box.append(cur_card)         
        for p in future_progs: 
            fut_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            fut_card.add_css_class("card")
            fut_card.set_size_request(-1, 50)                
            fut_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            fut_vbox.set_hexpand(True) 
            fut_vbox.set_margin_top(12); fut_vbox.set_margin_bottom(12)
            fut_vbox.set_margin_start(8)              
            p_s = p['start'].astimezone()
            p_e = p['stop'].astimezone()
            time_str = f"{p_s.strftime('%a %H:%M')} - {p_e.strftime('%H:%M')}"               
            time_lbl = Gtk.Label(label=time_str)
            time_lbl.set_halign(Gtk.Align.START)
            time_lbl.add_css_class("dim-label")
            fut_vbox.append(time_lbl)                                         
            title_lbl_fut = Gtk.Label(label=p.get('title', ''))
            title_lbl_fut.set_ellipsize(Pango.EllipsizeMode.END)
            title_lbl_fut.set_wrap(False)
            title_lbl_fut.set_width_chars(1)
            title_lbl_fut.set_max_width_chars(1)
            title_lbl_fut.set_hexpand(True)
            title_lbl_fut.set_halign(Gtk.Align.FILL)
            title_lbl_fut.set_xalign(0.0) 
            title_lbl_fut.set_tooltip_text(p.get('title', ''))               
            fut_vbox.append(title_lbl_fut)                
            fut_card.append(fut_vbox)           
            click_gesture_fut = Gtk.GestureClick()
            
            def on_fut_click(gesture, n_press, x, y, ch=item['raw_channel'], pr=p):
                self._on_program_clicked(None, ch, pr)
            click_gesture_fut.connect("released", on_fut_click)
            fut_vbox.add_controller(click_gesture_fut)           
            actions_box_fut = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
            actions_box_fut.set_valign(Gtk.Align.CENTER)
            actions_box_fut.set_halign(Gtk.Align.END)
            actions_box_fut.set_hexpand(True)
            actions_box_fut.set_margin_end(4)            
            if p.get('is_recorded', False):
                rec_icon_fut = Gtk.Image.new_from_icon_name("media-record-symbolic")
                rec_icon_fut.add_css_class("error")
                actions_box_fut.append(rec_icon_fut)
            more_btn_fut = Gtk.Button()
            more_btn_fut.set_icon_name("view-more-symbolic") 
            more_btn_fut.add_css_class("flat")
            more_btn_fut.set_valign(Gtk.Align.CENTER)
            
            def on_more_clicked_fut(btn, ch_data=item['raw_channel'], prog_data=p, abox=actions_box_fut):
                popover = Gtk.Popover()
                menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)              
                rec_btn = Gtk.Button(label=_("Add to Record List"))
                rec_btn.add_css_class("flat")
                
                def on_record_clicked_fut(r_btn):
                    popover.popdown()
                    self._show_record_dialog(ch_data, prog_data, abox)                                    
                rec_btn.connect("clicked", on_record_clicked_fut)
                menu_box.append(rec_btn)
                popover.set_child(menu_box)
                popover.set_parent(btn)
                popover.connect("closed", lambda pop: pop.unparent())
                popover.popup()              
            more_btn_fut.connect("clicked", on_more_clicked_fut)
            actions_box_fut.append(more_btn_fut)
            fut_card.append(actions_box_fut)
            col_box.append(fut_card)
        self.list_fixed.put(col_box, x_pos, 0)
        return header_col_box, col_box

    def _update_now_line_position(self):
        if not self.now_line or not getattr(self, 'start_time', None): return False
        diff_mins = (datetime.now().astimezone() - self.start_time).total_seconds() / 60.0
        new_x = self.CHANNEL_WIDTH + int(diff_mins * self.PIXELS_PER_MIN)
        if self.now_line.get_parent() == self.grid_fixed:
            self.grid_fixed.remove(self.now_line)           
        self.grid_fixed.put(self.now_line, new_x, 0)
        return True

    def update_detail_panel(self, channel, prog):
        if not channel or not prog: return
        self.selected_channel_data = channel       
        start_dt = prog.get('start')
        stop_dt = prog.get('stop')       
        if start_dt and stop_dt:
            now = datetime.now().astimezone()
            p_s = start_dt.astimezone()
            p_e = stop_dt.astimezone()          
            is_now_playing = p_s <= now <= p_e
            self.watch_button.set_visible(is_now_playing)
        else:
            self.watch_button.set_visible(False)
        self.detail_channel_name.set_text(channel.get("name", _("Unknown Channel")))
        self.detail_title.set_text(prog.get('title', ''))       
        if start_dt and stop_dt:
            self.detail_time.set_text(f"{start_dt.astimezone().strftime('%H:%M')} - {stop_dt.astimezone().strftime('%H:%M')}")
            now, p_s, p_e = datetime.now().astimezone(), start_dt.astimezone(), stop_dt.astimezone()
            if p_s <= now <= p_e:
                self.progress_bar.set_fraction((now - p_s).total_seconds() / (p_e - p_s).total_seconds())
            else: 
                self.progress_bar.set_fraction(1.0 if now > p_e else 0.0)               
        self.detail_desc.set_text(prog.get('desc') or _("No details available for this program."))
        
    def _on_program_clicked(self, button, channel, prog):
        self.update_detail_panel(channel, prog)

    def _on_watch_clicked(self, button):
        if self.selected_channel_data:
            self.emit("channel-selected", self.selected_channel_data)

    def set_paintable(self, paintable):
        self.picture_widget.set_paintable(paintable)

    def _on_back_clicked(self, button):
        self.clear_board()
        self.emit("close-requested")

    def _on_view_grid_selected(self, action, param):
        self.view_stack.set_visible_child_name("grid_view")
        self.view_button.set_icon_name("view-grid-symbolic")
        self.timeline_label.set_text(_("Timeline"))
        database.set_config_value("epg_view_mode", "grid_view")
        self._on_grid_scroll()

    def _on_view_list_selected(self, action, param):
        self.view_stack.set_visible_child_name("list_view")
        self.view_button.set_icon_name("view-list-symbolic")
        self.timeline_label.set_text(_("Channels"))
        database.set_config_value("epg_view_mode", "list_view")
        self._on_list_scroll()
        
    def _show_sleep_warning(self):
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading=_("Important Notice"),
            body=_("For the scheduled recording to complete successfully, please ensure your computer does not go to sleep during the recording time and that the sleep mode feature is disabled.")
        )
        dialog.add_css_class("sleep-warning-dialog")
        dialog.add_response("close", _("Close"))
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        dialog.connect("response", lambda dlg, resp: dlg.close())
        dialog.present()        

    def _show_record_dialog(self, channel_data, prog_data, actions_box=None):
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(), 
            heading=_("Schedule Recording"),
            body=_("Check the details below and adjust recording offsets if necessary.")
        )
        dialog.add_css_class("scheduler-selection-dialog")
        content_box = Gtk.ListBox()
        content_box.set_selection_mode(Gtk.SelectionMode.NONE) 
        content_box.add_css_class("boxed-list") 
        content_box.set_margin_top(12)
        content_box.set_size_request(420, -1)               
        name_row = Adw.ActionRow(title=_("Program Name"))
        self.record_name_entry = Gtk.Entry()
        self.record_name_entry.set_text(prog_data.get('title', ''))
        self.record_name_entry.set_valign(Gtk.Align.CENTER)
        name_row.add_suffix(self.record_name_entry)
        content_box.append(name_row)       
        p_s = prog_data['start'].astimezone()
        p_e = prog_data['stop'].astimezone()
        time_str = f"{p_s.strftime('%d.%m %H:%M')} - {p_e.strftime('%H:%M')}"       
        info_row = Adw.ActionRow(title=_("Channel / Time"), subtitle=f"{channel_data.get('name', '')} | {time_str}")
        content_box.append(info_row)      
        start_offset_row = Adw.ActionRow(title=_("Start Offset"), subtitle=_("Start early if broadcast begins early"))
        start_offset_row.set_title_lines(1)   
        start_offset_row.set_subtitle_lines(2) 
        self.start_combo = Gtk.ComboBoxText()
        self.start_combo.append("0", _("Exact Time"))
        self.start_combo.append("5", _("5 Minutes Before"))
        self.start_combo.append("10", _("10 Minutes Before"))
        self.start_combo.append("15", _("15 Minutes Before"))
        self.start_combo.append("20", _("20 Minutes Before"))
        self.start_combo.append("custom", _("Custom (Manual)"))
        self.start_combo.set_active_id("0") 
        self.start_combo.set_valign(Gtk.Align.CENTER)              
        self.start_custom_spin = Gtk.SpinButton.new_with_range(0, 180, 1)
        self.start_custom_spin.set_visible(False)
        self.start_custom_spin.set_valign(Gtk.Align.CENTER)
        self.start_custom_spin.set_width_chars(3)             
        start_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        start_box.append(self.start_combo)
        start_box.append(self.start_custom_spin)
        start_offset_row.add_suffix(start_box)
        content_box.append(start_offset_row)

        def on_start_combo_changed(combo):
            self.start_custom_spin.set_visible(combo.get_active_id() == "custom")
        self.start_combo.connect("changed", on_start_combo_changed)       
        end_offset_row = Adw.ActionRow(title=_("End Offset"), subtitle=_("Extend if broadcast runs late"))
        end_offset_row.set_title_lines(1)   
        end_offset_row.set_subtitle_lines(2) 
        self.end_combo = Gtk.ComboBoxText()
        self.end_combo.append("0", _("Exact Time"))
        self.end_combo.append("5", _("5 Minutes After"))
        self.end_combo.append("10", _("10 Minutes After"))
        self.end_combo.append("15", _("15 Minutes After"))
        self.end_combo.append("20", _("20 Minutes After"))
        self.end_combo.append("custom", _("Custom (Manual)"))
        self.end_combo.set_active_id("0") 
        self.end_combo.set_valign(Gtk.Align.CENTER)             
        self.end_custom_spin = Gtk.SpinButton.new_with_range(0, 180, 1)
        self.end_custom_spin.set_visible(False)
        self.end_custom_spin.set_valign(Gtk.Align.CENTER)
        self.end_custom_spin.set_width_chars(3)             
        end_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        end_box.append(self.end_combo)
        end_box.append(self.end_custom_spin)
        end_offset_row.add_suffix(end_box)
        content_box.append(end_offset_row)

        def on_end_combo_changed(combo):
            self.end_custom_spin.set_visible(combo.get_active_id() == "custom")
        self.end_combo.connect("changed", on_end_combo_changed)       
        dialog.set_extra_child(content_box)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save"))
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_dialog_response(dlg, response_id):
            if response_id == "save":
                prog_name = self.record_name_entry.get_text()              
                s_id = self.start_combo.get_active_id()
                start_offset = int(self.start_custom_spin.get_value()) if s_id == "custom" else int(s_id)              
                e_id = self.end_combo.get_active_id()
                end_offset = int(self.end_custom_spin.get_value()) if e_id == "custom" else int(e_id)
                p_start = prog_data['start'].astimezone()
                p_end = prog_data['stop'].astimezone()              
                adjusted_start = p_start - timedelta(minutes=start_offset)
                adjusted_end = p_end + timedelta(minutes=end_offset)
                start_ts = int(adjusted_start.timestamp())
                end_ts = int(adjusted_end.timestamp())             
                ch_name = channel_data.get('name', 'Unknown Channel')
                ch_url = channel_data.get('url', '')               
                logging.info(f"[EPG_DEBUG] Calculating recording...")
                logging.info(f"[EPG_DEBUG] Original Time: {p_start.strftime('%H:%M')} - {p_end.strftime('%H:%M')}")
                logging.info(f"[EPG_DEBUG] Adjusted Time ({start_offset} mins early, {end_offset} mins late): {adjusted_start.strftime('%H:%M')} - {adjusted_end.strftime('%H:%M')}")              
                self.emit("schedule-recording", ch_name, ch_url, start_ts, end_ts, prog_name)
                if not prog_data.get('is_recorded', False):
                    prog_data['is_recorded'] = True
                    if actions_box is not None:
                        rec_icon = Gtk.Image.new_from_icon_name("media-record-symbolic")
                        rec_icon.add_css_class("error")
                        actions_box.prepend(rec_icon)  
                self._show_sleep_warning()                                      
            dlg.close()           
        dialog.connect("response", on_dialog_response)
        dialog.present()

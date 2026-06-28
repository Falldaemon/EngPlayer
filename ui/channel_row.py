import logging
from gi.repository import Gtk, Pango, Gdk
import database
import gettext
_ = gettext.gettext

logger = logging.getLogger(__name__)

class ChannelRow(Gtk.Box):
    def __init__(self, channel_data, is_checked, buckets_text, on_toggled_cb, is_selectable=False, bucket_name=None, on_select_cb=None, on_edit_cb=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.data = channel_data
        self.on_toggled_cb = on_toggled_cb
        self._block_signal = False       
        self.bucket_name = bucket_name
        self.on_select_cb = on_select_cb
        self.on_edit_cb = on_edit_cb       
        self.set_margin_start(10)
        self.set_margin_end(10)
        self.set_margin_top(4)
        self.set_margin_bottom(4)      
        if is_selectable:
            click_ctrl = Gtk.GestureClick.new()
            click_ctrl.connect("pressed", self._on_clicked)
            self.add_controller(click_ctrl)
        self.name_label = Gtk.Label(label=channel_data.get("name", _("Unknown")))
        self.name_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.name_label.set_hexpand(True)
        self.name_label.set_xalign(0)
        self.name_label.set_margin_start(8)
        self.append(self.name_label)
        self.badge_label = Gtk.Label(label=buckets_text)
        self.badge_label.add_css_class("dim-label")
        self.badge_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.badge_label.set_max_width_chars(30)
        self.badge_label.set_valign(Gtk.Align.CENTER)
        self.append(self.badge_label)
        is_hidden = database.get_channel_hidden_status(channel_data.get("url", ""))
        self.hide_icon = Gtk.Image(icon_name="view-conceal-symbolic")
        self.hide_icon.add_css_class("dim-label")
        self.hide_icon.set_valign(Gtk.Align.CENTER)
        self.hide_icon.set_margin_end(8)
        self.hide_icon.set_tooltip_text(_("This channel is hidden in the main app"))
        self.hide_icon.set_visible(is_hidden)
        self.append(self.hide_icon)
        is_locked = database.get_channel_lock_status(channel_data.get("url", ""))
        self.lock_icon = Gtk.Image(icon_name="changes-prevent-symbolic")
        self.lock_icon.add_css_class("dim-label")
        self.lock_icon.set_valign(Gtk.Align.CENTER)
        self.lock_icon.set_margin_end(8)
        self.lock_icon.set_tooltip_text(_("This channel is locked"))
        self.lock_icon.set_visible(is_locked)
        self.append(self.lock_icon)
        self.edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
        self.edit_btn.add_css_class("flat")
        self.edit_btn.set_valign(Gtk.Align.CENTER)
        self.edit_btn.set_tooltip_text(_("Edit Channel"))
        self.edit_btn.connect("clicked", self._on_edit_clicked)
        self.append(self.edit_btn)
        self.check_btn = Gtk.CheckButton()
        self.check_btn.set_active(is_checked)
        self.check_btn.set_valign(Gtk.Align.CENTER)
        self.check_btn.set_margin_end(8)
        self.check_btn.connect("toggled", self._on_toggled)
        self.append(self.check_btn)

    def _on_edit_clicked(self, button):
        if self.on_edit_cb:
            self.on_edit_cb(self.data, self.bucket_name)

    def _on_clicked(self, gesture, n_press, x, y):
        if self.on_select_cb:
            self.on_select_cb(self.data.get("url"), self.bucket_name)

    def set_selected(self, is_selected):
        if is_selected:
            self.add_css_class("channel-selected")
        else:
            self.remove_css_class("channel-selected")

    def update_state(self, checked, buckets_text):
        self._block_signal = True
        self.check_btn.set_active(checked)
        self.badge_label.set_text(buckets_text)
        self._block_signal = False

    def _on_toggled(self, button):
        if self._block_signal:
            return
        if self.on_toggled_cb:
            self.on_toggled_cb(self.data, button.get_active())
            
    def update_channel_info(self, new_name):
        self.name_label.set_text(new_name)  
        
    def update_editor_icons(self, is_hidden, is_locked):
        if hasattr(self, 'hide_icon'):
            self.hide_icon.set_visible(is_hidden)                  
        if hasattr(self, 'lock_icon'):
            self.lock_icon.set_visible(is_locked)                                

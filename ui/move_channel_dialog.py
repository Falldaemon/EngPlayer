# ui/move_channel_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
import gettext
_ = gettext.gettext
class MoveChannelDialog(Adw.MessageDialog):
    """
    A small, modal window that allows the user to
    move a selected channel up/down.
    """

    def __init__(self, parent, row_to_move, channel_list_widget):
        super().__init__(transient_for=parent)
        self.row_to_move = row_to_move
        self.channel_list_widget = channel_list_widget
        self.set_heading(_("Move Channel"))
        self.set_body(f"'{self.row_to_move.channel_data['name']}'")
        self.set_default_size(300, -1)
        self.add_css_class("move-channel-dialog")
        self.add_response("ok", _("Done"))
        self.set_default_response("ok")
        self.set_close_response("ok")
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                              spacing=12,
                              halign=Gtk.Align.CENTER,
                              margin_top=24)
        self.set_extra_child(content_box)
        self.up_button = Gtk.Button(icon_name="go-up-symbolic", label=_("Up"))
        self.up_button.connect("clicked", self.on_move_up_clicked)
        content_box.append(self.up_button)
        self.down_button = Gtk.Button(icon_name="go-down-symbolic", label=_("Down"))
        self.down_button.connect("clicked", self.on_move_down_clicked)
        content_box.append(self.down_button)
        self.update_button_sensitivity()

    def on_move_up_clicked(self, button):
        """Calls the method in ChannelList when the 'Up' button is clicked."""
        success = self.channel_list_widget.move_row_up(self.row_to_move)
        if success:
            self.update_button_sensitivity()

    def on_move_down_clicked(self, button):
        """Calls the method in ChannelList when the 'Down' button is clicked."""
        success = self.channel_list_widget.move_row_down(self.row_to_move)
        if success:
            self.update_button_sensitivity()

    def update_button_sensitivity(self):
        """Enables/disables buttons based on the row's current position."""
        current_index = self.row_to_move.get_index()
        is_last_row = self.row_to_move.get_next_sibling() is None
        self.up_button.set_sensitive(current_index > 0)
        self.down_button.set_sensitive(not is_last_row)

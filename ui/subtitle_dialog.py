# ui/subtitle_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GObject
import gettext
from .subtitle_settings_dialog import SubtitleSettingsDialog
_ = gettext.gettext
class SubtitleDialog(Adw.MessageDialog):
    __gsignals__ = {
        'subtitle-toggled': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        'load-external-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'track-selected': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        'online-search-requested': (GObject.SignalFlags.RUN_FIRST, None, ()),
        'sync-adjust-requested': (GObject.SignalFlags.RUN_FIRST, None, (int,))
    }

    def __init__(self, parent, embedded_tracks, current_state=False, current_track_index=-1):
        super().__init__(transient_for=parent)
        self.set_heading(_("Subtitle Options"))
        self.set_default_size(400, -1)
        self.add_css_class("subtitle-dialog")
        self.add_response("close", _("Close"))
        self.set_close_response("close")        
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12)
        self.set_extra_child(content_box)      
        self.toggle_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.toggle_switch.set_active(current_state)
        self.toggle_switch.connect("notify::active", self.on_toggle_changed)     
        toggle_row = Adw.ActionRow(title=_("Show Subtitles"))
        toggle_row.add_suffix(self.toggle_switch)
        toggle_row.set_activatable_widget(self.toggle_switch)
        content_box.append(toggle_row)      
        if embedded_tracks:
            self.track_combo = Gtk.ComboBoxText()
            for track in embedded_tracks:
                self.track_combo.append(str(track['index']), track['name'])
            if current_track_index != -1:
                self.track_combo.set_active_id(str(current_track_index))          
            self.track_combo.connect("changed", self.on_track_changed)
            combo_row = Adw.ActionRow(title=_("Embedded Track"))
            combo_row.add_suffix(self.track_combo)
            combo_row.set_activatable_widget(self.track_combo)
            content_box.append(combo_row)         
        load_button = Gtk.Button.new_with_label(_("Load from File"))
        load_button.connect("clicked", lambda w: self.emit('load-external-requested'))
        content_box.append(load_button)      
        online_search_button = Gtk.Button.new_with_label(_("Search Online"))
        online_search_button.connect("clicked", lambda w: self.emit('online-search-requested'))
        content_box.append(online_search_button)      
        sync_row = Adw.ActionRow(title=_("Synchronization Adjust"))
        sync_box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        btn_sync_minus = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        btn_sync_minus.set_tooltip_text(_("Delay Subtitles (-100ms)"))
        btn_sync_minus.connect("clicked", self._on_sync_adjust_clicked, -100)
        sync_box.append(btn_sync_minus)
        self.sync_label = Gtk.Label(label="0 ms")
        sync_box.append(self.sync_label)
        btn_sync_plus = Gtk.Button.new_from_icon_name("go-next-symbolic")
        btn_sync_plus.set_tooltip_text(_("Advance Subtitles (+100ms)"))
        btn_sync_plus.connect("clicked", self._on_sync_adjust_clicked, 100)
        sync_box.append(btn_sync_plus)
        sync_row.add_suffix(sync_box)
        sync_row.set_activatable(False)
        content_box.append(sync_row)      
        settings_button = Gtk.Button.new_with_label(_("Settings"))
        settings_button.connect("clicked", self._on_settings_clicked)
        content_box.append(settings_button)

    def _on_settings_clicked(self, button):
        """Opens the subtitle settings window."""
        settings_dialog = SubtitleSettingsDialog(self.get_transient_for())
        settings_dialog.present()

    def on_toggle_changed(self, switch, _):
        is_active = switch.get_active()
        self.emit('subtitle-toggled', is_active)

    def on_track_changed(self, combo):
        track_id_str = combo.get_active_id()
        if track_id_str is not None:
            self.emit('track-selected', int(track_id_str))

    def set_toggle_active(self, is_active):
        self.toggle_switch.set_active(is_active)

    def set_active_track_id(self, track_id):
        if hasattr(self, 'track_combo'):
            self.track_combo.set_active_id(str(track_id))

    def _on_sync_adjust_clicked(self, button, adjustment_ms):
        """Emits the signal when the +/- buttons are clicked."""
        self.emit('sync-adjust-requested', adjustment_ms)

    def update_sync_label(self, delay_ms):
        """Method to be called from MainWindow to update the label."""
        self.sync_label.set_text(f"{delay_ms} ms")

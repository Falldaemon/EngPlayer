import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango
import gettext

_ = gettext.gettext

class MediaInfoDialog(Adw.Window):
    def __init__(self, parent, player):
        super().__init__(transient_for=parent, modal=True)
        self.set_title(_("Stream Technical Information"))
        self.set_default_size(400, 450)
        self.add_css_class("media-info-dialog")
        self.player = player
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(content_box)
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        content_box.append(header)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                           margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        scroll.set_child(main_box)
        content_box.append(scroll)
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        main_box.append(switcher)
        main_box.append(self.stack)
        self.video_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        self.stack.add_titled_with_icon(self.video_list, "video", _("Video"), "video-x-generic-symbolic")
        self.audio_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        self.stack.add_titled_with_icon(self.audio_list, "audio", _("Audio"), "audio-x-generic-symbolic")
        footer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                             margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        footer_box.append(Gtk.Separator())
        location_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)       
        self.location_label = Gtk.Label(
            xalign=0, 
            wrap=True, 
            wrap_mode=Pango.WrapMode.CHAR, 
            selectable=False,
            lines=3,
            ellipsize=Pango.EllipsizeMode.END,
            css_classes=["caption"],
            hexpand=True
        )
        location_box.append(self.location_label)
        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic")
        copy_btn.set_valign(Gtk.Align.CENTER)
        copy_btn.set_tooltip_text(_("Copy Original URL"))
        copy_btn.connect("clicked", self.on_copy_clicked)
        location_box.append(copy_btn)
        footer_box.append(location_box)
        self.bitrate_label = Gtk.Label(label=_("Bitrate: 0.0 Mbps"), css_classes=["caption-heading"])
        footer_box.append(self.bitrate_label)
        content_box.append(footer_box)
        self.update_ui()
        self.timer_id = GLib.timeout_add_seconds(1, self.update_ui)
        self.connect("close-request", self.on_close)

    def on_copy_clicked(self, button):
        stats = self.player.get_detailed_stats()
        original_url = stats.get("url", "")
        if original_url and original_url != "-":
            clipboard = self.get_clipboard()
            clipboard.set(original_url)
            parent = self.get_transient_for()
            if parent and hasattr(parent, 'show_toast'):
                parent.show_toast(_("Original URL copied to clipboard!"))

    def _add_row(self, listbox, title, value):
        row = Adw.ActionRow(title=title)
        label = Gtk.Label(label=str(value), selectable=True)
        row.add_suffix(label)
        listbox.append(row)

    def update_ui(self):
        stats = self.player.get_detailed_stats()
        while r := self.video_list.get_first_child(): self.video_list.remove(r)
        while r := self.audio_list.get_first_child(): self.audio_list.remove(r)
        codec_display = f"{stats.get('video_codec', '-')}"
        if stats.get('profile') != "-":
            codec_display += f" ({stats['profile']}@{stats['level']})"
        self._add_row(self.video_list, _("Codec"), codec_display)
        self._add_row(self.video_list, _("Resolution"), stats.get("resolution", "-"))
        self._add_row(self.video_list, _("Frame Rate (FPS)"), stats.get("fps", "-"))
        self._add_row(self.video_list, _("Decoded Format"), stats.get("format", "-"))
        self._add_row(self.audio_list, _("Codec"), stats.get("audio_codec", "-"))
        self._add_row(self.audio_list, _("Language"), stats.get("language", "-"))
        self._add_row(self.audio_list, _("Channels"), stats.get("channels", "-"))
        self._add_row(self.audio_list, _("Sample Rate"), stats.get("sample_rate", "-"))
        self.location_label.set_text(f'{_("Location")}: {stats.get("safe_url", "-")}')
        raw_bitrate = stats.get("bitrate", 0)
        mbps = raw_bitrate / 1_000_000
        self.bitrate_label.set_text(f'{_("Bitrate")}: {mbps:.2f} Mbps')        
        return True
        
    def on_close(self, *args):
        if hasattr(self, 'timer_id') and self.timer_id:
            GLib.source_remove(self.timer_id)

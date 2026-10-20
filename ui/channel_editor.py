import logging
import os
import threading
import urllib.request
from gi.repository import Gtk, Adw, GLib, GdkPixbuf, Gdk
import database
from core.config import APP_USER_AGENT

import gettext

_ = gettext.gettext

logger = logging.getLogger(__name__)

class ChannelEditor(Gtk.Box):
    def __init__(self, on_back_cb, on_save_cb, on_delete_cb):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=15)       
        self.on_back_cb = on_back_cb
        self.on_save_cb = on_save_cb
        self.on_delete_cb = on_delete_cb       
        self.current_channel_data = None
        self.current_bucket = None
        self._logo_preview_timer = None
        self._logo_request_id = 0
        self._build_ui()

    def _build_ui(self):
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        back_btn = Gtk.Button(icon_name="go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.connect("clicked", self._on_back_clicked)
        header_box.append(back_btn)       
        self.title_label = Gtk.Label(label=_("Edit Channel"))
        self.title_label.add_css_class("title-2")
        header_box.append(self.title_label)
        self.append(header_box)
        logo_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        logo_box.set_margin_top(10)
        logo_box.set_margin_bottom(10)
        self.logo_image = Gtk.Image(icon_name="tv-symbolic")
        self.logo_image.set_pixel_size(64)
        self.logo_image.add_css_class("dim-label")
        logo_box.append(self.logo_image)
        logo_entry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        logo_entry_box.set_hexpand(True)
        logo_entry_box.set_valign(Gtk.Align.CENTER)
        logo_entry_box.append(Gtk.Label(label=_("Logo URL or Local File:"), xalign=0))       
        logo_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.logo_entry = Gtk.Entry(placeholder_text="http://... or /home/...")
        self.logo_entry.set_hexpand(True)
        self.logo_entry.connect("changed", self._on_logo_text_changed)
        logo_input_box.append(self.logo_entry)
        self.logo_btn = Gtk.Button(icon_name="folder-open-symbolic")
        self.logo_btn.set_tooltip_text(_("Select Image from Device"))
        self.logo_btn.connect("clicked", self._on_select_logo_clicked)
        logo_input_box.append(self.logo_btn)    
        logo_entry_box.append(logo_input_box)
        logo_box.append(logo_entry_box)
        self.append(logo_box)
        self.name_entry = Gtk.Entry()
        self.append(Gtk.Label(label=_("Channel Name:"), xalign=0))
        self.append(self.name_entry)      
        self.url_entry = Gtk.Entry()
        self.append(Gtk.Label(label=_("Stream URL / ID:"), xalign=0))
        self.append(self.url_entry)       
        self.epg_entry = Gtk.Entry(placeholder_text=_("e.g. 813294 or beIN.Sports.1"))
        self.append(Gtk.Label(label=_("EPG ID (tvg-id / stream_id):"), xalign=0))
        self.append(self.epg_entry)
        self.append(Gtk.Label(label=_("Saved in Favorites:"), xalign=0))
        self.buckets_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(self.buckets_box)
        switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        switch_box.set_margin_top(10)      
        lock_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lock_box.append(Gtk.Label(label=_("Lock Channel:")))
        self.lock_switch = Gtk.Switch()
        lock_box.append(self.lock_switch)
        switch_box.append(lock_box)      
        hide_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hide_box.append(Gtk.Label(label=_("Hide Channel:")))
        self.hide_switch = Gtk.Switch()
        hide_box.append(self.hide_switch)
        switch_box.append(hide_box)       
        self.append(switch_box)
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_margin_top(20)     
        delete_btn = Gtk.Button(label=_("Delete Channel"))
        delete_btn.add_css_class("destructive-action")
        delete_btn.set_hexpand(True)
        delete_btn.connect("clicked", self._on_delete_clicked)
        action_box.append(delete_btn)     
        save_btn = Gtk.Button(label=_("Save Changes"))
        save_btn.add_css_class("suggested-action")
        save_btn.set_hexpand(True)
        save_btn.connect("clicked", self._on_save_clicked)
        action_box.append(save_btn)     
        self.append(action_box)

    def set_channel(self, channel_data, bucket_name, in_buckets=None):
        self.current_channel_data = channel_data
        self.current_bucket = bucket_name       
        name_val = channel_data.get("name") or ""
        url_val = channel_data.get("url") or ""
        logo_val = channel_data.get("tvg-logo") or channel_data.get("logo") or ""
        epg_val = channel_data.get("tvg-id") or channel_data.get("stream_id") or ""       
        self.name_entry.set_text(str(name_val))
        self.url_entry.set_text(str(url_val))
        self.logo_entry.set_text(str(logo_val))
        if self._logo_preview_timer:
            GLib.source_remove(self._logo_preview_timer)
            self._logo_preview_timer = None
        self._update_logo_preview()
        self.epg_entry.set_text(str(epg_val))      
        is_locked = database.get_channel_lock_status(str(url_val))
        is_hidden = database.get_channel_hidden_status(str(url_val))
        self.lock_switch.set_active(is_locked)
        self.hide_switch.set_active(is_hidden)
        while self.buckets_box.get_first_child():
            self.buckets_box.remove(self.buckets_box.get_first_child())
        if in_buckets:
            for b in in_buckets:
                badge = Gtk.Label(label=f"📁 {b}")
                badge.add_css_class("badge-pill") 
                self.buckets_box.append(badge)

    def _on_select_logo_clicked(self, btn):
        dialog = Gtk.FileChooserNative(
            title=_("Select Channel Logo"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Select"),
            cancel_label=_("Cancel")
        )
        dialog.set_transient_for(self.get_root())
        filter = Gtk.FileFilter()
        filter.set_name(_("Images"))
        filter.add_mime_type("image/png")
        filter.add_mime_type("image/jpeg")
        dialog.add_filter(filter)    
        dialog.connect("response", self._on_logo_response)
        dialog.show()

    def _on_logo_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            self.logo_entry.set_text(file.get_path())
        dialog.destroy()
        
    def _reset_logo_preview(self):
        self.logo_image.set_from_icon_name("tv-symbolic")
        self.logo_image.add_css_class("dim-label")

    def _on_logo_text_changed(self, entry):
        if self._logo_preview_timer:
            GLib.source_remove(self._logo_preview_timer)
        self._logo_preview_timer = GLib.timeout_add(500, self._update_logo_preview)

    def _update_logo_preview(self):
        self._logo_preview_timer = None
        self._logo_request_id += 1
        request_id = self._logo_request_id
        source = self.logo_entry.get_text().strip()
        if not source:
            self._reset_logo_preview()
            return False
        threading.Thread(target=self._load_logo_thread, args=(source, request_id), daemon=True).start()
        return False

    def _load_logo_thread(self, source, request_id):
        pixbuf = None
        try:
            if source.startswith(("http://", "https://")):
                request = urllib.request.Request(source, headers={"User-Agent": APP_USER_AGENT})
                with urllib.request.urlopen(request, timeout=6) as response:
                    data = response.read(5 * 1024 * 1024)
                loader = GdkPixbuf.PixbufLoader.new()
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()
            else:
                path = GLib.filename_from_uri(source)[0] if source.startswith("file://") else source
                if os.path.isfile(path):
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            if pixbuf and (pixbuf.get_width() > 256 or pixbuf.get_height() > 256):
                scale = 256 / max(pixbuf.get_width(), pixbuf.get_height())
                pixbuf = pixbuf.scale_simple(max(1, int(pixbuf.get_width() * scale)),
                                             max(1, int(pixbuf.get_height() * scale)),
                                             GdkPixbuf.InterpType.BILINEAR)
        except Exception as e:
            logger.debug(f"Logo preview could not be loaded from '{source}': {e}")
            pixbuf = None
        GLib.idle_add(self._apply_logo_preview, pixbuf, request_id)

    def _apply_logo_preview(self, pixbuf, request_id):
        if request_id != self._logo_request_id:
            return False
        if pixbuf is None:
            self._reset_logo_preview()
            return False
        self.logo_image.remove_css_class("dim-label")
        self.logo_image.set_from_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        return False    

    def _on_back_clicked(self, btn):
        if self.on_back_cb:
            self.on_back_cb()

    def _on_save_clicked(self, btn):
        if self.on_save_cb and self.current_channel_data:
            new_name = self.name_entry.get_text()
            new_url = self.url_entry.get_text()
            new_logo = self.logo_entry.get_text()
            new_epg = self.epg_entry.get_text()       
            is_locked = self.lock_switch.get_active()
            is_hidden = self.hide_switch.get_active()
            password_is_set = database.get_config_value('app_password') is not None
            was_locked = database.get_channel_lock_status(self.current_channel_data.get("url", ""))
            if is_locked and not password_is_set:
                dialog = Adw.MessageDialog(
                    transient_for=self.get_root(),
                    heading=_("Password Not Set"),
                    body=_("To lock items, you must first set a master password for the application from the settings menu."),
                    modal=True
                )
                dialog.add_css_class("set-password-warning-dialog")
                dialog.add_response("close", _("Close"))
                dialog.add_response("set-password", _("Set Password"))
                dialog.set_default_response("set-password")
                
                def on_set_pass_response(d, response_id):
                    if response_id == "set-password":
                        from ui.password_dialog import PasswordDialog
                        toast_overlay = getattr(self.get_root(), 'toast_overlay', None)
                        password_dialog = PasswordDialog(self.get_root(), toast_overlay)
                        password_dialog.present()
                    self.lock_switch.set_active(False)               
                dialog.connect("response", on_set_pass_response)
                dialog.present()
                return
            if was_locked and not is_locked:
                from ui.password_prompt_dialog import PasswordPromptDialog
                prompt = PasswordPromptDialog(self.get_root())              
                def on_password_response(dialog, response_id):
                    if response_id == "ok":
                        if database.check_password(dialog.get_password()):
                            self.on_save_cb(self.current_channel_data, self.current_bucket, new_name, new_url, new_logo, new_epg, is_locked, is_hidden)
                        else:
                            self.get_root().show_toast(_("Wrong Password!"))
                            self.lock_switch.set_active(True)               
                prompt.connect("response", on_password_response)
                prompt.present()
                return 
            self.on_save_cb(self.current_channel_data, self.current_bucket, new_name, new_url, new_logo, new_epg, is_locked, is_hidden)

    def _on_delete_clicked(self, btn):
        if self.on_delete_cb and self.current_channel_data:
            self.on_delete_cb(self.current_channel_data, self.current_bucket)

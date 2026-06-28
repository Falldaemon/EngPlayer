# ui/profile_manager_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib
import gettext
import logging
import uuid
import os

from utils.profile_manager import load_profiles, save_profiles

_ = gettext.gettext

class ProfileManagerDialog(Adw.MessageDialog):
    def __init__(self, parent_window, profile_data):
        super().__init__(
            transient_for=parent_window,
            heading=_("Profile Management"),
            body=_("Backup your current profile or restore a previously saved one.")
        )
        self.parent_window = parent_window
        self.profile_data = profile_data
        logging.debug(f"ProfileManagerDialog initialized for profile: {self.profile_data.get('name', 'Unknown')}")
        self.add_css_class("profile-manager-dialog")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12)
        self.set_extra_child(content)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        switcher = Gtk.StackSwitcher(stack=self.stack, halign=Gtk.Align.CENTER, margin_bottom=12)
        content.append(switcher)
        content.append(self.stack)
        self._setup_export_page()
        self._setup_import_page()
        self.add_response("close", _("Close"))
        self.set_default_response("close")
        self.set_close_response("close")

    def _setup_export_page(self):
        export_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)       
        export_box.append(Gtk.Label(
            label=_("Select the format to export your current profile '{}':").format(self.profile_data.get("name", "Profile")),
            halign=Gtk.Align.START,
            wrap=True
        ))
        self.format_combo = Gtk.ComboBoxText()
        self.format_combo.append("m3u_url", _("M3U Playlist URL (.m3u)"))       
        if self.profile_data.get("type") == "xtream":
            self.format_combo.append("xtream_codes", _("Xtream Codes Details (.txt)"))           
        self.format_combo.set_active(0)
        export_box.append(self.format_combo)
        export_btn = Gtk.Button(label=_("Export to File"))
        export_btn.add_css_class("suggested-action")
        export_btn.set_margin_top(12)
        export_btn.connect("clicked", self._on_export_button_clicked)
        export_box.append(export_btn)
        self.stack.add_titled(export_box, "export", _("Export Profile"))
        logging.debug("Export page setup completed.")

    def _setup_import_page(self):
        import_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)      
        import_box.append(Gtk.Label(
            label=_("Choose a previously exported backup file (.m3u or .txt) to import it as a new profile."),
            halign=Gtk.Align.START,
            wrap=True
        ))
        import_btn = Gtk.Button(label=_("Import from File"))
        import_btn.add_css_class("suggested-action")
        import_btn.set_margin_top(12)
        import_btn.connect("clicked", self._on_import_button_clicked)
        import_box.append(import_btn)
        self.stack.add_titled(import_box, "import", _("Import Profile"))
        logging.debug("Import page setup completed.")

    def _on_export_button_clicked(self, button):
        export_format = self.format_combo.get_active_id()
        logging.info(f"User requested export. Format selected: {export_format}")      
        dialog = Gtk.FileChooserDialog(
            title=_("Export Full Playlist") if export_format == "m3u_url" else _("Export Details"),
            transient_for=self.parent_window,
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Save"), Gtk.ResponseType.ACCEPT
        )
        dialog.set_modal(True)
        download_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if download_dir:
            dialog.set_current_folder(Gio.File.new_for_path(download_dir))
        safe_name = self.profile_data.get('name', 'Profile').replace(" ", "_").lower()      
        if export_format == "m3u_url":
            dialog.set_current_name(f"{safe_name}_full_playlist.m3u")
            m3u_filter = Gtk.FileFilter()
            m3u_filter.set_name(_("M3U Playlist"))
            m3u_filter.add_pattern("*.m3u")
            dialog.add_filter(m3u_filter)
        else:
            dialog.set_current_name(f"{safe_name}_xtream_details.txt")
            txt_filter = Gtk.FileFilter()
            txt_filter.set_name(_("Text Files"))
            txt_filter.add_pattern("*.txt")
            dialog.add_filter(txt_filter)

        def on_export_response(d, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                gfile = d.get_file()
                if gfile:
                    path = gfile.get_path()
                    logging.info(f"User selected path for export: {path}")
                    self._export_real_data_offline(path, export_format)
                    self.close()
            else:
                logging.debug("User cancelled the export file dialog.")              
            d.hide()
            GLib.idle_add(d.destroy)
        dialog.connect("response", on_export_response)
        dialog.present()

    def _export_real_data_offline(self, file_path, export_format):
        logging.info(f"Starting offline export generation for format: {export_format}")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                if export_format == "xtream_codes":
                    logging.debug("Writing Xtream Codes account details...")
                    f.write("=== XTREAM CODES ACCOUNT DETAILS ===\n\n")
                    f.write(f"Profile Name: {self.profile_data.get('name')}\n")
                    f.write(f"Server URL:   {self.profile_data.get('host')}\n")
                    f.write(f"Username:     {self.profile_data.get('username')}\n")
                    f.write(f"Password:     {self.profile_data.get('password')}\n")
                elif export_format == "m3u_url":
                    logging.debug("Writing #EXTM3U header...")
                    f.write("#EXTM3U\n")                 
                    all_items = []
                    if hasattr(self.parent_window, "bouquets_data") and self.parent_window.bouquets_data:
                        for bouquet_name, channels in self.parent_window.bouquets_data.items():
                            for ch in channels:
                                ch_dict = dict(ch)
                                ch_dict["group_title"] = bouquet_name
                                ch_dict["type"] = "live"
                                all_items.append(ch_dict)
                    if hasattr(self.parent_window, "vod_data") and self.parent_window.vod_data:
                        for category_name, vods in self.parent_window.vod_data.items():
                            for v in vods:
                                v_dict = dict(v)
                                v_dict["group_title"] = category_name
                                v_dict["type"] = "vod"
                                all_items.append(v_dict)
                    logging.info(f"Found {len(all_items)} total items (channels + VOD) to export.")
                    for item in all_items:
                        ch_id = item.get("stream_id", item.get("tvg-id", ""))
                        logo = item.get("logo", item.get("stream_icon", ""))
                        group = item.get("group_title", "Uncategorized")
                        name = item.get("name", "Unknown Item")
                        url = ""
                        if self.profile_data.get("type") == "xtream":
                            host = self.profile_data.get('host', '').rstrip('/')
                            user = self.profile_data.get('username', '')
                            pwd = self.profile_data.get('password', '')                          
                            if item.get("type") == "vod":
                                ext = item.get("container_extension", "mp4")
                                url = f"{host}/movie/{user}/{pwd}/{ch_id}.{ext}"
                            else:
                                url = f"{host}/live/{user}/{pwd}/{ch_id}.ts"
                        else:
                            url = item.get("url", "")                     
                        if not url: continue                    
                        f.write(f'#EXTINF:-1 tvg-id="{ch_id}" tvg-logo="{logo}" group-title="{group}",{name}\n')
                        f.write(f"{url}\n")                 
                    logging.debug("Finished writing all items to M3U file.")                     
            logging.info(f"File successfully written to disk: {file_path}")
            if hasattr(self.parent_window, "show_toast"):
                self.parent_window.show_toast(_("Playlist exported successfully!"))               
        except Exception as e:
            logging.error(f"CRITICAL ERROR during offline export: {e}")
            if hasattr(self.parent_window, "show_toast"):
                self.parent_window.show_toast(_("Error: ") + str(e))

    def _on_import_button_clicked(self, button):
        logging.info("User requested import. Opening file dialog...")
        dialog = Gtk.FileChooserDialog(
            title=_("Import Profile"),
            transient_for=self.parent_window,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Open"), Gtk.ResponseType.ACCEPT
        )
        dialog.set_modal(True)
        playlist_filter = Gtk.FileFilter()
        playlist_filter.set_name(_("Playlist & Backup Files (.m3u, .txt)"))
        playlist_filter.add_pattern("*.txt")
        playlist_filter.add_pattern("*.m3u")
        dialog.add_filter(playlist_filter)

        def on_import_response(d, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                gfile = d.get_file()
                if gfile:
                    path = gfile.get_path()
                    logging.info(f"User selected path for import: {path}")
                    self._read_and_import_data(path)
                    self.close()
            else:
                logging.debug("User cancelled the import file dialog.")               
            d.hide()
            GLib.idle_add(d.destroy)
        dialog.connect("response", on_import_response)
        dialog.present()

    def _read_and_import_data(self, file_path):
        logging.info(f"Starting import process from file: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            if not lines:
                logging.error("Import failed: The selected file is empty.")
                raise ValueError(_("The selected file is empty."))
            header = lines[0]
            logging.debug(f"File header detected: {header}")          
            new_profile = {
                "id": str(uuid.uuid4()),
                "icon_path": "",
                "epg_url": ""
            }
            if "XTREAM CODES" in header:
                logging.info("Recognized as Xtream Codes backup format.")
                new_profile["type"] = "xtream"
                for line in lines:
                    if line.startswith("Profile Name:"):
                        new_profile["name"] = line.split(":", 1)[1].strip() + " " + _("(Imported)")
                    elif line.startswith("Server URL:"):
                        new_profile["host"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Username:"):
                        new_profile["username"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Password:"):
                        new_profile["password"] = line.split(":", 1)[1].strip()                      
            elif "M3U PLAYLIST" in header:
                logging.info("Recognized as M3U Playlist backup format.")
                new_profile["type"] = "m3u_url"
                new_profile["name"] = _("Imported M3U Profile")
                for i, line in enumerate(lines):
                    if line.startswith("URL:"):
                        if i + 1 < len(lines):
                            new_profile["url"] = lines[i+1].strip()
            elif header.startswith("#EXTM3U"):
                logging.info("Recognized as standard M3U Playlist file.")
                new_profile["type"] = "m3u_file" 
                file_name_only = os.path.basename(file_path)
                new_profile["name"] = f"{file_name_only} " + _("(Imported)")
                new_profile["url"] = file_path 
                new_profile["path"] = file_path
            else:
                logging.error(f"Unrecognized file format. Header was: {header}")
                raise ValueError(_("Unrecognized file format. Please select a valid backup file."))               
            logging.debug(f"Saving new profile to system: {new_profile['name']}")
            profiles = load_profiles()
            profiles.append(new_profile)
            save_profiles(profiles)
            logging.info("Import process completed successfully.")
            if hasattr(self.parent_window, "show_toast"):
                self.parent_window.show_toast(_("Profile imported successfully! You can switch to it from the profile menu."))
        except Exception as e:
            logging.error(f"CRITICAL ERROR during import: {e}")
            if hasattr(self.parent_window, "show_toast"):
                self.parent_window.show_toast(_("Error: Could not import profile. {}").format(str(e)))

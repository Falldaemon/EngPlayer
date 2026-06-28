# ui/download_manager.py

import os
import threading
import logging
import requests
import database
import gettext
import time
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")  
from gi.repository import Gtk, GLib, GObject, Adw

_ = gettext.gettext

class DownloadManagerWidget(Gtk.Box):    
    __gsignals__ = {
        "download-finished": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "download-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "download-cancelled": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, **kwargs)
        self.set_visible(False)
        self.set_valign(Gtk.Align.CENTER)
        self.set_margin_end(12)
        self.icon = Gtk.Image.new_from_icon_name("folder-download-symbolic")
        self.append(self.icon)
        self.speed_label = Gtk.Label(label="")
        self.speed_label.add_css_class("caption")
        self.speed_label.add_css_class("dim-label")
        self.speed_label.set_width_chars(7) 
        self.speed_label.set_xalign(1.0)
        self.append(self.speed_label)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(120, -1)
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("0%")
        self.append(self.progress_bar)
        self.cancel_btn = Gtk.Button(icon_name="process-stop-symbolic")
        self.cancel_btn.add_css_class("flat")
        self.cancel_btn.add_css_class("circular")
        self.cancel_btn.set_tooltip_text(_("Cancel Download"))
        self.cancel_btn.connect("clicked", self._on_cancel_clicked)
        self.append(self.cancel_btn)
        self.active_url = None
        self.output_path = None
        self._stop_event = threading.Event()
        self.download_thread = None

    def start_download(self, url, output_path, speed_limit=None):
        if self.download_thread and self.download_thread.is_alive():
            logging.warning("DownloadManager: A download is already in progress.")
            return
        self.active_url = url
        self.output_path = output_path
        self.speed_limit = speed_limit 
        self._stop_event.clear()
        self.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text(_("Connecting..."))
        self.speed_label.set_text("")
        self.download_thread = threading.Thread(target=self._download_worker, daemon=True)
        database.save_active_download(self.active_url, self.output_path, self.speed_limit)       
        self.download_thread.start()

    def _on_cancel_clicked(self, btn):
        parent_window = self.get_root()
        if not parent_window:
            self._execute_cancel()
            return           
        dialog = Adw.MessageDialog(
            transient_for=parent_window,
            heading=_("Cancel Download?"),
            body=_("The download will be stopped and the incomplete file will be permanently deleted from your disk.\n\nAre you sure you want to cancel?"),
            modal=True
        )
        dialog.add_css_class("download-cancel-dialog")      
        dialog.add_response("continue", _("Resume Download"))
        dialog.add_response("delete", _("Cancel & Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("continue")
        dialog.set_close_response("continue")

        def _on_response(d, response_id):
            if response_id == "delete":
                self._execute_cancel()
            d.close()
        dialog.connect("response", _on_response)
        dialog.present()
        
    def _execute_cancel(self):
        self.cancel_download(user_cancelled=True)
        self.set_visible(False)
        self.emit("download-cancelled") 

    def cancel_download(self, user_cancelled=False):
        self._stop_event.set()
        self.is_user_cancelled = user_cancelled        
        if user_cancelled and self.active_url:
            database.remove_active_download(self.active_url)
            logging.info("DownloadManager: Download explicitly cancelled and removed from DB.")
        else:
            logging.info("DownloadManager: Download paused (App closing).")

    def _update_ui_progress(self, downloaded_bytes, total_bytes, speed_text):
        if speed_text:
            self.speed_label.set_text(speed_text)
        if total_bytes > 0:
            fraction = downloaded_bytes / total_bytes
            fraction = max(0.0, min(1.0, fraction))
            self.progress_bar.set_fraction(fraction)
            percentage = int(fraction * 100)
            self.progress_bar.set_text(f"%{percentage}")
        else:
            self.progress_bar.pulse()
            done_mb = downloaded_bytes / (1024 * 1024)
            self.progress_bar.set_text(f"{done_mb:.1f} MB")

    def _download_worker(self):
        headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0'}
        downloaded_bytes = 0
        total_bytes = 0
        if os.path.exists(self.output_path):
            downloaded_bytes = os.path.getsize(self.output_path)
            logging.info(f"DownloadManager: Found existing file, {downloaded_bytes} bytes downloaded so far.")
        try:
            head_req = requests.head(self.active_url, headers=headers, timeout=10, allow_redirects=True)
            if head_req.status_code in [200, 206]:
                total_bytes = int(head_req.headers.get('Content-Length', 0))
                if head_req.status_code == 200 and downloaded_bytes > 0:
                    total_bytes += downloaded_bytes
        except Exception as e:
            logging.warning(f"DownloadManager: Could not fetch Content-Length via HEAD: {e}")
        if total_bytes > 0 and downloaded_bytes >= total_bytes:
            logging.info("DownloadManager: File is already fully downloaded.")
            GLib.idle_add(self.set_visible, False)
            GLib.idle_add(self.emit, "download-finished", self.output_path)
            database.remove_active_download(self.active_url)
            return
        if downloaded_bytes > 0:
            headers['Range'] = f'bytes={downloaded_bytes}-'
            logging.info(f"DownloadManager: Resuming from byte {downloaded_bytes}")
        try:
            with requests.get(self.active_url, headers=headers, stream=True, timeout=15) as r:
                r.raise_for_status()               
                if total_bytes == 0:
                    cl = r.headers.get('Content-Length')
                    if cl:
                        total_bytes = int(cl)
                        if downloaded_bytes > 0 and r.status_code == 206:
                            total_bytes += downloaded_bytes
                mode = 'ab' if downloaded_bytes > 0 else 'wb'
                last_calc_time = time.time()
                last_calc_bytes = downloaded_bytes
                current_speed_text = ""
                throttle_start_time = time.time()
                throttle_bytes = 0
                with open(self.output_path, mode) as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self._stop_event.is_set():
                            break
                        if chunk:
                            f.write(chunk)
                            chunk_len = len(chunk)
                            downloaded_bytes += chunk_len
                            throttle_bytes += chunk_len
                            if getattr(self, 'speed_limit', None):
                                elapsed_throttle = time.time() - throttle_start_time
                                expected_time = throttle_bytes / self.speed_limit
                                if expected_time > elapsed_throttle:
                                    time.sleep(expected_time - elapsed_throttle)
                                if elapsed_throttle > 1.0:
                                    throttle_start_time = time.time()
                                    throttle_bytes = 0
                            current_time = time.time()
                            time_diff = current_time - last_calc_time                           
                            if time_diff >= 0.5:
                                f.flush()                                
                                bytes_diff = downloaded_bytes - last_calc_bytes
                                speed_kb = (bytes_diff / time_diff) / 1024
                                if speed_kb > 1024:
                                    current_speed_text = f"{speed_kb / 1024:.1f} MB/s"
                                else:
                                    current_speed_text = f"{speed_kb:.0f} KB/s"                             
                                last_calc_time = current_time
                                last_calc_bytes = downloaded_bytes
                                GLib.idle_add(self._update_ui_progress, downloaded_bytes, total_bytes, current_speed_text)
                    if not self._stop_event.is_set():
                        f.flush()
                        os.fsync(f.fileno()) 
                        GLib.idle_add(self._update_ui_progress, downloaded_bytes, total_bytes, current_speed_text)
            if getattr(self, 'is_user_cancelled', False):
                if self.output_path and os.path.exists(self.output_path):
                    try:
                        os.remove(self.output_path)
                        logging.info(f"DownloadManager: Incomplete file safely deleted: {self.output_path}")
                    except Exception as e:
                        logging.error(f"DownloadManager: Failed to delete incomplete file: {e}")
            elif not self._stop_event.is_set():
                logging.info(f"DownloadManager: Download completed successfully: {self.output_path}")
                GLib.idle_add(self.set_visible, False)
                GLib.idle_add(self.emit, "download-finished", self.output_path)
                database.remove_active_download(self.active_url)              
        except Exception as e:
            logging.error(f"DownloadManager: Download failed: {e}")
            GLib.idle_add(self.set_visible, False)
            GLib.idle_add(self.emit, "download-failed", str(e))

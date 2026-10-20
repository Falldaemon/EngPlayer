# main.py

import sys
import os
import time
import logging
import threading
import subprocess
import gi
import warnings
import ctypes
import ctypes.util


from utils.platform_utils import setup_platform_environment
setup_platform_environment()

warnings.filterwarnings("ignore", category=UserWarning)

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
os.chdir(script_dir)

from core.config import APP_ID
from utils.logging_setup import setup_logging
from utils.i18n_setup import setup_translation
from database import initialize_database
from utils.cache_cleaner import clean_all_caches
from utils import platform_utils

def ensure_daemon_started():
    platform_utils.start_daemon()

def request_background_permission_via_shell():
    try:
        logging.info("Setting up portal permission and command line...")
        cmd = [
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.portal.Desktop",
            "--object-path", "/org/freedesktop/portal/desktop",
            "--method", "org.freedesktop.portal.Background.RequestBackground",
            "/",
            "{'autostart': <true>, 'reason': <'Background Recording'>, 'commandline': <['engplayer-daemon']>}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logging.info(f"Portal Setup Successful: {result.stdout.strip()}")
        else:
            logging.error(f"Portal Error: {result.stderr.strip()}")
    except Exception as e:
        logging.error(f"Command execution error: {e}")
    finally:
        GLib.idle_add(ensure_daemon_started)

def install_host_service_if_needed():
    if os.path.exists("/.flatpak-info"):
        return
    try:
        os.system("systemctl --user daemon-reload")
        os.system("systemctl --user enable --now io.github.falldaemon.engplayer.recorder.service")
    except Exception:
        pass

def _get_libc():
    return platform_utils.get_glibc()

def _configure_malloc_tuning():
    libc = _get_libc()
    if not libc:
        return
    try:
        M_MMAP_THRESHOLD = -3
        M_TRIM_THRESHOLD = -1
        MMAP_TRIM_BYTES = 64 * 1024
        libc.mallopt(M_MMAP_THRESHOLD, MMAP_TRIM_BYTES)
        libc.mallopt(M_TRIM_THRESHOLD, MMAP_TRIM_BYTES)
        logging.info(f"glibc malloc tuning applied (mmap/trim threshold={MMAP_TRIM_BYTES} bytes).")
    except Exception as e:
        logging.info(f"glibc malloc tuning call failed, continuing without it: {e}")

def _malloc_trim_loop():
    libc = _get_libc()
    if not libc:
        logging.info("malloc_trim not available on this system; periodic trim disabled.")
        return
    while True:
        time.sleep(300)
        try:
            libc.malloc_trim(0)
        except Exception as e:
            logging.warning(f"malloc_trim failed, stopping periodic trim: {e}")
            return
            
_app_running_lock_handle = None

def _hold_app_running_lock():
    global _app_running_lock_handle
    if platform_utils.IS_WINDOWS:
        platform_utils.acquire_named_mutex(platform_utils.APP_MUTEX_NAME, exclusive=False)
        return
    try:
        import fcntl
        from core.config import APP_CONFIG_DIR
        os.makedirs(APP_CONFIG_DIR, exist_ok=True)
        handle = open(os.path.join(APP_CONFIG_DIR, "app.lock"), "a")
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        _app_running_lock_handle = handle
    except Exception as e:
        logging.warning(f"Could not acquire app running lock: {e}")            

def main():
    setup_logging()
    _configure_malloc_tuning()
    setup_translation()
    GLib.set_prgname("io.github.falldaemon.engplayer")
    GLib.set_application_name("EngPlayer")
    initialize_database()
    _hold_app_running_lock()
    if platform_utils.IS_FLATPAK:
        threading.Thread(target=request_background_permission_via_shell, daemon=True).start()
    elif platform_utils.IS_WINDOWS:
        ensure_daemon_started()
    else:
        threading.Thread(target=install_host_service_if_needed, daemon=True).start()
    threading.Thread(target=clean_all_caches, args=(30,), daemon=True).start()
    try:
        display = Gdk.Display.get_default()
        if display:
            icon_theme = Gtk.IconTheme.get_for_display(display)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            icons_dir = os.path.join(base_dir, "resources", "icons")
            if os.path.isdir(icons_dir):
                icon_theme.add_search_path(icons_dir)
    except Exception as e:
        logging.error(f"Icon path error: {e}")
    from core.app import MediaCenterApplication
    arguments = [arg for arg in sys.argv if arg != '--debug']
    app = MediaCenterApplication(application_id=APP_ID)
    threading.Thread(target=_malloc_trim_loop, daemon=True).start()
    return app.run(arguments)

if __name__ == "__main__":
    sys.exit(main())

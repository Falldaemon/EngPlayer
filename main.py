# main.py

import sys
import os
import logging
import threading
import subprocess
import gi
import warnings

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

def ensure_daemon_started():
    """
    Manually starts the daemon service for the current session.
    """
    try:
        subprocess.Popen(['/app/bin/engplayer-daemon'],
                         start_new_session=True,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception as e:
        logging.warning(f"Failed to start daemon: {e}")

def request_background_permission_via_shell():
    """
    Requests permission using the 'gdbus' command, including the 'commandline' parameter.
    """
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

def main():
    setup_logging()
    setup_translation()
    GLib.set_prgname("io.github.falldaemon.engplayer")
    GLib.set_application_name("EngPlayer")
    initialize_database()
    if os.path.exists("/.flatpak-info"):
        threading.Thread(target=request_background_permission_via_shell, daemon=True).start()
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
    return app.run(arguments)

if __name__ == "__main__":
    sys.exit(main())

# main.py

import sys
import os
import logging
import threading
import gi
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="fuzzywuzzy")

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

def install_flatpak_daemon_service():
    """
    Configures the background service.
    If running inside Flatpak, it relies on XDG Autostart (no host access needed).
    If running natively, it ensures the systemd service is enabled.
    """
    if os.path.exists("/.flatpak-info"):
        logging.info("Running inside Flatpak. Skipping host systemd setup (using internal Autostart).")
        return
    try:
        os.system("systemctl --user daemon-reload")
        os.system("systemctl --user enable --now io.github.falldaemon.engplayer.recorder.service")
        logging.info("Background recorder service check completed (Host Mode).")
    except Exception as e:
        logging.error(f"Failed to check background service: {e}")

def main():
    setup_logging()
    setup_translation()
    GLib.set_prgname("io.github.falldaemon.engplayer")
    GLib.set_application_name("EngPlayer")
    initialize_database()
    threading.Thread(target=install_flatpak_daemon_service, daemon=True).start()
    logging.info("Starting background cache cleanup task...")
    cleanup_thread = threading.Thread(target=clean_all_caches, args=(30,), daemon=True)
    cleanup_thread.start()
    try:
        display = Gdk.Display.get_default()
        if display:
            icon_theme = Gtk.IconTheme.get_for_display(display)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            icons_dir = os.path.join(base_dir, "resources", "icons")
            if os.path.isdir(icons_dir):
                icon_theme.add_search_path(icons_dir)
                logging.info(f"Icon search path added: {icons_dir}")
            else:
                logging.warning(f"Icon directory not found: {icons_dir}")
    except Exception as e:
        logging.error(f"Failed to set icon search path: {e}")
    from core.app import MediaCenterApplication    
    arguments = [arg for arg in sys.argv if arg != '--debug']
    app = MediaCenterApplication(application_id=APP_ID)
    return app.run(arguments)

if __name__ == "__main__":
    sys.exit(main())


# utils/sleep_inhibitor.py

import logging
from gi.repository import Gio, GLib
import gettext
_ = gettext.gettext

INHIBIT_SERVICE = "org.freedesktop.ScreenSaver"
INHIBIT_PATH = "/org/freedesktop/ScreenSaver"
INHIBIT_INTERFACE = "org.freedesktop.ScreenSaver"
class SleepInhibitor:
    """
    Uses DBus to inhibit system sleep and screensaver activation.
    """
    def __init__(self, app_name="EngPlayer", reason=_("Video Playing")):
        self.app_name = app_name
        self.reason = reason
        self.cookie = None
        self.proxy = None
        try:
            self.proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.NONE,
                None,
                INHIBIT_SERVICE,
                INHIBIT_PATH,
                INHIBIT_INTERFACE,
                None
            )
            logging.info("Successfully connected to DBus ScreenSaver service.")
        except GLib.Error as e:
            logging.warning(f"Could not connect to DBus ScreenSaver service: {e}. Sleep inhibition will be disabled.")

    def inhibit(self):
        """Starts inhibiting sleep/screensaver."""
        if not self.proxy or self.cookie is not None:
            return
        try:
            variant = self.proxy.call_sync(
                "Inhibit",
                GLib.Variant("(ss)", (self.app_name, self.reason)),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            self.cookie = variant.get_child_value(0).get_uint32()
            logging.info(f"Sleep mode inhibited with cookie: {self.cookie}")
        except GLib.Error as e:
            logging.error(f"Failed to inhibit sleep mode: {e}")
            self.cookie = None

    def uninhibit(self):
        """Stops inhibiting sleep/screensaver."""
        if not self.proxy or self.cookie is None:
            return
        try:
            self.proxy.call_sync(
                "UnInhibit",
                GLib.Variant("(u)", (self.cookie,)),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            logging.info(f"Sleep mode uninhibited for cookie: {self.cookie}")
        except GLib.Error as e:
            logging.warning(f"Could not uninhibit sleep mode (might be already released): {e}")
        finally:
            self.cookie = None

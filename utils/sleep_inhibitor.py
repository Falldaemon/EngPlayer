# utils/sleep_inhibitor.py

import logging
import gettext
from gi.repository import Gio, GLib, Gtk
from utils import platform_utils

_ = gettext.gettext

_GNOME_INHIBIT_FLAGS = 4 | 8

class SleepInhibitor:
    def __init__(self, application):
        self.application = application
        self.cookie = 0
        self.reason = _("Video Playing")
        self._win_inhibited = False
        self._gnome_cookie = 0

    def _call_gnome_session(self, method, args, reply_type):
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return bus.call_sync("org.gnome.SessionManager", "/org/gnome/SessionManager",
                             "org.gnome.SessionManager", method, args,
                             GLib.VariantType.new(reply_type) if reply_type else None,
                             Gio.DBusCallFlags.NONE, 2000, None)

    def _gnome_inhibit(self):
        try:
            app_id = self.application.get_application_id() or "engplayer"
            result = self._call_gnome_session(
                "Inhibit", GLib.Variant("(susu)", (app_id, 0, self.reason, _GNOME_INHIBIT_FLAGS)), "(u)")
            return result.unpack()[0]
        except GLib.Error as e:
            logging.debug(f"GNOME session manager inhibit not available: {e.message}")
            return 0

    def inhibit(self):
        if platform_utils.IS_WINDOWS:
            if not self._win_inhibited:
                platform_utils.set_windows_sleep_inhibited(True)
                self._win_inhibited = True
                logging.info("Sleep inhibited via SetThreadExecutionState.")
            return
        if self.cookie == 0 and self._gnome_cookie == 0 and self.application:
            if not platform_utils.IS_FLATPAK:
                self._gnome_cookie = self._gnome_inhibit()
                if self._gnome_cookie:
                    logging.info(f"Sleep inhibited via GNOME session manager. Cookie: {self._gnome_cookie}")
                    return
            flags = Gtk.ApplicationInhibitFlags.SUSPEND | Gtk.ApplicationInhibitFlags.IDLE
            self.cookie = self.application.inhibit(None, flags, self.reason)
            logging.info(f"Sleep inhibited via Portal/Gtk. Cookie: {self.cookie}")

    def uninhibit(self):
        if platform_utils.IS_WINDOWS:
            if self._win_inhibited:
                platform_utils.set_windows_sleep_inhibited(False)
                self._win_inhibited = False
                logging.info("Sleep uninhibited.")
            return
        if self._gnome_cookie != 0:
            try:
                self._call_gnome_session("Uninhibit", GLib.Variant("(u)", (self._gnome_cookie,)), None)
            except GLib.Error as e:
                logging.debug(f"GNOME session manager uninhibit failed: {e.message}")
            self._gnome_cookie = 0
            logging.info("Sleep uninhibited.")
            return
        if self.cookie != 0 and self.application:
            self.application.uninhibit(self.cookie)
            self.cookie = 0
            logging.info("Sleep uninhibited.")

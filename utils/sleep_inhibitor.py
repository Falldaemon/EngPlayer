# utils/sleep_inhibitor.py

import logging
import gettext
from gi.repository import Gtk

_ = gettext.gettext

class SleepInhibitor:
    """
    Uses Gtk.Application's built-in inhibit method which automatically
    uses the correct Portal mechanism under Flatpak.
    """
    def __init__(self, application):
        self.application = application
        self.cookie = 0
        self.reason = _("Video Playing")

    def inhibit(self):
        """Starts inhibiting sleep/screensaver."""
        if self.cookie == 0 and self.application:
            flags = Gtk.ApplicationInhibitFlags.SUSPEND | Gtk.ApplicationInhibitFlags.IDLE
            self.cookie = self.application.inhibit(None, flags, self.reason)
            logging.info(f"Sleep inhibited via Portal/Gtk. Cookie: {self.cookie}")

    def uninhibit(self):
        """Stops inhibiting sleep/screensaver."""
        if self.cookie != 0 and self.application:
            self.application.uninhibit(self.cookie)
            self.cookie = 0
            logging.info("Sleep uninhibited.")

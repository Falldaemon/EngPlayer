# utils/sleep_inhibitor.py

import logging
import gettext
from gi.repository import Gtk

_ = gettext.gettext

class SleepInhibitor:
    def __init__(self, application):
        self.application = application
        self.cookie = 0
        self.reason = _("Video Playing")

    def inhibit(self):
        if self.cookie == 0 and self.application:
            flags = Gtk.ApplicationInhibitFlags.SUSPEND | Gtk.ApplicationInhibitFlags.IDLE
            self.cookie = self.application.inhibit(None, flags, self.reason)
            logging.info(f"Sleep inhibited via Portal/Gtk. Cookie: {self.cookie}")

    def uninhibit(self):
        if self.cookie != 0 and self.application:
            self.application.uninhibit(self.cookie)
            self.cookie = 0
            logging.info("Sleep uninhibited.")

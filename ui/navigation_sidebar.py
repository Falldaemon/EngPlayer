# ui/navigation_sidebar.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
import gettext
_ = gettext.gettext
class NavigationSidebar(Gtk.Box):

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        self.set_size_request(300, -1)
        self.nav_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.append(self.nav_buttons_box)
        self.list_stack = Gtk.Stack()
        self.list_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.list_stack.set_transition_duration(350)
        self.list_stack.set_vexpand(True)
        self.append(self.list_stack)

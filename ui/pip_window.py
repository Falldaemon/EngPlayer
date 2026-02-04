# ui/pip_window.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GObject
import gettext
import logging

_ = gettext.gettext

class PipWindow(Gtk.Window):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("Picture-in-Picture"))
        self.set_default_size(360, 202)
        self.set_decorated(False) 
        self.set_resizable(True) 
        self.window_handle = Gtk.WindowHandle()
        self.set_child(self.window_handle)
        self.overlay = Gtk.Overlay()
        self.window_handle.set_child(self.overlay)
        main_box = Gtk.Box()
        main_box.add_css_class("black")
        self.overlay.set_child(main_box)
        self.aspect_frame = Gtk.AspectFrame(ratio=16/9, obey_child=False, xalign=0.5, yalign=0.5)
        main_box.append(self.aspect_frame)
        self.picture_widget = Gtk.Picture(hexpand=True, vexpand=True, can_shrink=True)
        self.picture_widget.set_can_target(False)
        self.aspect_frame.set_child(self.picture_widget)
        self.controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.controls_box.set_halign(Gtk.Align.END)
        self.controls_box.set_valign(Gtk.Align.START)
        self.controls_box.set_margin_top(10)
        self.controls_box.set_margin_end(10)
        self.controls_box.set_opacity(0.0)
        close_btn = Gtk.Button(icon_name="window-close-symbolic")
        close_btn.add_css_class("circular")
        close_btn.add_css_class("osd")
        close_btn.set_tooltip_text(_("Close"))
        close_btn.connect("clicked", self.on_close_clicked)
        close_btn.set_cursor(Gdk.Cursor.new_from_name("pointer", None))        
        self.controls_box.append(close_btn)
        self.overlay.add_overlay(self.controls_box)
        hover_controller = Gtk.EventControllerMotion()
        hover_controller.connect("enter", self.on_mouse_enter)
        hover_controller.connect("leave", self.on_mouse_leave)
        self.add_controller(hover_controller)
        scroll_controller = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_controller.connect("scroll", self.on_scroll_resize)
        self.add_controller(scroll_controller)

    def set_paintable(self, paintable):
        if self.picture_widget:
            self.picture_widget.set_paintable(paintable)

    def on_close_clicked(self, btn):
        self.close()

    def on_mouse_enter(self, controller, x, y):
        self.controls_box.set_opacity(1.0)

    def on_mouse_leave(self, controller):
        self.controls_box.set_opacity(0.0)

    def on_scroll_resize(self, controller, dx, dy):
        current_width = self.get_width()
        step = 20
        change = -1 * dy * step      
        new_width = current_width + change
        if new_width < 200:
            new_width = 200
        if new_width > 1200:
            new_width = 1200
        new_height = new_width * (9/16)
        self.set_default_size(int(new_width), int(new_height))

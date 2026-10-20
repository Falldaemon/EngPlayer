# ui/native_video_host.py

import os
import ctypes
import logging
from ctypes import wintypes

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

_user32 = ctypes.WinDLL("user32", use_last_error=True)

_user32.CreateWindowExW.restype = wintypes.HWND
_user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.SetParent.restype = wintypes.HWND
_user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_GA_ROOT = 2
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_WINEVENTPROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                   wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
_user32.SetWinEventHook.restype = wintypes.HANDLE
_user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, _WINEVENTPROC,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
_user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

_WS_POPUP = 0x80000000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_NOACTIVATE = 0x08000000
_GWLP_HWNDPARENT = -8
_SS_BLACKRECT = 0x00000004
_GWL_STYLE = -16
_GW_OWNER = 4
_SW_HIDE = 0
_SW_SHOWNA = 8
_SWP_NOSIZE = 0x0001
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_EVENT_OBJECT_LOCATIONCHANGE = 0x800B
_EVENT_OBJECT_SHOW = 0x8002
_HWND_TOP = 0
_SWP_NOMOVE = 0x0002
_OBJID_WINDOW = 0

_OSD_CSS = """
popover.native-osd-layer, popover.native-osd-layer > contents {
    background: transparent; box-shadow: none; border: none;
    padding: 0; margin: 0; border-radius: 0;
}
.native-osd-base { background-color: rgba(0, 0, 0, 0.01); }
"""
_css_installed = False


def _surface_hwnd(surface):
    if surface is None:
        return None
    try:
        get_ptr = ctypes.pythonapi.PyCapsule_GetPointer
        get_ptr.restype = ctypes.c_void_p
        get_ptr.argtypes = [ctypes.py_object, ctypes.c_char_p]
        ptr = get_ptr(surface.__gpointer__, None)
        gtk = ctypes.CDLL("libgtk-4-1.dll")
        fn = gtk.gdk_win32_surface_get_handle
        fn.restype = ctypes.c_void_p
        fn.argtypes = [ctypes.c_void_p]
        hwnd = fn(ptr)
        return hwnd or None
    except Exception as e:
        logging.debug(f"NativeVideoHost: gdk_win32_surface_get_handle failed: {e}")
        return None


class NativeVideoHost:
    def __init__(self, anchor):
        global _css_installed
        self.anchor = anchor
        self.hwnd = None
        self.parent_hwnd = None
        self.video_visible = True
        self.video_active = False
        self.key_forward = None
        self.motion_forward = None
        self.resized_callback = None
        self._last_rect = None
        self._layer_size = None
        self._parent_rect = None
        self._tick_id = None
        self._hook = None
        self._hook_proc = None
        self._show_hook = None
        self._show_hook_proc = None
        self._cursor_name = None
        self._mapped = False
        self._alt_anchor = None
        self._alt_mapped = False
        self._override_anchor = None   
        self._current_parent = None
        if not _css_installed:
            css = Gtk.CssProvider()
            css.load_from_string(_OSD_CSS)
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            _css_installed = True
        self.layer = Gtk.Popover()
        self.layer.add_css_class("native-osd-layer")
        self.layer.set_parent(anchor)
        self.layer.set_autohide(False)
        self.layer.set_has_arrow(False)
        self.layer.set_can_focus(True)
        self.osd_overlay = Gtk.Overlay()
        self._osd_base = Gtk.Box(hexpand=True, vexpand=True)
        self._osd_base.add_css_class("native-osd-base")
        self.osd_overlay.set_child(self._osd_base)
        self.layer.set_child(self.osd_overlay)
        self.layer.connect("closed", self._on_layer_closed)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_layer_key)
        self.layer.add_controller(keys)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_layer_motion)
        self.osd_overlay.add_controller(motion)
        anchor.connect("map", self._on_map)
        anchor.connect("unmap", self._on_unmap)
        anchor.connect("unrealize", lambda *_: self.destroy())

    def get_window_handle(self):
        if self.hwnd is None:
            root = self.anchor.get_root()
            if root is not None and root.get_realized():
                self._create_native_window()
        return self.hwnd

    def set_video_visible(self, visible):
        self.video_visible = bool(visible)
        self._apply_hwnd_visibility()

    def set_video_active(self, active):
        self.video_active = bool(active)
        logging.debug(f"NativeVideoHost: video active={self.video_active}.")
        self._apply_hwnd_visibility()

    def destroy(self):
        self._stop_tick()
        if self._hook:
            _user32.UnhookWinEvent(self._hook)
            self._hook = None
        if self._show_hook:
            _user32.UnhookWinEvent(self._show_hook)
            self._show_hook = None
        if self.hwnd:
            _user32.DestroyWindow(self.hwnd)
            self.hwnd = None

    def _create_native_window(self):
        root = self.anchor.get_root()
        parent = _surface_hwnd(root.get_surface() if root else None)
        if not parent:
            logging.error("NativeVideoHost: could not resolve the main window HWND.")
            return
        self.parent_hwnd = parent
        self._current_parent = parent
        self.hwnd = _user32.CreateWindowExW(
            _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE, "STATIC", None, _WS_POPUP | _SS_BLACKRECT,
            0, 0, 16, 16, parent, None, None, None)
        if not self.hwnd:
            logging.error(f"NativeVideoHost: CreateWindowExW failed ({ctypes.get_last_error()}).")
            return
        self._hook_proc = _WINEVENTPROC(self._on_win_event)
        self._hook = _user32.SetWinEventHook(_EVENT_OBJECT_LOCATIONCHANGE, _EVENT_OBJECT_LOCATIONCHANGE,
                                             None, self._hook_proc, os.getpid(), 0, 0)
        self._show_hook_proc = _WINEVENTPROC(self._on_win_show)
        self._show_hook = _user32.SetWinEventHook(_EVENT_OBJECT_SHOW, _EVENT_OBJECT_SHOW,
                                                  None, self._show_hook_proc, os.getpid(), 0, 0)
        logging.info(f"NativeVideoHost: video HWND {self.hwnd:#x} created in {parent:#x} "
                     f"(move hook: {'yes' if self._hook else 'no'}).")
        self._reposition()
        self._apply_hwnd_visibility()

    def _apply_hwnd_visibility(self):
        if self.hwnd:
            show = self._target() is not None and self.video_visible and self.video_active
            was_visible = bool(_user32.IsWindowVisible(self.hwnd))
            if show != was_visible:
                logging.debug(f"NativeVideoHost: native window {'shown' if show else 'hidden'} "
                              f"(mapped={self._mapped}, video_visible={self.video_visible}, active={self.video_active}).")
            _user32.ShowWindow(self.hwnd, _SW_SHOWNA if show else _SW_HIDE)
            if show:
                self._keep_below_layer()

    def _keep_below_layer(self):
        layer_hwnd = _surface_hwnd(self.layer.get_surface())
        if self.hwnd and layer_hwnd:
            _user32.SetWindowPos(self.hwnd, layer_hwnd, 0, 0, 0, 0,
                                 _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)

    def _reposition(self):
        if not self.hwnd:
            return
        target = self._target()
        root = target.get_root() if target is not None else None
        if root is None:
            return
        root_hwnd = _surface_hwnd(root.get_surface())
        if root_hwnd and root_hwnd != self._current_parent:
            _user32.SetWindowLongPtrW(self.hwnd, _GWLP_HWNDPARENT, root_hwnd)
            self._current_parent = root_hwnd
            self._last_rect = None
            self._apply_hwnd_visibility()
            logging.debug(f"NativeVideoHost: video window now owned by HWND {root_hwnd:#x}.")
        ok, bounds = target.compute_bounds(root)
        if not ok:
            return
        left = max(bounds.get_x(), 0)
        top = max(bounds.get_y(), 0)
        right = min(bounds.get_x() + bounds.get_width(), root.get_width())
        bottom = min(bounds.get_y() + bounds.get_height(), root.get_height())
        ox, oy = root.get_surface_transform()
        surface = root.get_surface()
        scale = surface.get_scale() if hasattr(surface, "get_scale") else surface.get_scale_factor()
        origin = wintypes.POINT(int(round((left + ox) * scale)),
                                int(round((top + oy) * scale)))
        if not _user32.ClientToScreen(self._current_parent, ctypes.byref(origin)):
            return
        rect = (origin.x, origin.y,
                max(1, int(round((right - left) * scale))), max(1, int(round((bottom - top) * scale))))
        if rect != self._last_rect:
            size_changed = self._last_rect is None or rect[2:] != self._last_rect[2:]
            _user32.SetWindowPos(self.hwnd, None, *rect, _SWP_NOZORDER | _SWP_NOACTIVATE)
            self._last_rect = rect
            if size_changed and self.resized_callback:
                try:
                    self.resized_callback(rect[2], rect[3])
                except Exception as e:
                    logging.debug(f"NativeVideoHost: resized callback failed: {e}")

    def _on_win_event(self, _hook, _event, hwnd, id_object, _child, _thread, _time):
        if id_object != _OBJID_WINDOW:
            return
        if hwnd == self._current_parent:
            self._reposition()
        if hwnd != self.parent_hwnd:
            return
        r = wintypes.RECT()
        if not _user32.GetWindowRect(self.parent_hwnd, ctypes.byref(r)):
            return
        rect = (r.left, r.top, r.right, r.bottom)
        old = self._parent_rect
        self._parent_rect = rect
        if old is None or rect == old or not self.layer.get_visible():
            return
        same_size = (rect[2] - rect[0] == old[2] - old[0]) and (rect[3] - rect[1] == old[3] - old[1])
        if not same_size:
            return
        dx, dy = rect[0] - old[0], rect[1] - old[1]
        for h in self._layer_hwnds():
            pr = wintypes.RECT()
            if _user32.GetWindowRect(h, ctypes.byref(pr)):
                _user32.SetWindowPos(h, None, pr.left + dx, pr.top + dy, 0, 0,
                                     _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE)

    def _layer_hwnds(self):
        h = _surface_hwnd(self.layer.get_surface())
        if h:
            return [h]
        found = []
        pid = os.getpid()
        want = self._layer_size

        def cb(hwnd, _lp):
            if hwnd != self.parent_hwnd and _user32.IsWindowVisible(hwnd) \
                    and _user32.GetWindow(hwnd, _GW_OWNER) == self.parent_hwnd:
                owner_pid = wintypes.DWORD()
                _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
                if owner_pid.value == pid:
                    r = wintypes.RECT()
                    _user32.GetWindowRect(hwnd, ctypes.byref(r))
                    if want is None or abs((r.right - r.left) - want[0]) < 64:
                        found.append(hwnd)
            return True
        _user32.EnumWindows(_WNDENUMPROC(cb), 0)
        return found

    def add_alt_anchor(self, widget):
        self._alt_anchor = widget
        widget.connect("map", self._on_alt_map)
        widget.connect("unmap", self._on_alt_unmap)

    def set_override_anchor(self, widget):
        self._override_anchor = widget
        self._last_rect = None
        if self.hwnd is None and widget is not None:
            self._create_native_window()
        self._start_tick()
        self._reposition()
        self._apply_hwnd_visibility()

    def _target(self):
        if self._override_anchor is not None and self._override_anchor.get_mapped():
            return self._override_anchor
        if self._mapped:
            return self.anchor
        if self._alt_mapped:
            return self._alt_anchor
        return None

    def _on_alt_map(self, *_):
        self._alt_mapped = True
        self._last_rect = None
        if self.hwnd is None:
            self._create_native_window()
        self._apply_hwnd_visibility()
        self._start_tick()

    def _on_alt_unmap(self, *_):
        self._alt_mapped = False
        self._last_rect = None
        self._apply_hwnd_visibility()
        if not self._mapped and self._override_anchor is None:
            self._stop_tick()

    def _on_map(self, *_):
        self._mapped = True
        self._last_rect = None
        if self.hwnd is None:
            self._create_native_window()
        self._apply_hwnd_visibility()
        self._start_tick()
        GLib.idle_add(self._show_layer)

    def _on_unmap(self, *_):
        self._mapped = False
        self._last_rect = None
        if not self._alt_mapped and self._override_anchor is None:
            self._stop_tick()
        self._apply_hwnd_visibility()
        if self.layer.get_visible():
            layer_hwnds = self._layer_hwnds()
            self.layer.popdown()
            GLib.timeout_add(100, self._ensure_layer_hidden, layer_hwnds)

    def _ensure_layer_hidden(self, layer_hwnds):
        if self.layer.get_visible():
            return GLib.SOURCE_REMOVE
        for h in layer_hwnds:
            if _user32.IsWindowVisible(h):
                _user32.ShowWindow(h, _SW_HIDE)
                logging.info(f"NativeVideoHost: stale OSD layer window {h:#x} hidden.")
        return GLib.SOURCE_REMOVE

    def _show_layer(self):
        if self._mapped and not self.layer.get_visible():
            self._layer_size = None
            self._place_layer()
            self.layer.popup()
            logging.debug("NativeVideoHost: OSD layer shown.")
            GLib.idle_add(self._raise_other_popups)
        return GLib.SOURCE_REMOVE

    def _on_layer_closed(self, *_):
        logging.debug(f"NativeVideoHost: OSD layer closed (mapped={self._mapped}).")
        if self._mapped:
            GLib.idle_add(self._show_layer)

    def _is_other_popup(self, hwnd):
        if not hwnd or hwnd in (self.parent_hwnd, self.hwnd):
            return False
        if _user32.GetAncestor(hwnd, _GA_ROOT) != hwnd:
            return False  
        layer_hwnd = _surface_hwnd(self.layer.get_surface())
        if layer_hwnd and _user32.GetWindow(hwnd, _GW_OWNER) == layer_hwnd:
            return False
        return hwnd != layer_hwnd

    def _raise_popup(self, hwnd):
        _user32.SetWindowPos(hwnd, _HWND_TOP, 0, 0, 0, 0,
                             _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE)

    def _on_win_show(self, _hook, _event, hwnd, id_object, _child, _thread, _time):
        if id_object != _OBJID_WINDOW or not self.layer.get_visible():
            return
        if self._is_other_popup(hwnd):
            self._raise_popup(hwnd)
            logging.debug(f"NativeVideoHost: popup {hwnd:#x} raised above the OSD layer.")

    def _raise_other_popups(self):
        pid = os.getpid()

        def cb(hwnd, _lp):
            if _user32.IsWindowVisible(hwnd) and self._is_other_popup(hwnd):
                owner_pid = wintypes.DWORD()
                _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
                if owner_pid.value == pid:
                    self._raise_popup(hwnd)
            return True
        _user32.EnumWindows(_WNDENUMPROC(cb), 0)
        return GLib.SOURCE_REMOVE

    def _place_layer(self):
        w = self.anchor.get_width()
        h = self.anchor.get_height()
        root = self.anchor.get_root()
        if root is not None:
            ok, bounds = self.anchor.compute_bounds(root)
            if ok:
                w = min(w, int(root.get_width() - max(bounds.get_x(), 0)))
                h = min(h, int(root.get_height() - max(bounds.get_y(), 0)))
        if w <= 0 or h <= 0 or (w, h) == self._layer_size:
            return
        self._layer_size = (w, h)
        self.osd_overlay.set_size_request(w, h)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = 0, 0, w, 1
        self.layer.set_pointing_to(rect)
        self.layer.set_position(Gtk.PositionType.BOTTOM)
        if self.layer.get_visible():
            self.layer.present()

    def _start_tick(self):
        if self._tick_id is None:
            self._tick_id = GLib.timeout_add(100, self._tick)

    def _stop_tick(self):
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None

    def _tick(self):
        self._reposition()
        self._place_layer()
        self._sync_cursor()
        return GLib.SOURCE_CONTINUE

    def _sync_cursor(self):
        root = self.anchor.get_root()
        layer_surface = self.layer.get_surface()
        if root is None or layer_surface is None:
            return
        cursor = root.get_surface().get_cursor()
        name = cursor.get_name() if cursor else None
        if name != self._cursor_name:
            self._cursor_name = name
            layer_surface.set_cursor(cursor)

    def _on_layer_key(self, controller, keyval, keycode, state):
        handled = False
        if self.key_forward:
            try:
                handled = bool(self.key_forward(controller, keyval, keycode, state))
            except Exception as e:
                logging.error(f"NativeVideoHost: key forward failed: {e}")
        if keyval == Gdk.KEY_Escape:
            return True
        return handled

    def _on_layer_motion(self, controller, x, y):
        if self.motion_forward:
            try:
                self.motion_forward(controller, x, y)
            except Exception as e:
                logging.error(f"NativeVideoHost: motion forward failed: {e}")

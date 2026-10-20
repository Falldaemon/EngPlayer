# ui/provider_test_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Adw
import logging
import time
import threading
import requests
import gettext
from datetime import datetime
from data_providers import xtream_client
from data_providers.m3u_provider import parse_m3u_content

_ = gettext.gettext


class ProviderTestDialog(Adw.MessageDialog):
    def __init__(self, main_window, profile_data):
        super().__init__()
        self.set_transient_for(main_window)
        self.profile_data = profile_data
        self.add_css_class("provider-test-dialog")
        self.set_default_size(420, 480)
        self.set_heading(_("Provider Test"))
        self.add_response("close", _("Close"))
        self.set_default_response("close")
        self.set_close_response("close")
        self.connect("response", lambda d, r: self.destroy())
        self.root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.root_box.set_margin_top(10)
        self.root_box.set_margin_bottom(10)
        self.root_box.set_margin_start(10)
        self.root_box.set_margin_end(10)
        self.set_extra_child(self.root_box)
        self.status_page = Adw.StatusPage()
        self.status_page.set_title(_("Testing provider..."))
        self.status_page.set_description(_("This may take a few seconds."))
        if hasattr(Adw, "Spinner"):
            spinner = Adw.Spinner(width_request=32, height_request=32, halign=Gtk.Align.CENTER)
        else:
            spinner = Gtk.Spinner(width_request=32, height_request=32, halign=Gtk.Align.CENTER)
            spinner.start()
        self.status_page.set_child(spinner)
        self.root_box.append(self.status_page)
        self.results_group = None
        self._start_test()

    def _start_test(self):
        threading.Thread(target=self._run_test_thread, daemon=True).start()

    def _run_test_thread(self):
        profile_type = self.profile_data.get("type")
        result = {"success": False, "error": None}
        try:
            if profile_type == "xtream":
                result = self._test_xtream()
            elif profile_type in ("m3u_url", "m3u_file"):
                result = self._test_m3u()
            else:
                result = {"success": False, "error": _("Unsupported profile type for testing.")}
        except Exception as e:
            logging.error(f"[ProviderTest] Unexpected error: {e}")
            result = {"success": False, "error": str(e)}
        GLib.idle_add(self._show_results, result)

    def _test_xtream(self):
        start = time.time()
        user_info = xtream_client.get_user_authentication(self.profile_data)
        elapsed_ms = int((time.time() - start) * 1000)
        if not user_info:
            return {"success": False, "error": _("Could not connect to the provider. Check your credentials and connection.")}
        live_categories = xtream_client.get_live_categories(self.profile_data)
        live_streams = xtream_client.get_live_streams(self.profile_data)
        vod_categories = xtream_client.get_vod_categories(self.profile_data)
        vod_streams = xtream_client.get_vod_streams(self.profile_data)
        series_categories = xtream_client.get_series_categories(self.profile_data)
        series_list = xtream_client.get_series_streams(self.profile_data, "all")
        exp_date = self._format_timestamp(user_info.get("exp_date"))
        status = user_info.get("status", "-")
        max_conn = user_info.get("max_connections", "-")
        active_conn = user_info.get("active_cons", "-")
        return {
            "success": True,
            "type": "xtream",
            "elapsed_ms": elapsed_ms,
            "status": status,
            "exp_date": exp_date or _("Unlimited / Unknown"),
            "max_connections": max_conn,
            "active_connections": active_conn,
            "live_categories": len(live_categories),
            "live_streams": len(live_streams),
            "vod_categories": len(vod_categories),
            "vod_streams": len(vod_streams),
            "series_categories": len(series_categories),
            "series_count": len(series_list),
            "catchup": self._count_catchup(live_streams),
        }

    def _test_m3u(self):
        profile_type = self.profile_data.get("type")
        start = time.time()
        try:
            if profile_type == "m3u_url":
                url = self.profile_data.get("url")
                response = requests.get(url, timeout=20)
                response.raise_for_status()
                lines = response.text.splitlines()
            else:
                path = self.profile_data.get("path")
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.read().splitlines()
        except Exception as e:
            return {"success": False, "error": f"{_('Could not access the M3U source.')} ({e})"}
        elapsed_ms = int((time.time() - start) * 1000)

        channels, vod, _epg = parse_m3u_content(lines)
        total_channels = sum(len(v) for v in channels.values())
        total_vod = sum(len(v) for v in vod.values())
        return {
            "success": True,
            "type": "m3u",
            "elapsed_ms": elapsed_ms,
            "total_channels": total_channels,
            "total_vod": total_vod,
            "category_count": len(channels),
            "catchup": self._count_catchup([c for items in channels.values() for c in items]),
        }

    def _format_timestamp(self, ts):
        if not ts or not str(ts).isdigit() or int(ts) == 0:
            return None
        try:
            return datetime.fromtimestamp(int(ts)).strftime('%d.%m.%Y')
        except (ValueError, OSError):
            return None

    def _count_catchup(self, streams):
        count = 0
        max_days = 0
        for stream in streams:
            if str(stream.get("tv_archive", "0")).strip() in ("", "0"):
                continue
            count += 1
            try:
                max_days = max(max_days, int(stream.get("tv_archive_duration") or 0))
            except (TypeError, ValueError):
                pass
        return count, max_days

    def _show_results(self, result):
        self.root_box.remove(self.status_page)
        if not result.get("success"):
            error_page = Adw.StatusPage()
            error_page.set_icon_name("dialog-warning-symbolic")
            error_page.set_title(_("Test Failed"))
            error_page.set_description(result.get("error", _("Unknown error.")))
            self.root_box.append(error_page)
            return False
        group = Adw.PreferencesGroup()
        self.root_box.append(group)
        speed_row = Adw.ActionRow(title=_("Response Time"))
        speed_row.add_suffix(Gtk.Label(label=f"{result['elapsed_ms']} ms"))
        group.add(speed_row)
        if result["type"] == "xtream":
            status_row = Adw.ActionRow(title=_("Account Status"))
            status_row.add_suffix(Gtk.Label(label=str(result["status"])))
            group.add(status_row)
            exp_row = Adw.ActionRow(title=_("Expiration Date"))
            exp_row.add_suffix(Gtk.Label(label=str(result["exp_date"])))
            group.add(exp_row)
            conn_row = Adw.ActionRow(title=_("Connections"))
            conn_row.add_suffix(Gtk.Label(label=f"{result['active_connections']} / {result['max_connections']}"))
            group.add(conn_row)
            live_row = Adw.ActionRow(title=_("Live TV"))
            live_row.add_suffix(Gtk.Label(label=_("{} categories, {} channels").format(
                result["live_categories"], result["live_streams"])))
            group.add(live_row)
            vod_row = Adw.ActionRow(title=_("Movies (VOD)"))
            vod_row.add_suffix(Gtk.Label(label=_("{} categories, {} movies").format(
                result["vod_categories"], result["vod_streams"])))
            group.add(vod_row)
            series_row = Adw.ActionRow(title=_("Series"))
            series_row.add_suffix(Gtk.Label(label=_("{} categories, {} series").format(
                result["series_categories"], result["series_count"])))
            group.add(series_row)
        elif result["type"] == "m3u":
            channels_row = Adw.ActionRow(title=_("Channels"))
            channels_row.add_suffix(Gtk.Label(label=str(result["total_channels"])))
            group.add(channels_row)
            vod_row = Adw.ActionRow(title=_("VOD Files"))
            vod_row.add_suffix(Gtk.Label(label=str(result["total_vod"])))
            group.add(vod_row)
            cat_row = Adw.ActionRow(title=_("Categories"))
            cat_row.add_suffix(Gtk.Label(label=str(result["category_count"])))
            group.add(cat_row)
        catchup_count, catchup_days = result.get("catchup", (0, 0))
        catchup_row = Adw.ActionRow(title=_("Catch-up"))
        if catchup_count:
            catchup_text = _("{} channels, up to {} days").format(catchup_count, catchup_days)
        else:
            catchup_text = "0"
        catchup_row.add_suffix(Gtk.Label(label=catchup_text))
        group.add(catchup_row)
        return False

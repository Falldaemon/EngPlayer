# ui/catchup_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GObject, GLib
import gettext
from datetime import datetime, timedelta, timezone
import logging
_ = gettext.gettext
class CatchupDialog(Adw.PreferencesWindow):
    __gsignals__ = {
        'program-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,))
    }

    def __init__(self, parent, channel_id, archive_duration_days, all_epg_data):
        super().__init__(transient_for=parent)
        self.add_css_class("catchup-dialog")
        self.channel_id = channel_id
        self.archive_duration_days = archive_duration_days
        self.all_epg_data = all_epg_data
        self.set_title(_("Past Programs"))
        self.set_default_size(550, 600)
        self.set_modal(True)
        self.set_search_enabled(False)
        self.page = Adw.PreferencesPage()
        self.add(self.page)
        self._populate_programs()

    def _populate_programs(self):
        """Filters EPG data, groups by date, and populates the list."""
        channel_programs = self.all_epg_data.get(self.channel_id, [])
        if not channel_programs:
            no_data_group = Adw.PreferencesGroup()
            no_data_label = Gtk.Label(label=_("No EPG data found for this channel."), margin_top=15, margin_bottom=15)
            no_data_group.add(no_data_label)
            self.page.add(no_data_group)
            return
        grouped_programs = {}
        now_local = datetime.now().astimezone()
        start_date_limit_local = now_local - timedelta(days=self.archive_duration_days)
        for program in channel_programs:
            program_start_local = program['start'].astimezone()
            program_stop_local = program['stop'].astimezone()
            if start_date_limit_local <= program_stop_local < now_local:
                date_str = program_start_local.strftime('%Y-%m-%d')
                if date_str not in grouped_programs:
                    grouped_programs[date_str] = []
                grouped_programs[date_str].append(program)
        if not grouped_programs:
            no_data_group = Adw.PreferencesGroup()
            no_data_label = Gtk.Label(label=_("No past programs found for the last {days} days.").format(days=self.archive_duration_days), margin_top=15, margin_bottom=15)
            no_data_group.add(no_data_label)
            self.page.add(no_data_group)
            return
        sorted_dates = sorted(grouped_programs.keys(), reverse=True)
        today_str = now_local.strftime('%Y-%m-%d')
        yesterday_str = (now_local - timedelta(days=1)).strftime('%Y-%m-%d')
        for date_str in sorted_dates:
            programs_for_day = grouped_programs[date_str]
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                if date_str == today_str:
                     formatted_date_title = _("Today") + date_obj.strftime(" (%d %B %A)")
                elif date_str == yesterday_str:
                     formatted_date_title = _("Yesterday") + date_obj.strftime(" (%d %B %A)")
                else:
                    dt_glib = GLib.DateTime.new_local(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0)
                    formatted_date_title = dt_glib.format("%x (%A)")
            except Exception as e:
                 logging.warning(f"Error formatting date: {e}")
                 formatted_date_title = date_str
            day_group = Adw.PreferencesGroup(title=formatted_date_title)
            self.page.add(day_group)
            for program in sorted(programs_for_day, key=lambda p: p['start'], reverse=True):
                local_start = program['start'].astimezone()
                local_stop = program['stop'].astimezone()
                time_range_str = f"{local_start.strftime('%H:%M')} - {local_stop.strftime('%H:%M')}"
                safe_title = GLib.markup_escape_text(program['title'])
                row = Adw.ActionRow(
                    title=safe_title,
                    subtitle=time_range_str
                )
                row.program_data = program
                row.set_activatable(True)
                row.connect("activated", self._on_program_row_activated)
                day_group.add(row)

    def _on_program_row_activated(self, row):
        """Runs when a program row is clicked."""
        if hasattr(row, "program_data"):
            selected_program = row.program_data
            logging.info(f"Catch-up program selected: {selected_program['title']} @ {selected_program['start']}")
            self.emit('program-selected', selected_program)
            self.close()

# ui/scheduler_window.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GObject, GLib, Pango
import gettext
from datetime import datetime, time, timedelta
import database
_ = gettext.gettext
class SchedulerWindow(Adw.PreferencesWindow):
    __gsignals__ = {
        'schedule-saved': (GObject.SignalFlags.RUN_FIRST, None, (str, str, str, int, int, str)), 
        'schedule-deleted': (GObject.SignalFlags.RUN_FIRST, None, (int,))
    }

    def __init__(self, parent, bouquets_data):
        super().__init__(transient_for=parent)
        self.set_title(_("Recording Scheduler"))
        self.set_default_size(600, 750)
        self.set_modal(True)
        self.add_css_class("scheduler-window")
        self.set_search_enabled(False)
        self.bouquets_data = bouquets_data
        self.all_bouquet_names = sorted(self.bouquets_data.keys())
        self.selected_bouquet_name = None
        self.selected_channel_data = None
        main_page = Adw.PreferencesPage()
        self.add(main_page)
        add_group = Adw.PreferencesGroup(title=_("Add New Scheduled Recording"))
        self.program_name_entry = Gtk.Entry(placeholder_text=_("E.g. TV Show Name (Optional)"))
        name_row = Adw.ActionRow(title=_("Program Name"), subtitle=_("Enter a custom name for the recording file"))
        name_row.add_suffix(self.program_name_entry)
        add_group.add(name_row)
        main_page.add(add_group)
        self.bouquet_label = Gtk.Label(label=_("No bouquet selected..."), halign=Gtk.Align.END, ellipsize=Pango.EllipsizeMode.END)
        bouquet_row = Adw.ActionRow(title=_("Bouquet"), subtitle=_("Select the bouquet for the channel to be recorded"))
        bouquet_row.add_suffix(self.bouquet_label)
        bouquet_row.set_activatable(True)
        bouquet_row.connect("activated", self.on_select_bouquet_clicked)
        add_group.add(bouquet_row)
        self.channel_label = Gtk.Label(label=_("Select a bouquet first..."), halign=Gtk.Align.END, ellipsize=Pango.EllipsizeMode.END)
        self.channel_row = Adw.ActionRow(title=_("Channel"), subtitle=_("Select the channel to be recorded"))
        self.channel_row.add_suffix(self.channel_label)
        self.channel_row.set_activatable(True)
        self.channel_row.set_sensitive(False)
        self.channel_row.connect("activated", self.on_select_channel_clicked)
        add_group.add(self.channel_row)
        self.calendar = Gtk.Calendar(margin_top=12, margin_bottom=12)
        add_group.add(self.calendar)
        now = datetime.now()
        self.start_hour_spin = Gtk.SpinButton.new_with_range(0, 23, 1); self.start_hour_spin.set_value(now.hour)
        self.start_minute_spin = Gtk.SpinButton.new_with_range(0, 59, 1); self.start_minute_spin.set_value(now.minute)
        start_time_row = Adw.ActionRow(title=_("Start Time"))
        start_box = Gtk.Box(spacing=6); start_box.append(self.start_hour_spin); start_box.append(Gtk.Label(label=":")); start_box.append(self.start_minute_spin)
        start_time_row.add_suffix(start_box)
        add_group.add(start_time_row)
        self.end_hour_spin = Gtk.SpinButton.new_with_range(0, 23, 1); self.end_hour_spin.set_value((now.hour + 1) % 24)
        self.end_minute_spin = Gtk.SpinButton.new_with_range(0, 59, 1); self.end_minute_spin.set_value(now.minute)
        end_time_row = Adw.ActionRow(title=_("End Time"))
        end_box = Gtk.Box(spacing=6); end_box.append(self.end_hour_spin); end_box.append(Gtk.Label(label=":")); end_box.append(self.end_minute_spin)
        end_time_row.add_suffix(end_box)
        add_group.add(end_time_row)
        save_button = Gtk.Button(label=_("Schedule Recording"), halign=Gtk.Align.CENTER, margin_top=12)
        save_button.add_css_class("suggested-action")
        save_button.connect("clicked", self.on_save_clicked)
        add_group.add(save_button)
        list_group = Adw.PreferencesGroup(title=_("Scheduled Tasks"))
        main_page.add(list_group)
        self.tasks_listbox = Gtk.ListBox()
        self.tasks_listbox.add_css_class("boxed-list")
        list_group.add(self.tasks_listbox)
        self.refresh_tasks_list()

    def refresh_tasks_list(self):
        while (child := self.tasks_listbox.get_first_child()):
            self.tasks_listbox.remove(child)        
        all_tasks = database.get_all_scheduled_recordings()       
        if not all_tasks:
            self.tasks_listbox.append(Gtk.Label(label=_("No scheduled recordings found.")))
            return        
        status_map = {'pending': _("Pending"), 'recording': _("Recording"), 'completed': _("Completed"), 'failed': _("Failed")}       
        for task in all_tasks:
            start_dt = datetime.fromtimestamp(task['start_time'])
            end_dt = datetime.fromtimestamp(task['end_time'])
            task_dict = dict(task)
            custom_name = task_dict.get('program_name')
            channel_name = task['channel_name']
            if custom_name:
                title_text = custom_name
                subtitle_text = f"{channel_name}  |  {start_dt.strftime('%d.%m %H:%M')} - {end_dt.strftime('%H:%M')}"
            else:
                title_text = channel_name
                subtitle_text = f"{start_dt.strftime('%d.%m %H:%M')} - {end_dt.strftime('%H:%M')}"           
            raw_status = task['status']
            translated_status = status_map.get(raw_status, raw_status)
            subtitle_text += f"  |  {translated_status}"
            row = Adw.ActionRow(title=title_text, subtitle=subtitle_text)
            delete_button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
            delete_button.add_css_class("destructive-action")
            delete_button.connect("clicked", self.on_delete_clicked, task['id'])
            row.add_suffix(delete_button)
            self.tasks_listbox.append(row)

    def on_delete_clicked(self, button, task_id):
        """Emits a signal to delete the corresponding task when the delete button is pressed."""
        self.emit("schedule-deleted", task_id)

    def on_save_clicked(self, button):
        if not self.selected_channel_data:
            self.get_transient_for().show_toast(_("Please select a valid channel!"))
            return
        channel_url = self.selected_channel_data['url']
        channel_name = self.selected_channel_data['name']
        program_name = self.program_name_entry.get_text().strip() or None
        cal_date = self.calendar.get_date()
        selected_date = datetime(cal_date.get_year(), cal_date.get_month(), cal_date.get_day_of_month())
        start_t = time(int(self.start_hour_spin.get_value()), int(self.start_minute_spin.get_value()))
        end_t = time(int(self.end_hour_spin.get_value()), int(self.end_minute_spin.get_value()))
        start_datetime = datetime.combine(selected_date.date(), start_t)
        end_datetime = datetime.combine(selected_date.date(), end_t)
        if end_datetime <= start_datetime:
            end_datetime += timedelta(days=1)
        start_timestamp = int(start_datetime.timestamp())
        end_timestamp = int(end_datetime.timestamp())
        self.emit("schedule-saved", self.get_transient_for().profile_data['id'], channel_name, channel_url, start_timestamp, end_timestamp, program_name)

    def _create_selection_dialog(self, title, placeholder_text):
        """Creates a basic selection dialog with a search bar and a list."""
        dialog = Adw.MessageDialog(transient_for=self, heading=title)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=12)
        search_entry = Gtk.SearchEntry(placeholder_text=placeholder_text)
        list_box = Gtk.ListBox()
        list_box.add_css_class("boxed-list")
        scrolled_window = Gtk.ScrolledWindow(vexpand=True, min_content_height=400)
        scrolled_window.set_child(list_box)
        content_box.append(search_entry)
        content_box.append(scrolled_window)
        dialog.set_extra_child(content_box)
        dialog.add_response("cancel", _("Cancel"))
        dialog.set_close_response("cancel")
        return dialog, search_entry, list_box

    def _on_generic_search_changed(self, entry, list_box):
        """Common search filter function for Bouquet and Channel lists."""
        search_text = entry.get_text().lower().strip()
        current_row = list_box.get_first_child()
        while current_row:
            row_text = getattr(current_row, "search_text", "")
            current_row.set_visible(search_text in row_text)
            current_row = current_row.get_next_sibling()

    def on_select_bouquet_clicked(self, row):
        """Opens the bouquet selection window when the 'Bouquet' row is clicked."""
        dialog, search_entry, list_box = self._create_selection_dialog(
            title=_("Select Bouquet"),
            placeholder_text=_("Search bouquet...")
        )
        for name in self.all_bouquet_names:
            list_row = Gtk.ListBoxRow()
            list_row.set_child(Gtk.Label(label=name, xalign=0, margin_start=10, margin_end=10))
            list_row.item_name = name
            list_row.search_text = name.lower()
            list_box.append(list_row)
        search_entry.connect("search-changed", self._on_generic_search_changed, list_box)
        list_box.connect("row-activated", self.on_bouquet_selected_from_dialog, dialog)
        dialog.present()

    def on_bouquet_selected_from_dialog(self, list_box, row, dialog):
        """Runs when a bouquet is selected from the bouquet selection window."""
        selected_name = row.item_name
        if self.selected_bouquet_name != selected_name:
            self.selected_bouquet_name = selected_name
            self.bouquet_label.set_text(selected_name)
            self.selected_channel_data = None
            self.channel_label.set_text(_("Select Channel"))
            self.channel_row.set_sensitive(True)
        dialog.close()

    def on_select_channel_clicked(self, row):
        """Opens the channel selection window when the 'Channel' row is clicked."""
        if not self.selected_bouquet_name:
            return
        channels_in_bouquet = self.bouquets_data.get(self.selected_bouquet_name, [])
        dialog, search_entry, list_box = self._create_selection_dialog(
            title=_("Select Channel"),
            placeholder_text=_("Search channel...")
        )
        for channel in channels_in_bouquet:
            list_row = Gtk.ListBoxRow()
            list_row.set_child(Gtk.Label(label=channel['name'], xalign=0, margin_start=10, margin_end=10))
            list_row.item_data = channel
            list_row.search_text = channel['name'].lower()
            list_box.append(list_row)
        search_entry.connect("search-changed", self._on_generic_search_changed, list_box)
        list_box.connect("row-activated", self.on_channel_selected_from_dialog, dialog)
        dialog.present()

    def on_channel_selected_from_dialog(self, list_box, row, dialog):
        """Runs when a channel is selected from the channel selection window."""
        self.selected_channel_data = row.item_data
        self.channel_label.set_text(self.selected_channel_data['name'])
        dialog.close()

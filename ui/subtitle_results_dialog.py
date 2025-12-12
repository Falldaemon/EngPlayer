# ui/subtitle_results_dialog.py

import gi
import logging
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GObject, Pango
import gettext
_ = gettext.gettext
class SubtitleResultsDialog(Adw.PreferencesWindow):
    __gsignals__ = {
        'subtitle-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,))
    }

    def __init__(self, parent, subtitle_results):
        super().__init__(transient_for=parent)
        self.add_css_class("subtitle-results-dialog")
        self.set_title(_("Subtitle Search Results"))
        self.set_default_size(600, 450)
        self.set_modal(True)
        self.set_hide_on_close(True)
        self.set_search_enabled(False)
        page = Adw.PreferencesPage()
        self.add(page)
        results_group = Adw.PreferencesGroup()
        page.add(results_group)
        self.results_listbox = Gtk.ListBox()
        self.results_listbox.connect("row-activated", self._on_row_activated)
        self.results_listbox.add_css_class("boxed-list")
        results_group.add(self.results_listbox)
        self._populate_results(subtitle_results)

    def _populate_results(self, results):
        """Populates the ListBox with subtitle results."""
        if not results:
            label = Gtk.Label(label=_("No subtitles found."), margin_top=15, margin_bottom=15)
            self.results_listbox.append(label)
            return
        for sub_data in results:
            row = Adw.ActionRow()
            row.subtitle_data = sub_data
            language = sub_data.get('language', '??').upper()
            file_name = sub_data.get('file_name', _('Untitled Subtitle'))
            release_name = sub_data.get('release_name', '')
            fps = sub_data.get('fps', 0.0)
            row.set_title(f"[{language}] {file_name}")
            subtitle_parts = []
            if release_name and release_name != file_name:
                subtitle_parts.append(f"({release_name})")
            if fps and fps > 0.01:
                subtitle_parts.append(f"{fps:.3f} FPS")
            row.set_subtitle(" - ".join(subtitle_parts))
            row.set_activatable(True)
            self.results_listbox.append(row)

    def _on_row_activated(self, listbox, row):
        """Runs when a subtitle row is clicked in the list."""
        if hasattr(row, 'subtitle_data'):
            selected_subtitle = row.subtitle_data
            logging.info(f"Subtitle selected: ID {selected_subtitle.get('subtitle_id')}, Language: {selected_subtitle.get('language')}")
            self.emit('subtitle-selected', selected_subtitle)
            self.close()

# ui/epg_detail_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango
import gettext
_ = gettext.gettext
class EPGDetailDialog(Adw.MessageDialog):
    def __init__(self, parent, program_data, tmdb_data=None):
        super().__init__(transient_for=parent)
        self.add_css_class("epg-detail-dialog")
        self.set_property("heading-use-markup", True)
        start_time = program_data['start'].astimezone().strftime('%H:%M')
        stop_time = program_data['stop'].astimezone().strftime('%H:%M')
        title_markup = f"<span weight='bold' size='large'>{GLib.markup_escape_text(program_data['title'])}</span>\n<span size='small'>({start_time} - {stop_time})</span>"
        self.set_heading(title_markup)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_extra_child(content_box)
        self.set_default_size(500, 400)
        if tmdb_data:
            extra_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=6)
            content_box.append(extra_info_box)
            year = tmdb_data.get('release_date', '????').split('-')[0]
            rating = tmdb_data.get('rating', 0)
            extra_info_box.append(Gtk.Label(label=f"{_('Year')}: {year}   •   {_('TMDb Rating')}: {rating:.1f}/10", xalign=0, css_classes=["caption"]))
            extra_info_box.append(Gtk.Label(label=f"{_('Director')}: {tmdb_data.get('director', 'N/A')}", xalign=0, css_classes=["caption"]))
            cast_label = Gtk.Label(label=f"{_('Cast')}: {tmdb_data.get('cast', 'N/A')}", xalign=0, wrap=True, css_classes=["caption"])
            extra_info_box.append(cast_label)
        scrolled_window = Gtk.ScrolledWindow(vexpand=True)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content_box.append(scrolled_window)
        desc_view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 left_margin=6, right_margin=6, top_margin=6, bottom_margin=6)
        desc_view.get_buffer().set_text(program_data.get('desc', _("Description not found.")))
        scrolled_window.set_child(desc_view)
        self.add_response("close", _("Close"))
        self.set_close_response("close")
        self.connect("response", lambda d, r: self.destroy())

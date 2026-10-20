# ui/changelog_dialog.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
import gettext
import logging
import os
import threading
from utils.translation_utils import translate_text_manually
from utils.theme_utils import get_icon_theme_folder

_ = gettext.gettext


class ChangelogDialog(Adw.Window):
    def __init__(self, parent, current_version, changelog_dict, **kwargs):
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(700, 480)
        self.set_title(_("Version History"))
        self.add_css_class("dialog")
        self.add_css_class("changelog-dialog")
        self._version_labels = {}
        self._version_originals = {}
        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)
        header = Adw.HeaderBar()
        self.translate_button = Gtk.Button()
        self.translate_button.set_tooltip_text(_("Translate"))
        theme_folder = get_icon_theme_folder()
        trans_icon_path = os.path.join("resources", "icons", theme_folder, "translate.svg")
        if os.path.exists(trans_icon_path):
            img = Gtk.Image.new_from_file(trans_icon_path)
            img.set_pixel_size(16)
            self.translate_button.set_child(img)
        else:
            self.translate_button.set_icon_name("preferences-desktop-locale-symbolic")
        self.translate_button.connect("clicked", self._on_translate_clicked)
        header.pack_end(self.translate_button)
        toolbar_view.add_top_bar(header)
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar_view.set_content(main_box)
        version_scrolled = Gtk.ScrolledWindow(vexpand=True)
        version_scrolled.set_size_request(180, -1)
        version_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        version_scrolled.add_css_class("navigation-sidebar")
        main_box.append(version_scrolled)
        self.version_listbox = Gtk.ListBox()
        self.version_listbox.add_css_class("navigation-sidebar")
        version_scrolled.set_child(self.version_listbox)
        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(separator)
        self.detail_stack = Gtk.Stack()
        self.detail_stack.set_hexpand(True)
        self.detail_stack.set_vexpand(True)
        main_box.append(self.detail_stack)
        sorted_versions = sorted(
            changelog_dict.keys(),
            key=lambda v: [int(p) for p in v.split(".")],
            reverse=True
        )
        current_row = None
        for version in sorted_versions:
            row = Adw.ActionRow(title=version)
            if version == current_version:
                row.add_suffix(Gtk.Label(label=_("Current"), css_classes=["dim-label", "caption"]))
                current_row = row
            self.version_listbox.append(row)
            self.detail_stack.add_named(
                self._build_change_list(version, changelog_dict[version]), version
            )
        self.version_listbox.connect("row-selected", self._on_version_selected)
        if current_row:
            self.version_listbox.select_row(current_row)
        elif sorted_versions:
            self.version_listbox.select_row(self.version_listbox.get_row_at_index(0))

    def _build_change_list(self, version, changes):
        scrolled = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        scrolled.set_child(box)
        labels = []
        originals = []
        for change in changes:
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            bullet = Gtk.Label(label="•")
            bullet.set_valign(Gtk.Align.START)
            row_box.append(bullet)
            change_label = Gtk.Label(label=change, wrap=True, xalign=0)
            change_label.set_hexpand(True)
            row_box.append(change_label)
            box.append(row_box)
            labels.append(change_label)
            originals.append(change)
        self._version_labels[version] = labels
        self._version_originals[version] = originals
        return scrolled

    def _on_version_selected(self, listbox, row):
        if row is None:
            return
        self.detail_stack.set_visible_child_name(row.get_title())

    def _on_translate_clicked(self, button):
        current_version = self.detail_stack.get_visible_child_name()
        if not current_version:
            return
        labels = self._version_labels.get(current_version, [])
        originals = self._version_originals.get(current_version, [])
        if not labels:
            return
        self.translate_button.set_sensitive(False)
        remaining = [len(labels)] 

        def on_one_translated(label_widget, translated_text):
            label_widget.set_text(translated_text)
            remaining[0] -= 1
            if remaining[0] <= 0:
                self.translate_button.set_sensitive(True)
        for label_widget, original_text in zip(labels, originals):
            translate_text_manually(
                original_text,
                lambda translated, lw=label_widget: on_one_translated(lw, translated),
            )

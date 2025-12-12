# ui/collection_grid_view.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject, Pango, GLib
import os
import logging

class CollectionItem(GObject.Object):
    """
    Data object representing a single library collection.
    """
    __gtype_name__ = "CollectionItem"
    db_id = GObject.Property(type=int)
    name = GObject.Property(type=str)
    type = GObject.Property(type=str)

    def __init__(self, db_id, name, type, **kwargs):
        super().__init__(**kwargs)
        self.props.db_id = db_id
        self.props.name = name
        self.props.type = type

class CollectionGridView(Gtk.ScrolledWindow):
    """
    UI component that displays libraries (collections) from the database
    in a grid view.
    """
    __gsignals__ = {
        "collection-activated": (GObject.SignalFlags.RUN_FIRST, None, (CollectionItem,)),
        "collection-right-clicked": (GObject.SignalFlags.RUN_FIRST, None, (CollectionItem, Gtk.Widget,)),
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.model = Gio.ListStore.new(CollectionItem)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)
        self.grid_view = Gtk.GridView.new(None, factory)
        self.grid_view.set_max_columns(20)
        self.grid_view.set_min_columns(2)
        self.grid_view.set_vexpand(True)
        self.grid_view.set_margin_start(12)
        self.grid_view.set_margin_end(12)
        self.grid_view.set_margin_top(12)
        self.grid_view.set_margin_bottom(12)
        self.set_child(self.grid_view)
        selection_model = Gtk.SingleSelection.new(self.model)
        self.grid_view.set_model(selection_model)

    def populate_collections(self, libraries_data):
        """Populates the grid with the list of libraries from the database."""
        self.model.remove_all()
        for lib in libraries_data:
            item = CollectionItem(
                db_id=lib['id'],
                name=lib['name'],
                type=lib['type']
            )
            self.model.append(item)

    def _on_factory_setup(self, factory, list_item):
        """Sets up the visual structure for each item in the GridView once."""
        overlay = Gtk.Overlay()
        overlay.set_halign(Gtk.Align.CENTER)
        overlay.set_valign(Gtk.Align.CENTER)
        overlay.set_hexpand(False)
        overlay.set_vexpand(False)
        list_item.set_child(overlay)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["media-grid-item"])
        box.set_size_request(160, 160)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_hexpand(False)
        box.set_vexpand(False)
        overlay.set_child(box)
        gesture = Gtk.GestureClick.new()
        gesture.connect("pressed", self._on_item_pressed, list_item)
        box.add_controller(gesture)
        right_click_gesture = Gtk.GestureClick.new()
        right_click_gesture.set_button(3)
        right_click_gesture.connect("pressed", self._on_item_right_clicked, list_item)
        box.add_controller(right_click_gesture)
        image = Gtk.Image(pixel_size=128, icon_name="folder-symbolic")
        image.set_size_request(128, 128)
        image.set_halign(Gtk.Align.CENTER)
        image.set_valign(Gtk.Align.CENTER)
        image.set_hexpand(False)
        image.set_vexpand(False)
        label = Gtk.Label(wrap=True,
                          ellipsize=Pango.EllipsizeMode.END,
                          justify=Gtk.Justification.CENTER,
                          max_width_chars=20)
        label.set_vexpand(False)
        box.append(image)
        box.append(label)

    def _on_factory_bind(self, factory, list_item):
        """Binds the data to the visual structure when an item comes into view."""
        overlay = list_item.get_child()
        box = overlay.get_child()
        item_data = list_item.get_item()
        image = box.get_first_child()
        label = box.get_last_child()
        library_type = item_data.props.type
        icon_name_to_use = "folder-symbolic"
        is_custom_icon = False
        if library_type == "video":
            icon_name_to_use = "video-library.svg"
            is_custom_icon = True
        elif library_type == "picture":
            icon_name_to_use = "picture-library.svg"
            is_custom_icon = True
        elif library_type == "music":
            icon_name_to_use = "music-library.svg"
            is_custom_icon = True
        if is_custom_icon:
            icon_path = os.path.join("resources", "icons", icon_name_to_use)
            try:
                if os.path.exists(icon_path):
                    image.set_from_file(icon_path)
                else:
                    logging.warning(f"Icon file not found (using fallback): {icon_path}")
                    image.set_from_file(None)
                    image.set_from_icon_name("folder-symbolic")
            except GLib.Error as e:
                logging.error(f"Failed to load icon file (may be corrupt): {icon_path} | Error: {e}")
                image.set_from_file(None)
                image.set_from_icon_name("folder-symbolic")
        else:
            image.set_from_file(None)
            image.set_from_icon_name(icon_name_to_use)
        label.set_text(item_data.props.name)

    def _on_item_pressed(self, gesture, n_press, x, y, list_item):
        """Emits the signal when a collection item is clicked."""
        if gesture.get_current_button() == 1:
            item_data = list_item.get_item()
            if item_data:
                self.emit("collection-activated", item_data)

    def _on_item_right_clicked(self, gesture, n_press, x, y, list_item):
        """Emits the signal when a collection item is right-clicked."""
        item_data = list_item.get_item()
        if item_data:
            overlay = list_item.get_child()
            box = overlay.get_child()
            self.emit("collection-right-clicked", item_data, box)

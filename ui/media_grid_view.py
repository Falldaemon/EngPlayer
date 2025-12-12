# ui/media_grid_view.py

import gi
import threading
import os
import logging
import hashlib
import re
import database
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject, Pango, GLib, GdkPixbuf, Gdk
from datetime import datetime
from utils.image_loader import load_image_async
from data_providers import tmdb_client
from background import image_download_pool

import gettext
_ = gettext.gettext

class MediaItem(GObject.Object):
    __gtype_name__ = "MediaItem"
    path_or_url = GObject.Property(type=str)
    title = GObject.Property(type=str)
    poster_path = GObject.Property(type=str, default=None)
    overview = GObject.Property(type=str, default=None)
    provider_plot = GObject.Property(type=str, default=None)
    provider_cast = GObject.Property(type=str, default=None)
    provider_director = GObject.Property(type=str, default=None)
    provider_genre = GObject.Property(type=str, default=None)
    provider_release_date = GObject.Property(type=str, default=None)
    provider_rating = GObject.Property(type=float, default=0.0)
    provider_added = GObject.Property(type=str, default=None)
    is_watched = GObject.Property(type=bool, default=False)

    def __init__(self, path_or_url, title=None, poster_path=None, **kwargs):
        super().__init__(**kwargs)
        self.props.path_or_url = path_or_url
        self.props.poster_path = poster_path
        if title: self.props.title = title
        else: self.props.title = os.path.splitext(os.path.basename(path_or_url))[0]
        self.props.provider_plot = kwargs.get('provider_plot')
        self.props.provider_cast = kwargs.get('provider_cast')
        self.props.provider_director = kwargs.get('provider_director')
        self.props.provider_genre = kwargs.get('provider_genre')
        self.props.provider_release_date = kwargs.get('provider_release_date')
        self.props.provider_rating = kwargs.get('provider_rating', 0.0)
        self.props.provider_added = kwargs.get('provider_added')

class MediaGridView(Gtk.ScrolledWindow):
    __gsignals__ = {
        "item-clicked": (GObject.SignalFlags.RUN_FIRST, None, (MediaItem,)),
        "item-right-clicked": (GObject.SignalFlags.RUN_FIRST, None, (MediaItem, Gtk.Widget,)),
        "poster-load-failed": (GObject.SignalFlags.RUN_FIRST, None, (MediaItem,)),
        "population-finished": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "item-watched-toggled": (GObject.SignalFlags.RUN_FIRST, None, (MediaItem, bool))
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_media_type = None
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.model = Gio.ListStore.new(MediaItem)
        self.search_text = ""
        self.custom_filter = Gtk.CustomFilter.new(self._on_filter_item)
        self.filter_model = Gtk.FilterListModel.new(self.model, self.custom_filter)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)
        factory.connect("unbind", self._on_factory_unbind)
        self.grid_view = Gtk.GridView.new(None, factory)
        self.grid_view.set_max_columns(6); self.grid_view.set_min_columns(2)
        self.grid_view.set_vexpand(True)
        self.grid_view.set_margin_start(12); self.grid_view.set_margin_end(12)
        self.grid_view.set_margin_top(12); self.grid_view.set_margin_bottom(12)
        self.set_child(self.grid_view)
        selection_model = Gtk.SingleSelection.new(self.filter_model)
        self.grid_view.set_model(selection_model)

    def populate_async(self, media_list, is_vod=False, media_type=None):
        self.current_media_type = media_type
        self.set_search_text("")
        self.model.remove_all()
        if is_vod: media_type = "vod"
        logging.debug(f"MediaGridView: Querying batch watched status (type: {media_type})...")
        paths_to_check = []
        try:
            if not media_list:
                logging.debug("MediaGridView: Media list to populate is empty.")
            is_dict_list = False
            if media_list and isinstance(media_list[0], dict):
                is_dict_list = True
            if media_type == "music":
                paths_to_check = [str(item['album_id']) for item in media_list if 'album_id' in item.keys()]
            elif media_type == "series":
                paths_to_check = [str(item.get('series_id')) for item in media_list if item.get('series_id')]
            elif media_type == "vod":
                for item_data in media_list:
                    path_or_url = str(item_data.get('stream_id'))
                    if path_or_url == "None": path_or_url = None
                    if not path_or_url: path_or_url = item_data.get('url')
                    if path_or_url: paths_to_check.append(path_or_url)
            else:
                paths_to_check = [item["file_path"] for item in media_list if "file_path" in item.keys()]
        except TypeError as e:
            logging.error(f"MediaGridView: Type error while creating 'paths_to_check': {e}")
            logging.error(f"Received media_list (first 2 items): {media_list[:2]}")
        except Exception as ex:
            logging.error(f"MediaGridView: Unexpected error while creating 'paths_to_check': {ex}")
        watched_set = set()
        if paths_to_check:
            watched_set = database.get_watched_status_batch(paths_to_check)
        logging.debug(f"MediaGridView: {len(watched_set)} watched items found.")
        media_generator = (item for item in media_list)
        GLib.idle_add(self._populate_chunk, media_generator, media_type, watched_set)

    def _populate_chunk(self, media_generator, media_type, watched_set):
        chunk_size = 20
        main_window = self.get_ancestor(Gtk.Window)
        trakt_movies_cache = getattr(main_window, 'trakt_watched_movies', set())
        try:
            for _ in range(chunk_size):
                item_data = next(media_generator)
                item = None
                is_watched = False
                db_key_for_check = None
                if media_type == "music":
                    db_key_for_check = str(item_data['album_id'])
                    album_name_safe = GLib.markup_escape_text(item_data['album_name'])
                    artist_name_safe = GLib.markup_escape_text(item_data['artist_name'])
                    title = f"<b>{album_name_safe}</b><small> ({artist_name_safe})</small>"
                    item = MediaItem(path_or_url=str(item_data['album_id']), title=title, poster_path=item_data['album_art_path'])
                elif media_type == "series":
                    db_key_for_check = str(item_data.get('series_id'))
                    item = MediaItem(
                        path_or_url=str(item_data.get('series_id')),
                        title=item_data.get('name'),
                        poster_path=item_data.get('cover')
                    )
                elif media_type == "vod":
                    path_or_url = str(item_data.get('stream_id'))
                    poster_path = item_data.get('stream_icon')
                    if path_or_url == "None": path_or_url = None
                    if not path_or_url: path_or_url = item_data.get('url')
                    if not poster_path: poster_path = item_data.get('logo')
                    db_key_for_check = path_or_url
                    item = MediaItem(
                        path_or_url=path_or_url,
                        title=item_data.get('name'),
                        poster_path=poster_path
                    )
                    provider_tmdb_id = str(item_data.get('tmdb_id', ''))
                    if provider_tmdb_id and provider_tmdb_id in trakt_movies_cache:
                        is_watched = True
                        if db_key_for_check:
                            database.save_playback_progress(db_key_for_check, position=0, is_finished=1)
                else:
                    db_key_for_check = item_data["file_path"]
                    item = MediaItem(path_or_url=item_data["file_path"], title=item_data["title"], poster_path=item_data["poster_path"])
                if item:
                    if db_key_for_check and db_key_for_check in watched_set:
                        item.props.is_watched = True
                    self.model.append(item)
            return True
        except StopIteration:
            logging.info("Incremental population of the media grid is complete.")
            self.emit("population-finished")
            return False
        except Exception as e:
            item_data_str = "Unknown (generator error)"
            if 'item_data' in locals():
                item_data_str = str(item_data)
            logging.exception(f"Error in _populate_chunk: {e} | Data: {item_data_str}")
            return True

    def clear(self): self.model.remove_all()

    def _on_item_pressed(self, gesture, n_press, x, y, list_item):
        item = list_item.get_item()
        if item: self.emit("item-clicked", item)

    def _on_poster_load_failed(self, item):
        self.emit("poster-load-failed", item)
        return GLib.SOURCE_REMOVE

    def _on_item_right_clicked(self, gesture, n_press, x, y, list_item):
        item = list_item.get_item()
        if item:
            self.emit("item-right-clicked", item, list_item.get_child())

    def _on_factory_setup(self, factory, list_item):
        overlay = Gtk.Overlay()
        list_item.set_child(overlay)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_size_request(160, 240)
        box.add_css_class("media-grid-item")
        overlay.set_child(box)
        gesture = Gtk.GestureClick.new()
        gesture.connect("pressed", self._on_item_pressed, list_item)
        box.add_controller(gesture)
        right_click_gesture = Gtk.GestureClick.new()
        right_click_gesture.set_button(3)
        right_click_gesture.connect("pressed", self._on_item_right_clicked, list_item)
        box.add_controller(right_click_gesture)
        image = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        image.set_vexpand(True)
        image.set_hexpand(False)
        image.set_halign(Gtk.Align.CENTER)
        image.set_valign(Gtk.Align.FILL)
        label = Gtk.Label(wrap=False, ellipsize=Pango.EllipsizeMode.END, use_markup=True, justify=Gtk.Justification.CENTER, vexpand=False, xalign=0.5)
        label.set_lines(1)
        box.append(image)
        box.append(label)
        watched_button = Gtk.Button()
        watched_button.set_icon_name("object-select-symbolic")
        watched_button.add_css_class("watched-button")
        watched_button.set_valign(Gtk.Align.START)
        watched_button.set_halign(Gtk.Align.START)
        watched_button.set_margin_start(8)
        watched_button.set_margin_top(8)
        watched_button.set_size_request(32, 32)
        watched_button.connect("clicked", self._on_watched_button_clicked, list_item)
        overlay.add_overlay(watched_button)
        list_item.watched_button = watched_button

    def _on_factory_bind(self, factory, list_item):
        overlay = list_item.get_child()
        box = overlay.get_child()
        item = list_item.get_item()
        watched_button = getattr(list_item, "watched_button", None)
        picture_widget = box.get_first_child()
        label = box.get_last_child()
        title = item.props.title
        if self.current_media_type == "music":
            label.set_markup(title if title else "")
        else:
            label.set_text(title if title else "")
        if watched_button:
            if item.props.is_watched:
                watched_button.add_css_class("watched")
                watched_button.set_icon_name("object-select-symbolic")
                watched_button.set_tooltip_text(_("Mark as Unwatched"))
            else:
                watched_button.remove_css_class("watched")
                watched_button.set_icon_name("object-select-symbolic")
                watched_button.set_tooltip_text(_("Mark as Watched"))
            if self.current_media_type in ["music", "picture"]:
                watched_button.set_visible(False)
            else:
                watched_button.set_visible(True)

        def _replace_image_widget(widget, pixbuf):
            if widget and pixbuf:
                try:
                    original_width = pixbuf.get_width()
                    original_height = pixbuf.get_height()
                    target_width = 200
                    if original_width > target_width:
                        scale_factor = target_width / original_width
                        target_height = int(original_height * scale_factor)
                        scaled_pixbuf = pixbuf.scale_simple(target_width, target_height, GdkPixbuf.InterpType.BILINEAR)
                        texture = Gdk.Texture.new_for_pixbuf(scaled_pixbuf)
                    else:
                        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                    widget.set_paintable(texture)
                except Exception as e:
                    logging.error(f"Texture conversion failed: {e}")

        def load_poster_or_thumbnail(media_item, _=None):
            picture_widget.set_paintable(None)
            path = media_item.props.path_or_url
            poster = media_item.props.poster_path
            if self.current_media_type == "picture":
                box.set_size_request(160, 240)
                def _load_picture_in_thread(p, widget):
                    base_cache_dir = database.get_cache_path()
                    cache_dir = os.path.join(base_cache_dir, "grid_thumbnails")
                    os.makedirs(cache_dir, exist_ok=True)
                    hash_name = hashlib.md5(p.encode()).hexdigest()
                    thumbnail_path = os.path.join(cache_dir, f"{hash_name}.jpg")
                    final_pixbuf = None
                    if os.path.exists(thumbnail_path):
                        try:
                            final_pixbuf = GdkPixbuf.Pixbuf.new_from_file(thumbnail_path)
                        except GLib.Error: pass
                    if not final_pixbuf:
                        try:
                            original_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(p, 160, 240, True)
                            background_pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 176, 256)
                            dest_x = (160 - original_pixbuf.get_width()) // 2
                            dest_y = (240 - original_pixbuf.get_height()) // 2
                            original_pixbuf.composite(
                                background_pixbuf, dest_x, dest_y,
                                original_pixbuf.get_width(), original_pixbuf.get_height(),
                                dest_x, dest_y, 1, 1, GdkPixbuf.InterpType.BILINEAR, 255
                            )
                            background_pixbuf.savev(thumbnail_path, "jpeg", ["quality"], ["90"])
                            final_pixbuf = background_pixbuf
                        except GLib.Error as e:
                            logging.warning(f"Thumbnail creation failed: {e}")
                    if final_pixbuf:
                        GLib.idle_add(_replace_image_widget, widget, final_pixbuf)
                image_download_pool.submit(_load_picture_in_thread, path, picture_widget)
                return
            if poster:
                box.set_size_request(160, 240)
                if os.path.isabs(poster):
                    try:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file(poster)
                        _replace_image_widget(picture_widget, pixbuf)
                    except GLib.Error:
                        self._on_poster_load_failed(media_item)
                elif poster.startswith("http"):
                    load_image_async(
                        poster, picture_widget,
                        on_success_callback=_replace_image_widget,
                        on_failure=lambda: self._on_poster_load_failed(media_item)
                    )
                else:
                    full_poster_url = tmdb_client.get_poster_url(poster)
                    if full_poster_url:
                        load_image_async(
                            full_poster_url, picture_widget,
                            on_success_callback=_replace_image_widget,
                            on_failure=lambda: self._on_poster_load_failed(media_item)
                        )
        load_poster_or_thumbnail(item)
        handler_id = item.connect("notify::poster-path", load_poster_or_thumbnail)
        list_item.notify_handler_id = handler_id
        if not item.props.poster_path or not item.props.poster_path.startswith("http"):
            load_poster_or_thumbnail(item)

    def _on_factory_unbind(self, factory, list_item):
        handler_id = getattr(list_item, "notify_handler_id", None)
        if handler_id:
            item = list_item.get_item()
            if item and GObject.signal_handler_is_connected(item, handler_id):
                item.disconnect(handler_id)
            delattr(list_item, "notify_handler_id")

    def _on_filter_item(self, item):
        if not self.search_text:
            return True
        title = item.props.title
        if not title:
            return False
        title_no_markup = re.sub('<[^<]+?>', '', title).strip()
        return self.search_text in title_no_markup.lower()

    def set_search_text(self, text):
        new_text = text.lower().strip()
        if self.search_text != new_text:
            self.search_text = new_text
            if self.custom_filter:
                self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)

    def _on_watched_button_clicked(self, button, list_item):
        item = list_item.get_item()
        if not item: return
        new_state = not item.props.is_watched
        self.emit("item-watched-toggled", item, new_state)
        item.props.is_watched = new_state
        if new_state:
            button.add_css_class("watched")
            button.set_tooltip_text(_("Mark as Unwatched"))
        else:
            button.remove_css_class("watched")
            button.set_tooltip_text(_("Mark as Watched"))


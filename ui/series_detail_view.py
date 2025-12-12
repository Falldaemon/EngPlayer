# ui/series_detail_view.py

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject, Pango, GLib, GdkPixbuf, Gdk
import gettext
_ = gettext.gettext
import logging
import threading
import os
import json
import re
from utils.image_loader import load_image_async
from data_providers import tmdb_client
from core.config import get_fallback_tmdb_key
import database
from utils.theme_utils import get_icon_theme_folder
IMAGE_BASE_URL_PROFILE = "https://image.tmdb.org/t/p/w185"
class SeriesDetailView(Gtk.Box):
    __gsignals__ = {
        "back-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "episode-activated": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "trailer-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, **kwargs)
        self.set_margin_start(24); self.set_margin_end(24)
        self.set_margin_top(12); self.set_margin_bottom(12)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(header_box)
        back_button = Gtk.Button(icon_name="go-previous-symbolic", label=_("Back to Series List"))
        back_button.connect("clicked", lambda w: self.emit("back-requested"))
        back_button.set_halign(Gtk.Align.START)
        header_box.append(back_button)
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=30)
        main_box.set_vexpand(True); main_box.set_valign(Gtk.Align.FILL)
        main_box.set_margin_top(12)
        self.append(main_box)
        self.info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.append(self.info_box)
        self.poster_image = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        self.poster_image.set_size_request(200, 300)
        self.poster_image.set_valign(Gtk.Align.START)
        self.info_box.append(self.poster_image)
        self.title_label = Gtk.Label(xalign=0, wrap=True)
        self.title_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.info_box.append(self.title_label)
        self.genre_label = Gtk.Label(xalign=0, css_classes=["caption"], wrap=True)
        self.info_box.append(self.genre_label)
        self.release_date_label = Gtk.Label(xalign=0, css_classes=["caption"])
        self.info_box.append(self.release_date_label)
        self.rating_label = Gtk.Label(xalign=0)
        self.info_box.append(self.rating_label)
        self.director_label = Gtk.Label(xalign=0, wrap=True)
        self.director_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.director_label.set_hexpand(False)
        self.director_label.set_halign(Gtk.Align.START)
        self.info_box.append(self.director_label)
        self.country_label = Gtk.Label(xalign=0, wrap=True)
        self.country_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.country_label.set_hexpand(False)
        self.country_label.set_halign(Gtk.Align.START)
        self.info_box.append(self.country_label)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_min_content_height(100)
        self.overview_textview = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR, editable=False, cursor_visible=False,
            top_margin=6, bottom_margin=6, left_margin=6, right_margin=6
        )
        scrolled_window.set_child(self.overview_textview)
        self.info_box.append(scrolled_window)
        self.current_trailer_key = None
        self.trailer_button = Gtk.Button(css_classes=["pill"], halign=Gtk.Align.CENTER, margin_top=10)
        button_content_box = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        theme_folder = get_icon_theme_folder()
        icon_path = os.path.join("resources", "icons", theme_folder, "fragman.svg")
        try:
            if os.path.exists(icon_path):
                 trailer_icon = Gtk.Image.new_from_file(icon_path)
                 trailer_icon.set_pixel_size(16)
                 button_content_box.append(trailer_icon)
            else: logging.warning(f"Series Detail: Trailer icon not found: {icon_path}")
        except GLib.Error as e: logging.error(f"Series Detail: Trailer icon could not be loaded: {icon_path}, Error: {e}")
        trailer_label = Gtk.Label(label=_("Watch Trailer"))
        button_content_box.append(trailer_label)
        self.trailer_button.set_child(button_content_box)
        self.trailer_button.set_sensitive(False)
        self.trailer_button.connect("clicked", self._on_trailer_clicked)
        self.info_box.append(self.trailer_button)
        episodes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        main_box.append(episodes_box)
        season_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        season_box.append(Gtk.Label(label=_("Season:")))
        self.season_combo = Gtk.ComboBoxText()
        season_box.append(self.season_combo)
        episodes_box.append(season_box)
        self.episode_listbox = Gtk.ListBox()
        self.episode_listbox.connect("row-activated", self._on_episode_row_activated)
        scrolled_episodes = Gtk.ScrolledWindow()
        scrolled_episodes.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_episodes.set_vexpand(True)
        scrolled_episodes.set_min_content_height(200)
        scrolled_episodes.set_child(self.episode_listbox)
        episodes_box.append(scrolled_episodes)
        cast_header = Gtk.Label(xalign=0, margin_top=10)
        cast_header.set_markup(f"<b>{_('Cast')}</b>")
        episodes_box.append(cast_header)
        cast_scrolled = Gtk.ScrolledWindow()
        cast_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cast_scrolled.set_min_content_height(200)
        cast_scrolled.set_vexpand(False)
        self.cast_flowbox = Gtk.FlowBox(valign=Gtk.Align.START, max_children_per_line=10, selection_mode=Gtk.SelectionMode.NONE)
        cast_scrolled.set_child(self.cast_flowbox)
        episodes_box.append(cast_scrolled)
        self.episodes_data = {}
        self.series_id_xtream = None
        self.clean_tmdb_title = None
        self.current_tmdb_season_data = None

    def update_content(self, series_info, series_id=None):
        """Processes series info, checks TMDb, and updates the UI."""
        logging.debug(f"SERIES DETAIL: update_content STARTED.")
        self.current_tmdb_season_data = None
        self.episodes_data = {}
        self.series_id_xtream = str(series_id) if series_id else None
        self.poster_image.set_paintable(None)
        initial_title = _('Unknown Series')
        info = {}
        if series_info and "info" in series_info:
            info = series_info.get("info", {})
            initial_title = info.get('name', initial_title)
        self.episodes_data = series_info.get("episodes", {}) if series_info else {}
        self.clean_tmdb_title = initial_title.split(' (')[0].strip()
        self.title_label.set_markup(f"<span weight='bold' size='large'>{GLib.markup_escape_text(initial_title)}</span>")
        self.release_date_label.set_text("")
        self.rating_label.set_text("")
        self._set_overview_text(_("Loading information..."))
        self.director_label.set_text("")
        self.country_label.set_text("")
        self.genre_label.set_text("")
        while (child := self.cast_flowbox.get_child_at_index(0)):
            self.cast_flowbox.remove(child)
        loading_cast = Gtk.Label(label=_("Loading cast..."), css_classes=["caption"])
        self.cast_flowbox.append(loading_cast)
        self.current_trailer_key = None
        self.trailer_button.set_sensitive(False)
        poster_url = info.get('cover') or info.get('backdrop_path')
        if poster_url and isinstance(poster_url, str) and poster_url.startswith("http"):
            load_image_async(poster_url, self.poster_image,
                             on_success_callback=lambda w, p: w.set_paintable(Gdk.Texture.new_for_pixbuf(p)))
        user_key = database.get_config_value("tmdb_api_key")
        api_key = user_key if user_key else get_fallback_tmdb_key()
        use_tmdb = database.get_use_tmdb_status()
        tmdb_id_from_xtream_str = info.get('tmdb')
        tmdb_id_from_xtream = None
        if tmdb_id_from_xtream_str and isinstance(tmdb_id_from_xtream_str, str) and tmdb_id_from_xtream_str.isdigit():
            try: tmdb_id_from_xtream = int(tmdb_id_from_xtream_str)
            except ValueError: tmdb_id_from_xtream = None
        logging.debug(f"SERIES DETAIL: Main logic starting. use_tmdb={use_tmdb}, tmdb_id_from_xtream={tmdb_id_from_xtream}")
        tmdb_handled = False
        if use_tmdb and tmdb_id_from_xtream:
            logging.debug("SERIES DETAIL: use_tmdb=True and ID found. Checking database...")
            db_row = database.get_metadata(self.series_id_xtream) if self.series_id_xtream else None
            if db_row:
                 logging.info(f"SERIES DETAIL: TMDb data found in DB ({self.series_id_xtream}). CALLING _update_labels_from_tmdb_data.")
                 self._update_labels_from_tmdb_data(dict(db_row))
                 tmdb_handled = True
            else:
                 if api_key:
                     logging.info(f"SERIES DETAIL: No TMDb data in DB ({self.series_id_xtream}). STARTING _fetch_tmdb_details_by_id_thread.")
                     thread = threading.Thread(
                         target=self._fetch_tmdb_details_by_id_thread,
                         args=(api_key, tmdb_id_from_xtream),
                         daemon=True
                     )
                     thread.start()
                     tmdb_handled = True
                 else:
                     logging.warning("SERIES DETAIL: TMDb ID found but API key is missing (and fallback failed).")

        if not tmdb_handled:
            logging.debug("SERIES DETAIL: TMDb not handled. CALLING fallback _update_labels_from_xtream_info.")
            self._update_labels_from_xtream_info(series_info)
        logging.debug("SERIES DETAIL: Populating seasons and episodes...")
        if hasattr(self, "season_combo_handler_id"):
             if self.season_combo.handler_is_connected(self.season_combo_handler_id):
                 self.season_combo.disconnect(self.season_combo_handler_id)
        self.season_combo.remove_all()
        if self.episodes_data:
             try:
                 season_numbers = sorted([int(k) for k in self.episodes_data.keys()])
             except ValueError:
                 logging.warning("Could not sort season numbers (invalid key?), sorting as string.")
                 season_numbers = sorted(self.episodes_data.keys())
             for season_num in season_numbers:
                 self.season_combo.append(str(season_num), f"{_('Season')} {season_num}")
             if season_numbers:
                 self.season_combo_handler_id = self.season_combo.connect("changed", self._on_season_changed)
                 self.season_combo.set_active(0)
                 if self.season_combo.get_active_id():
                     self._on_season_changed(self.season_combo)
                 else:
                     first_id = str(season_numbers[0])
                     first_episodes = self.episodes_data.get(first_id, [])
                     self._populate_episode_list(first_episodes)
             else:
                  self._populate_episode_list([])
        else:
            self._populate_episode_list([])
            logging.warning("No episode data found for this series.")
        logging.info("SERIES DETAIL: update_content FINISHED.")

    def _fetch_tmdb_details_by_id_thread(self, api_key, tmdb_id):
        """(Background Thread) Fetches series details using the provided TMDb ID."""
        logging.debug(f"SERIES DETAIL: TMDb API thread (by ID) started: ID={tmdb_id}")
        tmdb_details = tmdb_client.get_media_details(api_key, tmdb_id, 'tv')
        if tmdb_details:
            logging.debug("SERIES DETAIL: Details successfully fetched from TMDb API (by ID).")
            if self.series_id_xtream:
                logging.info(f"SERIES DETAIL (ID): Saving metadata to DB for {self.series_id_xtream}")
                database.save_metadata(self.series_id_xtream, tmdb_details)
                logging.debug("SERIES DETAIL: TMDb data saved to DB.")
            else:
                 logging.warning("SERIES DETAIL: Could not save TMDb data to DB because Xtream Series ID is missing.")
            logging.info(f"SERIES DETAIL (ID): Scheduling _update_labels_from_tmdb_data via idle_add")
            GLib.idle_add(self._update_labels_from_tmdb_data, tmdb_details)
        else:
            logging.warning(f"SERIES DETAIL: Could not get details for TMDb ID ({tmdb_id}). Triggering fallback.")
            logging.info(f"SERIES DETAIL (ID): Scheduling _trigger_xtream_fallback_update via idle_add")
            GLib.idle_add(self._trigger_xtream_fallback_update)

    def _update_labels_from_tmdb_data(self, tmdb_api_or_db_data):
         """Updates labels with TMDb data (from API response OR DB row format)."""
         logging.debug("SERIES DETAIL: Updating UI labels with TMDb data...")
         try:
             initial_title = self.title_label.get_text().split(' (')[0]
             release_date = tmdb_api_or_db_data.get("first_air_date", "") or tmdb_api_or_db_data.get("release_date", "") or ""
             year_str = f" ({release_date[:4]})" if release_date else ""
             tmdb_title = tmdb_api_or_db_data.get('name', initial_title) or tmdb_api_or_db_data.get('title', initial_title) or initial_title
             self.clean_tmdb_title = tmdb_title
             self.title_label.set_markup(f"<span weight='bold' size='large'>{GLib.markup_escape_text(tmdb_title + year_str)}</span>")
             self.release_date_label.set_text(_("First Aired:") + f" {release_date}" if release_date else "")
             rating_val = tmdb_api_or_db_data.get('rating')
             if rating_val is None: rating_val = tmdb_api_or_db_data.get('vote_average')
             self.rating_label.set_markup(f"<b>{_('TMDb Rating')}:</b> {rating_val:.1f} / 10" if rating_val is not None else "")
             overview = tmdb_api_or_db_data.get("overview", "") or ""
             self._set_overview_text(overview if overview else _("Plot information not found."))
             director_val = tmdb_api_or_db_data.get('director', "") or ""
             self.director_label.set_markup(f"<b>{_('Creator/Director')}:</b> {director_val if director_val else 'N/A'}")
             countries = tmdb_api_or_db_data.get('countries', "")
             if countries:
                 self.country_label.set_markup(f"<b>{_('Production Country')}:</b> {countries}")
             else:
                 self.country_label.set_text("")
             genres = tmdb_api_or_db_data.get('genres', '')
             logging.debug(f"SERIES DETAIL: Updating genres: '{genres}'")
             safe_genres = GLib.markup_escape_text(genres) if genres else ""
             self.genre_label.set_markup(f"<i>{safe_genres}</i>" if safe_genres else "")
             cast_with_pics_json = tmdb_api_or_db_data.get('cast_members')
             cast_list = []
             logging.debug(f"SERIES DETAIL: Searching for cast data... DB JSON: {cast_with_pics_json is not None}, API List: {'cast_with_pics' in tmdb_api_or_db_data}")
             if cast_with_pics_json:
                try:
                    cast_list = json.loads(cast_with_pics_json)
                    logging.debug(f"SERIES DETAIL: {len(cast_list)} cast members read from database JSON.")
                except json.JSONDecodeError:
                    logging.warning("SERIES DETAIL: Cast data in database is not in JSON format.")
                    cast_list = []
             elif 'cast_with_pics' in tmdb_api_or_db_data and isinstance(tmdb_api_or_db_data['cast_with_pics'], list):
                 cast_list = tmdb_api_or_db_data['cast_with_pics']
                 logging.debug(f"SERIES DETAIL: {len(cast_list)} cast members list from API response used.")
             while (child := self.cast_flowbox.get_child_at_index(0)):
                self.cast_flowbox.remove(child)
             if cast_list:
                logging.debug(f"SERIES DETAIL: Creating boxes for {len(cast_list)} cast members...")
                for actor in cast_list:
                    actor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_bottom=6)
                    actor_box.set_size_request(100, -1)
                    actor_image = Gtk.Image(pixel_size=138, icon_name="avatar-default-symbolic")
                    profile_path = actor.get('profile_path')
                    if profile_path:
                        full_image_url = IMAGE_BASE_URL_PROFILE + profile_path
                        load_image_async(
                            full_image_url, actor_image,
                            on_success_callback=lambda widget, pixbuf: widget.set_from_pixbuf(pixbuf)
                        )
                    actor_name_label = Gtk.Label(label=actor.get('name', 'N/A'), wrap=True, justify=Gtk.Justification.CENTER, xalign=0.5)
                    actor_name_label.set_size_request(100, -1)
                    actor_box.append(actor_image)
                    actor_box.append(actor_name_label)
                    self.cast_flowbox.append(actor_box)
             else:
                 no_cast_label = Gtk.Label(label=_("Cast information not found."), css_classes=["caption"])
                 self.cast_flowbox.append(no_cast_label)
                 logging.debug("SERIES DETAIL: Cast list is empty, 'not found' message added.")
             poster_key = tmdb_api_or_db_data.get("poster_path")
             if poster_key:
                 full_poster_url = tmdb_client.get_poster_url(poster_key)
                 if full_poster_url:
                     load_image_async(
                         full_poster_url, self.poster_image,
                         on_success_callback=lambda widget, pixbuf: widget.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                     )
             trailer_key = tmdb_api_or_db_data.get("trailer_key")
             logging.info(f"SERIES DETAIL UI Update: Found trailer_key = {trailer_key}")
             if trailer_key:
                 self.current_trailer_key = trailer_key
                 self.trailer_button.set_sensitive(True)
                 logging.debug(f"SERIES DETAIL: Trailer key found and button enabled: {trailer_key}")
             else:
                 self.current_trailer_key = None
                 self.trailer_button.set_sensitive(False)
                 logging.debug("SERIES DETAIL: No trailer key found in TMDb data.")
             logging.info("SERIES DETAIL: UI update with TMDb data completed successfully.")
             active_season_id = self.season_combo.get_active_id()
             tmdb_id_val = tmdb_api_or_db_data.get("id")
             if active_season_id and tmdb_id_val:
                 logging.info(f"Auto-refreshing plots for Season {active_season_id} now that TMDb ID ({tmdb_id_val}) is available...")
                 user_key = database.get_config_value("tmdb_api_key")
                 api_key = user_key if user_key else get_fallback_tmdb_key()
                 if api_key:
                    episodes = self.episodes_data.get(active_season_id, [])
                    thread = threading.Thread(
                        target=self._fetch_season_details_thread,
                        args=(api_key, tmdb_id_val, active_season_id, episodes),
                        daemon=True
                    )
                    thread.start()
         except Exception as e:
             logging.error(f"SERIES DETAIL: Error processing TMDb data (_update_labels_from_tmdb_data): {e}", exc_info=True)
         return GLib.SOURCE_REMOVE

    def _update_labels_from_xtream_info(self, series_info_data):
        """Updates labels with Xtream series_info data (FALLBACK)."""
        logging.debug("SERIES DETAIL: Fallback - Updating UI labels with Xtream data...")
        if not series_info_data or "info" not in series_info_data:
            self.current_trailer_key = None
            self.trailer_button.set_sensitive(False)
            return GLib.SOURCE_REMOVE
        info = series_info_data.get("info", {})
        plot = info.get('plot')
        self._set_overview_text(plot if plot else _("Plot information not found."))
        director = info.get('director')
        self.director_label.set_markup(f"<b>{_('Director/Creator')}:</b> {director if director else 'N/A'}")
        release_date = info.get('releasedate') or info.get('releaseDate')
        self.release_date_label.set_text(_("Release Date:") + f" {release_date}" if release_date else "")
        genre_xtream = info.get('genre')
        self.genre_label.set_markup(f"<i>{genre_xtream}</i>" if genre_xtream else "")
        while (child := self.cast_flowbox.get_child_at_index(0)):
            self.cast_flowbox.remove(child)
        cast_text = info.get('cast')
        if cast_text and isinstance(cast_text, str) and cast_text.strip():
            cast_label = Gtk.Label(label=cast_text,
                                   wrap=True,
                                   justify=Gtk.Justification.LEFT,
                                   xalign=0,
                                   css_classes=["caption"])
            self.cast_flowbox.append(cast_label)
        else:
            no_cast_label = Gtk.Label(label=_("Cast information not found."), css_classes=["caption"])
            self.cast_flowbox.append(no_cast_label)
        provider_trailer_key = info.get('youtube_trailer')
        extracted_youtube_id = None
        if provider_trailer_key and isinstance(provider_trailer_key, str):
            youtube_id_match = re.search(r'(?:v=|\/|embed\/|youtu.be\/)([0-9A-Za-z_-]{11})', provider_trailer_key)
            if youtube_id_match:
                extracted_youtube_id = youtube_id_match.group(1)
            elif len(provider_trailer_key) == 11 and re.match(r'^[0-9A-Za-z_-]+$', provider_trailer_key):
                 extracted_youtube_id = provider_trailer_key
        if extracted_youtube_id:
            self.current_trailer_key = extracted_youtube_id
            self.trailer_button.set_sensitive(True)
            logging.debug(f"SERIES DETAIL Fallback: Provider trailer key found and button enabled: {self.current_trailer_key}")
        else:
            self.current_trailer_key = None
            self.trailer_button.set_sensitive(False)
            if provider_trailer_key:
                 logging.warning(f"SERIES DETAIL Fallback: Provider trailer found but YouTube ID could not be extracted: {provider_trailer_key}")
        logging.debug("SERIES DETAIL: Fallback - UI labels updated with Xtream info data.")
        return GLib.SOURCE_REMOVE

    def _trigger_xtream_fallback_update(self):
         """Called when fetching data with TMDb ID fails."""
         logging.debug("SERIES DETAIL: Could not get data with TMDb ID, triggering Xtream fallback.")
         self._update_labels_from_xtream_info(None)
         return GLib.SOURCE_REMOVE

    def _set_overview_text(self, text):
        buffer = self.overview_textview.get_buffer()
        buffer.delete(buffer.get_start_iter(), buffer.get_end_iter())
        buffer.insert(buffer.get_start_iter(), text)

    def _on_season_changed(self, combo):
        selected_season = combo.get_active_id()
        if selected_season is None or not self.episodes_data: return
        episodes_in_season = self.episodes_data.get(selected_season, [])
        self._populate_episode_list(episodes_in_season)
        user_key = database.get_config_value("tmdb_api_key")
        api_key = user_key if user_key else get_fallback_tmdb_key()
        use_tmdb = database.get_use_tmdb_status()
        if use_tmdb and api_key and self.series_id_xtream:
             meta_row = database.get_metadata(self.series_id_xtream)
             if meta_row:
                 meta = dict(meta_row)
                 seasons_json = meta.get('seasons_json')
                 if seasons_json:
                     try:
                         all_seasons_data = json.loads(seasons_json)
                         if str(selected_season) in all_seasons_data:
                             logging.info(f"Season {selected_season} data found in DB. Skipping API.")
                             season_data = all_seasons_data[str(selected_season)]
                             self._populate_episode_list(episodes_in_season, season_data)
                             return
                     except json.JSONDecodeError:
                         logging.warning("Invalid seasons JSON in DB.")
                 if meta.get('tmdb_id'):
                     tmdb_id = meta['tmdb_id']
                     logging.info(f"Fetching extra details for Season {selected_season} (TMDb ID: {tmdb_id})...")
                     thread = threading.Thread(
                         target=self._fetch_season_details_thread,
                         args=(api_key, tmdb_id, selected_season, episodes_in_season),
                         daemon=True
                     )
                     thread.start()

    def _populate_episode_list(self, episodes, tmdb_season_data=None):
        if tmdb_season_data:
            self.current_tmdb_season_data = tmdb_season_data
        elif self.current_tmdb_season_data:
            tmdb_season_data = self.current_tmdb_season_data
        while (child := self.episode_listbox.get_first_child()):
            self.episode_listbox.remove(child)
        if not episodes:
             self.episode_listbox.append(Gtk.Label(label=_("No episodes found for this season.")))
             return
        main_window = self.get_ancestor(Gtk.Window)
        trakt_cache = set()
        if main_window and hasattr(main_window, 'trakt_watched_episodes'):
            trakt_cache = main_window.trakt_watched_episodes
        episode_ids = [str(ep.get('id')) for ep in episodes if ep.get('id')]
        watched_set = set()
        if episode_ids:
            watched_set = database.get_watched_status_batch(episode_ids)
        try: sorted_episodes = sorted(episodes, key=lambda x: int(x.get('episode_num', 0)))
        except: sorted_episodes = episodes
        for episode in sorted_episodes:
            row = Gtk.ListBoxRow()
            ep_num = str(episode.get('episode_num', '?'))
            title = episode.get('title') or episode.get('name', _('Unknown Episode'))
            tmdb_episode_id = None
            if tmdb_season_data:
                t_data = tmdb_season_data.get(ep_num) or tmdb_season_data.get(str(int(ep_num))) if ep_num.isdigit() else None
                if t_data:
                    if t_data.get('id'): tmdb_episode_id = t_data.get('id')
                    if t_data.get('name'): title = t_data.get('name')
                    episode['tmdb_id'] = tmdb_episode_id
            row.episode_data = episode
            episode_id_str = str(episode.get('id'))
            is_watched = False
            if episode_id_str in watched_set:
                is_watched = True
            elif tmdb_episode_id and str(tmdb_episode_id) in trakt_cache:
                is_watched = True
                database.save_playback_progress(episode_id_str, position=0, is_finished=1)
            main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=8, margin_bottom=8, margin_start=10, margin_end=10)
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            vbox.append(Gtk.Label(xalign=0, use_markup=True, label=f"<b>{ep_num}. {GLib.markup_escape_text(title)}</b>"))
            if tmdb_season_data and tmdb_episode_id and t_data and t_data.get('overview'):
                 overview_lbl = Gtk.Label(xalign=0, label=t_data['overview'], wrap=True, max_width_chars=60, lines=2, ellipsize=Pango.EllipsizeMode.END)
                 overview_lbl.add_css_class("caption"); overview_lbl.set_opacity(0.7)
                 vbox.append(overview_lbl)
            main_hbox.append(vbox)
            if is_watched:
                watched_indicator = Gtk.Button(icon_name="object-select-symbolic")
                watched_indicator.add_css_class("watched-button")
                watched_indicator.add_css_class("watched")
                watched_indicator.set_can_focus(False)
                watched_indicator.set_focusable(False)
                watched_indicator.set_valign(Gtk.Align.CENTER)
                watched_indicator.set_halign(Gtk.Align.END)
                watched_indicator.set_hexpand(True)
                main_hbox.append(watched_indicator)
            row.set_child(main_hbox)
            self.episode_listbox.append(row)

    def _on_episode_row_activated(self, listbox, row):
        if hasattr(row, "episode_data"):
            self.emit("episode-activated", row.episode_data)

    def _on_trailer_clicked(self, button):
        if self.current_trailer_key:
            self.emit("trailer-requested", self.current_trailer_key)

    def _fetch_season_details_thread(self, api_key, tmdb_id, season_num, provider_episodes):
        """Fetches season details, saves to DB, and updates UI."""
        tmdb_season_data = tmdb_client.get_season_details(api_key, tmdb_id, season_num)
        if tmdb_season_data:
            if self.series_id_xtream:
                try:
                    meta_row = database.get_metadata(self.series_id_xtream)
                    all_seasons_data = {}
                    if meta_row:
                        meta_dict = dict(meta_row)
                        if meta_dict.get('seasons_json'):
                            try:
                                all_seasons_data = json.loads(meta_dict['seasons_json'])
                            except json.JSONDecodeError: pass
                    all_seasons_data[str(season_num)] = tmdb_season_data
                    new_json_str = json.dumps(all_seasons_data)
                    database.update_season_data(self.series_id_xtream, new_json_str)
                except Exception as e:
                    logging.error(f"Error saving season data to DB: {e}")

            def update_ui_safe():
                if not hasattr(self, "season_combo"): return False
                current_active = str(self.season_combo.get_active_id())
                if current_active == str(season_num):
                    self.current_tmdb_season_data = tmdb_season_data
                    self._populate_episode_list(provider_episodes, tmdb_season_data)
                return False
            GLib.idle_add(update_ui_safe)

    def refresh_current_season(self):
        active_season_id = self.season_combo.get_active_id()
        if active_season_id and self.episodes_data:
            episodes = self.episodes_data.get(active_season_id, [])
            self._populate_episode_list(episodes)
            logging.info("Series Detail: Episode list refreshed (Updated watched status).")

    def _fetch_tmdb_series_data(self, series_name):
        user_key = database.get_config_value("tmdb_api_key")
        api_key = user_key if user_key else get_fallback_tmdb_key()
        if not api_key: return

        clean_title, year = title_parser.parse_title_for_search(series_name)
        self.clean_tmdb_title = clean_title 
        if not clean_title: return

        search_result, status = tmdb_client.search_media(api_key, clean_title, 'tv', year)
        if status == "success" and search_result:
            tmdb_id = search_result.get('id')
            if tmdb_id:
                details = tmdb_client.get_media_details(api_key, tmdb_id, 'tv')
                if details:
                    database.save_metadata(str(self.series_id), details)
                    GLib.idle_add(self._update_ui_with_tmdb, details)
                season_id = self.season_combo.get_active_id()
                if season_id and season_id.isdigit():
                    if self.all_seasons_tmdb_data.get(str(season_id)):
                        logging.info(f"Using cached season data for Season {season_id}")
                        GLib.idle_add(self._update_episodes_with_tmdb, self.all_seasons_tmdb_data[str(season_id)])
                    else:
                        season_data = tmdb_client.get_season_details(api_key, tmdb_id, int(season_id))
                        if season_data:
                            GLib.idle_add(self._update_episodes_with_tmdb, season_data)

    def _update_episodes_with_tmdb(self, season_data):
        self.current_tmdb_season_data = season_data
        season_num = self.season_combo.get_active_id()
        if season_num:
            thread = threading.Thread(target=self._save_season_data, args=(season_num, season_data), daemon=True)
            thread.start()
        main_window = self.get_ancestor(Gtk.Window)
        trakt_cache = getattr(main_window, 'trakt_watched_episodes', set())
        child = self.episode_listbox.get_first_child()
        while child:
            row = child
            child = child.get_next_sibling()
            ep_data = row.episode_data
            ep_num = str(ep_data.get('episode_num'))
            if ep_num in season_data:
                tmdb_ep = season_data[ep_num]
                tmdb_ep_id = tmdb_ep.get('id')
                ep_data['tmdb_id'] = tmdb_ep_id
                box = row.get_child()
                is_visually_watched = False
                last_child = box.get_last_child()
                if last_child and last_child.get_style_context().has_class("watched-button"):
                    is_visually_watched = True
                if not is_visually_watched and tmdb_ep_id and str(tmdb_ep_id) in trakt_cache:
                    database.save_playback_progress(str(ep_data.get('id')), position=0, is_finished=1)
                    icon = Gtk.Button(icon_name="object-select-symbolic")
                    icon.add_css_class("watched-button")
                    icon.add_css_class("watched")
                    icon.set_can_focus(False)
                    icon.set_focusable(False)
                    icon.set_valign(Gtk.Align.CENTER)
                    icon.set_halign(Gtk.Align.END)
                    icon.set_hexpand(True)
                    box.append(icon)
                vbox = box.get_first_child()
                title_label = vbox.get_first_child()
                new_title = tmdb_ep.get('name')
                if new_title:
                    title_label.set_markup(f"<b>{ep_num}. {GLib.markup_escape_text(new_title)}</b>")
                if tmdb_ep.get('overview'):
                    if vbox.get_last_child() != title_label:
                        vbox.remove(vbox.get_last_child())
                    overview_lbl = Gtk.Label(xalign=0, label=tmdb_ep['overview'], wrap=True, max_width_chars=60, lines=2, ellipsize=Pango.EllipsizeMode.END)
                    overview_lbl.add_css_class("caption"); overview_lbl.set_opacity(0.7)
                    vbox.append(overview_lbl)

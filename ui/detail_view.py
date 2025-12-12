# ui/detail_view.py

import gi
import os
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject, Pango, GLib, GdkPixbuf, Gdk
import gettext
_ = gettext.gettext
import logging
import threading
import json
import re
from utils.theme_utils import get_icon_theme_folder
from utils.image_loader import load_image_async
from utils import title_parser
from data_providers import tmdb_client, xtream_client
from core.config import get_fallback_tmdb_key
import database
IMAGE_BASE_URL_PROFILE = "https://image.tmdb.org/t/p/w185"
class DetailView(Gtk.Box):
    __gsignals__ = {
        "play-requested": (GObject.SignalFlags.RUN_FIRST, None, (str, str,)),
        "back-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "trailer-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,))
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, **kwargs)
        self.set_margin_start(24)
        self.set_margin_end(24)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.media_url = None
        self.media_type = None
        self.current_trailer_key = None
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(header_box)
        back_button = Gtk.Button(icon_name="go-previous-symbolic", label=_("Back"))
        back_button.connect("clicked", self._on_back_clicked)
        back_button.set_halign(Gtk.Align.START)
        header_box.append(back_button)
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=30)
        main_box.set_vexpand(True)
        main_box.set_valign(Gtk.Align.FILL)
        main_box.set_margin_top(12)
        self.append(main_box)
        self.poster_image = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        self.poster_image.set_size_request(200, 300)
        self.poster_image.set_valign(Gtk.Align.START)
        main_box.append(self.poster_image)
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_box.set_hexpand(True)
        info_box.set_vexpand(True)
        info_box.set_valign(Gtk.Align.FILL)
        main_box.append(info_box)
        self.title_label = Gtk.Label(xalign=0, wrap=True)
        self.title_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.title_label.set_markup("<span weight='bold' size='xx-large'></span>")
        info_box.append(self.title_label)
        self.genre_label = Gtk.Label(xalign=0, css_classes=["caption"], wrap=True)
        info_box.append(self.genre_label)
        self.release_date_label = Gtk.Label(xalign=0, css_classes=["caption"])
        info_box.append(self.release_date_label)
        self.rating_label = Gtk.Label(xalign=0)
        info_box.append(self.rating_label)
        self.director_label = Gtk.Label(xalign=0, wrap=True)
        self.director_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.director_label.set_hexpand(False)
        self.director_label.set_halign(Gtk.Align.START)
        info_box.append(self.director_label)
        self.country_label = Gtk.Label(xalign=0, wrap=True)
        self.country_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.country_label.set_hexpand(False)
        self.country_label.set_halign(Gtk.Align.START)
        info_box.append(self.country_label)
        self.cast_label = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_max_content_height(300)
        self.overview_textview = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, editable=False, cursor_visible=False,
                                             left_margin=6, right_margin=6, top_margin=6, bottom_margin=6)
        scrolled_window.set_child(self.overview_textview)
        info_box.append(scrolled_window)
        cast_header = Gtk.Label(xalign=0, margin_top=10)
        cast_header.set_markup(f"<b>{_('Cast')}</b>")
        info_box.append(cast_header)
        cast_scrolled = Gtk.ScrolledWindow()
        cast_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cast_scrolled.set_min_content_height(75)
        cast_scrolled.set_vexpand(True)
        self.cast_flowbox = Gtk.FlowBox(valign=Gtk.Align.START, max_children_per_line=10, selection_mode=Gtk.SelectionMode.NONE)
        cast_scrolled.set_child(self.cast_flowbox)
        info_box.append(cast_scrolled)
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER, margin_top=15)
        self.append(button_box)
        play_button = Gtk.Button(label=_("PLAY"), icon_name="media-playback-start-symbolic", css_classes=["suggested-action", "pill"])
        play_button.connect("clicked", self._on_play_clicked)
        button_box.append(play_button)
        self.trailer_button = Gtk.Button(css_classes=["pill"])
        button_content_box = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        theme_folder = get_icon_theme_folder()
        icon_path = os.path.join("resources", "icons", theme_folder, "fragman.svg")
        try:
            if os.path.exists(icon_path):
                 trailer_icon = Gtk.Image.new_from_file(icon_path)
                 trailer_icon.set_pixel_size(16)
                 button_content_box.append(trailer_icon)
            else: logging.warning(f"Trailer icon not found: {icon_path}")
        except GLib.Error as e: logging.error(f"Trailer icon could not be loaded: {icon_path}, Error: {e}")
        trailer_label = Gtk.Label(label=_("Watch Trailer"))
        button_content_box.append(trailer_label)
        self.trailer_button.set_child(button_content_box)
        self.trailer_button.set_sensitive(False)
        self.trailer_button.connect("clicked", self._on_trailer_clicked)
        button_box.append(self.trailer_button)

    def update_content(self, item, media_type):
        logging.info(f"DETAILVIEW: update_content STARTED - Item: {item.props.title}, Type: {media_type}, URL/ID: {item.props.path_or_url}")
        self.media_url = item.props.path_or_url
        self.media_type = media_type
        self.current_trailer_key = None
        self.trailer_button.set_sensitive(False)
        logging.debug("DETAILVIEW: Clearing UI and setting initial info...")
        self.poster_image.set_paintable(None)
        initial_title = item.props.title or ""
        self.title_label.set_markup(f"<span weight='bold' size='xx-large'>{GLib.markup_escape_text(initial_title)}</span>")
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
        provider_poster = item.props.poster_path or ""
        if provider_poster.startswith("http"):
             load_image_async(provider_poster, self.poster_image,
                              on_success_callback=lambda w, p: w.set_paintable(Gdk.Texture.new_for_pixbuf(p)),
                              on_failure=None)
        rating = item.props.provider_rating
        self.rating_label.set_markup(f"<b>{_('Rating')}:</b> {rating:.1f}" if rating > 0.01 else "")
        release_date = item.props.provider_release_date
        self.release_date_label.set_text(release_date if release_date else "")
        provider_year = release_date[:4] if release_date and len(release_date) >= 4 else ""
        year_str_provider = f" ({provider_year})" if provider_year else ""
        self.title_label.set_markup(f"<span weight='bold' size='xx-large'>{GLib.markup_escape_text(initial_title + year_str_provider)}</span>")
        logging.debug("DETAILVIEW: Initial info set.")
        main_window = self.get_ancestor(Gtk.Window)
        profile_data = main_window.profile_data if main_window else None
        use_tmdb = database.get_use_tmdb_status()
        logging.debug(f"DETAILVIEW: Main logic starting. use_tmdb={use_tmdb}, media_type={self.media_type}")
        if self.media_type == 'media':
            logging.debug("DETAILVIEW: Media type 'media'.")
            if use_tmdb:
                logging.debug("DETAILVIEW: use_tmdb=True. Checking database...")
                db_row = database.get_metadata(self.media_url)
                if db_row:
                    logging.info(f"DETAILVIEW ('media'): TMDb data found in DB. CALLING _update_labels_from_tmdb_data.")
                    self._update_labels_from_tmdb_data(dict(db_row))
                else:
                    logging.info(f"DETAILVIEW ('media'): No TMDb data in DB. STARTING _search_and_fetch_tmdb_thread.")
                    thread = threading.Thread(
                        target=self._search_and_fetch_tmdb_thread,
                        args=(initial_title, provider_year),
                        daemon=True
                    )
                    thread.start()
            else:
                logging.debug("DETAILVIEW ('media'): use_tmdb=False. Applying fallback.")
                self._set_overview_text(_("Detailed information not found."))
                self.genre_label.set_text("")
                while (child := self.cast_flowbox.get_child_at_index(0)): self.cast_flowbox.remove(child)
                no_cast_label = Gtk.Label(label=_("Detailed cast information not available."), css_classes=["caption"])
                self.cast_flowbox.append(no_cast_label)
        elif self.media_type == 'vod':
            logging.debug(f"DETAILVIEW: Media type 'vod'. Profile type checking...")
            profile_type = profile_data.get("type") if profile_data else None
            if profile_type == 'xtream':
                logging.debug(f"DETAILVIEW ('vod'): Profile type 'xtream'. URL/ID: {self.media_url}")
                if profile_data and self.media_url.isdigit():
                    stream_id = self.media_url
                    logging.info(f"DETAILVIEW ('vod'-xtream): STARTING _fetch_xtream_info_and_decide_tmdb_thread (ID: {stream_id}).")
                    thread = threading.Thread(
                        target=self._fetch_xtream_info_and_decide_tmdb_thread,
                        args=(profile_data, stream_id, use_tmdb),
                        daemon=True
                    )
                    thread.start()
                else:
                    logging.warning(f"DETAILVIEW ('vod'-xtream): Invalid VOD ID or missing profile data: {self.media_url}")
                    self._set_overview_text(_("Invalid Xtream VOD information."))
                    self.genre_label.set_text("")
                    while (child := self.cast_flowbox.get_child_at_index(0)): self.cast_flowbox.remove(child)
                    no_cast_label = Gtk.Label(label=_("Detailed information could not be retrieved."), css_classes=["caption"])
                    self.cast_flowbox.append(no_cast_label)
            else:
                logging.debug(f"DETAILVIEW ('vod'): Profile type 'm3u'. URL: {self.media_url}")
                if use_tmdb:
                    logging.debug("DETAILVIEW ('vod'-m3u): use_tmdb=True. Checking database...")
                    db_row = database.get_metadata(self.media_url)
                    if db_row:
                        logging.info(f"DETAILVIEW ('vod'-m3u): TMDb data found in DB. CALLING _update_labels_from_tmdb_data.")
                        self._update_labels_from_tmdb_data(dict(db_row))
                    else:
                        logging.info(f"DETAILVIEW ('vod'-m3u): No TMDb data in DB. STARTING _search_and_fetch_tmdb_thread.")
                        thread = threading.Thread(
                            target=self._search_and_fetch_tmdb_thread,
                            args=(initial_title, provider_year),
                            daemon=True
                        )
                        thread.start()
                else:
                    logging.debug("DETAILVIEW ('vod'-m3u): use_tmdb=False. Applying fallback.")
                    self._set_overview_text(_("Detailed information not found."))
                    self.genre_label.set_text("")
                    while (child := self.cast_flowbox.get_child_at_index(0)): self.cast_flowbox.remove(child)
                    no_cast_label = Gtk.Label(label=_("Detailed cast information not available."), css_classes=["caption"])
                    self.cast_flowbox.append(no_cast_label)
        logging.info("DETAILVIEW: update_content FINISHED.")

    def _fetch_xtream_info_and_decide_tmdb_thread(self, profile_data, stream_id, use_tmdb_setting):
        """
        (Background Thread) First calls get_vod_info.
        If TMDb ID is in the response AND TMDb is enabled:
           1. Checks LOCAL DATABASE first.
           2. If not in DB, fetches from TMDb API.
        Otherwise, triggers UI update with Xtream data.
        """
        logging.debug(f"Fetching Xtream info for ID: {stream_id}")
        xtream_info_data = xtream_client.get_vod_info(profile_data, stream_id)
        tmdb_id_from_xtream = None
        if xtream_info_data and "info" in xtream_info_data:
            info_part = xtream_info_data.get("info", {})
            movie_data_part = xtream_info_data.get("movie_data", {})
            tmdb_id_info = None
            tmdb_id_movie_data = None
            if isinstance(info_part, dict):
                tmdb_id_info = info_part.get('tmdb_id')
            if isinstance(movie_data_part, dict):
                tmdb_id_movie_data = movie_data_part.get('tmdb_id')
            tmdb_id_from_xtream = tmdb_id_info or tmdb_id_movie_data
            if isinstance(tmdb_id_from_xtream, str) and tmdb_id_from_xtream.isdigit():
                 try: tmdb_id_from_xtream = int(tmdb_id_from_xtream)
                 except ValueError: tmdb_id_from_xtream = None
            elif not isinstance(tmdb_id_from_xtream, int):
                 tmdb_id_from_xtream = None
        if use_tmdb_setting and tmdb_id_from_xtream:
            logging.info(f"TMDb ID ({tmdb_id_from_xtream}) found in Xtream info.")
            cached_data = database.get_metadata(stream_id)
            if cached_data:
                cached_dict = dict(cached_data)
                if cached_dict.get('overview') or cached_dict.get('title'):
                    logging.info(f"Valid metadata found in DB for stream {stream_id}. Skipping API fetch.")
                    GLib.idle_add(self._update_labels_from_tmdb_data, cached_dict)
                    return
            user_key = database.get_config_value("tmdb_api_key")
            api_key = user_key if user_key else get_fallback_tmdb_key()
            if api_key:
                logging.info(f"Fetching TMDb details from API for ID: {tmdb_id_from_xtream}")
                tmdb_details = tmdb_client.get_media_details(api_key, tmdb_id_from_xtream, 'movie')
                if tmdb_details:
                    database.save_metadata(stream_id, tmdb_details)
                    logging.info(f"DETAILVIEW (Xtream-TMDb): Scheduling _update_labels_from_tmdb_data via idle_add")
                    GLib.idle_add(self._update_labels_from_tmdb_data, tmdb_details)
                    return
                else:
                    logging.warning(f"Could not get details for TMDb ID ({tmdb_id_from_xtream}).")
            else:
                logging.warning("TMDb ID found but API key is not set (and fallback failed).")
        logging.debug("TMDb ID missing/not in use/failed/API missing. UI will be updated with Xtream info data.")
        logging.info(f"DETAILVIEW (Xtream-Fallback): Scheduling _update_labels_from_xtream_info via idle_add")
        GLib.idle_add(self._update_labels_from_xtream_info, xtream_info_data)

    def _search_and_fetch_tmdb_thread(self, title_to_search, year):
        """(Background Thread) Searches TMDb by TITLE and fetches details."""
        tmdb_data = None
        user_key = database.get_config_value("tmdb_api_key")
        api_key = user_key if user_key else get_fallback_tmdb_key()
        if not api_key:
             logging.warning("TMDb API key is not set (and fallback failed).")
        else:
            try:
                clean_title, parsed_year = title_parser.parse_title_for_search(title_to_search)
                search_year_final = parsed_year or year
                if clean_title:
                    media_search_type = 'movie' if self.media_type in ['vod', 'media'] else 'tv'
                    search_result, status = tmdb_client.search_media(api_key, clean_title, media_search_type, search_year_final)
                    if status == "success" and search_result and search_result.get("id"):
                        media_id = search_result["id"]
                        logging.info(f"TMDb title search match found: ID {media_id}")
                        tmdb_data = tmdb_client.get_media_details(api_key, media_id, media_search_type)
                        if tmdb_data:
                             database.save_metadata(self.media_url, tmdb_data)
                             logging.debug(f"TMDb data (title search) saved to database (key: {self.media_url})")
                    else:
                         logging.warning(f"No match found in TMDb title search for '{clean_title}' ({search_year_final}). Status: {status}")
                else:
                     logging.warning(f"Could not parse title (title search), skipping TMDb search: '{title_to_search}'")
            except Exception as e:
                logging.error(f"Error during TMDb title search/detail fetch: {e}", exc_info=True)
        logging.info(f"DETAILVIEW (Search): Scheduling _process_tmdb_result_search via idle_add (data found: {tmdb_data is not None})")
        GLib.idle_add(self._process_tmdb_result_search, tmdb_data)

    def _process_tmdb_result_search(self, tmdb_data):
        """(Main Thread) Processes the TMDb TITLE search result."""
        logging.info("===== _process_tmdb_result_search CALLED =====")
        if tmdb_data:
            logging.debug("TMDb data (title search) received successfully, scheduling UI update.")
            logging.info(f"DETAILVIEW (Search-Result): Scheduling _update_labels_from_tmdb_data via idle_add")
            GLib.idle_add(self._update_labels_from_tmdb_data, tmdb_data)
        else:
            logging.debug("TMDb data (title search) not found, running fallback (basic info).")
            self._set_overview_text(_("Detailed information not found (TMDb search failed)."))
        return GLib.SOURCE_REMOVE

    def _update_labels_from_tmdb_data(self, tmdb_api_or_db_data):
        """Updates labels and ACTOR POSTERS with TMDb data (from API response OR DB row format)."""
        logging.info("===== _update_labels_from_tmdb_data CALLED =====")
        logging.debug(f"Received Data Type: {type(tmdb_api_or_db_data)}")
        logging.debug(f"Received Data Content (first 500 chars): {str(tmdb_api_or_db_data)[:500]}")
        try:
            logging.info("Starting to process TMDb data...")
            initial_title = self.title_label.get_text().split(' (')[0]
            release_date = tmdb_api_or_db_data.get("release_date", "") or ""
            year_str = f" ({release_date[:4]})" if release_date else ""
            tmdb_title = tmdb_api_or_db_data.get('title', initial_title) or initial_title
            logging.debug(f"Updating title: '{tmdb_title + year_str}'")
            self.title_label.set_markup(f"<span weight='bold' size='xx-large'>{GLib.markup_escape_text(tmdb_title + year_str)}</span>")
            self.release_date_label.set_text(release_date)
            rating_val = tmdb_api_or_db_data.get('rating')
            if rating_val is None: rating_val = tmdb_api_or_db_data.get('vote_average')
            self.rating_label.set_markup(f"<b>{_('TMDb Rating')}:</b> {rating_val:.1f} / 10" if rating_val is not None else "")
            overview = tmdb_api_or_db_data.get("overview", "") or ""
            logging.debug(f"Updating overview (first 50 chars): {overview[:50]}")
            self._set_overview_text(overview if overview else _("Plot information not found."))
            director = tmdb_api_or_db_data.get('director', "") or ""
            self.director_label.set_markup(f"<b>{_('Director')}:</b> {director if director else 'N/A'}")
            countries = tmdb_api_or_db_data.get('countries', "")
            if countries:
                self.country_label.set_markup(f"<b>{_('Production Country')}:</b> {countries}")
            else:
                self.country_label.set_text("")
            genres = tmdb_api_or_db_data.get('genres', '')
            logging.debug(f"Updating genres: '{genres}'")
            self.genre_label.set_markup(f"<i>{genres}</i>" if genres else "")
            cast_with_pics_json = tmdb_api_or_db_data.get('cast_members')
            cast_list = []
            logging.debug(f"Searching for cast data... DB JSON: {cast_with_pics_json is not None}, API List: {'cast_with_pics' in tmdb_api_or_db_data}")
            if cast_with_pics_json:
                try:
                    cast_list = json.loads(cast_with_pics_json)
                    logging.debug(f"{len(cast_list)} cast members read from database JSON.")
                except json.JSONDecodeError:
                    logging.warning("Cast data in database is not in JSON format.")
                    cast_list = []
            elif 'cast_with_pics' in tmdb_api_or_db_data and isinstance(tmdb_api_or_db_data['cast_with_pics'], list):
                 cast_list = tmdb_api_or_db_data['cast_with_pics']
                 logging.debug(f"{len(cast_list)} cast members list from API response used.")
            while (child := self.cast_flowbox.get_child_at_index(0)):
                self.cast_flowbox.remove(child)
            if cast_list:
                logging.debug(f"Creating boxes for {len(cast_list)} cast members...")
                for actor in cast_list:
                    actor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_bottom=6)
                    actor_box.set_size_request(100, -1)
                    actor_image = Gtk.Image()
                    actor_image.set_pixel_size(138)
                    actor_image.set_from_icon_name("avatar-default-symbolic")
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
                 logging.debug("Cast list is empty, 'not found' message added.")
            poster_key = tmdb_api_or_db_data.get("poster_path")
            if poster_key:
                full_poster_url = tmdb_client.get_poster_url(poster_key)
                if full_poster_url:
                    load_image_async(
                        full_poster_url, self.poster_image,
                        on_success_callback=lambda widget, pixbuf: widget.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                    )
            trailer_key = tmdb_api_or_db_data.get("trailer_key")
            logging.info(f"UI Update DEBUG: Found trailer_key = {trailer_key}")
            if trailer_key:
                self.current_trailer_key = trailer_key
                self.trailer_button.set_sensitive(True)
                logging.debug(f"Trailer key found and button enabled: {trailer_key}")
            else:
                self.current_trailer_key = None
                self.trailer_button.set_sensitive(False)
                logging.debug("No trailer key found in TMDb data.")
            logging.info("UI update with TMDb data completed successfully.")
        except Exception as e:
            logging.error(f"Detail view: ERROR processing TMDb data (_update_labels_from_tmdb_data): {e}", exc_info=True)
        return GLib.SOURCE_REMOVE

    def _on_trailer_clicked(self, button):
        if self.current_trailer_key:
            logging.info(f"Trailer button clicked, emitting signal with key: {self.current_trailer_key}")
            self.emit("trailer-requested", self.current_trailer_key)
        else:
            logging.warning("Trailer button clicked but no trailer key available.")

    def _update_labels_from_xtream_info(self, xtream_info_data):
        """(Main Thread) Updates labels with the response from get_vod_info (FALLBACK)."""
        logging.debug("DETAILVIEW: Fallback - Updating UI labels with Xtream data...")
        info = {}
        movie_data = {}
        if xtream_info_data:
            if isinstance(xtream_info_data.get("info"), dict):
                info = xtream_info_data.get("info", {})
            if isinstance(xtream_info_data.get("movie_data"), dict):
                movie_data = xtream_info_data.get("movie_data", {})
        plot = info.get('plot')
        self._set_overview_text(plot if plot else _("Plot information not found."))
        director = info.get('director')
        self.director_label.set_markup(f"<b>{_('Director')}:</b> {director if director else 'N/A'}")
        release_date = info.get('releasedate') or movie_data.get('releasedate')
        self.release_date_label.set_text(release_date if release_date else "")
        title_val = info.get('name') or movie_data.get('name')
        if title_val:
             self.title_label.set_markup(f"<span weight='bold' size='xx-large'>{GLib.markup_escape_text(title_val)}</span>")
        rating_val = info.get('rating') or movie_data.get('rating')
        if rating_val:
            try:
                rating_float = float(rating_val)
                self.rating_label.set_markup(f"<b>{_('Rating')}:</b> {rating_float:.1f}" if rating_float > 0.01 else "")
            except (ValueError, TypeError):
                self.rating_label.set_text("")
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
            logging.debug(f"DETAILVIEW Fallback: Provider trailer key found and button enabled: {self.current_trailer_key}")
        else:
            self.current_trailer_key = None
            self.trailer_button.set_sensitive(False)
            if provider_trailer_key:
                 logging.warning(f"DETAILVIEW Fallback: Provider trailer found but YouTube ID could not be extracted: {provider_trailer_key}")
        logging.debug("DetailView labels updated with Xtream get_vod_info data (fallback).")
        return GLib.SOURCE_REMOVE

    def _set_overview_text(self, text):
        buffer = self.overview_textview.get_buffer()
        buffer.delete(buffer.get_start_iter(), buffer.get_end_iter())
        buffer.insert(buffer.get_start_iter(), text)

    def _on_play_clicked(self, button):
        if self.media_url and self.media_type:
            self.emit("play-requested", self.media_url, self.media_type)

    def _on_back_clicked(self, button):
        self.emit("back-requested")

    def _create_actor_placeholder(self):
        """Creates a placeholder widget to display while loading the actor image."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(100, 150)
        spinner = Gtk.Spinner(spinning=True, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, hexpand=True, vexpand=True)
        box.append(spinner)
        return box

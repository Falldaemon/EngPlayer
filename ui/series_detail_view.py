# ui/series_detail_view.py

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Pango, GLib, GdkPixbuf, Gdk, Adw
import gettext
_ = gettext.gettext
import logging
import threading
import os
import json
import re

import locale
from deep_translator import GoogleTranslator

def get_system_language():
    try:
        langs = GLib.get_language_names()
        for lang in langs:
            code = lang[:2].lower()
            if code and code != 'c':
                return code               
        env_lang = os.environ.get('LANG', '')
        if env_lang:
            code = env_lang[:2].lower()
            if code and code != 'c':
                return code             
        return 'en'        
    except Exception as e:
        logging.error(f"Language detection error: {e}")
        return 'en'

def translate_text_manually(text, callback, button_to_disable=None):
    if not text or len(text.strip()) == 0:
        return
    if button_to_disable:
        button_to_disable.set_sensitive(False)

    def run_translation():
        try:
            target_lang = get_system_language()
            translated = GoogleTranslator(source='auto', target=target_lang).translate(text)
            GLib.idle_add(callback, translated)
        except Exception as e:
            logging.error(f"Translation error: {e}")
            GLib.idle_add(callback, text)
        finally:
            if button_to_disable:
                GLib.idle_add(button_to_disable.set_sensitive, True)
    threading.Thread(target=run_translation, daemon=True).start()

from utils.image_loader import load_image_async
from data_providers import tmdb_client
from core.config import get_fallback_tmdb_key
import database
from utils.theme_utils import get_icon_theme_folder
IMAGE_BASE_URL_PROFILE = "https://image.tmdb.org/t/p/w185"

class ActorBioDialog(Adw.Window):
    def __init__(self, parent, actor_id, actor_name_fallback):
        super().__init__(transient_for=parent, modal=True)
        self.set_title(actor_name_fallback)
        self.set_default_size(750, 600) 
        self.add_css_class("media-info-dialog")
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(content_box)       
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        content_box.append(header)
        self.translate_btn = Gtk.Button()
        self.translate_btn.set_tooltip_text(_("Translate"))      
        theme_folder = get_icon_theme_folder()
        trans_icon_path = os.path.join("resources", "icons", theme_folder, "translate.svg")
        if os.path.exists(trans_icon_path):
            img = Gtk.Image.new_from_file(trans_icon_path)
            img.set_pixel_size(16)
            self.translate_btn.set_child(img)
        else:
            self.translate_btn.set_icon_name("preferences-desktop-locale-symbolic")          
        self.translate_btn.connect("clicked", self._on_translate_clicked)
        header.pack_end(self.translate_btn)       
        self.original_bio = ""
        main_scroll = Gtk.ScrolledWindow(vexpand=True)
        content_box.append(main_scroll)
        container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, 
            spacing=24, 
            margin_top=24, 
            margin_bottom=24, 
            margin_start=24, 
            margin_end=24
        )
        main_scroll.set_child(container)
        top_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        container.append(top_hbox)
        self.profile_image = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        self.profile_image.set_size_request(200, 300)
        self.profile_image.set_valign(Gtk.Align.START)
        img_frame = Gtk.Frame(child=self.profile_image)
        top_hbox.append(img_frame)
        info_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        top_hbox.append(info_vbox)       
        self.name_label = Gtk.Label(xalign=0, css_classes=["title-1"])
        self.name_label.set_markup(f"<b>{GLib.markup_escape_text(actor_name_fallback)}</b>")
        info_vbox.append(self.name_label)       
        self.birth_label = Gtk.Label(xalign=0, css_classes=["dim-label"])
        info_vbox.append(self.birth_label)       
        self.bio_label = Gtk.Label(xalign=0, yalign=0, wrap=True)
        self.bio_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.bio_label.set_markup("<i>" + _("Loading biography...") + "</i>")
        info_vbox.append(self.bio_label)
        self.known_for_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.known_for_section.set_visible(False)
        container.append(self.known_for_section)
        kf_label = Gtk.Label(xalign=0, css_classes=["title-2"])
        kf_label.set_markup(f"<b>{_('Known For')}</b>")
        self.known_for_section.append(kf_label)
        self.posters_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.known_for_section.append(self.posters_hbox)      
        threading.Thread(target=self._fetch_data, args=(actor_id,), daemon=True).start()

    def _fetch_data(self, actor_id):
        user_key = database.get_config_value("tmdb_api_key")
        api_key = user_key if user_key else get_fallback_tmdb_key()
        if api_key:
            details = tmdb_client.get_person_details(api_key, actor_id)
            GLib.idle_add(self._update_ui, details)

    def _update_ui(self, details):
        if not details: return
        if details.get("profile_path"):
            url = f"https://image.tmdb.org/t/p/w300{details['profile_path']}"
            load_image_async(url, self.profile_image, on_success_callback=lambda w, p: w.set_paintable(Gdk.Texture.new_for_pixbuf(p)))      
        bday = details.get("birthday"); place = details.get("place_of_birth")
        self.birth_label.set_text(f"{bday} • {place}" if bday and place else (bday or place or ""))
        self.original_bio = details.get("biography") or _("No biography found.")
        self.bio_label.set_text(self.original_bio)
        known_works = details.get("known_for", [])
        if known_works:
            self.known_for_section.set_visible(True)
            for work in known_works:
                p_path = work.get("poster_path")
                if not p_path: continue               
                work_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                work_vbox.set_size_request(80, -1)
                work_img = Gtk.Image(pixel_size=120)
                work_img.set_from_icon_name("view-more-symbolic")
                load_image_async(f"https://image.tmdb.org/t/p/w154{p_path}", work_img, 
                                 on_success_callback=lambda w, p: w.set_from_pixbuf(p))              
                work_title = Gtk.Label(label=work.get("title") or work.get("name", ""), wrap=True, lines=2, ellipsize=Pango.EllipsizeMode.END)
                work_title.add_css_class("caption")              
                work_vbox.append(work_img); work_vbox.append(work_title)
                self.posters_hbox.append(work_vbox)

    def _on_translate_clicked(self, btn):
        if getattr(self, "original_bio", "") == "" or self.original_bio == _("No biography found."):
            return        
        self.bio_label.set_markup("<i>" + _("Translating...") + "</i>")
        
        def on_translated(result):
            self.bio_label.set_text(result)           
        translate_text_manually(self.original_bio, on_translated, btn)

class SeriesDetailView(Gtk.Box):
    __gsignals__ = {
        "back-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "episode-activated": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "trailer-requested": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "episode-download-requested": (GObject.SignalFlags.RUN_FIRST, None, (object, str)),
        "cancel-episode-download-requested": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, **kwargs)
        self.set_margin_start(24); self.set_margin_end(24)
        self.set_margin_top(12); self.set_margin_bottom(12)        
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(header_box)
        back_button = Gtk.Button()
        back_button.set_halign(Gtk.Align.START)
        back_button.set_has_frame(False)         
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.append(Gtk.Image.new_from_icon_name("go-previous-symbolic"))
        btn_box.append(Gtk.Label(label=_("Back")))
        back_button.set_child(btn_box)      
        back_button.connect("clicked", lambda w: self.emit("back-requested"))
        header_box.append(back_button)
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=30)
        main_box.set_vexpand(True); main_box.set_valign(Gtk.Align.FILL)
        main_box.set_margin_top(12)
        self.append(main_box)
        self.info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.append(self.info_box)
        self.poster_image = Gtk.Picture(content_fit=Gtk.ContentFit.COVER)
        self.poster_image.set_size_request(100, 200)
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
        action_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, margin_top=10)
        action_button_box.append(self.trailer_button)
        self.translate_btn = Gtk.Button(css_classes=["pill"], halign=Gtk.Align.CENTER, margin_top=10)      
        translate_box = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        trans_icon_path = os.path.join("resources", "icons", theme_folder, "translate.svg")
        if os.path.exists(trans_icon_path):
             trans_icon = Gtk.Image.new_from_file(trans_icon_path)
             trans_icon.set_pixel_size(16)
             translate_box.append(trans_icon)
        else:
             trans_fallback = Gtk.Image.new_from_icon_name("preferences-desktop-locale-symbolic")
             trans_fallback.set_pixel_size(16)
             translate_box.append(trans_fallback)            
        trans_label = Gtk.Label(label=_("Translate"))
        translate_box.append(trans_label)
        self.translate_btn.set_child(translate_box)
        self.translate_btn.connect("clicked", self._on_translate_clicked)
        action_button_box.append(self.translate_btn)
        self.info_box.append(action_button_box)      
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
        self._episode_download_buttons = {}
        self._is_downloading = False
        self._active_download_episode_id = None

    def update_content(self, series_info, series_id=None):
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
            self.country_label.set_markup(f"<b>{_('Production Country')}:</b> {countries}" if countries else "")           
            genres = tmdb_api_or_db_data.get('genres', '')
            self.genre_label.set_markup(f"<i>{GLib.markup_escape_text(genres)}</i>" if genres else "")
            cast_with_pics_json = tmdb_api_or_db_data.get('cast_members')
            cast_list = []
            if cast_with_pics_json:
                try: cast_list = json.loads(cast_with_pics_json)
                except: cast_list = []
            elif 'cast_with_pics' in tmdb_api_or_db_data:
                cast_list = tmdb_api_or_db_data['cast_with_pics']
            while (child := self.cast_flowbox.get_child_at_index(0)):
                self.cast_flowbox.remove(child)
            if cast_list:
                theme_folder = get_icon_theme_folder()
                info_icon_path = os.path.join("resources", "icons", theme_folder, "info.svg")
                for actor in cast_list:
                    actor_id = actor.get('id'); actor_name = actor.get('name', 'N/A')
                    actor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_bottom=6)
                    actor_box.set_size_request(110, -1)
                    header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                    header_box.set_size_request(-1, 24)
                    actor_box.append(header_box)
                    if actor_id:
                        icon = Gtk.Image.new_from_file(info_icon_path) if os.path.exists(info_icon_path) else Gtk.Image.new_from_icon_name("info-symbolic")
                        icon.set_pixel_size(18); icon.set_halign(Gtk.Align.END); icon.set_hexpand(True); icon.set_opacity(0.8)
                        header_box.append(icon)
                    actor_image = Gtk.Image(pixel_size=110, icon_name="avatar-default-symbolic")
                    if actor.get('profile_path'):
                        load_image_async(IMAGE_BASE_URL_PROFILE + actor['profile_path'], actor_image, on_success_callback=lambda w, p: w.set_from_pixbuf(p))
                    actor_box.append(actor_image)                 
                    name_lbl = Gtk.Label(label=actor_name, wrap=True, justify=Gtk.Justification.CENTER, css_classes=["caption"])
                    actor_box.append(name_lbl)                  
                    actor_button = Gtk.Button(css_classes=["actor-cast-button"])
                    actor_button.set_child(actor_box); actor_button.set_halign(Gtk.Align.CENTER)
                    if actor_id:
                        actor_button.set_tooltip_text(_("Click for biography"))
                        actor_button.connect("clicked", lambda b, aid=actor_id, anm=actor_name: ActorBioDialog(self.get_root(), aid, anm).present())
                    self.cast_flowbox.append(actor_button)
            else:
                self.cast_flowbox.append(Gtk.Label(label=_("Cast information not found."), css_classes=["caption"]))
            if cast_list and database.get_use_tmdb_status():
                has_ids = any(actor.get('id') for actor in cast_list if isinstance(actor, dict))
                if not has_ids:
                    logging.info("SERIES DETAIL: Legacy data detected (missing IDs). Starting silent background repair...")
                    tmdb_id = tmdb_api_or_db_data.get('tmdb_id') or tmdb_api_or_db_data.get('id')
                    user_key = database.get_config_value("tmdb_api_key")
                    api_key = user_key if user_key else get_fallback_tmdb_key()
                    if api_key and tmdb_id:
                        threading.Thread(target=self._fetch_tmdb_details_by_id_thread, args=(api_key, tmdb_id), daemon=True).start()
            trailer_key = tmdb_api_or_db_data.get("trailer_key")
            if trailer_key:
                self.current_trailer_key = trailer_key
                self.trailer_button.set_sensitive(True)
            else:
                self.current_trailer_key = None
                self.trailer_button.set_sensitive(False)
            active_season_id = self.season_combo.get_active_id()
            tmdb_id_val = tmdb_api_or_db_data.get("id") or tmdb_api_or_db_data.get("tmdb_id")
            if active_season_id and tmdb_id_val:
                user_key = database.get_config_value("tmdb_api_key")
                api_key = user_key if user_key else get_fallback_tmdb_key()
                if api_key:
                    episodes = self.episodes_data.get(active_season_id, [])
                    threading.Thread(target=self._fetch_season_details_thread, args=(api_key, tmdb_id_val, active_season_id, episodes), daemon=True).start()
        except Exception as e:
            logging.error(f"SERIES DETAIL: Error processing TMDb data: {e}", exc_info=True)
        return GLib.SOURCE_REMOVE

    def _update_labels_from_xtream_info(self, series_info_data):
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
        self._episode_download_buttons.clear()    
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
                 overview_text = t_data['overview']
                 overview_lbl = Gtk.Label(xalign=0, label=overview_text, wrap=True, max_width_chars=60, lines=2, ellipsize=Pango.EllipsizeMode.END)
                 overview_lbl.add_css_class("caption"); overview_lbl.set_opacity(0.7)
                 overview_lbl._is_episode_overview = True
                 overview_lbl._original_text = overview_text              
                 vbox.append(overview_lbl)
            main_hbox.append(vbox)
            action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            action_box.set_halign(Gtk.Align.END)
            action_box.set_hexpand(True)
            action_box.set_valign(Gtk.Align.CENTER)
            action_box.set_name("episode-action-box")
            main_hbox.append(action_box)
            if is_watched:
                watched_indicator = Gtk.Button(icon_name="object-select-symbolic")
                watched_indicator.add_css_class("watched-button")
                watched_indicator.add_css_class("watched")
                watched_indicator.set_can_focus(False)
                watched_indicator.set_focusable(False)
                action_box.append(watched_indicator) 
            download_btn = Gtk.Button(icon_name="folder-download-symbolic")
            download_btn.add_css_class("flat")
            download_btn.set_tooltip_text(_("Download Episode"))
            download_btn.connect("clicked", lambda b, ep=episode: self._on_episode_download_clicked(b, ep))
            ep_unique_id = str(episode.get('id')) or f"{episode.get('season')}_{episode.get('episode_num')}"
            self._episode_download_buttons[ep_unique_id] = download_btn
            if self._is_downloading:
                if self._active_download_episode_id == ep_unique_id:
                    download_btn.set_icon_name("process-stop-symbolic")
                    download_btn.add_css_class("destructive-action")
                else:
                    download_btn.set_sensitive(False)                  
            action_box.append(download_btn)
            row.set_child(main_hbox)
            self.episode_listbox.append(row)

    def _on_episode_row_activated(self, listbox, row):
        if hasattr(row, "episode_data"):
            self.emit("episode-activated", row.episode_data)
            
    def _on_translate_clicked(self, btn):
        buffer = self.overview_textview.get_buffer()
        start_iter = buffer.get_start_iter()
        end_iter = buffer.get_end_iter()
        text_to_translate = buffer.get_text(start_iter, end_iter, True)      
        ignore_list = [
            _("Loading information..."), 
            _("Plot information not found.")
        ]      
        if text_to_translate and text_to_translate not in ignore_list:
            buffer.insert(end_iter, "\n\n(" + _("Translating...") + ")")
            def on_main_translated(result):
                buffer.delete(buffer.get_start_iter(), buffer.get_end_iter())
                buffer.insert(buffer.get_start_iter(), result)
            translate_text_manually(text_to_translate, on_main_translated, btn)
        child = self.episode_listbox.get_first_child()
        while child:
            row_box = child.get_first_child()
            if row_box:
                vbox = row_box.get_first_child()
                if vbox:
                    lbl = vbox.get_first_child()
                    while lbl:
                        if hasattr(lbl, "_is_episode_overview") and getattr(lbl, "_original_text", ""):
                            orig_text = lbl._original_text
                            lbl.set_text("(" + _("Translating...") + ")")
                            def make_callback(label_widget):
                                def callback(translated):
                                    label_widget.set_text(translated)
                                return callback
                            translate_text_manually(orig_text, make_callback(lbl), None)                         
                        lbl = lbl.get_next_sibling()
            child = child.get_next_sibling()

    def _on_trailer_clicked(self, button):
        if self.current_trailer_key:
            self.emit("trailer-requested", self.current_trailer_key)

    def _fetch_season_details_thread(self, api_key, tmdb_id, season_num, provider_episodes):
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
                action_container = last_child if last_child and last_child.get_name() == "episode-action-box" else None               
                if action_container:
                    child_widget = action_container.get_first_child()
                    while child_widget:
                        if child_widget.get_style_context().has_class("watched-button"):
                            is_visually_watched = True
                            break
                        child_widget = child_widget.get_next_sibling()
                elif last_child and last_child.get_style_context().has_class("watched-button"):
                    is_visually_watched = True
                if not is_visually_watched and tmdb_ep_id and str(tmdb_ep_id) in trakt_cache:
                    database.save_playback_progress(str(ep_data.get('id')), position=0, is_finished=1)
                    icon = Gtk.Button(icon_name="object-select-symbolic")
                    icon.add_css_class("watched-button")
                    icon.add_css_class("watched")
                    icon.set_can_focus(False)
                    icon.set_focusable(False)
                    icon.set_valign(Gtk.Align.CENTER)                   
                    if action_container:
                        action_container.prepend(icon) 
                    else:
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
                    overview_text = tmdb_ep['overview']
                    overview_lbl = Gtk.Label(xalign=0, label=overview_text, wrap=True, max_width_chars=60, lines=2, ellipsize=Pango.EllipsizeMode.END)
                    overview_lbl.add_css_class("caption"); overview_lbl.set_opacity(0.7)
                    overview_lbl._is_episode_overview = True
                    overview_lbl._original_text = overview_text                    
                    vbox.append(overview_lbl)
                    
    def _on_episode_download_clicked(self, button, episode_data):
        ep_unique_id = str(episode_data.get('id')) or f"{episode_data.get('season')}_{episode_data.get('episode_num')}"       
        if self._is_downloading and self._active_download_episode_id == ep_unique_id:
            self.emit("cancel-episode-download-requested")
        elif not self._is_downloading:
            series_title = getattr(self, 'clean_tmdb_title', "Unknown Series")
            self.emit("episode-download-requested", episode_data, series_title)

    def set_download_state(self, is_downloading, active_episode_data=None):
        self._is_downloading = is_downloading      
        if is_downloading and active_episode_data:
            self._active_download_episode_id = str(active_episode_data.get('id')) or f"{active_episode_data.get('season')}_{active_episode_data.get('episode_num')}"
        elif not is_downloading:
            self._active_download_episode_id = None
        for ep_id, btn in self._episode_download_buttons.items():
            if self._is_downloading:
                if ep_id == self._active_download_episode_id:
                    btn.set_icon_name("process-stop-symbolic")
                    btn.add_css_class("destructive-action")
                    btn.set_sensitive(True)
                else:
                    btn.set_icon_name("folder-download-symbolic")
                    btn.remove_css_class("destructive-action")
                    btn.set_sensitive(False)
            else:
                btn.set_icon_name("folder-download-symbolic")
                btn.remove_css_class("destructive-action")
                btn.set_sensitive(True)                    

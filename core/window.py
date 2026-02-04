# core/window.py 

import gi
import re
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gst", "1.0")
from gi.repository import Gtk, Adw, Gio, GLib, Pango, Gst, Gdk, GObject
from playback.recorder import Recorder
import gettext
import logging
import os
import sys
import yt_dlp
import threading
import hashlib
import subprocess
import time
import shutil
import tempfile
import sqlite3
import database
import unicodedata
from ui.navigation_sidebar import NavigationSidebar
from ui.bouquet_list import BouquetList
from ui.channel_list import ChannelList
from ui.media_library_sidebar import MediaLibrarySidebar
from ui.media_grid_view import MediaGridView, MediaItem
from ui.video_view import VideoView
from ui.password_dialog import PasswordDialog
from ui.password_prompt_dialog import PasswordPromptDialog
from ui.favorites_view import FavoritesView
from ui.detail_view import DetailView
from data_providers import m3u_provider, tmdb_client, xtream_client
from playback.player import Player
from core.config import get_fallback_tmdb_key
try:
    from thefuzz import fuzz, process
    logging.info("Loaded 'thefuzz' library for smart searching.")
    FUZZ_AVAILABLE = True
except ImportError:
    try:
        from fuzzywuzzy import fuzz, process
        logging.info("Loaded fallback 'fuzzywuzzy' library for smart searching.")
        FUZZ_AVAILABLE = True
    except ImportError:
        logging.warning("Smart search library ('thefuzz' or 'fuzzywuzzy') not found!")
        logging.warning("'Fuzzy' search will be skipped for Logo/EPG/TMDb matching.")
        logging.warning("For better results, install 'python3-thefuzz' (Debian/Ubuntu) or 'python3-fuzzywuzzy' (Fedora) package.")
        fuzz = None
        process = None
        FUZZ_AVAILABLE = False
from background import task_manager
from background import image_download_pool
from utils.theme_utils import get_icon_theme_folder
from utils import title_parser
from utils.sleep_inhibitor import SleepInhibitor
from datetime import datetime, timezone, timedelta
from ui.epg_detail_dialog import EPGDetailDialog
from ui.subtitle_dialog import SubtitleDialog
from ui.scheduler_window import SchedulerWindow
from utils.subtitle_manager import SubtitleManager
from ui.image_viewer import ImageViewer
from ui.track_list_view import TrackListView
from ui.collection_grid_view import CollectionGridView
from ui.series_detail_view import SeriesDetailView
from ui.equalizer_window import EqualizerWindow
from ui.catchup_dialog import CatchupDialog
from ui.subtitle_results_dialog import SubtitleResultsDialog
from utils import subtitle_searcher
from data_providers import trakt_client
from core.config import VERSION
from ui.media_info_dialog import MediaInfoDialog
from ui.video_settings_window import VideoSettingsWindow
from ui.podcast_feed_list import PodcastFeedList
from ui.podcast_detail_view import PodcastDetailView
from ui.podcast_episode_list import PodcastEpisodeList
from utils import rss_parser
from ui.temp_playlist_view import TempPlaylistView
from ui.category_manager_dialog import CategoryManagerDialog
import urllib.request

_ = gettext.gettext

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, profile, channels, vod, epg_data, **kwargs):
        super().__init__(**kwargs)
        self.profile = kwargs.get("profile")
        self.set_title(_("Eng Player"))
        self.set_default_size(1100, 700)
        self.active_media_type = "video"
        self.is_immersive_fullscreen = False
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_box)
        self.toast_overlay = Adw.ToastOverlay()
        self.player = Player()
        self.video_settings_win = None
        self.inhibitor = SleepInhibitor(self.get_application())
        self.subtitle_delay_ms = 0
        self.all_channels_map = {}
        self.active_recorder = None
        self.current_playing_channel_data = None
        self.slider_visibility_determined = False
        self.slider_check_attempts = 0
        self.slider_range_is_set = False
        self.current_channels_in_view = []
        self.metadata_fetch_queue = set()
        self.playback_start_timer = None
        self.stream_has_started = False
        self.equalizer_window = None
        self.current_epg_program = None
        self._failed_active_epg_searches = set()
        self.last_epg_check_time = 0
        self.last_save_time = 0
        self.current_playing_media_path = None
        self.seek_on_start = None
        self.is_seeking = False
        self.is_temp_playlist_music = False
        self.startup_volume = 0.8
        self.is_volume_initialized = False
        self.last_slider_position = 0
        self.hide_cursor_timer = None
        self.current_media_type = None
        self.is_stopping_recording = False
        self.last_volume_before_mute = self.startup_volume
        self.series_categories_data = []
        self.vod_categories_data = []
        self.next_episode_timer_id = None
        self.next_episode_prompt_timer_id = None
        self.next_episode_data_to_play = None
        self.auto_play_cancelled = False
        self.is_playing_trailer = False
        self.return_view_after_trailer = None
        self.pip_player = None
        self.pip_window = None
        self.metadata_semaphore = threading.Semaphore(4)
        self.is_scrobble_triggered = False
        self.profile_data = profile
        self.icon_path = profile.get("icon_path", "")
        self.logo_map = self._build_logo_map(self.icon_path)
        self.bouquets_data = channels
        self.vod_data = vod
        self.epg_data = epg_data
        self.trakt_watched_movies = set()
        self.trakt_watched_episodes = set()
        logging.info(f"Converting EPG data ({len(epg_data)} channels) to clean key map...")
        self.epg_clean_map = {self._clean_key(epg_id): programs for epg_id, programs in epg_data.items() if self._clean_key(epg_id)}
        logging.info(f"EPG clean key map created ({len(self.epg_clean_map)} unique keys).")
        logging.debug(f"MainWindow received EPG data for {len(self.epg_data)} channels.")
        self.connect("destroy", self.on_destroy)
        task_manager.connect("scan-finished", self.on_scan_finished)
        self.header = Adw.HeaderBar()
        self.header.set_show_start_title_buttons(False)
        self.header.set_decoration_layout(":minimize,maximize,close")
        root_box.append(self.header)
        self.settings_popover = Gtk.Popover()
        self.settings_popover.add_css_class("settings-popover")
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_propagate_natural_height(True)
        scrolled_window.set_propagate_natural_width(True)
        scrolled_window.set_min_content_height(350)
        scrolled_window.set_max_content_height(600)
        self.settings_popover.set_child(scrolled_window)
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        scrolled_window.set_child(popover_box)
        general_list = Gtk.ListBox()
        general_list.add_css_class("boxed-list")
        popover_box.append(general_list)
        row = Adw.ActionRow(title=_("Set/Change Password"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", lambda x: self.on_set_password_clicked(None))
        general_list.append(row)
        row = Adw.ActionRow(title=_("Set TMDb API Key"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", lambda x: self.on_set_tmdb_api_key_clicked(None))
        general_list.append(row)
        row = Adw.ActionRow(title=_("Set OpenSubtitles API Key"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", lambda x: self.on_set_opensubtitles_api_key_clicked(None))
        general_list.append(row)
        self.trakt_row = Adw.ActionRow(title=_("Connect to Trakt.tv"))
        self.trakt_row.set_activatable(True)
        self.trakt_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self.trakt_row.connect("activated", lambda x: self.on_trakt_login_clicked(None))
        general_list.append(self.trakt_row)
        self.tmdb_switch_row = Adw.SwitchRow(title=_("Use TMDb Metadata"))
        self.tmdb_switch_row.set_active(database.get_use_tmdb_status())
        self.tmdb_switch_row.connect("notify::active", self._on_tmdb_toggle_changed)
        general_list.append(self.tmdb_switch_row)
        self.poster_cache_switch_row = Adw.SwitchRow(title=_("Use Poster Cache"))
        self.poster_cache_switch_row.set_subtitle(_("Saves posters to disk (loads faster)"))
        self.poster_cache_switch_row.set_active(database.get_use_poster_disk_cache_status())
        self.poster_cache_switch_row.connect("notify::active", self._on_poster_cache_toggle_changed)
        general_list.append(self.poster_cache_switch_row)
        theme_row = Adw.ActionRow(title=_("Theme"))
        self.theme_combo = Gtk.ComboBoxText()
        self.theme_combo.append("default", _("System Theme"))
        self.theme_combo.append("force_light", _("Light"))
        self.theme_combo.append("force_dark", _("Dark"))
        saved_theme = database.get_config_value('app_theme')
        if saved_theme == "force_light": self.theme_combo.set_active_id("force_light")
        elif saved_theme == "force_dark": self.theme_combo.set_active_id("force_dark")
        else: self.theme_combo.set_active_id("default")
        self.theme_combo.connect("changed", self._on_theme_combo_changed)
        self.theme_combo.set_valign(Gtk.Align.CENTER)
        theme_row.add_suffix(self.theme_combo)
        general_list.append(theme_row)
        buffer_row = Adw.ActionRow(title=_("Stream Buffer"))
        buffer_row.set_subtitle(_("Playback stability"))
        buffer_row.set_subtitle_lines(0) 
        self.buffer_combo = Gtk.ComboBoxText()
        self.buffer_combo.append("2", _("2s (Low)"))
        self.buffer_combo.append("4", _("4s (Balanced)"))
        self.buffer_combo.append("6", _("6s (Stable)"))
        self.buffer_combo.append("8", _("8s (Max)"))
        saved_buffer = database.get_config_value('stream_buffer_duration')
        if not saved_buffer: saved_buffer = "4"       
        self.buffer_combo.set_active_id(saved_buffer)
        self.buffer_combo.connect("changed", self._on_buffer_combo_changed)
        self.buffer_combo.set_valign(Gtk.Align.CENTER)      
        buffer_row.add_suffix(self.buffer_combo)
        general_list.append(buffer_row)
        row = Adw.ActionRow(title=_("Video Settings"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("emblem-system-symbolic"))
        row.connect("activated", lambda x: self.on_open_video_settings_clicked(None))
        general_list.append(row)
        row = Adw.ActionRow(title=_("Accent Color"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("applications-graphics-symbolic"))
        row.connect("activated", lambda x: self._on_open_color_picker(None))
        general_list.append(row)
        row = Adw.ActionRow(title=_("Manage Hidden Categories"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("view-list-bullet-symbolic"))
        row.connect("activated", lambda x: self.on_open_category_manager(None))
        general_list.append(row)
        popover_box.append(Gtk.Label(label=_("Notifications"), css_classes=["caption-heading"], xalign=0, margin_start=6, margin_top=6))
        notif_list = Gtk.ListBox(); notif_list.add_css_class("boxed-list")
        popover_box.append(notif_list)
        notif_switch_row = Adw.SwitchRow(title=_("Enable Notifications"))
        notif_switch_row.set_active(database.get_notifications_enabled())
        notif_switch_row.connect("notify::active", self._on_notif_toggle_changed)
        notif_list.append(notif_switch_row)       
        duration_row = Adw.ActionRow(title=_("Duration (Seconds)"))
        duration_spin = Gtk.SpinButton.new_with_range(1, 10, 1)
        duration_spin.set_value(database.get_notification_timeout())
        duration_spin.connect("value-changed", self._on_notif_duration_changed)
        duration_spin.set_valign(Gtk.Align.CENTER)
        duration_row.add_suffix(duration_spin)
        notif_list.append(duration_row)
        popover_box.append(Gtk.Label(label=_("System"), css_classes=["caption-heading"], xalign=0, margin_start=6, margin_top=6))
        system_list = Gtk.ListBox(); system_list.add_css_class("boxed-list")
        popover_box.append(system_list)       
        row = Adw.ActionRow(title=_("Change Recordings Folder"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("folder-open-symbolic"))
        row.connect("activated", lambda x: self.on_set_recordings_path_clicked(None))
        system_list.append(row)
        row = Adw.ActionRow(title=_("Change Cache Folder"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("folder-download-symbolic"))
        row.connect("activated", lambda x: self.on_set_cache_path_clicked(None))
        system_list.append(row)      
        row = Adw.ActionRow(title=_("Keyboard Shortcuts"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("input-keyboard-symbolic"))
        row.connect("activated", lambda x: self.on_show_shortcuts_clicked(None))
        system_list.append(row)
        row = Adw.ActionRow(title=_("Clear Cache"))
        row.set_activatable(True)
        row.add_css_class("destructive-action") 
        row.add_suffix(Gtk.Image.new_from_icon_name("user-trash-symbolic"))
        row.connect("activated", lambda x: self.on_clear_cache_clicked(None))
        system_list.append(row)      
        row = Adw.ActionRow(title=_("About EngPlayer"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("help-about-symbolic"))
        row.connect("activated", lambda x: self.on_show_about_clicked(None))
        system_list.append(row)
        theme_folder = get_icon_theme_folder()
        settings_icon_path = os.path.join("resources", "icons", theme_folder, "settings.svg")
        settings_icon = Gtk.Image.new_from_file(settings_icon_path)
        settings_icon.set_pixel_size(24)
        settings_button = Gtk.MenuButton()
        settings_button.set_child(settings_icon)
        settings_button.set_tooltip_text(_("Settings"))
        settings_button.set_popover(self.settings_popover)
        self.settings_popover.set_has_arrow(False)
        settings_button.set_direction(Gtk.ArrowType.DOWN)       
        self.header.pack_start(settings_button)
        scheduler_icon_path = os.path.join("resources", "icons", theme_folder, "calendar.svg")
        scheduler_icon = Gtk.Image.new_from_file(scheduler_icon_path); scheduler_icon.set_pixel_size(24)
        scheduler_button = Gtk.Button(child=scheduler_icon); scheduler_button.set_tooltip_text(_("Recording Scheduler"))
        scheduler_button.connect("clicked", self.on_open_scheduler_clicked); self.header.pack_start(scheduler_button)
        recordings_icon_path = os.path.join("resources", "icons", theme_folder, "folder-videos.svg")
        recordings_icon = Gtk.Image.new_from_file(recordings_icon_path); recordings_icon.set_pixel_size(24)
        recordings_button = Gtk.Button(child=recordings_icon); recordings_button.set_tooltip_text(_("Recorded Videos"))
        recordings_button.connect("clicked", self.on_show_recordings_clicked); self.header.pack_start(recordings_button)
        self.toast_overlay.set_vexpand(True)
        root_box.append(self.toast_overlay)
        main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.toast_overlay.set_child(main_hbox)
        self.nav_rail_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.nav_rail_container.add_css_class("navigation-rail") 
        self.nav_rail_container.set_size_request(60, -1) 
        self.nav_rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=25) 
        self.nav_rail.set_valign(Gtk.Align.CENTER)
        self.nav_rail.set_halign(Gtk.Align.CENTER)
        self.nav_rail.set_vexpand(True)        
        self.nav_rail_container.append(self.nav_rail)
        main_hbox.append(self.nav_rail_container)
        self.sidebar = NavigationSidebar()
        self.sidebar.set_hexpand(False)
        if hasattr(self.sidebar, 'nav_buttons_box'):
            self.sidebar.nav_buttons_box.set_visible(False)
        main_hbox.append(self.sidebar)
        self.main_content_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=200, hexpand=True)
        main_hbox.append(self.main_content_stack)
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.loading_spinner = Gtk.Spinner(); self.loading_spinner.set_size_request(48, 48)
        loading_box.append(self.loading_spinner)
        loading_box.append(Gtk.Label(label=_("Processing channels and VOD content...")))
        self.main_content_stack.add_named(loading_box, "loading_view")
        self.main_content_stack.set_visible_child_name("loading_view")
        self.loading_spinner.start()
        self.top_buttons = {}
        settings = Gtk.Settings.get_default()
        is_dark = settings.props.gtk_application_prefer_dark_theme or "dark" in (settings.props.gtk_theme_name or "").lower()
        target_folder = "dark" if is_dark else "light"      
        logging.info(f"Theme Mode: {target_folder.upper()} (Loading icons from resources/icons/{target_folder})")      
        icon_base_path = os.path.join("resources", "icons", target_folder)
        button_defs = [
            ("iptv", "iptv.svg", "tv-symbolic", _("Live TV")),
            ("favorites", "favorites.svg", "starred-symbolic", _("Favorites")),
            ("vod", "vod.svg", "user-desktop-symbolic", _("VOD")),
            ("series", "series.svg", "view-list-symbolic", _("Series")),
            ("media", "media.svg", "folder-videos-symbolic", _("Local Media"))
        ]
        for name, filename, fallback_icon, tooltip in button_defs:
            full_path = os.path.join(icon_base_path, filename)
            if os.path.exists(full_path):
                try:
                    texture = Gdk.Texture.new_from_filename(full_path)
                    icon = Gtk.Image.new_from_paintable(texture)
                    icon.set_pixel_size(32)
                except Exception as e:
                    logging.error(f"Error loading SVG {filename}: {e}")
                    icon = Gtk.Image.new_from_icon_name(fallback_icon)
                    icon.set_pixel_size(32)
            else:
                logging.warning(f"Icon not found at: {full_path}")
                icon = Gtk.Image.new_from_icon_name(fallback_icon)
                icon.set_pixel_size(32)
            btn = Gtk.Button(child=icon)
            btn.set_tooltip_text(tooltip)
            btn.add_css_class("nav-icon-button") 
            btn.set_cursor(Gdk.Cursor.new_from_name("pointer", None))           
            btn.connect("clicked", self.on_nav_button_clicked, name)
            self.top_buttons[name] = btn
            self.nav_rail.append(btn)
        profile_filename = "user-switch.svg"
        profile_full_path = os.path.join(icon_base_path, profile_filename)       
        if os.path.exists(profile_full_path):
            try:
                texture = Gdk.Texture.new_from_filename(profile_full_path)
                p_icon = Gtk.Image.new_from_paintable(texture)
                p_icon.set_pixel_size(32)
            except Exception as e:
                logging.error(f"Error loading SVG {profile_filename}: {e}")
                p_icon = Gtk.Image.new_from_icon_name("system-users-symbolic")
                p_icon.set_pixel_size(32)
        else:
            p_icon = Gtk.Image.new_from_icon_name("system-users-symbolic")
            p_icon.set_pixel_size(32)
        profile_btn = Gtk.Button(child=p_icon)
        profile_btn.set_tooltip_text(_("Switch Profile"))
        profile_btn.add_css_class("nav-icon-button") 
        profile_btn.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
        profile_btn.connect("clicked", self.on_switch_profile_clicked)
        self.nav_rail.append(profile_btn)
        self.top_buttons["iptv"].add_css_class("active-nav-icon")
        self.iptv_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=300)
        self.bouquet_list = BouquetList(); self.channel_list = ChannelList()
        self.iptv_stack.add_titled(self.bouquet_list, "bouquets", "Bouquet List")
        self.iptv_stack.add_titled(self.channel_list, "channels", "Channel List")
        self.sidebar.list_stack.add_titled(self.iptv_stack, "iptv", "IPTV")
        self.favorites_view = FavoritesView(self.all_channels_map, self.toast_overlay)
        self.favorites_view.connect("playlist-selected", self.on_favorites_playlist_selected)
        self.sidebar.list_stack.add_titled(self.favorites_view, "favorites", "Favorites")
        self.vod_category_list = BouquetList()
        self.sidebar.list_stack.add_titled(self.vod_category_list, "vod", "VOD")
        self.media_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, transition_duration=300)
        self.media_sidebar = MediaLibrarySidebar()
        self.media_stack.add_titled(self.media_sidebar, "sidebar", "Media Sidebar")
        self.track_list_view = TrackListView()
        self.media_stack.add_titled(self.track_list_view, "tracks", "Track List")
        self.podcast_feed_list = PodcastFeedList()
        self.podcast_detail_view = PodcastDetailView()
        self.podcast_detail_view.connect("episode-clicked", self.on_podcast_episode_clicked)
        self.main_content_stack.add_named(self.podcast_detail_view, "podcast_detail_view")
        self.podcast_feed_list.connect("back-clicked", self.on_podcast_list_back_clicked)
        self.podcast_feed_list.connect("podcast-selected", self.on_podcast_feed_selected)
        self.podcast_feed_list.connect("podcast-right-clicked", self.on_podcast_list_right_clicked)
        self.media_stack.add_titled(self.podcast_feed_list, "podcasts_list", "Podcast List")
        self.podcast_episode_list = PodcastEpisodeList()
        self.podcast_episode_list.connect("back-clicked", self.on_episode_list_back_clicked)
        self.podcast_episode_list.connect("episode-selected", self.on_episode_playing_requested)
        self.media_stack.add_titled(self.podcast_episode_list, "podcast_episodes", "Episodes")
        self.sidebar.list_stack.add_titled(self.media_stack, "media", "Media")
        self.series_sidebar = BouquetList()
        self.series_sidebar.show_locked_button.set_visible(False)
        self.series_sidebar.bouquet_listbox.connect("row-activated", self.on_series_category_selected)
        self.sidebar.list_stack.add_titled(self.series_sidebar, "series", "Series")
        self.temp_playlist_view = TempPlaylistView()
        self.temp_playlist_view.connect("channel-selected", self.on_temp_channel_selected)
        self.temp_playlist_view.connect("close-clicked", self.on_temp_playlist_closed)
        self.sidebar.list_stack.add_named(self.temp_playlist_view, "temp_list")
        self.video_view = VideoView(); self.video_view.set_paintable(self.player.paintable)
        self.main_content_stack.add_titled(self.video_view, "player_view", "Player")
        self.video_view.controls.time_label_current.set_width_chars(8)
        self.video_view.controls.time_label_current.set_xalign(1.0)
        self.video_view.controls.time_label_duration.set_width_chars(8)
        self.video_view.controls.time_label_duration.set_xalign(0.0)
        self.media_grid_view = MediaGridView()
        self.media_grid_view.connect("population-finished", self.on_media_grid_populated)
        self.media_grid_view.connect("item-watched-toggled", self.on_media_item_watched_toggled)
        self.back_button_box = Gtk.Box(halign=Gtk.Align.START, margin_start=12, margin_top=6)
        back_button = Gtk.Button(label=_("Back to Collections"), icon_name="go-previous-symbolic")
        back_button.connect("clicked", self.on_back_to_collections_clicked)
        self.back_button_box.append(back_button)
        self.back_button_box.set_visible(False)
        library_view_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        library_view_container.append(self.back_button_box)
        self.media_search_entry = Gtk.SearchEntry(
            placeholder_text=_("Search media library..."),
            margin_start=12,
            margin_end=12,
            margin_top=6
        )
        self.media_search_entry.connect("search-changed", self._on_media_search_changed)
        library_view_container.append(self.media_search_entry)
        library_view_container.append(self.media_grid_view)
        self.main_content_stack.add_titled(library_view_container, "library_view", "Library")
        self.collection_grid_view = CollectionGridView()
        self.main_content_stack.add_named(self.collection_grid_view, "collection_view")
        self.collection_grid_view.connect("collection-activated", self.on_collection_selected)
        self.series_view_placeholder = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER
        )
        self.series_view_placeholder.append(
            Gtk.Label(label=_("Series feature is under development..."))
        )
        self.main_content_stack.add_named(self.series_view_placeholder, "series_view")
        self.recordings_grid_view = MediaGridView()
        self.recordings_grid_view.connect("item-clicked", self.on_recorded_item_clicked)
        self.recordings_grid_view.connect("item-right-clicked", self.on_recorded_item_right_clicked)
        self.main_content_stack.add_named(self.recordings_grid_view, "recordings_view")
        self.detail_view = DetailView()
        self.main_content_stack.add_titled(self.detail_view, "detail_view", "Details")
        self.series_detail_view = SeriesDetailView()
        self.main_content_stack.add_named(self.series_detail_view, "series_detail_view")
        self.series_detail_view.connect("back-requested", self.on_series_detail_back_requested)
        self.series_detail_view.connect("episode-activated", self.on_episode_activated)
        self.series_detail_view.connect("trailer-requested", self.on_trailer_requested)
        self.image_viewer = ImageViewer()
        self.main_content_stack.add_named(self.image_viewer, "image_viewer_view")
        self.main_content_stack.add_titled(Gtk.Box(), "placeholder_view", "Placeholder")
        self.subtitle_manager = SubtitleManager(self.player, self.video_view.subtitle_label)
        self.bouquet_list.bouquet_listbox.connect("row-activated", self.on_bouquet_selected)
        self.vod_category_list.bouquet_listbox.connect("row-activated", self.on_vod_category_selected)
        self.channel_list.channel_listbox.connect("row-activated", self.on_channel_selected)
        self.favorites_view.get_favorite_channels_list_widget().connect("row-activated", self.on_channel_selected)
        self.favorites_view.connect("favorites-changed", self.on_favorites_changed)
        self.collection_grid_view.connect("collection-right-clicked", self.on_collection_item_right_clicked)
        self.media_grid_view.connect("item-right-clicked", self.on_media_item_right_clicked)
        self.track_list_view.connect("track-right-clicked", self.on_track_item_right_clicked)
        self.media_grid_view.connect("item-clicked", self.on_grid_item_clicked)
        self.media_grid_view.connect("poster-load-failed", self.on_poster_load_failed)
        self.image_viewer.connect("back-requested", self._on_image_viewer_back_requested)
        self.track_list_view.connect("track-activated", self._on_track_activated)
        self.media_sidebar.buttons["add_source"].connect("clicked", self.on_add_source_clicked)
        self.media_sidebar.buttons["refresh_library"].connect("clicked", self.on_refresh_clicked)
        self.media_sidebar.buttons["videos"].connect("clicked", self.on_media_type_selected, "video")
        self.media_sidebar.buttons["pictures"].connect("clicked", self.on_media_type_selected, "picture")
        self.media_sidebar.buttons["music"].connect("clicked", self.on_media_type_selected, "music")
        self.media_sidebar.buttons["podcasts"].connect("clicked", self.on_media_type_selected, "podcasts")
        self.detail_view.connect("play-requested", self.on_detail_view_play_requested)
        self.detail_view.connect("back-requested", self.on_detail_view_back_requested)
        self.detail_view.connect("trailer-requested", self.on_trailer_requested)
        handler_id = self.bouquet_list.show_locked_button.connect("toggled", self._on_show_locked_toggled)
        self.bouquet_list.show_locked_button.handler_block(handler_id)
        initial_show_locked_state = database.get_show_locked_bouquets_status()
        self.bouquet_list.show_locked_button.set_active(initial_show_locked_state)
        self.bouquet_list.show_locked_button.handler_unblock(handler_id)
        vod_handler_id = self.vod_category_list.show_locked_button.connect("toggled", self._on_show_locked_toggled)
        self.vod_category_list.show_locked_button.handler_block(vod_handler_id)
        self.vod_category_list.show_locked_button.set_active(initial_show_locked_state)
        self.vod_category_list.show_locked_button.handler_unblock(vod_handler_id)
        self.video_view.connect("epg-item-activated", self.on_epg_item_activated)
        controls = self.video_view.controls
        controls.buttons["play-pause"].connect("clicked", self.on_play_pause_clicked)
        controls.buttons["equalizer"].connect("clicked", self.on_equalizer_button_clicked)
        controls.connect("record-button-clicked", self.on_record_button_clicked)
        controls.connect("stop-trailer-clicked", self.on_stop_trailer_clicked)
        controls.connect("catch-up-button-clicked", self.on_catch_up_button_clicked)
        controls.buttons["fullscreen"].connect("clicked", self.on_fullscreen_clicked)
        controls.buttons["info"].connect("clicked", self.on_info_button_clicked)
        controls.volume_scale.connect("value-changed", self.on_volume_changed)
        controls.buttons["seek-forward"].connect("clicked", self.on_seek_forward_clicked)
        controls.buttons["seek-backward"].connect("clicked", self.on_seek_backward_clicked)
        controls.connect("seek-value-changed", self.on_seek_requested)
        self.channel_list.connect("pip-requested", self.on_pip_requested)
        self.favorites_view.favorite_channels_list.connect("pip-requested", self.on_pip_requested)
        self.player.connect("tracks-changed", self.on_tracks_changed)
        self.player.connect("about-to-finish", self.on_music_track_finished)
        self.player.connect("playback-error", self.on_playback_error)
        self.player.connect("stream-started", self.on_stream_started)
        self.player.connect("paintable-changed", self.on_paintable_changed)
        self.player.connect("playback-finished", self.on_playback_finished)
        controls.connect("audio-track-selected", self.on_audio_track_selected)
        controls.connect("subtitle-button-clicked", self.on_subtitle_button_clicked)
        self.video_view.next_episode_cancel_button.connect("clicked", self._on_cancel_auto_play_clicked)
        self.video_view.next_episode_skip_button.connect("clicked", self._on_skip_to_next_episode_clicked)
        self.current_subtitle_track = -1
        self.subtitles_visible = False
        self.is_external_subtitle_active = False
        self.last_selected_embedded_track = 0
        startup_volume = 0.8
        controls = self.video_view.controls
        controls.volume_scale.set_value(self.startup_volume)
        GLib.timeout_add(200, self._update_stream_info)
        thread = threading.Thread(target=self._process_data_thread, daemon=True)
        thread.start()
        self.video_view.connect("video-area-clicked", self._on_video_area_clicked)
        self.video_view.fullscreen_channel_list.connect("back-clicked", self.on_fullscreen_back_clicked)
        self.video_view.fullscreen_channel_list.channel_listbox.connect("row-activated", self.on_fullscreen_list_item_activated)
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)
        motion_controller = Gtk.EventControllerMotion()       
        motion_controller.connect("motion", self._on_mouse_motion_for_cursor)
        self.add_controller(motion_controller)
        saved_color = database.get_config_value("app_accent_color")
        default_color = "#3584e4"
        self.apply_accent_color(saved_color if saved_color else default_color)

    def on_back_to_collections_clicked(self, button):
        self.main_content_stack.set_visible_child_name("collection_view")
        self.back_button_box.set_visible(False)
        self.media_search_entry.set_text("")

    def on_collection_selected(self, grid_view, collection_item):
        library_id = collection_item.props.db_id
        library_name = collection_item.props.name
        library_type = collection_item.props.type
        logging.info(f"Collection '{library_name}' (ID: {library_id}, Type: {library_type}) selected.")
        self.media_search_entry.set_text("")
        if library_type == "music":
            albums = database.get_albums_by_library_id(library_id)
            self.media_grid_view.populate_async(albums, media_type="music")
        else:
            media_files = database.get_media_files_by_library_id(library_id)
            self.media_grid_view.populate_async(media_files, media_type=library_type)
        self.main_content_stack.set_visible_child_name("library_view")
        self.back_button_box.set_visible(True)

    def on_media_type_selected(self, button, media_type):
        self.image_viewer.stop_all_activity()
        self.player.pause()
        if media_type == "podcasts":
            for btn in self.media_sidebar.buttons.values():
                btn.remove_css_class("active-nav-button")
            button.add_css_class("active-nav-button")
            podcasts = database.get_all_podcasts()
            self.podcast_feed_list.populate(podcasts)
            self.media_stack.set_visible_child_name("podcasts_list")
            self.main_content_stack.set_visible_child_name("placeholder_view")
            self.active_media_type = "podcasts"
            return 
        for btn in self.media_sidebar.buttons.values():
            btn.remove_css_class("active-nav-button")
        button.add_css_class("active-nav-button")
        self.active_media_type = media_type
        libraries = database.get_libraries_by_type(media_type)
        self.collection_grid_view.populate_collections(libraries)
        self.main_content_stack.set_visible_child_name("collection_view")
        self.back_button_box.set_visible(False)

    def on_nav_button_clicked(self, button, view_name):
        self.image_viewer.stop_all_activity()
        if view_name != "iptv":
            self.current_channels_in_view = []
        for btn in self.top_buttons.values():
            btn.remove_css_class("active-nav-icon")
        button.add_css_class("active-nav-icon")
        self.player.pause()
        self.sidebar.list_stack.set_visible_child_name(view_name)
        try:
            self.bouquet_list.search_entry.set_text("")
            self.channel_list.search_entry.set_text("")
            self.favorites_view.fav_list_search_entry.set_text("")
            self.favorites_view.favorite_channels_list.search_entry.set_text("")
            self.vod_category_list.search_entry.set_text("")
            self.series_sidebar.search_entry.set_text("")
            self.media_search_entry.set_text("")
            if view_name not in ["vod", "series", "media"]:
                 self.media_search_entry.set_text("")
        except AttributeError as e:
            logging.warning(f"Error while clearing search box (might be normal): {e}")
        if view_name != "iptv":
            self.bouquet_list.search_entry.set_text("")
            self.channel_list.search_entry.set_text("")
        if view_name != "favorites":
            self.favorites_view.fav_list_search_entry.set_text("")
            self.favorites_view.favorite_channels_list.search_entry.set_text("")
        if view_name not in ["vod", "series", "media"]:
            self.media_search_entry.set_text("")
        if view_name == "iptv":
            self.main_content_stack.set_visible_child_name("placeholder_view")
            self.iptv_stack.set_visible_child_name("bouquets")
        elif view_name == "favorites":
            self.main_content_stack.set_visible_child_name("placeholder_view")
            self.favorites_view.refresh_lists()
            self.favorites_view.reset_view()
        elif view_name == "media":
            self.main_content_stack.set_visible_child_name("collection_view")
            self.media_stack.set_visible_child_name("sidebar")
            for btn in self.media_sidebar.buttons.values():
                btn.remove_css_class("active-nav-button")               
            self.collection_grid_view.populate_collections([])
        elif view_name == "series":
            self.sidebar.list_stack.set_visible_child_name("series")
            self.main_content_stack.set_visible_child_name("series_view")
            if self.profile_data.get("type") != "xtream":
                self.series_view_placeholder.get_first_child().set_text(
                    _("This feature is only available for Xtream Codes profiles.")
                )
                return
            self.series_view_placeholder.get_first_child().set_text(
                _("Fetching series categories...")
            )
            thread = threading.Thread(
                target=self._fetch_series_categories_thread,
                daemon=True
            )
            thread.start()
        elif view_name == "vod":
            self.sidebar.list_stack.set_visible_child_name("vod")
            self.main_content_stack.set_visible_child_name("placeholder_view")
            self.media_grid_view.clear()
            data_shown = False
            hidden_bouquets = database.get_hidden_bouquets()           
            if self.vod_data:
                logging.info("VOD data found in cache/memory. Populating from local data...")
                category_names = [c for c in self.vod_data.keys() if c not in hidden_bouquets]
                self.vod_category_list.populate_bouquets_async(category_names)
                data_shown = True          
            if self.profile_data.get("type") == "xtream":
                logging.info("Xtream profile detected. Fetching fresh VOD categories from API...")
                thread = threading.Thread(
                    target=self._fetch_vod_categories_thread,
                    daemon=True
                )
                thread.start()
            elif not data_shown:
                self.show_toast(_("No VOD categories found."))
        else:
            self.main_content_stack.set_visible_child_name("placeholder_view")

    def on_music_track_finished(self, player):
        if self.current_media_type != 'music':
            return
        GLib.idle_add(self.play_next_track)

    def play_next_track(self):
        if self.media_stack.get_visible_child_name() == "podcast_episodes":
            listbox = self.podcast_episode_list.listbox
            selected_row = listbox.get_selected_row()
            if not selected_row: return           
            current_index = selected_row.get_index()
            next_row = listbox.get_row_at_index(current_index + 1)          
            if next_row:
                listbox.select_row(next_row)
                url = getattr(next_row, "audio_url", None)
                title = getattr(next_row, "title", "Unknown Episode")
                if url:
                    self._start_playback(url=url, media_type='music', channel_data={'name': title})
            else:
                self.show_toast(_("End of podcast list."))
            return
        listbox = self.track_list_view.track_listbox
        all_tracks = self.track_list_view.current_tracks
        if not all_tracks:
            return
        selected_row = listbox.get_selected_row()
        current_index = -1
        if selected_row:
            current_index = selected_row.get_index()
        next_index = (current_index + 1) % len(all_tracks)
        next_track_data = all_tracks[next_index]
        next_row = listbox.get_row_at_index(next_index)
        if next_row:
            listbox.select_row(next_row)
        self._on_track_activated(None, next_track_data)

    def on_paintable_changed(self, player, new_paintable):
        """Connects the new video surface from the player to the UI."""
        self.video_view.set_paintable(new_paintable)

    def play_previous_track(self):
        if self.media_stack.get_visible_child_name() == "podcast_episodes":
            listbox = self.podcast_episode_list.listbox
            selected_row = listbox.get_selected_row()
            if not selected_row: return           
            current_index = selected_row.get_index()
            if current_index > 0:
                prev_row = listbox.get_row_at_index(current_index - 1)
                if prev_row:
                    listbox.select_row(prev_row)
                    url = getattr(prev_row, "audio_url", None)
                    title = getattr(prev_row, "title", "Unknown Episode")
                    if url:
                        self._start_playback(url=url, media_type='music', channel_data={'name': title})
            return
        listbox = self.track_list_view.track_listbox
        all_tracks = self.track_list_view.current_tracks
        if not all_tracks:
            return
        selected_row = listbox.get_selected_row()
        current_index = 0
        if selected_row:
            current_index = selected_row.get_index()
        next_index = (current_index - 1 + len(all_tracks)) % len(all_tracks)
        next_track_data = all_tracks[next_index]
        next_row = listbox.get_row_at_index(next_index)
        if next_row:
            listbox.select_row(next_row)
        self._on_track_activated(None, next_track_data)
        
    def _on_buffer_combo_changed(self, combo):
        value = combo.get_active_id()
        if value:
            database.set_config_value('stream_buffer_duration', value)
            logging.info(f"User changed buffer duration to: {value}s")
            self.show_toast(_("Buffer set to {} seconds. Change takes effect on next channel.").format(value))
            self.settings_popover.popdown()        

    def on_set_recordings_path_clicked(self, button):
        self.settings_popover.popdown()
        dialog = Gtk.FileChooserDialog(
            title=_("Select Recordings Folder"),
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Select"), Gtk.ResponseType.ACCEPT
        )
        dialog.set_modal(True)
        dialog.connect("response", self.on_recordings_folder_dialog_response)
        dialog.present()

    def on_recordings_folder_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.ACCEPT:
            try:
                gfile = dialog.get_file()
                if gfile:
                    folder_path = gfile.get_path()
                    logging.info(f"New recordings path selected: {folder_path}")
                    database.set_config_value('recordings_path', folder_path)
                    self.show_toast(_("Recordings folder set successfully!"))
            except Exception as e:
                logging.error(f"Error setting recordings path: {e}")
        dialog.hide()
        def _safe_destroy():
            dialog.destroy()
            return GLib.SOURCE_REMOVE
        GLib.idle_add(_safe_destroy)

    def on_set_cache_path_clicked(self, button):
        self.settings_popover.popdown()
        dialog = Gtk.FileChooserDialog(
            title=_("Select Cache Folder"),
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Select"), Gtk.ResponseType.ACCEPT
        )
        dialog.set_modal(True)
        dialog.connect("response", self.on_cache_folder_dialog_response)
        dialog.present()

    def on_cache_folder_dialog_response(self, dialog, response_id):
        target_path = None
        should_move = False
        if response_id == Gtk.ResponseType.ACCEPT:
            try:
                gfile = dialog.get_file()
                if gfile:
                    selected_folder_path = gfile.get_path()
                    old_path = database.get_cache_path()
                    old_folder_name = os.path.basename(old_path)
                    new_path = os.path.join(selected_folder_path, old_folder_name)
                    if old_path == new_path:
                        self.show_toast(_("This is already the current cache location."))
                    elif os.path.exists(new_path):
                        self.show_toast(_("Error: A '{}' folder already exists at the destination!").format(old_folder_name))
                    else:
                        target_path = new_path
                        should_move = True
                        logging.info(f"Cache move initiated: {old_path} -> {new_path}")
            except Exception as e:
                logging.error(f"Error processing cache path selection: {e}")
                self.show_toast(_("Error: Could not set cache folder!"))
        dialog.hide()
        def _safe_destroy():
            dialog.destroy()
            return GLib.SOURCE_REMOVE
        GLib.idle_add(_safe_destroy)
        if should_move and target_path:
            old_path = database.get_cache_path()
            self.show_toast(_("Moving cache... This might take a moment."))
            self.get_root().set_sensitive(False)
            thread = threading.Thread(
                target=self._move_cache_thread,
                args=(old_path, target_path),
                daemon=True
            )
            thread.start()

    def on_seek_forward_clicked(self, button):
        if self.current_media_type == 'music':
            self.play_next_track()
        else:
            self.player.seek_forward()

    def on_seek_backward_clicked(self, button):
        if self.current_media_type == 'music':
            self.play_previous_track()
        else:
            self.player.seek_backward()           

    def _start_playback(self, url, media_type, channel_data=None, start_position=None, episode_data=None, is_trailer=False, correct_logo_path=None):
        """
        Starts playback for the given URL and media type.
        Stores playback info for subtitle search etc.
        """
        self._hide_next_episode_prompt()
        self.auto_play_cancelled = False
        self.is_scrobble_triggered = False
        self.last_slider_position = 0
        self.next_episode_data_to_play = None
        self.retry_count = 0
        controls = self.video_view.controls
        self.subtitle_delay_ms = 0
        self.current_playing_info = {
            "title": None,
            "year": None,
            "tmdb_id": None,
            "key_for_db": None
        }
        self.currently_playing_episode_data = None
        if episode_data:
            logging.debug(f"TV episode detected, setting metadata for subtitle search: {episode_data.get('id')}")
            self.currently_playing_episode_data = episode_data
            temp_title = None
            temp_year = None
            temp_tmdb_id = None
            ep_tmdb_id_str = episode_data.get('tmdb') or episode_data.get('tmdb_id')
            if ep_tmdb_id_str:
                try:
                    temp_tmdb_id = int(ep_tmdb_id_str)
                    logging.info(f"Found episode's own TMDb ID: {temp_tmdb_id}")
                except (ValueError, TypeError):
                    pass
            if not temp_tmdb_id:
                ep_title_from_data = episode_data.get('title', "")
                try: season_num = int(episode_data.get('season', 0))
                except (ValueError, TypeError): season_num = 0
                try: ep_num = int(episode_data.get('episode_num', 0))
                except (ValueError, TypeError): ep_num = 0
                season_ep_str = f"S{season_num:02d}E{ep_num:02d}"
                clean_series_title = ""
                try:
                    clean_series_title = self.series_detail_view.clean_tmdb_title or ""
                    if not clean_series_title:
                         clean_series_title = self.series_detail_view.title_label.get_text().split(' (')[0].strip()
                    if " - " in clean_series_title:
                         parts = clean_series_title.split(" - ", 1)
                         if len(parts) > 1 and len(parts[0]) < 10 and parts[0].isupper():
                              clean_series_title = parts[1].strip()
                except Exception as e:
                    logging.warning(f"Exception while getting clean series title: {e}")
                    pass
                temp_title = f"{clean_series_title} {season_ep_str}"
                if ep_title_from_data and clean_series_title and clean_series_title.lower() not in ep_title_from_data.lower():
                    temp_title = f"{temp_title} {ep_title_from_data}"
                temp_title = temp_title.strip()
                logging.info(f"TMDb ID not found for episode, constructed search title: {temp_title}")
            try:
                release_date_str = self.series_detail_view.release_date_label.get_text()
                year_match = re.search(r'(\d{4})', release_date_str)
                if year_match:
                    temp_year = year_match.group(1)
            except Exception:
                 pass
            self.current_playing_info["title"] = temp_title
            self.current_playing_info["year"] = temp_year
            self.current_playing_info["tmdb_id"] = temp_tmdb_id
        elif media_type in ['vod', 'media'] and hasattr(self, 'current_media_item') and self.current_media_item:
             item = self.current_media_item
             temp_title = item.props.title
             release_date_str = item.props.provider_release_date
             active_view = self.main_content_stack.get_visible_child()
             if isinstance(active_view, DetailView):
                 tmdb_date = active_view.release_date_label.get_text()
                 if tmdb_date: release_date_str = tmdb_date
             temp_year = None
             if release_date_str:
                 year_match = re.search(r'(\d{4})', release_date_str)
                 if year_match: temp_year = year_match.group(1)
             self.current_playing_info["title"] = temp_title
             self.current_playing_info["year"] = temp_year
        elif channel_data:
             temp_title = None
             temp_year = None
             if media_type == 'music' and isinstance(channel_data, sqlite3.Row):
                try:
                    temp_title = channel_data['album_name']
                except KeyError:
                    logging.warning("Could not find 'album_name' key in sqlite3.Row for music.")
             elif isinstance(channel_data, dict):
                 temp_title = channel_data.get('name')
                 release_date_str = channel_data.get('releaseDate')
                 if release_date_str and len(release_date_str) >= 4:
                     try:
                         temp_year = release_date_str[:4]
                     except:
                         pass
             self.current_playing_info["title"] = temp_title
             self.current_playing_info["year"] = temp_year
        if is_trailer:
            self.current_playing_media_path = None
            logging.info("Trailer playback started, position saving disabled.")
        elif episode_data or media_type in ['media', 'vod']:
            self.current_playing_media_path = url
        elif media_type == 'music' and url.startswith("http"):
             self.current_playing_media_path = url
        else:
            self.current_playing_media_path = None
        controls = self.video_view.controls
        controls.set_stop_trailer_button_visibility(is_trailer)
        db_key = None
        if media_type == 'media':
            db_key = url
        elif media_type == 'iptv' and channel_data:
            db_key = channel_data.get('tvg-id') or url
        elif media_type == 'vod':
            profile_type = self.profile_data.get("type")
            if profile_type == "xtream":
                potential_id = url.split('/')[-1].split('.')[0]
                if potential_id.isdigit():
                    db_key = potential_id
                else:
                    db_key = url
            else:
                db_key = url
        elif media_type == 'music':
             db_key = url
        self.current_playing_info["key_for_db"] = db_key
        logging.debug(f"Database key for playback determined: {db_key}")
        if not episode_data:
            temp_title = self.current_playing_info["title"]
            temp_year = self.current_playing_info["year"]
            if temp_title:
                match = re.search(r'(.*?)\s*\((\d{4})\)', temp_title)
                if match:
                    self.current_playing_info["title"] = match.group(1).strip()
                    if not temp_year: temp_year = match.group(2)
                else:
                    self.current_playing_info["title"] = temp_title
            self.current_playing_info["year"] = temp_year
        if db_key and self.current_playing_info["tmdb_id"] is None:
             db_data = database.get_metadata(db_key)
             if db_data:
                 tmdb_id_val = None
                 try:
                     if 'tmdb_id' in db_data.keys(): tmdb_id_val = db_data['tmdb_id']
                     elif 'id' in db_data.keys(): tmdb_id_val = db_data['id']
                     if tmdb_id_val:
                          self.current_playing_info["tmdb_id"] = int(tmdb_id_val)
                 except (ValueError, TypeError, KeyError) as e:
                      logging.warning(f"Error getting TMDb ID from DB (key: {db_key}): {e}")
        logging.debug(f"Current Playing Info Set: {self.current_playing_info}")
        controls.time_label_current.set_text("0:00:00")
        controls.time_label_duration.set_text("0:00:00")
        controls.progress_slider.set_range(0, 1)
        controls.progress_slider.set_value(0)
        self.slider_range_is_set = False
        self.is_volume_initialized = False
        if self.playback_start_timer:
            GLib.source_remove(self.playback_start_timer)
            self.playback_start_timer = None
        self.seek_on_start = start_position
        if db_key and not is_trailer:
            self.current_playing_media_path = db_key
            logging.debug(f"Watch progress key (current_playing_media_path) set to: {self.current_playing_media_path}")
        else:
            self.current_playing_media_path = None
        self.stream_has_started = False
        self.playback_start_timer = GLib.timeout_add_seconds(10, self._on_playback_timeout)
        logging.info(f"Playback starting. Setting current_media_type to: '{media_type}'")
        self.current_media_type = media_type
        final_url = url
        if os.path.isabs(url) and not url.startswith("file://"):
            try:
                gfile = Gio.File.new_for_path(url)
                final_url = gfile.get_uri()
                logging.debug(f"Local file path converted to URI: {final_url}")
            except Exception as e:
                 logging.error(f"Could not convert local file path to URI: {e}, using original path.")
                 final_url = f"file://{os.path.abspath(url)}"
        self.player.play_url(final_url, media_type=media_type)
        if media_type == 'music':
            self.player.enable_equalizer()
        else:
            self.player.disable_equalizer()
        self.slider_visibility_determined = False
        self.slider_range_is_set = False
        self.slider_check_attempts = 0
        self.current_playing_channel_data = channel_data
        self.subtitle_manager.clear()
        self.inhibitor.inhibit()
        self.player.set_subtitle_track(-1)
        self.current_subtitle_track = -1
        self.is_external_subtitle_active = False
        controls = self.video_view.controls
        VIDEO_FLAG, AUDIO_FLAG, TEXT_FLAG, VIS_FLAG = 1, 2, 4, 8
        base_flags = AUDIO_FLAG
        if media_type == 'music':
            final_flags = base_flags | VIDEO_FLAG | VIS_FLAG
            self.video_view.set_mode('video')
            controls.set_mode('audio')
            self.video_view.set_epg_visibility(False)
            controls.set_button_visibility("record", False)
            controls.set_seek_controls_visibility(True)
            controls.set_button_visibility("equalizer", True)
            controls.set_catchup_button_visibility(False)
            album_art_path_found = None
            if channel_data:
                if isinstance(channel_data, sqlite3.Row):
                    try:
                        if 'album_art_path' in channel_data.keys():
                             album_art_path_found = channel_data['album_art_path']
                    except KeyError:
                        pass
                elif isinstance(channel_data, dict):
                    album_art_path_found = channel_data.get('album_art_path')
            if album_art_path_found:
                controls.set_channel_icon_visibility(True)
                controls.update_channel_icon(album_art_path_found)
            else:
                controls.set_channel_icon_visibility(False)
        else:
            final_flags = base_flags | VIDEO_FLAG
            self.video_view.set_mode('video')
            controls.set_mode('video')
            controls.set_button_visibility("equalizer", False)
            is_iptv = (media_type == 'iptv')
            should_show_epg_panel = is_iptv and not self.is_immersive_fullscreen
            self.video_view.set_epg_visibility(should_show_epg_panel)
            controls.set_channel_icon_visibility(is_iptv)
            controls.set_button_visibility("record", is_iptv)
            controls.set_seek_controls_visibility(not is_iptv)
            if is_iptv and channel_data:
                logo_to_use = correct_logo_path
                if not logo_to_use and hasattr(self, 'logo_map') and self.logo_map:
                    logo_to_use = self.channel_list._find_logo_path(channel_data, self.logo_map)
                if not logo_to_use:
                    logo_to_use = channel_data.get("logo")
                controls.update_channel_icon(logo_to_use)
                self._update_epg_for_channel(channel_data)
            else:
                self.video_view.update_epg([])
                if not is_iptv:
                     controls.update_channel_icon(None)
            if is_iptv and channel_data:
                try:
                    archive_duration_str = channel_data.get("tv_archive_duration")
                    if channel_data.get("tv_archive") == "1" and archive_duration_str:
                        self.current_channel_archive_duration = int(archive_duration_str)
                        controls.set_catchup_button_visibility(True)
                    else:
                        self.current_channel_archive_duration = 0
                        controls.set_catchup_button_visibility(False)
                except Exception as e:
                    logging.warning(f"Error processing catch-up info: {e}")
                    self.current_channel_archive_duration = 0
                    controls.set_catchup_button_visibility(False)
            else:
                 self.current_channel_archive_duration = 0
                 controls.set_catchup_button_visibility(False)
        if self.player.player:
             self.player.player.set_property("flags", final_flags)
        if episode_data:
            self.currently_playing_episode_data = episode_data
            logging.debug(f"Playing TV episode, data stored: {episode_data.get('id')}")
        else:
            self.currently_playing_episode_data = None
        self.main_content_stack.set_visible_child_name("player_view")
        self.video_view.controls.set_playing_state(True)
        self.player.play()

    def on_playback_finished(self, player):
        logging.debug("on_playback_finished called.")
        if self.current_media_type == 'iptv':
            MAX_RETRIES = 12           
            if self.retry_count < MAX_RETRIES:
                self.retry_count += 1
                logging.warning(f"IPTV Stream finished unexpectedly. Retry attempt {self.retry_count}/{MAX_RETRIES}...")               
                if self.current_playing_channel_data:
                    url = self.current_playing_channel_data.get('url')
                    if url:
                        if self.retry_count == 1:
                            self.show_toast(_("Connection lost. Reconnecting..."), duration=20)
                        self.player.play_url(url, media_type='iptv')
                        self.player.play()
                        return 
            else:
                logging.error("Max retries reached. Stopping playback.")
                self.show_toast(_("Connection failed. Stream cancelled."))
                if self.playback_start_timer:
                     GLib.source_remove(self.playback_start_timer)
                     self.playback_start_timer = None               
                self.video_view.controls.set_playing_state(False)
                return
        if self.current_media_type == 'music':
            logging.info("Music track finished (EOS). Calling play_next_track.")
            path_to_mark = self.current_playing_media_path
            if path_to_mark and path_to_mark.startswith("http"):
                logging.info(f"Marking Podcast '{path_to_mark}' as finished (is_finished=1).")
                database.save_playback_progress(
                    path_to_mark,
                    position=0,
                    is_finished=1
                )
            GLib.idle_add(self.play_next_track)
            self.video_view.controls.set_playing_state(False)
            self.inhibitor.uninhibit()
            self.currently_playing_episode_data = None
            self.current_playing_media_path = None
            self._hide_next_episode_prompt()
            self.auto_play_cancelled = False
            self.next_episode_data_to_play = None
            return
        if self.is_scrobble_triggered:
            logging.debug("Content was already marked as 'watched' at 90%. Skipping EOS (end of stream) scrobble.")
            if self.currently_playing_episode_data and not self.auto_play_cancelled and self.next_episode_data_to_play:
                 logging.info("Autoplay active, starting next episode (EOS after 90%).")
                 self.play_next_series_episode(self.next_episode_data_to_play)
            else:
                 self.video_view.controls.set_playing_state(False)
                 self.inhibitor.uninhibit()
            self.currently_playing_episode_data = None
            self.current_playing_media_path = None
            self._hide_next_episode_prompt()
            self.auto_play_cancelled = False
            self.next_episode_data_to_play = None
            return
        if self.is_playing_trailer:
            logging.info("Trailer finished playing. Returning to detail view.")
            self.player.shutdown()
            self.is_playing_trailer = False
            controls = self.video_view.controls
            controls.set_stop_trailer_button_visibility(False)
            self.inhibitor.uninhibit()
            if self.return_view_after_trailer:
                self.main_content_stack.set_visible_child_name(self.return_view_after_trailer)
            else:
                self.main_content_stack.set_visible_child_name("placeholder_view")
            self.return_view_after_trailer = None
            return
        finished_episode_data = self.currently_playing_episode_data
        media_path_to_clear = self.current_playing_media_path
        tmdb_id_for_movie = self.current_playing_info.get('tmdb_id')
        self.currently_playing_episode_data = None
        self.current_playing_media_path = None
        self._hide_next_episode_prompt()
        if finished_episode_data:
            logging.info(f"Finished media is a TV episode: {finished_episode_data.get('id')}")
            if not self.auto_play_cancelled and self.next_episode_data_to_play:
                logging.info("Autoplay active, starting next episode (EOS).")
                self.play_next_series_episode(self.next_episode_data_to_play)
            elif self.auto_play_cancelled:
                logging.info("Autoplay was cancelled by user (EOS).")
                self.player.pause()
                self.video_view.controls.set_playing_state(False)
            else:
                logging.info("Next episode data not found or prompt was not shown (EOS).")
                self.show_toast(
                    _("Last episode of the season finished.")
                )
                self.player.pause()
                self.video_view.controls.set_playing_state(False)
            self.auto_play_cancelled = False
            self.next_episode_data_to_play = None
            if media_path_to_clear:
                logging.info(f"Marking TV episode '{media_path_to_clear}' as finished (is_finished=1).")
                database.save_playback_progress(
                    media_path_to_clear,
                    position=0,
                    is_finished=1
                )
            try:
                tmdb_id_to_scrobble = finished_episode_data.get('tmdb') or finished_episode_data.get('tmdb_id')
                if tmdb_id_to_scrobble:
                    logging.info(f"Trakt: TV episode finished, adding to history (TMDb ID: {tmdb_id_to_scrobble}).")
                    thread = threading.Thread(target=trakt_client.add_to_history,
                                              args=(tmdb_id_to_scrobble, 'episode'),
                                              daemon=True)
                    thread.start()
            except Exception as e:
                logging.warning(f"Error starting Trakt scrobble (episode): {e}")
            return
        if media_path_to_clear:
            logging.info(f"Marking VOD/Media '{media_path_to_clear}' as finished (is_finished=1).")
            database.save_playback_progress(
                media_path_to_clear,
                position=0,
                is_finished=1
            )
            try:
                if tmdb_id_for_movie:
                    logging.info(f"Trakt: Movie finished, adding to history (TMDb ID: {tmdb_id_for_movie}).")
                    thread = threading.Thread(target=trakt_client.add_to_history,
                                              args=(tmdb_id_for_movie, 'movie'),
                                              daemon=True)
                    thread.start()
                else:
                     logging.warning("Trakt: Movie finished but TMDb ID not found for scrobble.")
            except Exception as e:
                logging.warning(f"Error starting Trakt scrobble (movie): {e}")
        self.video_view.controls.set_playing_state(False)
        self.inhibitor.uninhibit()
        current_page = self.main_content_stack.get_visible_child_name()
        if current_page == "series_detail_view":
             self.series_detail_view.refresh_current_season()

    def _find_next_episode(self, current_episode_data):
        """
        Finds the next episode in the list based on the given episode data.
        Searches for the next episode in the same season.
        Returns: Next episode's data (dict) or None.
        """
        if not current_episode_data or not hasattr(self, 'series_detail_view'):
            return None
        all_episodes_in_season_dict = self.series_detail_view.episodes_data
        current_season_num_str = str(current_episode_data.get('season'))
        if not current_season_num_str or current_season_num_str not in all_episodes_in_season_dict:
            logging.warning("Could not find next episode: Current season data is missing.")
            return None
        episodes_in_current_season = all_episodes_in_season_dict[current_season_num_str]
        try:
            sorted_episodes = sorted(episodes_in_current_season, key=lambda x: int(x.get('episode_num', 0)))
        except (ValueError, TypeError):
            logging.warning("Could not sort episodes, using original order.")
            sorted_episodes = episodes_in_current_season
        current_episode_id = current_episode_data.get('id')
        current_index = -1
        for i, ep in enumerate(sorted_episodes):
            if ep.get('id') == current_episode_id:
                current_index = i
                break
        if current_index == -1:
            logging.warning("Could not find next episode: Finished episode not found in list.")
            return None
        next_index = current_index + 1
        if next_index < len(sorted_episodes):
            return sorted_episodes[next_index]
        else:
            return None

    def play_next_series_episode(self, next_episode_data):
        """
        Starts playback for the given episode data.
        (Plays directly for now, confirmation will be added later)
        """
        logging.info(f"Playing next episode: S{next_episode_data.get('season')}E{next_episode_data.get('episode_num')}")
        final_url = None
        final_url = next_episode_data.get('direct_source')
        if not final_url:
            episode_stream_id = next_episode_data.get('id') or next_episode_data.get('stream_id')
            container_extension = next_episode_data.get('container_extension')
            if episode_stream_id and container_extension:
                host = self.profile_data.get('host')
                username = self.profile_data.get('username')
                password = self.profile_data.get('password')
                final_url = f"{host}/series/{username}/{password}/{episode_stream_id}.{container_extension}"
            else:
                 logging.error("Could not create URL for next episode (required data missing).")
                 self.show_toast(
                     _("Error: Could not get address for the next episode.")
                 )
                 return
        self._start_playback(url=final_url, media_type='vod', episode_data=next_episode_data)

    def _process_data_thread(self):
        logging.info("Starting to process channel and VOD data in background...")
        if self.bouquets_data:
            for bouquet in self.bouquets_data.values():
                for channel in bouquet: self.all_channels_map[channel['url']] = channel
        if self.vod_data:
            for category in self.vod_data.values():
                 for item in category: self.all_channels_map[item['url']] = item
        logging.info("Data processing finished. Updating UI.")
        GLib.idle_add(self._on_data_processed)

    def _on_data_processed(self):
        logging.info("Populating UI with pre-loaded data...")
        hidden_bouquets = database.get_hidden_bouquets()       
        if self.bouquets_data:
            visible_bouquets = [b for b in self.bouquets_data.keys() if b not in hidden_bouquets]
            self.bouquet_list.populate_bouquets_async(visible_bouquets)            
        self.favorites_view.refresh_lists()
        self.loading_spinner.stop()
        self.main_content_stack.set_visible_child_name("placeholder_view")
        self._start_trakt_sync()
        self.show_toast(_("Channels loaded successfully!"))
        self.on_nav_button_clicked(self.top_buttons["vod"], "vod")
        self.on_nav_button_clicked(self.top_buttons["iptv"], "iptv")

    def _start_trakt_sync(self):
        """
        Fetches watch history from Trakt.tv when the application starts
        and syncs the local library (local media only).
        """
        token = database.get_trakt_token()
        if not token:
            logging.debug("Trakt sync skipped (not logged in).")
            return
        logging.info("Starting background synchronization with Trakt.tv...")
        thread_movies = threading.Thread(target=trakt_client.get_watched_history,
                                          args=('movies', self._on_trakt_movies_fetched),
                                         daemon=True)
        thread_movies.start()
        thread_episodes = threading.Thread(target=trakt_client.get_watched_history,
                                           args=('episodes', self._on_trakt_episodes_fetched),
                                           daemon=True)
        thread_episodes.start()

    def _on_trakt_movies_fetched(self, watched_data, error):
        """(Main Thread) Runs when the watched MOVIE list arrives from Trakt."""
        if error or not watched_data:
            logging.warning(f"Could not get Trakt movie history: {error or 'No data'}")
            return
        try:
            tmdb_id_list = [
                item['movie']['ids']['tmdb']
                for item in watched_data
                 if item.get('movie') and item['movie'].get('ids') and item['movie']['ids'].get('tmdb')
            ]
            if not tmdb_id_list:
                logging.info("Trakt: Watched movie list is empty.")
                return
            self.trakt_watched_movies = {str(tid) for tid in tmdb_id_list}
            logging.info(f"Trakt: {len(self.trakt_watched_movies)} watched movies cached in memory.")    
            logging.info(f"Trakt: {len(tmdb_id_list)} watched movie TMDb IDs found.")
            thread_db_sync = threading.Thread(target=self._sync_trakt_ids_to_db,
                                              args=(tmdb_id_list,),
                                              daemon=True)
            thread_db_sync.start()
        except Exception as e:
            logging.error(f"Error processing Trakt movie data: {e}")

    def _on_trakt_episodes_fetched(self, watched_data, error):
        """(Main Thread) Runs when the watched EPISODE list arrives from Trakt."""
        if error or not watched_data:
            logging.warning(f"Could not get Trakt episode history: {error or 'No data'}")
            return
        try:
            tmdb_id_list = []
            for item in watched_data:
                if item.get('episode') and item['episode'].get('ids') and item['episode']['ids'].get('tmdb'):
                    tmdb_id = item['episode']['ids']['tmdb']
                    tmdb_id_list.append(tmdb_id)           
            if not tmdb_id_list:
                logging.info("Trakt: Watched episode list is empty.")
                return
            self.trakt_watched_episodes = {str(tid) for tid in tmdb_id_list}
            logging.info(f"Trakt: {len(self.trakt_watched_episodes)} watched episodes cached in memory.")
            logging.info(f"Trakt: {len(tmdb_id_list)} watched episode TMDb IDs found.")
            thread_db_sync = threading.Thread(target=self._sync_trakt_ids_to_db, 
                                               args=(tmdb_id_list,), 
                                              daemon=True)
            thread_db_sync.start()
        except Exception as e:
            logging.error(f"Error processing Trakt episode data: {e}")

    def _sync_trakt_ids_to_db(self, tmdb_id_list):
        """
        (Background Thread)
        Takes the TMDb ID list, finds local file paths, and
        updates the profile database as 'watched'.
        """
        logging.debug(f"Trakt DB Sync Thread: Searching for paths for {len(tmdb_id_list)} IDs...")
        paths_to_mark = database.get_paths_for_tmdb_ids(tmdb_id_list)
        if paths_to_mark:
            logging.debug(f"Trakt DB Sync Thread: {len(paths_to_mark)} matching file paths found. Updating Profile DB...")
            database.set_batch_watched_status_by_path(paths_to_mark)
        else:
            logging.debug("Trakt DB Sync Thread: No matching local file paths found.")

    def on_favorites_changed(self, widget):
        if self.iptv_stack.get_visible_child() == self.channel_list and self.current_channels_in_view:
            self.channel_list.populate_channels_async(self.current_channels_in_view)
            
    def on_favorites_playlist_selected(self, view, channels):
        self.current_channels_in_view = channels            

    def on_playback_error(self, player, error_message):
        logging.error(f"Playback Error: {error_message}")
        if self.current_media_type == 'iptv':
             MAX_RETRIES = 12              
             if self.retry_count < MAX_RETRIES:
                 self.retry_count += 1
                 logging.warning(f"IPTV Error detected. Retry attempt {self.retry_count}/{MAX_RETRIES}...")               
                 if self.current_playing_channel_data:
                    url = self.current_playing_channel_data.get('url')
                    if url:
                        if self.retry_count == 1:
                            self.show_toast(_("Connection lost. Reconnecting..."), duration=20)                        
                        def do_secure_retry():
                            saved_count = self.retry_count 
                            self._play_channel(self.current_playing_channel_data)
                            self.retry_count = saved_count
                            logging.debug(f"Retry counter restored to {self.retry_count}")
                            return False 
                        GLib.timeout_add(1500, do_secure_retry)
                        return
             else:
                 logging.error("Max retries reached. Stopping.")
                 self.show_toast(_("Connection failed. Stream cancelled."))                
                 if self.playback_start_timer:
                     GLib.source_remove(self.playback_start_timer)
                     self.playback_start_timer = None
                 self.video_view.controls.set_playing_state(False)
                 GLib.idle_add(self.player.shutdown)
                 return 
        display_message = f"{_('Could not open stream')}: {error_message}"
        self.show_toast(display_message)
        self.video_view.controls.set_playing_state(False)

    def on_stream_started(self, player):
        """Runs when the 'stream started successfully' signal is received from GStreamer."""
        self.retry_count = 0
        logging.info("Stream started successfully, retry counter reset.")
        if hasattr(self, "current_active_toast") and self.current_active_toast:
            try:
                self.current_active_toast.dismiss()
                self.current_active_toast = None
            except:
                pass
        if self.is_seeking:
            self.is_seeking = False
            logging.debug("Stream started after seek, is_seeking flag cleared.")
        if not self.is_volume_initialized:
            self.player.set_volume(self.startup_volume)
            self.is_volume_initialized = True
        self.stream_has_started = True
        if self.playback_start_timer:
            GLib.source_remove(self.playback_start_timer)
            self.playback_start_timer = None
        if self.seek_on_start is not None and self.seek_on_start > 0:
            GLib.timeout_add(100, self._perform_initial_seek)

    def _perform_initial_seek(self):
        """
        Seeks to the start position and resets the seek variable.
        This function is called only once by GLib.timeout_add.
        """
        if self.seek_on_start is not None:
            logging.info(f"Seeking to saved position: {self.seek_on_start} seconds")
            self.player.seek_to_seconds(self.seek_on_start)
            self.seek_on_start = None
        return GLib.SOURCE_REMOVE

    def _on_playback_timeout(self):
        """
        This method runs if the stream does not start within 10 seconds.
        """
        if self.stream_has_started:
            return GLib.SOURCE_REMOVE
        logging.warning("Could not start stream: Timeout!")
        self.player.shutdown()
        self.on_playback_error(None, _("Connection timed out."))
        return GLib.SOURCE_REMOVE

    def on_poster_load_failed(self, grid_view, item):
        if self.media_grid_view.current_media_type == "music":
            return
        if self.media_grid_view.current_media_type in ["vod", "series"]:
            logging.warning(f"Poster failed for VOD/Series '{item.props.title}'. Skipping TMDb fallback to save API quota.")
            return
        if not database.get_use_tmdb_status():
            logging.debug("Poster failed, but TMDb usage is disabled by user.")
            return         
        user_key = database.get_config_value("tmdb_api_key")
        api_key = user_key if user_key else get_fallback_tmdb_key()
        if not api_key:
            logging.debug("No API Key found (User or Fallback). Skipping TMDb search.")
            return
        logging.info(f"Poster for '{item.props.title}' failed to load (Local Media). Trying TMDb fallback.")
        database.clear_metadata_for_path(item.props.path_or_url)
        if item.props.path_or_url not in self.metadata_fetch_queue:
            self.metadata_fetch_queue.add(item.props.path_or_url)
            media_type = self.media_grid_view.current_media_type
            thread = threading.Thread(
                target=self._metadata_fetch_task,
                args=(item, api_key, media_type),
                daemon=True
            )
            thread.start()

    def on_vod_category_selected(self, listbox, row):
        """
        Runs when the user clicks a VOD category in the sidebar.
        Includes security check for locked categories.
        """
        if not row:
            return
        self.vod_category_list.search_entry.set_text("")
        self.player.pause()
        category_name = row.bouquet_name
        password_is_set = database.get_config_value('app_password') is not None
        is_locked = database.get_bouquet_lock_status(category_name)
        if password_is_set and is_locked:
            logging.info(f"Category '{category_name}' is locked. Prompting for password.")
            prompt = PasswordPromptDialog(self)
            prompt.connect("response", self.on_password_prompt_response_vod, category_name)
            prompt.present()
            return
        self._show_vod_category(category_name)

    def on_password_prompt_response_vod(self, dialog, response_id, category_name):
        """Handles the response from the password prompt for a VOD category."""
        if response_id == "ok":
            if database.check_password(dialog.get_password()):
                self._show_vod_category(category_name)
            else:
                self.show_toast(_("Wrong Password!"))

    def _show_vod_category(self, category_name):
        """
        The main function that loads the content after password verification (or if no password is required).
        """
        logging.info(f"VOD category '{category_name}' selected. Populating grid...")
        vod_list_for_category = self.vod_data.get(category_name)
        if vod_list_for_category is not None:
            self.media_search_entry.set_text("")
            self.media_grid_view.populate_async(vod_list_for_category, media_type="vod")
            self.main_content_stack.set_visible_child_name("library_view")
            self.back_button_box.set_visible(False)
            count = len(vod_list_for_category)
            self.show_toast(_("{} VOD items listed.").format(count))
        else:
            logging.error(f"VOD data for category '{category_name}' not found in cache.")
            self.main_content_stack.set_visible_child_name("placeholder_view")
            self.show_toast(_("Error: Data for this category not found in cache."))

    def on_set_tmdb_api_key_clicked(self, button):
        self.settings_popover.popdown()
        dialog = Adw.MessageDialog.new(self, _("Set TMDb API Key"), _("Please enter your TMDb API Key (v3 Auth)."))
        dialog.add_css_class("tmdb-api-dialog"); dialog.set_transient_for(self); dialog.set_modal(True)
        entry = Gtk.Entry()
        current_key = database.get_config_value("tmdb_api_key")
        if current_key:
            masked_key = self._mask_api_key(current_key)
            entry.set_placeholder_text(_("Current: {} (Enter new key to change)").format(masked_key))
        else:
            entry.set_placeholder_text(_("API Key (v3 Auth)"))
        dialog.set_extra_child(entry); dialog.add_response("cancel", _("Cancel")); dialog.add_response("save", _("Save"))
        dialog.set_default_response("save"); dialog.set_close_response("cancel")
        dialog.connect("response", self.on_tmdb_dialog_response, entry); dialog.present()

    def on_tmdb_dialog_response(self, dialog, response_id, entry):
        if response_id == "save":
            api_key = entry.get_text().strip()
            if api_key:
                database.set_config_value("tmdb_api_key", api_key)
                self.show_toast(_("TMDb API Key saved successfully!"))
            else:
                 logging.info("TMDb API Key entry was empty, key not changed.")

    def on_set_opensubtitles_api_key_clicked(self, button):
        """Runs when the 'Set OpenSubtitles API Key' button in the settings menu is clicked."""
        self.settings_popover.popdown()
        dialog = Adw.MessageDialog.new(self, _("Set OpenSubtitles API Key"),
                                       _("Please enter your OpenSubtitles API Key.\nYou can get one from their website after registering."))
        dialog.add_css_class("opensubtitles-api-dialog")
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        entry = Gtk.Entry()
        entry.set_placeholder_text(_("API Key"))
        current_key = database.get_config_value("opensubtitles_api_key")
        if current_key:
            masked_key = self._mask_api_key(current_key)
            entry.set_placeholder_text(_("Current: {} (Enter new key to change)").format(masked_key))
        else:
            entry.set_placeholder_text(_("API Key"))
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("save", _("Save"))
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.connect("response", self.on_opensubtitles_dialog_response, entry)
        dialog.present()

    def on_opensubtitles_dialog_response(self, dialog, response_id, entry):
        """Handles the response from the OpenSubtitles API key dialog."""
        if response_id == "save":
            api_key = entry.get_text().strip()
            if api_key:
                database.set_config_value("opensubtitles_api_key", api_key)
                self.show_toast(
                     _("OpenSubtitles API Key saved successfully!")
                )
            else:
                logging.info("OpenSubtitles API Key entry was empty, key not changed.")

    def _update_trakt_login_button_status(self):
        """
        Checks the Trakt.tv token and updates the state of the 'Log In' / 'Log Out'
        button.
        """
        token = database.get_trakt_token()
        if token:
            self.trakt_row.set_title(_("Disconnect from Trakt.tv"))
        else:
            self.trakt_row.set_title(_("Connect to Trakt.tv"))

    def on_trakt_login_clicked(self, button):
        """Runs when the Trakt.tv Login/Logout button is pressed."""
        self.settings_popover.popdown()
        token = database.get_trakt_token()
        if token:
            database.clear_trakt_token()
            self._update_trakt_login_button_status()
            self.show_toast(_("Logged out from Trakt.tv account."))
            return
        try:
            self.show_toast(_("Opening browser to connect to Trakt.tv..."))
            trakt_client.start_pkce_authentication(self._on_trakt_auth_complete)
        except Exception as e:
            logging.error(f"Could not start Trakt PKCE flow: {e}")
            self.show_toast(_("Error: Authentication could not be initiated."))

    def _on_trakt_auth_complete(self, token_data, error):
        """(Main Thread) Runs when the token retrieval process is complete or an error occurs."""
        if hasattr(self, 'trakt_dialog') and self.trakt_dialog:
            try:
                handler_id = GObject.signal_lookup("response", self.trakt_dialog)
                if handler_id > 0 and GObject.signal_handler_is_connected(self.trakt_dialog, handler_id):
                    GObject.signal_handler_disconnect(self.trakt_dialog, handler_id)
            except Exception as e:
                logging.warning(f"Could not disconnect Trakt dialog signal: {e}")
            self.trakt_dialog.close()
            self.trakt_dialog = None
        if error:
            self.show_toast(_("Login Failed: {}").format(error))
            return
        if token_data:
            self.show_toast(_("Successfully connected to Trakt.tv account!"))
            self._update_trakt_login_button_status()

    def on_set_password_clicked(self, button):
        self.settings_popover.popdown()
        dialog = PasswordDialog(self, self.toast_overlay); dialog.present()

    def on_seek_requested(self, controls, value):
        self.is_seeking = True
        self.player.seek_to_seconds(value)

    def on_record_button_clicked(self, controls):
        if self.is_stopping_recording:
            logging.warning("Recording is already being stopped, no new action.")
            return
        if self.active_recorder:
            logging.info("Stop recording request received...")
            self.is_stopping_recording = True
            record_button = self.video_view.controls.buttons.get("record")
            if record_button:
                record_button.set_sensitive(False)
            self.show_toast(_("Stopping recording... Saving file."))
            recorder_to_stop = self.active_recorder
            stop_thread = threading.Thread(
                 target=recorder_to_stop.stop,
                args=(self._on_recording_stopped,)
            )
            stop_thread.start()
            return
        if not self.current_playing_channel_data:
            self.show_toast(_("No channel found to record!"))
            return
        channel_name = self.current_playing_channel_data.get("name", "recording").replace(" ", "_").replace("/", "-")
        channel_url = self.current_playing_channel_data.get("url")
        recordings_dir = database.get_recordings_path()
        os.makedirs(recordings_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{channel_name}_{timestamp}.mkv"
        output_path = os.path.join(recordings_dir, file_name)
        try:
            self.active_recorder = Recorder(channel_url, output_path)
            self.active_recorder.start()
            self.show_toast(_("Recording started: {}").format(file_name))
            self.video_view.controls.set_recording_state(True)
        except Exception as e:
            logging.error(f"Could not start recording: {e}")
            self.show_toast(_("Error: Could not start recording!"))
            self.active_recorder = None
            
    def on_info_button_clicked(self, button):
        """Opens the technical information dialog for the current stream."""
        if not self.player:
            return          
        logging.info("Opening Media Info Dialog.")
        dialog = MediaInfoDialog(self, self.player)
        dialog.present()            

    def on_catch_up_button_clicked(self, controls):
        """Opens the CatchupDialog when the catch-up button is clicked."""
        logging.info("Catch-up button clicked.")
        if not self.current_playing_channel_data or not isinstance(self.current_channel_archive_duration, int) or self.current_channel_archive_duration <= 0:
            logging.error("Catch-up info not found or archive duration is 0 or invalid!")
            self.show_toast(
                _("Error: Could not retrieve archive info for this channel or duration is invalid.")
            )
            return
        channel_id = self.current_playing_channel_data.get("tvg-id")
        archive_days = self.current_channel_archive_duration
        if not channel_id:
            logging.error("Channel tvg-id not found for catch-up!")
            self.show_toast(
                _("Error: Channel EPG ID not found.")
            )
            return
        logging.info(f"Creating CatchupDialog. Channel ID: {channel_id}, Duration: {archive_days} days")
        dialog = CatchupDialog(
            parent=self,
            channel_id=channel_id,
            archive_duration_days=archive_days,
            all_epg_data=self.epg_data
        )
        dialog.connect('program-selected', self.on_catchup_program_selected)
        dialog.present()

    def on_catchup_program_selected(self, dialog, selected_program):
        """Runs when a program is selected from CatchupDialog and starts playback."""
        program_title = selected_program.get('title', _('Unknown Program'))
        program_start_time = selected_program.get('start')
        program_stop_time = selected_program.get('stop')
        if not program_start_time or not program_stop_time:
             logging.error("Could not get start or end time for catch-up program!")
             self.show_toast(_("Error: Program time information is missing."))
             return
        logging.info(f"Playing catch-up program: '{program_title}' @ {program_start_time}")
        catchup_url = None
        if self.profile_data.get("type") == "xtream":
            host = self.profile_data.get('host')
            username = self.profile_data.get('username')
            password = self.profile_data.get('password')
            stream_id = self.current_playing_channel_data.get('stream_id')
            if not stream_id:
                 logging.error("Could not create catch-up URL for Xtream profile: Channel 'stream_id' not found.")
                 self.show_toast(_("Error: Channel ID could not be retrieved."))
                 return
            duration_seconds = (program_stop_time - program_start_time).total_seconds()
            duration_minutes = max(1, int(duration_seconds / 60))
            start_utc = program_start_time.astimezone(timezone.utc)
            time_str_for_url = start_utc.strftime('%Y-%m-%d:%H-%M')
            if host and username and password and stream_id:
                catchup_url = f"{host}/timeshift/{username}/{password}/{duration_minutes}/{time_str_for_url}/{stream_id}.ts"
                logging.info(f"Generated Xtream Catch-up URL: {catchup_url}")
            else:
                logging.error("Required Xtream profile info missing to create catch-up URL!")
                self.show_toast(_("Error: Profile information missing."))
                return
        elif self.profile_data.get("type") in ["m3u_url", "m3u_file"]:
            logging.warning("Standard Catch-up URL format for M3U profiles is unknown. Playback may fail.")
            self.show_toast(
                _("Catch-up playback for M3U profiles is not yet fully supported.")
            )
            return
        else:
             logging.error(f"Attempted Catch-up for unsupported profile type: {self.profile_data.get('type')}")
             return
        if catchup_url:
            self._start_playback(url=catchup_url, media_type='vod', channel_data=self.current_playing_channel_data)
        else:
             logging.error("Playback could not be started because catch-up URL could not be created.")
             self.show_toast(_("Error: Could not create catch-up URL."))

    def on_recorded_item_right_clicked(self, grid_view, item, widget):
        """Runs when an item in the recorded videos grid is right-clicked."""
        menu_model = Gio.Menu()
        menu_model.append(_("Remove from List (Record Only)"), "item.remove_record")
        menu_model.append(_("Permanently Delete from Disk"), "item.delete_file")
        popover = Gtk.PopoverMenu.new_from_model(menu_model)
        popover.add_css_class("video-action-popover")
        popover.set_parent(widget)
        action_group = Gio.SimpleActionGroup()
        delete_action = Gio.SimpleAction.new("delete_file", None)
        delete_action.connect("activate", self._on_delete_recording_action, item)
        action_group.add_action(delete_action)
        remove_record_action = Gio.SimpleAction.new("remove_record", None)
        remove_record_action.connect("activate", self._on_remove_recording_record_action, item)
        action_group.add_action(remove_record_action)
        widget.insert_action_group("item", action_group)
        popover.popup()

    def _on_delete_recording_action(self, action, value, item):
        """Shows the confirmation dialog when the 'Delete' menu action is selected."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_("Confirm Deletion of Recording"),
            body=_("The video '{}' will be permanently deleted. This action cannot be undone.\n\nAre you sure?").format(os.path.basename(item.path_or_url)),
            modal=True
        )
        dialog.add_css_class("delete-confirm-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_delete_recording_confirm, item)
        dialog.present()

    def _on_delete_recording_confirm(self, dialog, response_id, item):
        """Performs the deletion based on the response from the confirmation dialog."""
        if response_id == "delete":
            filepath = item.path_or_url
            try:
                os.remove(filepath)
                logging.info(f"Video file deleted successfully: {filepath}")
                self.show_toast(_("Video deleted successfully."))
                self.load_recorded_videos()
            except OSError as e:
                logging.error(f"Error occurred while deleting video file: {e}")
                self.show_toast(_("Error: Video file could not be deleted!"))

    def on_equalizer_button_clicked(self, button):
        """Shows or creates the equalizer window."""
        if not self.equalizer_window:
             self.equalizer_window = EqualizerWindow(self, self.player)
        self.equalizer_window.present()

    def _refresh_media_grid_thread(self, media_type):
        media_items = []
        try:
            if media_type == "music":
                media_items = database.get_all_albums()
            else:
                 media_items = database.get_media_files_with_metadata_by_type(media_type)
            GLib.idle_add(self._populate_media_grid_from_thread, media_items, media_type)
        except Exception as e:
            logging.error(f"Error fetching media grid data: {e}")

    def _populate_media_grid_from_thread(self, media_files, media_type):
        self.media_grid_view.populate_async(media_files, media_type=media_type)
        return GLib.SOURCE_REMOVE

    def on_media_grid_populated(self, grid_view):
        logging.info("Media grid populated, checking metadata.")
        active_main_tab = self.sidebar.list_stack.get_visible_child_name()
        if not database.get_use_tmdb_status():
            logging.info("TMDb usage is disabled in settings. Skipping metadata fetch.")
            return       
        user_key = database.get_config_value("tmdb_api_key")
        api_key = user_key if user_key else get_fallback_tmdb_key()
        if active_main_tab == "media" and self.media_grid_view.current_media_type == "video":
            if api_key:
                logging.info("Local Video library active, starting background metadata fetch.")
                self.start_metadata_fetch_for_model(self.media_grid_view.model)
            else:
                logging.info("TMDb API key not set (and no fallback found), skipping TMDb search.")
        else:
            logging.info(f"Active tab is '{active_main_tab}', skipping automatic metadata scan (Lazy Loading active).")

    def on_scan_finished(self, manager):
        """
        When the scan is finished, refreshes the currently displayed
        collection list with the correct media type.
        """
        active_main_tab = self.sidebar.list_stack.get_visible_child_name()
        if active_main_tab == "media":
            logging.info(f"Scan finished. Refreshing collections for '{self.active_media_type}' type.")
            libraries = database.get_libraries_by_type(self.active_media_type)
            self.collection_grid_view.populate_collections(libraries)

    def on_recorded_item_clicked(self, grid_view, item):
        """Runs when an item from the recorded videos grid is single-clicked."""
        if not item or not item.path_or_url:
            return
        logging.info(f"Playing recorded video: {item.path_or_url}")
        self._start_playback(url=item.path_or_url, media_type='media')

    def on_subtitle_button_clicked(self, controls):
        """Opens the dialog window when the subtitle button is clicked."""
        embedded_tracks = self.player.get_subtitle_tracks()
        dialog = SubtitleDialog(
            self,
            embedded_tracks,
            current_state=self.subtitles_visible,
            current_track_index=self.current_subtitle_track
        )
        dialog.connect("online-search-requested", self.on_online_subtitle_search_requested)
        dialog.connect('sync-adjust-requested', self.on_subtitle_sync_adjust)
        dialog.connect("subtitle-toggled", self.on_subtitle_toggled)
        dialog.connect("load-external-requested", self.on_load_external_subtitle)
        dialog.connect("track-selected", self.on_embedded_subtitle_selected)
        dialog.update_sync_label(self.subtitle_delay_ms)
        dialog.present()

    def on_online_subtitle_search_requested(self, dialog):
        """Triggered when the 'Search Online' button in SubtitleDialog is clicked."""
        logging.info("Online subtitle search request received.")
        dialog.close()
        api_key = database.get_config_value("opensubtitles_api_key")
        if not api_key:
            logging.warning("OpenSubtitles API key is not set.")
            self.show_toast(
                _("Please enter your OpenSubtitles API key from Settings first.")
            )
            return
        search_title = self.current_playing_info.get("title")
        search_year = self.current_playing_info.get("year")
        search_tmdb_id = self.current_playing_info.get("tmdb_id")
        media_path_or_id_for_log = self.current_playing_media_path
        logging.debug(f"Using stored info for subtitle search: Title='{search_title}', Year='{search_year}', TMDbID='{search_tmdb_id}'")
        if not search_title and not search_tmdb_id:
            if media_path_or_id_for_log:
                search_title = os.path.basename(media_path_or_id_for_log)
                logging.warning(f"No stored title/ID, using URL basename: {search_title}")
            else:
                logging.error("Could not find title or ID to search for subtitles.")
                self.show_toast(
                    _("Error: Content title/ID for subtitle search not found.")
                )
                return
        search_term_log = f"TMDb ID {search_tmdb_id}" if search_tmdb_id else f"'{search_title}'"
        self.show_toast(
            _("Searching for subtitles for {}...").format(search_term_log)
        )
        logging.info(f"Starting background subtitle search thread. Title: {search_title}, Year: {search_year}, TMDb ID: {search_tmdb_id}")
        image_download_pool.submit(
            subtitle_searcher.search_subtitles_online,
            media_path_or_id_for_log,
            search_title,
            api_key,
            self._on_subtitle_search_results_received,
            tmdb_id=search_tmdb_id,
            year=search_year
        )

    def _on_subtitle_search_results_received(self, results, error):
        """
        Processes subtitle search results from the background thread.
        (Called by GLib.idle_add on the main thread)
        """
        if error:
            logging.error(f"Subtitle search error: {error}")
            self.show_toast(error)
            return
        if not results:
            logging.info("Subtitle search result came back empty.")
            self.show_toast(_("No subtitles found."))
            return
        logging.info(f"{len(results)} subtitles found. Showing results window.")
        try:
            results_dialog = SubtitleResultsDialog(self, results)
            results_dialog.connect('subtitle-selected', self._on_subtitle_result_selected)
            results_dialog.present()
        except Exception as e:
             logging.exception("Error creating/showing subtitle results dialog.")
             self.show_toast(
                  _("Error: Could not display results.")
             )

    def _on_subtitle_result_selected(self, dialog, selected_subtitle_data):
        """Called when a subtitle is selected from SubtitleResultsDialog."""
        subtitle_id = selected_subtitle_data.get('subtitle_id')
        file_name = selected_subtitle_data.get('file_name', 'N/A')
        file_id = selected_subtitle_data.get('file_id')
        if not file_id:
            logging.error("Could not find 'file_id' in selected subtitle data.")
            self.show_toast(
                _("Error: Could not retrieve file ID for selected subtitle.")
            )
            return
        logging.info(f"User selected subtitle: ID {subtitle_id}, FileID: {file_id}, Name: {file_name}")
        api_key = database.get_config_value("opensubtitles_api_key")
        if not api_key:
            logging.error("OpenSubtitles API key not found (required for download).")
            self.show_toast(
                 _("Error: API key not found for download.")
            )
            return
        self.show_toast(
            _("Downloading '{0}'...").format(file_name)
        )
        image_download_pool.submit(
            subtitle_searcher.download_subtitle_file,
            file_id,
            api_key,
            self._on_subtitle_downloaded
        )

    def _on_subtitle_downloaded(self, temp_file_path, error):
        """
        Processes the subtitle download result from the background thread.
        (Called by GLib.idle_add on the main thread)
        """
        if error:
            logging.error(f"Subtitle download error: {error}")
            self.show_toast(error)
            return
        if temp_file_path and os.path.exists(temp_file_path):
            logging.info(f"Subtitle downloaded and saved successfully: {temp_file_path}")
            self.player.set_subtitle_track(-1)
            self.current_subtitle_track = -1
            self.subtitles_visible = False
            success = self.subtitle_manager.load_from_file(temp_file_path)
            if success:
                self.is_external_subtitle_active = True
                self.show_toast(
                     _("Subtitle loaded and enabled successfully.")
                )
            else:
                self.is_external_subtitle_active = False
                self.show_toast(
                    _("Error: Downloaded subtitle file could not be loaded.")
                )
                try: os.remove(temp_file_path)
                except OSError: pass
        else:
            logging.error("Download seems successful but temp file path was not received or file does not exist.")
            self.show_toast(
                 _("Error: Downloaded subtitle file not found.")
            )

    def on_subtitle_sync_adjust(self, dialog, adjustment_ms):
        """Handles the sync adjustment request from SubtitleDialog."""
        self.subtitle_delay_ms += adjustment_ms
        logging.debug(f"Subtitle delay set: {self.subtitle_delay_ms} ms")
        dialog.update_sync_label(self.subtitle_delay_ms)
        self.subtitle_manager.set_delay(self.subtitle_delay_ms)

    def on_show_recordings_clicked(self, button):
        self.player.pause()
        for btn in self.top_buttons.values():
            btn.remove_css_class("active-nav-button")
        self.main_content_stack.set_visible_child_name("recordings_view")
        self.load_recorded_videos()

    def load_recorded_videos(self):
        logging.info("Scanning recorded videos...")
        recordings_dir = database.get_recordings_path()
        if not os.path.isdir(recordings_dir):
            logging.warning(f"Recordings folder not found: {recordings_dir}")
            self.recordings_grid_view.clear()
            return
        self.recordings_grid_view.clear()
        if self.recordings_grid_view.grid_view.get_model() is None:
            selection_model = Gtk.SingleSelection.new(self.recordings_grid_view.model)
            self.recordings_grid_view.grid_view.set_model(selection_model)
        recorded_files_count = 0
        for filename in os.listdir(recordings_dir):
            if filename.lower().endswith(".mkv"):
                full_path = os.path.join(recordings_dir, filename)
                item = MediaItem(path_or_url=full_path)
                self.recordings_grid_view.model.append(item)
                thread = threading.Thread(target=self._thumbnail_creation_thread, args=(item,))
                thread.start()
                recorded_files_count += 1
        self.show_toast(_("{} recordings found.").format(recorded_files_count))

    def on_open_scheduler_clicked(self, button):
        logging.info("Opening recording scheduler window.")
        live_channels = {
            url: data for url, data in self.all_channels_map.items()
            if not any(url.lower().endswith(ext) for ext in ['.mkv', '.mp4', '.avi'])
        }
        dialog = SchedulerWindow(self, self.bouquets_data)
        dialog.connect("schedule-saved", self.on_schedule_saved)
        dialog.connect("schedule-deleted", self.on_schedule_deleted)
        dialog.present()

    def on_schedule_saved(self, dialog, profile_id, channel_name, channel_url, start_time, end_time, program_name):
        success = database.add_scheduled_recording(
            profile_id, channel_name, channel_url, start_time, end_time, program_name
        )
        if success:
            self.show_toast(_("Recording scheduled successfully!"))
            dialog.refresh_tasks_list()
        else:
            self.show_toast(_("Error: Could not schedule recording."))
            
    def on_schedule_deleted(self, window, task_id):
        database.delete_scheduled_recording(task_id)
        self.show_toast(_("Scheduled recording deleted."))
        window.refresh_tasks_list()

    def on_subtitle_toggled(self, dialog, is_active):
        database.set_config_value('subtitles_enabled_global', '1' if is_active else '0')
        if is_active and self.is_external_subtitle_active:
            return
        self.subtitles_visible = is_active
        if is_active:
            self.subtitle_manager.clear()
            self.is_external_subtitle_active = False
            track_to_activate = self.last_selected_embedded_track
            self.player.set_subtitle_track(track_to_activate)
            self.current_subtitle_track = track_to_activate
        else:
            self.subtitle_manager.clear()
            self.is_external_subtitle_active = False
            self.player.set_subtitle_track(-1)
            self.current_subtitle_track = -1

    def _apply_saved_track_preferences(self):
        """
        Checks the database for saved language preferences when a new video loads
        and automatically selects the matching audio/subtitle track if available.
        """
        saved_audio = database.get_config_value('preferred_audio_lang')
        if saved_audio:
            audio_tracks = self.player.get_audio_tracks()
            for t in audio_tracks:
                if t['name'] == saved_audio:
                    logging.info(f"Auto-selecting preferred audio: {saved_audio}")
                    self.player.set_audio_track(t['index'])
                    break
        is_subs_enabled = database.get_config_value('subtitles_enabled_global') == '1'
        if is_subs_enabled:
            saved_sub = database.get_config_value('preferred_subtitle_lang')
            if saved_sub:
                sub_tracks = self.player.get_subtitle_tracks()
                for t in sub_tracks:
                    if t['name'] == saved_sub:
                        logging.info(f"Auto-selecting preferred subtitle: {saved_sub}")
                        self.player.set_subtitle_track(t['index'])
                        self.subtitles_visible = True
                        self.subtitle_manager.clear()
                        self.is_external_subtitle_active = False
                        self.current_subtitle_track = t['index']
                        break
        else:
            self.player.set_subtitle_track(-1)
            self.subtitles_visible = False

    def on_tracks_changed(self, player):
        audio_tracks = self.player.get_audio_tracks()
        controls = self.video_view.controls
        controls.update_audio_tracks_menu(audio_tracks)
        self._apply_saved_track_preferences()

    def on_audio_track_selected(self, controls, index):
        self.player.set_audio_track(index)
        tracks = self.player.get_audio_tracks()
        for t in tracks:
            if t['index'] == index:
                database.set_config_value('preferred_audio_lang', t['name'])
                break

    def _on_track_activated(self, view, track_data):
        logging.info(f"Track selected for playback: {track_data['title']}")
        file_path = track_data['file_path']
        album_id = track_data['album_id']
        album_info = database.get_album_details(album_id)
        self._start_playback(url=file_path, media_type='music', channel_data=album_info)

    def on_load_external_subtitle(self, dialog):
        """
        Opens a GTK FileChooserDialog to select an external subtitle file.
        Updated to match the consistent style (Portal Bypass) and prevent segfaults.
        """
        dialog.close()
        chooser = Gtk.FileChooserDialog(
            title=_("Select External Subtitle File"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN
        )
        chooser.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Select"), Gtk.ResponseType.ACCEPT
        )
        chooser.set_modal(True)
        filter_subs = Gtk.FileFilter()
        filter_subs.set_name(_("Subtitle Files"))
        for pattern in ["*.srt", "*.vtt", "*.ass", "*.sub", "*.smi", "*.txt"]:
            filter_subs.add_pattern(pattern)
        chooser.add_filter(filter_subs)
        filter_all = Gtk.FileFilter()
        filter_all.set_name(_("All Files"))
        filter_all.add_pattern("*")
        chooser.add_filter(filter_all)

        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                gfile = d.get_file()
                if gfile:
                    file_path = gfile.get_path()
                    logging.info(f"External subtitle selected: {file_path}")
                    self.player.set_subtitle_track(-1)
                    success = self.subtitle_manager.load_from_file(file_path)
                    if success:
                        self.subtitles_visible = True
                        self.is_external_subtitle_active = True
                        self.current_subtitle_track = -1
                        self.show_toast(_("External subtitle loaded."))
                    else:
                        self.is_external_subtitle_active = False
                        self.show_toast(_("Could not load subtitle file."))
            d.hide()
            def _safe_destroy():
                d.destroy()
                return GLib.SOURCE_REMOVE
            GLib.idle_add(_safe_destroy)
        chooser.connect("response", on_response)
        chooser.present()

    def on_embedded_subtitle_selected(self, dialog, track_index):
        self.subtitle_manager.clear()
        self.is_external_subtitle_active = False
        self.player.set_subtitle_track(track_index)
        self.current_subtitle_track = track_index
        self.last_selected_embedded_track = track_index
        self.subtitles_visible = True
        database.set_config_value('subtitles_enabled_global', '1')
        tracks = self.player.get_subtitle_tracks()
        for t in tracks:
            if t['index'] == track_index:
                database.set_config_value('preferred_subtitle_lang', t['name'])
                break
                
    def _check_digits_match(self, str1, str2):
        d1 = "".join(re.findall(r'\d', str1))
        d2 = "".join(re.findall(r'\d', str2))
        return d1 == d2  
        
    def _check_country_match(self, key1, key2):
        if "." in key1 and "." in key2:
            return key1.split(".")[-1] == key2.split(".")[-1]
        if "." in key2:
            epg_suffix = key2.split(".")[-1].lower()
            if 2 <= len(epg_suffix) <= 3:
                channel_prefix = key1[:len(epg_suffix)].lower()               
                if channel_prefix != epg_suffix:
                    common_iso_codes = [
                        "tr", "us", "uk", "fr", "de", "it", "es", "pt", "nl", "be", 
                        "ru", "gr", "az", "de", "ch", "at", "pl", "ro", "bg", "hu", 
                        "cz", "sk", "al", "rs", "hr", "ba", "mk", "se", "no", "dk", 
                        "fi", "ie", "ca", "au", "nz", "br", "ar", "mx", "ae", "sa", 
                        "eg", "in", "cn", "jp", "kr", "za",
                        "tur", "usa", "gbr", "fra", "deu", "ita", "esp", "prt", "nld", "bel",
                        "rus", "grc", "aze", "che", "aut", "pol", "rou", "bgr", "hun", "cze",
                        "svk", "alb", "srb", "hrv", "bih", "mkd", "swe", "nor", "dnk", "fin",
                        "irl", "can", "aus", "nzl", "bra", "arg", "mex", "are", "sau", "egy"
                    ]
                    if channel_prefix in common_iso_codes:
                        return False               
        return True                   

    def _find_epg_data_for_channel(self, provider_tvg_id):
        """
        Performs a 4-step (direct, clean, fuzzy) search in the EPG data
        using the provider's TVG-ID.
        """
        if not provider_tvg_id:
            return None
        if provider_tvg_id in self.epg_data:
            logging.debug(f"EPG Found (Step 1: Direct): '{provider_tvg_id}'")
            return self.epg_data[provider_tvg_id]
        clean_key = self._clean_key(provider_tvg_id)
        if not clean_key:
            return None          
        if clean_key in self.epg_clean_map:
            logging.debug(f"EPG Found (Step 2: Clean Key): '{provider_tvg_id}' -> '{clean_key}'")
            return self.epg_clean_map[clean_key]
        if FUZZ_AVAILABLE and process:
            if not self.epg_clean_map:
                logging.debug("Fuzzy EPG search skipped (EPG map is empty).")
            else:
                best_match_tuple = process.extractOne(clean_key, self.epg_clean_map.keys())
                if best_match_tuple:
                    best_match, score = best_match_tuple
                    if score >= 80 and \
                       self._check_digits_match(clean_key, best_match) and \
                       self._check_country_match(clean_key, best_match):
                        len1, len2 = len(clean_key), len(best_match)
                        ratio = max(len1, len2) / min(len1, len2) if min(len1, len2) > 0 else 0
                        first_char_match = clean_key[0] == best_match[0] if clean_key and best_match else False                       
                        if ratio <= 2.0 and first_char_match:
                            logging.debug(f"EPG Found (Step 3: Fuzzy %{score}): '{provider_tvg_id}' -> '{best_match}'")
                            return self.epg_clean_map[best_match]
                        else:
                            reject_reason = "Ratio" if ratio > 2.0 else "First Char"
                            logging.debug(f"EPG Rejected ({reject_reason}): '{clean_key}' vs '{best_match}' (Ratio: {ratio:.2f})")
                soft_key = clean_key.replace("tv.", ".")
                if soft_key in self.epg_clean_map:
                    logging.debug(f"EPG Found (Step 3.5: Soft Match): '{provider_tvg_id}' as '{soft_key}'")
                    return self.epg_clean_map[soft_key]
        logging.debug(f"EPG Not Found (Step 4): No match for '{provider_tvg_id}'.")
        return None

    def _update_epg_for_channel(self, channel_data):
        if not channel_data:
            logging.debug("EPG Update: No channel_data provided.")
            return
        t_id = (channel_data.get("tvg-id") or "").strip()
        t_name = (channel_data.get("tvg-name") or "").strip()
        name = (channel_data.get("name") or "").strip()
        search_key = None
        if t_id:
            search_key = t_id
            logging.debug(f"EPG Search: Using tvg-id -> '{search_key}'")
        elif t_name:
            search_key = t_name
            logging.debug(f"EPG Search: tvg-id empty, falling back to tvg-name -> '{search_key}'")
        elif name:
            search_key = name
        if search_key in self._failed_active_epg_searches:
            self.video_view.update_epg([])
            return    
            logging.debug(f"EPG Search: ID and Name tags empty, using display name -> '{search_key}'")

        if not search_key:
            logging.debug("EPG Search: All identification tags are empty! Skipping.")
            self.video_view.update_epg([])
            return
        channel_programs = self._find_epg_data_for_channel(search_key)       
        if not channel_programs:
            self._failed_active_epg_searches.add(search_key) 
            self.video_view.update_epg([])
            return
        programs_to_display = []
        now = datetime.now(timezone.utc)
        found_current = False
        program_count = 0
        for program in channel_programs:
            if program["stop"] < now:
                continue          
            is_current = False
            if not found_current and program["start"] <= now < program["stop"]:
                is_current = True
                found_current = True
                self.current_epg_program = program          
            programs_to_display.append({"data": program, "is_current": is_current})
            program_count += 1
            if program_count >= 10:
                break
        self.video_view.update_epg(programs_to_display)

    def _update_player_ui_for_media_type(self, media_type):
        is_iptv = (media_type == 'iptv')
        self.video_view.set_epg_visibility(is_iptv)
        controls = self.video_view.controls
        controls.set_channel_icon_visibility(is_iptv)
        controls.set_button_visibility("record", is_iptv)

    def on_grid_item_clicked(self, view, item):
        if not item:
            return
        current_grid_type = self.media_grid_view.current_media_type
        if current_grid_type == "series":
            series_id = item.props.path_or_url
            logging.info(f"Series item clicked. ID: {series_id}. Fetching details...")
            self.main_content_stack.set_visible_child_name("loading_view")
            self.loading_spinner.start()
            thread = threading.Thread(
                target=self._fetch_series_info_thread,
                args=(series_id,),
                daemon=True
            )
            thread.start()
            return
        elif current_grid_type == "vod":
            logging.info(f"VOD item clicked. Stream ID: {item.props.path_or_url}")
            self.detail_view.update_content(item, "vod")
            self.main_content_stack.set_visible_child_name("detail_view")
        elif current_grid_type == "music":
            if item.props.path_or_url.isdigit():
                album_id = int(item.props.path_or_url)
                tracks = database.get_tracks_for_album(album_id)
                album_data_from_db = database.get_album_details(album_id)
                if tracks and album_data_from_db:
                    self.track_list_view.populate_tracks(album_data_from_db, tracks)
                    self.media_stack.set_visible_child_name("tracks")
                    first_track_data = tracks[0]
                    self._on_track_activated(None, first_track_data)
                    first_row = self.track_list_view.track_listbox.get_row_at_index(0)
                    if first_row:
                        self.track_list_view.track_listbox.select_row(first_row)
            else:
                 logging.warning(f"Music item clicked, but ID is not a digit: {item.props.path_or_url}")
        else:
            is_picture = any(item.props.path_or_url.lower().endswith(ext) for ext in {".jpg", ".jpeg", ".png", ".webp"})
            if is_picture:
                all_items = list(self.media_grid_view.model)
                clicked_index = all_items.index(item)
                self.image_viewer.set_images(all_items, clicked_index)
                self.main_content_stack.set_visible_child_name("image_viewer_view")
            else:
                self.detail_view.update_content(item, "media")
                self.main_content_stack.set_visible_child_name("detail_view")

    def _on_image_viewer_back_requested(self, viewer):
        self.media_search_entry.set_text("")
        viewer.stop_all_activity()
        self.main_content_stack.set_visible_child_name("library_view")

    def start_metadata_fetch_for_model(self, model):
        if not database.get_use_tmdb_status():
            logging.debug("Metadata fetch requested, but TMDb usage is disabled by user.")
            return
        user_key = database.get_config_value("tmdb_api_key")
        api_key = user_key if user_key else get_fallback_tmdb_key()
        if not api_key:
            logging.warning("Metadata fetch requested, but no API Key found (User or Fallback).")
            return
        media_type = self.media_grid_view.current_media_type
        for item in model:
            if item.path_or_url in self.metadata_fetch_queue: continue
            self.metadata_fetch_queue.add(item.path_or_url)
            thread = threading.Thread(
                target=self._metadata_fetch_task,
                args=(item, api_key, media_type),
                daemon=True
            )
            thread.start()

    def _metadata_fetch_task(self, item, api_key, media_type):
        """(Background Thread) Fetches metadata or gets it from cache."""
        with self.metadata_semaphore:
            try:
                cached_data = database.get_metadata(item.path_or_url)
                if cached_data and cached_data["director"]:
                    if cached_data["director"] == "FETCH_FAILED_NO_MATCH":
                        return
                    if cached_data["director"] != "FETCH_FAILED":
                        GLib.idle_add(self._on_metadata_fetched, item, cached_data)
                        return
                search_type = 'tv' if media_type == "series" else 'movie'
                clean_title, year = title_parser.parse_title_for_search(item.title)
                if not clean_title:
                    return
                search_result, status = tmdb_client.search_media(api_key, clean_title, search_type, year)
                tmdb_details = None
                if status == "success" and search_result and search_result.get("id"):
                    media_id = search_result["id"]
                    tmdb_details = tmdb_client.get_media_details(api_key, media_id, search_type)
                if tmdb_details:
                    database.save_metadata(item.path_or_url, tmdb_details)
                    fetched_data = database.get_metadata(item.path_or_url)
                    GLib.idle_add(self._on_metadata_fetched, item, fetched_data)
                elif status == "no_match_found":
                    logging.warning(f"No match found on TMDb for '{item.title}'. Caching permanent failure.")
                    database.save_metadata(item.path_or_url, {"director": "FETCH_FAILED_NO_MATCH"})
                elif status == "network_error":
                    logging.warning(f"TMDb search for '{item.title}' could not be performed due to NETWORK ERROR. Will try again next time.")
            except Exception as e:
                 logging.exception(f"Unexpected error during _metadata_fetch_task: {e}")
            finally:
                if item.path_or_url in self.metadata_fetch_queue:
                    self.metadata_fetch_queue.remove(item.path_or_url)

    def _on_metadata_fetched(self, item, fetched_data):
        """(Main Thread) Processes metadata from the background and updates the MediaItem."""
        logging.info(f"WINDOW: _on_metadata_fetched CALLED for item: {item.props.path_or_url}")
        if fetched_data:
            logging.debug(f"WINDOW: Fetched data exists. Updating item props: {item.props.path_or_url}")
            try:
                keys = fetched_data.keys()
                if 'title' in keys and fetched_data['title']: item.props.title = fetched_data['title']
                if 'poster_path' in keys and fetched_data['poster_path']: item.props.poster_path = tmdb_client.get_poster_url(fetched_data['poster_path'])
                if 'overview' in keys and fetched_data['overview']: item.props.overview = fetched_data['overview']
                logging.debug(f"WINDOW: Item props updated for {item.props.path_or_url}.")
            except Exception as e:
                logging.error(f"WINDOW: Error updating item props in _on_metadata_fetched: {e}")
        else:
             logging.warning(f"WINDOW: _on_metadata_fetched called, but fetched_data is None/empty for {item.props.path_or_url}")
        return GLib.SOURCE_REMOVE

    def _thumbnail_creation_thread(self, item):
        thumbnail_path = self.get_or_create_thumbnail(item.path_or_url)
        if thumbnail_path:
            GLib.idle_add(setattr, item.props, "poster_path", thumbnail_path)

    def get_or_create_thumbnail(self, video_path):
        try:
            base_cache_dir = database.get_cache_path()
            cache_dir = os.path.join(base_cache_dir, "thumbnails")
            os.makedirs(cache_dir, exist_ok=True)
            hash_name = hashlib.md5(video_path.encode()).hexdigest()
            thumbnail_path = os.path.join(cache_dir, f"{hash_name}.jpg")
            if os.path.exists(thumbnail_path): return thumbnail_path
            logging.info(f"Creating thumbnail: {video_path}")
            command = ['ffmpeg', '-i', video_path, '-ss', '00:00:05', '-vframes', '1', '-q:v', '3', '-f', 'image2', thumbnail_path]
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return thumbnail_path
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logging.error(f"Could not create thumbnail: {video_path} | Error: {e}")
            return None

    def _show_channels_for_bouquet(self, bouquet_name):
        channels_in_bouquet = self.bouquets_data.get(bouquet_name, [])
        self.current_channels_in_view = channels_in_bouquet
        self.channel_list.populate_channels_async(channels_in_bouquet)
        self.iptv_stack.set_visible_child_name("channels")

    def on_bouquet_selected(self, listbox, row):
        if not row: return
        self.bouquet_list.search_entry.set_text("")
        bouquet_name = row.bouquet_name
        password_is_set = database.get_config_value('app_password') is not None
        bouquet_is_locked = database.get_bouquet_lock_status(bouquet_name)
        if password_is_set and bouquet_is_locked:
            prompt = PasswordPromptDialog(self)
            prompt.connect("response", self.on_password_prompt_response_bouquet, bouquet_name)
            prompt.present()
        else:
            self._show_channels_for_bouquet(bouquet_name)

    def on_channel_selected(self, listbox, row):
        if not row: return
        active_sidebar_view = self.sidebar.list_stack.get_visible_child_name()
        if active_sidebar_view == "iptv":
            self.channel_list.search_entry.set_text("")
        elif active_sidebar_view == "favorites":
            self.favorites_view.favorite_channels_list.search_entry.set_text("")
        channel_data = row.channel_data
        correct_logo = getattr(row, 'correct_logo_path', channel_data.get("logo"))
        url = channel_data.get("url")
        password_is_set = database.get_config_value('app_password') is not None
        channel_is_locked = database.get_channel_lock_status(url)
        if password_is_set and channel_is_locked:
            prompt = PasswordPromptDialog(self)
            prompt.connect("response", self.on_password_prompt_response, channel_data, correct_logo)
            prompt.present()
        else:
            self._play_channel(channel_data, correct_logo)

    def _play_channel(self, channel_data, correct_logo_path=None):
        url = channel_data.get("url")
        if url:
            self._start_playback(url=url, media_type='iptv', channel_data=channel_data, correct_logo_path=correct_logo_path)
            if self.is_immersive_fullscreen and hasattr(self.video_view, 'fullscreen_channel_list'):
                self._sync_fullscreen_list_selection(url)
            self._sync_sidebar_list_selection(url)    

    def on_password_prompt_response(self, dialog, response_id, channel_data, correct_logo_path=None):
        if response_id == "ok":
            if database.check_password(dialog.get_password()):
                self._play_channel(channel_data, correct_logo_path)
            else:
                self.show_toast(_("Wrong Password!"))

    def on_password_prompt_response_bouquet(self, dialog, response_id, bouquet_name):
        if response_id == "ok":
            if database.check_password(dialog.get_password()):
                self._show_channels_for_bouquet(bouquet_name)
            else:
                self.show_toast(_("Wrong Password!"))

    def on_password_prompt_for_show_locked(self, dialog, response_id):
        if response_id == "ok" and database.check_password(dialog.get_password()):
            database.set_config_value('show_locked_bouquets', '1')
            self.bouquet_list.populate_bouquets_async(self.bouquets_data.keys())
            self.favorites_view.refresh_lists()
            self._refresh_vod_list()
        else:
            if response_id == "ok":
                self.show_toast(_("Wrong Password!"))
            self.bouquet_list.show_locked_button.set_active(False)
            self.vod_category_list.show_locked_button.set_active(False)

    def on_refresh_clicked(self, button):
        task_manager.start_library_scan()

    def _refresh_vod_list(self):
        """
        Checks the current VOD data source (M3U or Xtream) and repopulates
        the VOD category list based on lock AND hidden status.
        """
        logging.info("Refreshing VOD list due to status change...")
        hidden_bouquets = database.get_hidden_bouquets()    
        profile_type = self.profile_data.get("type")
        if profile_type == "xtream":
            category_names = [
                cat.get('category_name', _("Unknown")) 
                for cat in self.vod_categories_data
                if cat.get('category_name') not in hidden_bouquets
            ]
            self.vod_category_list.populate_bouquets_async(category_names)
        else:
            if self.vod_data:
                 visible_cats = [c for c in self.vod_data.keys() if c not in hidden_bouquets]
                 self.vod_category_list.populate_bouquets_async(visible_cats)
            else:
                self.vod_category_list.populate_bouquets_async([])

    def _on_show_locked_toggled(self, button):
        is_active = button.get_active()
        if is_active:
            prompt = PasswordPromptDialog(self)
            prompt.connect("response", self.on_password_prompt_for_show_locked)
            prompt.present()
        else:
            database.set_config_value('show_locked_bouquets', '0')
            self.bouquet_list.populate_bouquets_async(self.bouquets_data.keys())
            self.favorites_view.refresh_lists()
            self._refresh_vod_list()

    def _update_stream_info(self):
        if self.main_content_stack.get_visible_child_name() != "player_view":
            return True
        if not self.player or not self.player.player:
            return True    
        controls = self.video_view.controls
        is_seekable = False
        duration_sec = 0
        show_slider = False
        if self.current_media_type == 'music':
            is_seekable = True
            ok_dur, duration_ns = self.player.player.query_duration(Gst.Format.TIME)
            if ok_dur and duration_ns > 0:
                 duration_sec = duration_ns / Gst.SECOND
                 show_slider = True
            else:
                 show_slider = False
        elif self.current_media_type in ['media', 'vod']:
            start_ns, end_ns = self.player.get_seek_range()
            if start_ns is not None and end_ns is not None and end_ns > start_ns:
                 duration_ns = end_ns - start_ns
                 if duration_ns > 10 * Gst.SECOND:
                      is_seekable = True
                      duration_sec = duration_ns / Gst.SECOND
            show_slider = is_seekable
        elif self.current_media_type == 'iptv':
            show_slider = False
            is_seekable = False
        controls.set_seek_controls_visibility(show_slider)
        relative_position_sec = 0
        if show_slider:
            is_slider_active = controls.progress_slider.get_state_flags() & Gtk.StateFlags.ACTIVE
            if not is_slider_active and not self.is_seeking:
                start_ns_pos, _ = self.player.get_seek_range()
                if start_ns_pos is None and self.current_media_type == 'music':
                     start_ns_pos = 0
                position_ns = self.player.get_position()
                if start_ns_pos is not None and position_ns >= start_ns_pos and duration_sec > 0:
                    relative_position_sec = (position_ns - start_ns_pos) / Gst.SECOND
                    relative_position_sec = max(0, min(relative_position_sec, duration_sec))
                    controls.time_label_current.set_text(str(timedelta(seconds=int(relative_position_sec))))
                    controls.time_label_duration.set_text(str(timedelta(seconds=int(duration_sec))))
                    adjustment = controls.progress_slider.get_adjustment()
                    current_max = adjustment.get_upper()
                    if abs(current_max - duration_sec) > 0.1:
                        controls.progress_slider.set_range(0, duration_sec)
                        self.last_slider_position = 0
                    adj = controls.progress_slider.get_adjustment()
                    upper_bound = adj.get_upper()
                    clamped_pos = min(relative_position_sec, upper_bound)
                    if clamped_pos > self.last_slider_position:
                        controls.progress_slider.set_value(clamped_pos)
                    self.last_slider_position = clamped_pos
                else:
                     controls.time_label_current.set_text("0:00:00")
                     controls.time_label_duration.set_text("0:00:00")
                     adjustment = controls.progress_slider.get_adjustment()
                     _min_range = adjustment.get_lower()
                     max_range = adjustment.get_upper()
                     if max_range > 0:
                          controls.progress_slider.set_value(0)
                     self.last_slider_position = 0
        video_text, audio_text = self.player.get_stream_info()
        controls.update_info_labels(video_text, audio_text)
        if self.current_playing_media_path:
            now = time.time()
            if (now - self.last_save_time) > 10:
                if not self.player or not self.player.player:
                     return True
                position_sec = self.player.get_position() / Gst.SECOND
                ok_dur_save, duration_ns_save = self.player.player.query_duration(Gst.Format.TIME)
                duration_seconds_save = duration_ns_save / Gst.SECOND if ok_dur_save and duration_ns_save > 0 else 0
                if duration_seconds_save > 0 and not self.is_scrobble_triggered:
                    threshold_sec = duration_seconds_save * 0.90
                    if position_sec > threshold_sec and duration_seconds_save > 300:
                        logging.info(f"Content passed 90% threshold ({int(position_sec)}s / {int(duration_seconds_save)}s). Marking as 'Watched'...")
                        self.is_scrobble_triggered = True
                        database.save_playback_progress(
                            self.current_playing_media_path,
                            position=0,
                            is_finished=1
                        )
                        try:
                            media_type_to_scrobble = None
                            tmdb_id_to_scrobble = None
                            if self.currently_playing_episode_data:
                                tmdb_id_to_scrobble = self.currently_playing_episode_data.get('tmdb') or self.currently_playing_episode_data.get('tmdb_id')
                                media_type_to_scrobble = 'episode'
                            else:
                                tmdb_id_to_scrobble = self.current_playing_info.get('tmdb_id')
                                media_type_to_scrobble = 'movie'
                            if tmdb_id_to_scrobble:
                                logging.info(f"Trakt (90%): Content at 90%, adding to history (TMDb ID: {tmdb_id_to_scrobble}).")
                                thread = threading.Thread(target=trakt_client.add_to_history,
                                                          args=(tmdb_id_to_scrobble, media_type_to_scrobble),
                                                          daemon=True)
                                thread.start()
                            else:
                                logging.warning("Trakt (90%): TMDb ID not found for scrobble.")
                        except Exception as e:
                             logging.warning(f"Error starting Trakt scrobble (90%): {e}")
                if not self.is_scrobble_triggered and position_sec > 10 and (duration_seconds_save - position_sec) > 10:
                    logging.debug(f"Saving VOD Position. URL: {self.current_playing_media_path}, Position: {position_sec}")
                    database.save_playback_progress(
                        self.current_playing_media_path,
                        int(position_sec),
                        is_finished=0
                    )
                    self.last_save_time = now
        if self.current_media_type == 'iptv':
            now_ts = time.time()
            if (now_ts - self.last_epg_check_time) > 60:
                self.last_epg_check_time = now_ts
                if self.current_epg_program and datetime.now(timezone.utc) > self.current_epg_program['stop']:
                    logging.info("Active EPG program has expired. Refreshing EPG panel...")
                    if self.current_playing_channel_data:
                         self._update_epg_for_channel(self.current_playing_channel_data)
        if (self.currently_playing_episode_data and
                    self.next_episode_data_to_play is None and
                    not self.auto_play_cancelled):
            if show_slider and duration_sec > 0:
                remaining_seconds = duration_sec - relative_position_sec
                trigger_threshold = 180
                if 0 < remaining_seconds <= trigger_threshold:
                    logging.info(f"Episode has {remaining_seconds:.1f} seconds left, "
                                 f"triggering next episode prompt (Threshold: {trigger_threshold}s).")
                    next_episode_data = self._find_next_episode(self.currently_playing_episode_data)
                    if next_episode_data:
                        auto_play_enabled = True
                        if auto_play_enabled:
                             self._show_next_episode_prompt(next_episode_data)
        return True

    def on_add_source_clicked(self, button):
        dialog = Adw.MessageDialog.new(self, _("Add Media Source"), _("Choose the type of source you want to add."))
        dialog.add_css_class("source-selection-dialog")      
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("folder", _("Local Folder"))
        dialog.add_response("podcast", _("Podcast URL"))
        dialog.add_response("stream", _("Network Stream"))      
        dialog.set_close_response("cancel")
        dialog.set_default_response("folder")     
        dialog.connect("response", self._on_add_source_type_response)
        dialog.present()

    def _on_add_source_type_response(self, dialog, response_id):
        dialog.close()
        if response_id == "folder":
            self._open_media_folder_chooser()
        elif response_id == "podcast":
            self._open_podcast_url_dialog()
        elif response_id == "stream":
            self._open_network_stream_dialog()

    def _open_media_folder_chooser(self):
        dialog = Gtk.FileChooserDialog(
            title=_("Select Media Folder"),
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Select"), Gtk.ResponseType.ACCEPT)
        dialog.connect("response", self.on_media_folder_dialog_response)
        dialog.present()

    def _open_podcast_url_dialog(self):
        dialog = Adw.MessageDialog.new(self, _("Add Podcast"), _("Enter the podcast title and RSS URL."))
        dialog.add_css_class("add-podcast-dialog")
        dialog.set_modal(True)
        dialog.set_transient_for(self)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        title_entry = Gtk.Entry()
        title_entry.set_placeholder_text(_("Podcast Title"))
        content_box.append(title_entry)
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text(_("Podcast RSS URL"))
        content_box.append(url_entry)      
        dialog.set_extra_child(content_box)      
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("add", _("Add"))
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")      
        dialog.connect("response", self._on_podcast_dialog_response, title_entry, url_entry)
        dialog.present()

    def _on_podcast_dialog_response(self, dialog, response_id, title_entry, url_entry):
        if response_id == "add":
            user_title = title_entry.get_text().strip()
            url = url_entry.get_text().strip()           
            if url:
                self.show_toast(_("Fetching podcast info..."))
                thread = threading.Thread(
                    target=self._add_podcast_thread, 
                    args=(url, user_title), 
                    daemon=True
                )
                thread.start()
            else:
                self.show_toast(_("Please enter a URL."))
        dialog.set_visible(False)
        def _destroy_dialog():
            dialog.destroy()
            return GLib.SOURCE_REMOVE
        GLib.idle_add(_destroy_dialog)

    def _add_podcast_thread(self, url, user_title):
        data = rss_parser.parse_podcast_feed(url)      
        image_url = None
        final_title = user_title      
        if data:
            if not final_title:
                final_title = data.get("title", "Unknown Podcast")
            image_url = data.get("image")      
        if not final_title:
            final_title = "New Podcast"
        if database.add_podcast(final_title, url, image_url):
            GLib.idle_add(self._on_podcast_added_success)
        else:
            GLib.idle_add(self.show_toast, _("Error: Podcast could not be added."))

    def _on_podcast_added_success(self):
        self.show_toast(_("Podcast added successfully."))
        if self.active_media_type == "podcasts":
            podcasts = database.get_all_podcasts()
            self.podcast_feed_list.populate(podcasts)

    def on_media_folder_dialog_response(self, dialog, response_id):
        """
        Handles the response from the GTK FileChooserDialog.
        Updated to prevent Segfault on double-click.
        """
        if response_id == Gtk.ResponseType.ACCEPT:
            try:
                folder_gfile = dialog.get_file()
                if folder_gfile:
                    folder_path = folder_gfile.get_path()
                    logging.info(f"Folder selected (GTK Dialog): {folder_path}")
                    dialog.hide()
                    def _safe_destroy_success():
                        dialog.destroy()
                        return GLib.SOURCE_REMOVE
                    GLib.idle_add(_safe_destroy_success)
                    self.show_library_type_dialog(folder_path)
                    return
            except Exception as e:
                logging.error(f"Error getting folder path: {e}")
        dialog.hide()
        def _safe_destroy():
            dialog.destroy()
            return GLib.SOURCE_REMOVE
        GLib.idle_add(_safe_destroy)

    def show_library_type_dialog(self, folder_path):
        dialog = Adw.MessageDialog.new(self, _("Select Library Type"), _("Which type of media is in this folder?"))
        dialog.add_response("video", _("Video"))
        dialog.add_response("picture", _("Picture"))
        dialog.add_response("music", _("Music"))
        dialog.set_close_response("cancel")
        dialog.connect("response", self.on_library_type_response, folder_path)
        dialog.present()

    def on_library_type_response(self, dialog, response_id, folder_path):
        if response_id != "cancel":
            library_type = response_id
            library_name = os.path.basename(folder_path)
            success = database.add_library(folder_path, library_type, library_name)
            if success:
                task_manager.start_library_scan()

    def on_play_pause_clicked(self, button):
        state = self.player.player.get_state(0).state
        controls = self.video_view.controls
        if state == Gst.State.PLAYING:
            self.inhibitor.uninhibit()
            controls.set_playing_state(False)
            self._hide_next_episode_prompt()
        elif state == Gst.State.PAUSED:
            self.inhibitor.inhibit()
            controls.set_playing_state(True)
        self.player.toggle_play_pause()

    def _enable_motion_events_callback(self):
        """Re-enables mouse motion events after a short delay."""
        self.ignore_motion_events = False
        return GLib.SOURCE_REMOVE

    def on_fullscreen_clicked(self, button):
        controls = self.video_view.controls
        if not self.is_fullscreen():
            self.is_immersive_fullscreen = True
            self._set_ui_panels_visibility(False)
            self.fullscreen()
            self.video_view.enable_fullscreen_overlay_mode()
            self.get_surface().set_cursor(Gdk.Cursor.new_from_name("none", None))
            controls.set_fullscreen_mode(True)           
            if self.current_media_type == 'iptv':
                active_category_name = _("Channel List")
                if self.sidebar.list_stack.get_visible_child_name() == "favorites":
                     active_category_name = _("Favorites")
                else:
                    active_category_name = _("Channels")
                self.video_view.fullscreen_channel_list.set_header(active_category_name, show_back=True)
                self.video_view.fullscreen_channel_list.search_entry.set_visible(True)                
                self.video_view.fullscreen_channel_list.populate_channels_async(self.current_channels_in_view)
                self.video_view.fullscreen_channel_list.set_visible(True)
                if self.current_playing_channel_data:
                    url = self.current_playing_channel_data.get('url')
                    GLib.timeout_add(300, lambda: (self._sync_fullscreen_list_selection(url), False)[1])
            else:
                self.video_view.fullscreen_channel_list.set_visible(False)           
        else:
            self.is_immersive_fullscreen = False
            self.unfullscreen()
            self._set_ui_panels_visibility(True)
            self.video_view.disable_fullscreen_overlay_mode()
            self.video_view.fullscreen_channel_list.set_visible(False)           
            if self.hide_cursor_timer:
                GLib.source_remove(self.hide_cursor_timer)
                self.hide_cursor_timer = None
            self.get_surface().set_cursor(None)
            controls.set_fullscreen_mode(False)
            controls.set_visible(True)

    def _on_fullscreen_finished(self, window, param):
        """This method runs when the window finishes transitioning to fullscreen mode."""
        self._set_ui_panels_visibility(False)
        self.is_immersive_fullscreen = True
        self.disconnect_by_func(self._on_fullscreen_finished)
        
    def on_fullscreen_channel_selected(self, listbox, row):
        if not row: return
        channel_data = row.channel_data
        correct_logo = getattr(row, 'correct_logo_path', channel_data.get("logo"))
        self._play_channel(channel_data, correct_logo) 
        
    def _sync_fullscreen_list_selection(self, playing_url):
        listbox = self.video_view.fullscreen_channel_list.channel_listbox
        row = listbox.get_first_child()       
        while row:
            if hasattr(row, 'channel_data') and row.channel_data.get('url') == playing_url:
                listbox.select_row(row)
                row.grab_focus() 
                break
            row = row.get_next_sibling() 
            
    def _find_bouquet_name_by_url(self, url):
        if not self.bouquets_data:
            return None
        for bouquet_name, channels in self.bouquets_data.items():
            for channel in channels:
                if channel.get('url') == url:
                    return bouquet_name
        return None            
            
    def _sync_sidebar_list_selection(self, playing_url):
        active_sidebar = self.sidebar.list_stack.get_visible_child_name()      
        if active_sidebar not in ["iptv", "favorites"]:
            return
        target_listbox = None
        if active_sidebar == "iptv":
            target_listbox = self.channel_list.channel_listbox
            if hasattr(self.channel_list, 'search_entry'):
                self.channel_list.search_entry.set_text("")              
        elif active_sidebar == "favorites":
            target_listbox = self.favorites_view.get_favorite_channels_list_widget()
            if hasattr(self.favorites_view, 'fav_list_search_entry'):
                self.favorites_view.fav_list_search_entry.set_text("")
            if hasattr(self.favorites_view, 'favorite_channels_list') and hasattr(self.favorites_view.favorite_channels_list, 'search_entry'):
                self.favorites_view.favorite_channels_list.search_entry.set_text("")
        if not target_listbox:
            return
        row = target_listbox.get_first_child()
        while row:
            if hasattr(row, 'channel_data'):
                row_url = row.channel_data.get('url')
                if row_url == playing_url:
                    target_listbox.select_row(row)
                    if not self.is_immersive_fullscreen:
                        row.grab_focus()
                    return 
            row = row.get_next_sibling()
        if active_sidebar == "iptv":
            found_bouquet = self._find_bouquet_name_by_url(playing_url)
            if found_bouquet:
                logging.info(f"Sync: Channel found in bouquet '{found_bouquet}', switching...")
                self._show_channels_for_bouquet(found_bouquet)
                GLib.timeout_add(500, lambda: self._sync_sidebar_list_selection_delayed(playing_url, attempt=1))
        elif active_sidebar == "favorites":
            all_fav_lists = database.get_all_favorite_lists()
            found_list_id = None           
            for lst in all_fav_lists:
                l_id = lst['list_id']
                if database.is_channel_in_list(playing_url, l_id):
                    found_list_id = l_id
                    break           
            if found_list_id:
                fav_lists_box = self.favorites_view.favorite_lists_listbox
                row = fav_lists_box.get_first_child()              
                while row:
                    if hasattr(row, 'list_id') and str(row.list_id) == str(found_list_id):
                        logging.info(f"Sync: Loading Favorite List (ID: {found_list_id})...")
                        fav_lists_box.select_row(row)
                        fav_lists_box.emit("row-activated", row)                        
                        GLib.timeout_add(500, lambda: self._sync_sidebar_list_selection_delayed(playing_url, attempt=1))
                        break
                    row = row.get_next_sibling()

    def _sync_sidebar_list_selection_delayed(self, playing_url, attempt):
        target_listbox = None
        active_sidebar = self.sidebar.list_stack.get_visible_child_name()      
        if active_sidebar == "iptv":
            target_listbox = self.channel_list.channel_listbox
        elif active_sidebar == "favorites":
            target_listbox = self.favorites_view.get_favorite_channels_list_widget()          
        if not target_listbox:
            return False
        row = target_listbox.get_first_child()
        target_url_clean = playing_url.strip()
        while row:
            if hasattr(row, 'channel_data'):
                raw_url = row.channel_data.get('url', '')
                if raw_url.strip() == target_url_clean:
                    target_listbox.select_row(row)
                    if not self.is_immersive_fullscreen:
                        row.grab_focus()
                    return False
            row = row.get_next_sibling()
        if attempt < 10:
            GLib.timeout_add(500, lambda: self._sync_sidebar_list_selection_delayed(playing_url, attempt + 1))          
        return False                 

    def on_volume_changed(self, scale):
        self.player.set_volume(scale.get_value())

    def on_destroy(self, widget):
        self._hide_next_episode_prompt()
        if self.active_recorder:
            self.active_recorder.stop()
        self.stop_pip()
        self.inhibitor.uninhibit()
        self.subtitle_manager.clear()
        self.player.shutdown()

    def on_detail_view_play_requested(self, view, stream_id_or_path, media_type):
        """
        Handles play request from DetailView (VOD or Local Media).
        Checks for saved position before playing.
        """
        final_url = None
        db_key_for_check = None
        if media_type == 'media':
            final_url = stream_id_or_path
            db_key_for_check = final_url
        elif media_type == 'vod':
            if self.profile_data.get("type") == "xtream":
                logging.info(f"VOD (Xtream) play request received for stream_id: {stream_id_or_path}")
                db_key_for_check = str(stream_id_or_path)
                info_data = xtream_client.get_vod_info(self.profile_data, stream_id_or_path)
                if not info_data:
                    logging.error(f"Could not fetch VOD info (get_vod_info): {stream_id_or_path}")
                    self.show_toast(_("Error: Could not retrieve movie info."))
                    return
                movie_data = info_data.get('movie_data', {})
                final_url = movie_data.get('direct_source')
                if not final_url:
                    logging.warning(f"'direct_source' not found, creating manually.")
                    container_extension = movie_data.get('container_extension', 'ts')
                    host = self.profile_data.get('host')
                    username = self.profile_data.get('username')
                    password = self.profile_data.get('password')
                    final_url = f"{host}/movie/{username}/{password}/{stream_id_or_path}.{container_extension}"
                    logging.info(f"Manual VOD URL created: {final_url}")
            else:
                logging.info(f"VOD (M3U) play request received. URL is: {stream_id_or_path}")
                final_url = stream_id_or_path
                db_key_for_check = final_url
        if not final_url:
            logging.error("Could not create 'final_url' for playback.")
            return
        logging.debug(f"Checking playback position for key: {db_key_for_check}")
        saved_position = database.get_playback_position(db_key_for_check)
        if saved_position:
            minutes, seconds = divmod(int(saved_position), 60)
            time_str = f"{minutes}:{seconds:02d}"
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=_("Resume from Saved Position"),
                body=_("You last left this content at {}. Would you like to resume?").format(time_str)
            )
            dialog.add_css_class("resume-dialog")
            dialog.add_response("resume", _("Resume"))
            dialog.add_response("restart", _("Start Over"))
            dialog.set_default_response("resume")
            dialog.set_response_appearance("resume", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_close_response("restart")
            dialog.connect("response", self._on_resume_dialog_response, final_url, media_type, saved_position)
            dialog.present()
        else:
            self._start_playback(url=final_url, media_type=media_type)

    def _on_resume_dialog_response(self, dialog, response_id, url, media_type, position):
        """Handles the response from the resume dialog."""
        if response_id == "resume":
            self._start_playback(url=url, media_type=media_type, start_position=position)
        elif response_id == "restart":
            self._start_playback(url=url, media_type=media_type)

    def _on_resume_episode_dialog_response(self, dialog, response_id, url, episode_data, position):
        """Handles the response from the 'resume' dialog for TV episodes."""
        start_pos = None
        if response_id == "resume":
            start_pos = position
        self._start_playback(url=url, media_type='vod', start_position=start_pos, episode_data=episode_data)

    def on_detail_view_back_requested(self, view):
        active_nav = self.sidebar.list_stack.get_visible_child_name()
        if active_nav in ["vod", "media"]:
             self.main_content_stack.set_visible_child_name("library_view")
             self.media_search_entry.set_text("")
        else:
             self.main_content_stack.set_visible_child_name("placeholder_view")

    def on_epg_item_activated(self, video_view, program_data):
        thread = threading.Thread(target=self._show_epg_detail_thread, args=(program_data,), daemon=True)
        thread.start()

    def _show_epg_detail_thread(self, program_data):
        tmdb_data = None
        GLib.idle_add(self._present_epg_detail_dialog, program_data, tmdb_data)

    def _present_epg_detail_dialog(self, program_data, tmdb_data):
        dialog = EPGDetailDialog(self, program_data, tmdb_data)
        dialog.present()

    def _set_ui_panels_visibility(self, visible):
        """Shows/hides UI elements like the top bar, side panel, and controls."""
        self.header.set_visible(visible)
        self.sidebar.set_visible(visible)
        if hasattr(self, 'nav_rail_container'):
            self.nav_rail_container.set_visible(visible)
        if self.current_media_type == 'iptv':
            should_show_epg = visible and not self.is_immersive_fullscreen
            self.video_view.set_epg_visibility(should_show_epg)           
        if self.is_immersive_fullscreen:
            self.video_view.controls.set_visible(visible)
            if self.current_media_type == 'iptv' and hasattr(self.video_view, 'fullscreen_channel_list'):
                self.video_view.fullscreen_channel_list.set_visible(visible)
        else:
            self.video_view.controls.set_visible(True)
            if hasattr(self.video_view, 'fullscreen_channel_list'):
                self.video_view.fullscreen_channel_list.set_visible(False)

    def _on_mouse_motion(self, controller, x, y):
        """Runs when the mouse moves over the video area."""
        if not self.is_immersive_fullscreen:
            return
        if self.hide_panels_timer:
            GLib.source_remove(self.hide_panels_timer)
            self.hide_panels_timer = None
        self._set_ui_panels_visibility(True)
        self.hide_panels_timer = GLib.timeout_add_seconds(3, self._hide_panels_callback)

    def _hide_panels_callback(self):
        if self.is_immersive_fullscreen and hasattr(self.video_view, 'fullscreen_channel_list'):
            search_entry = self.video_view.fullscreen_channel_list.search_entry
            focused_widget = self.get_focus()
            if focused_widget and (focused_widget == search_entry or focused_widget.is_ancestor(search_entry)):
                return True 
        if self.is_immersive_fullscreen:
            self.video_view.controls.set_visible(False)
            if hasattr(self.video_view, 'fullscreen_channel_list'):
                self.video_view.fullscreen_channel_list.set_visible(False)
            self.get_surface().set_cursor(Gdk.Cursor.new_from_name("none", None))       
        self.hide_panels_timer = None
        return GLib.SOURCE_REMOVE

    def _on_video_area_clicked(self, video_view):
        """Toggles fullscreen mode when the video area is clicked."""
        if self.is_immersive_fullscreen:
            self.on_fullscreen_clicked(None)
        else:
            self.on_fullscreen_clicked(None)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        """Runs when keys are pressed and manages shortcuts."""
        key_name = Gdk.keyval_name(keyval)
        is_player_visible = self.main_content_stack.get_visible_child_name() == "player_view"
        if key_name == "Escape":
            if self.is_immersive_fullscreen:
                self.on_fullscreen_clicked(None)
                return True
        focused_widget = self.get_focus()
        if isinstance(focused_widget, Gtk.Editable):
             logging.debug(f"Key '{key_name}' pressed, but focus is on an Editable widget. Ignoring shortcut.")
             return False
        if key_name == "F11" or (is_player_visible and key_name == "f"):
            self.on_fullscreen_clicked(None)
            return True
        if not is_player_visible:
            return False
        if key_name == "space":
            self.on_play_pause_clicked(None)
            return True
        elif key_name == "Right":
            self._change_volume(0.05)
            return True
        elif key_name == "Left":
            self._change_volume(-0.05)
            return True
        elif key_name == "Up":
            self._play_previous_channel()
            return True
        elif key_name == "Down":
            self._play_next_channel()
            return True
        elif key_name == "m":
            self._toggle_mute()
            return True
        return False

    def _on_mouse_motion_for_cursor(self, controller, x, y):
        if not self.is_immersive_fullscreen:
            return
        if abs(x - self.last_mouse_x) < 1 and abs(y - self.last_mouse_y) < 1:
            return
        self.last_mouse_x = x
        self.last_mouse_y = y
        self.get_surface().set_cursor(None)
        if not self.video_view.controls.get_visible():
            self.video_view.controls.set_visible(True)
            if self.current_media_type == 'iptv' and hasattr(self.video_view, 'fullscreen_channel_list'):
                self.video_view.fullscreen_channel_list.set_visible(True)
        if self.hide_cursor_timer:
            GLib.source_remove(self.hide_cursor_timer)
            self.hide_cursor_timer = None
        if hasattr(self, 'hide_panels_timer') and self.hide_panels_timer:
            GLib.source_remove(self.hide_panels_timer)
        self.hide_panels_timer = GLib.timeout_add_seconds(4, self._hide_panels_callback)

    def _on_recording_stopped(self):
        """Called (on main thread) when the recording stop process (background) is finished."""
        logging.info("Recording stop process finished. Updating UI.")
        self.active_recorder = None
        self.is_stopping_recording = False
        record_button = self.video_view.controls.buttons.get("record")
        if record_button:
            record_button.set_sensitive(True)
        self.video_view.controls.set_recording_state(False)

    def _change_volume(self, delta):
        """Increases or decreases the volume by the given delta value."""
        controls = self.video_view.controls
        scale = controls.volume_scale
        current_value = scale.get_value()
        new_value = current_value + delta
        new_value = max(0.0, min(1.0, new_value))
        scale.set_value(new_value)
        controls.show_volume_popover_transiently()
        self.grab_focus()

    def _toggle_mute(self):
        """Mutes or restores the volume to its previous level."""
        scale = self.video_view.controls.volume_scale
        current_volume = scale.get_value()
        if current_volume > 0.01:
            self.last_volume_before_mute = current_volume
            scale.set_value(0.0)
        else:
            scale.set_value(self.last_volume_before_mute)

    def _play_next_channel(self):
        """Plays the next channel in the current list."""
        if self.is_immersive_fullscreen and hasattr(self.video_view, 'fullscreen_channel_list'):
            active_listbox = self.video_view.fullscreen_channel_list.channel_listbox
        else:
            active_listbox = self.channel_list.channel_listbox
            if self.sidebar.list_stack.get_visible_child_name() == "favorites":
                 active_listbox = self.favorites_view.get_favorite_channels_list_widget()
        selected_row = active_listbox.get_selected_row()
        if not selected_row: return
        current_index = selected_row.get_index()
        total_items = 0
        current_row = active_listbox.get_first_child()
        while current_row:
            total_items += 1
            current_row = current_row.get_next_sibling()
        if total_items == 0: return
        next_index = (current_index + 1) % total_items
        next_row = active_listbox.get_row_at_index(next_index)
        if next_row:
            active_listbox.select_row(next_row)
            channel_data = getattr(next_row, 'channel_data', None)
            if channel_data:
                 self._play_channel(channel_data)
            else:
                logging.warning("No channel data found on the next row.")

    def _play_previous_channel(self):
        """Plays the previous channel in the current list."""
        if self.is_immersive_fullscreen and hasattr(self.video_view, 'fullscreen_channel_list'):
            active_listbox = self.video_view.fullscreen_channel_list.channel_listbox
        else:
            active_listbox = self.channel_list.channel_listbox
            if self.sidebar.list_stack.get_visible_child_name() == "favorites":
                active_listbox = self.favorites_view.get_favorite_channels_list_widget()
        selected_row = active_listbox.get_selected_row()
        if not selected_row: return
        current_index = selected_row.get_index()
        total_items = 0
        current_row = active_listbox.get_first_child()
        while current_row:
            total_items += 1
            current_row = current_row.get_next_sibling()
        if total_items == 0: return
        prev_index = (current_index - 1 + total_items) % total_items
        prev_row = active_listbox.get_row_at_index(prev_index)
        if prev_row:
            active_listbox.select_row(prev_row)
            channel_data = getattr(prev_row, 'channel_data', None)
            if channel_data:
                self._play_channel(channel_data)
            else:
                 logging.warning("No channel data found on the previous row.")

    def on_show_shortcuts_clicked(self, button):
        """Creates and shows the keyboard shortcuts help window."""
        self.settings_popover.popdown()
        shortcuts_window = Gtk.ShortcutsWindow(
            transient_for=self,
            modal=True
        )
        shortcuts_window.add_css_class("shortcuts-window")
        header = Adw.HeaderBar()
        shortcuts_window.set_titlebar(header)
        shortcuts_window.set_title(_("Keyboard Shortcuts"))
        section = Gtk.ShortcutsSection()
        group_playback = Gtk.ShortcutsGroup(title=_("Playback Controls"))
        section.append(group_playback)
        shortcuts = [
            {"accelerator": "space", "title": _("Play / Pause")},
            {"accelerator": "Left", "title": _("Volume Down")},
            {"accelerator": "Right", "title": _("Volume Up")},
            {"accelerator": "M", "title": _("Mute / Unmute")},
            {"accelerator": "Down", "title": _("Next Channel")},
            {"accelerator": "Up", "title": _("Previous Channel")}
        ]
        for sc in shortcuts:
            shortcut_widget = Gtk.ShortcutsShortcut(accelerator=sc["accelerator"], title=sc["title"])
            group_playback.append(shortcut_widget)
        group_general = Gtk.ShortcutsGroup(title=_("General Controls"))
        section.append(group_general)
        shortcuts_general = [
            {"accelerator": "F", "title": _("Toggle Fullscreen")},
            {"accelerator": "F11", "title": _("Toggle Fullscreen")},
            {"accelerator": "Escape", "title": _("Exit Fullscreen")}
        ]
        for sc in shortcuts_general:
            shortcut_widget = Gtk.ShortcutsShortcut(accelerator=sc["accelerator"], title=sc["title"])
            group_general.append(shortcut_widget)
        shortcuts_window.set_child(section)
        shortcuts_window.present()

    def _perform_cache_clearing(self):
        """The main function that deletes the application's cache folder from disk."""
        cache_dir = database.get_cache_path()
        if os.path.isdir(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                logging.info(f"Cache folder successfully deleted: {cache_dir}")
                self.show_toast(
                    _("Cache cleared successfully!")
                )
                os.makedirs(cache_dir, exist_ok=True)
            except Exception as e:
                logging.error(f"Error occurred while clearing cache: {e}")
                self.show_toast(
                    _("Error while clearing cache!")
                )
        else:
            logging.info("Cache folder not found, already clean.")
            self.show_toast(
                _("Cache is already empty.")
            )
            try:
                 os.makedirs(cache_dir, exist_ok=True)
            except Exception as e:
                  logging.error(f"Could not create cache folder: {e}")

    def on_clear_cache_clicked(self, button):
        """Main trigger for the clear cache button."""
        self.settings_popover.popdown()
        password_is_set = database.get_config_value('app_password') is not None
        if password_is_set:
            prompt = PasswordPromptDialog(self)
            prompt.set_body(_("Please enter the password to clear the cache."))
            prompt.connect("response", self._on_clear_cache_password_response)
            prompt.present()
        else:
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=_("Confirm Cache Deletion"),
                body=_("This will permanently delete all cached data (posters, thumbnails, etc.).\n\nThis action cannot be undone. Are you sure?"),
                modal=True
            )
            dialog.add_css_class("delete-confirm-dialog")
            dialog.add_response("cancel", _("Cancel"))
            dialog.add_response("delete", _("Delete"))
            dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect("response", self._on_clear_cache_confirm_response)
            dialog.present()

    def _on_clear_cache_password_response(self, dialog, response_id):
        """Handles the response from the password prompt dialog."""
        if response_id == "ok":
            if database.check_password(dialog.get_password()):
                self._perform_cache_clearing()
            else:
                self.show_toast(_("Wrong Password!"))

    def _on_clear_cache_confirm_response(self, dialog, response_id):
        """Handles the response from the confirmation dialog (for non-password state)."""
        if response_id == "delete":
            self._perform_cache_clearing()

    def _on_series_categories_fetched(self, categories):
        """Called on the main thread after series categories are fetched."""
        if categories:
            self.series_categories_data = categories
            hidden_bouquets = database.get_hidden_bouquets()
            category_names = [
                cat.get('category_name', _('Unknown')) 
                for cat in categories
                if cat.get('category_name') not in hidden_bouquets
            ]          
            self.series_sidebar.populate_bouquets_async(category_names)
            self.show_toast(
                _("{} series categories found!").format(len(category_names))
            )
            self.series_view_placeholder.get_first_child().set_text(
                _("Please select a category from the left.")
            )
        else:
            self.show_toast(
                _("Could not fetch series categories or none found.")
            )
            self.series_view_placeholder.get_first_child().set_text(
                _("No series categories found for this profile.")
            )

    def _fetch_series_categories_thread(self):
        """Worker thread to fetch series categories from the API."""
        categories = xtream_client.get_series_categories(self.profile_data)
        GLib.idle_add(self._on_series_categories_fetched, categories)

    def on_series_category_selected(self, listbox, row):
        """Called when a user clicks on a series category in the sidebar."""
        if not row: return
        self.series_sidebar.search_entry.set_text("")
        self.player.pause()
        category_name = row.bouquet_name
        category_id = next(
            (cat.get('category_id') for cat in self.series_categories_data
             if cat.get('category_name', '').strip() == category_name.strip()),
            None
        )
        if category_id:
            logging.info(f"Series category '{category_name}' (ID: {category_id}) selected. Fetching series...")
            self.main_content_stack.set_visible_child_name("loading_view")
            self.loading_spinner.start()
            thread = threading.Thread(
                target=self._fetch_series_streams_thread,
                args=(category_id,),
                daemon=True
            )
            thread.start()
        else:
            logging.error(f"Could not find a category ID for name: '{category_name}'")

    def _fetch_series_streams_thread(self, category_id):
        """Worker thread to fetch series streams from the API for a category."""
        series_list = xtream_client.get_series_streams(self.profile_data, category_id)
        GLib.idle_add(self._on_series_streams_fetched, series_list)

    def _on_series_streams_fetched(self, series_list):
        """Called on the main thread after the list of series is fetched."""
        self.loading_spinner.stop()
        if series_list:
            self.media_search_entry.set_text("")
            self.media_grid_view.populate_async(series_list, media_type="series")
            self.main_content_stack.set_visible_child_name("library_view")
            self.back_button_box.set_visible(False)
            self.show_toast(
                _("Successfully fetched {} series!").format(len(series_list))
            )
        else:
            self.main_content_stack.set_visible_child_name("placeholder_view")
            self.show_toast(
                _("Could not fetch series for this category.")
            )

    def _fetch_series_info_thread(self, series_id):
        """Worker thread to fetch detailed series info from the API."""
        series_info = xtream_client.get_series_info(self.profile_data, series_id)
        GLib.idle_add(self._on_series_info_fetched, series_info, series_id)

    def _on_series_info_fetched(self, series_info, series_id):
        """Called on the main thread after detailed series info is fetched."""
        self.loading_spinner.stop()
        if series_info:
            self.series_detail_view.update_content(series_info, series_id)
            self.main_content_stack.set_visible_child_name("series_detail_view")
        else:
            self.main_content_stack.set_visible_child_name("placeholder_view")
            self.show_toast(
                _("Could not fetch series info.")
            )

    def on_series_detail_back_requested(self, view):
        """Handles the back button press from the SeriesDetailView."""
        self.main_content_stack.set_visible_child_name("library_view")
        self.media_search_entry.set_text("")

    def on_episode_activated(self, view, episode_data):
        """
        Handles the episode playback signal.
        Checks for saved position before playing.
        (Corrected to use db_key for recording)
        """
        episode_title = episode_data.get('title', 'Unknown Episode')
        logging.debug(f"on_episode_activated called: {episode_title}")
        final_url = None
        episode_stream_id_str = None
        final_url = episode_data.get('direct_source')
        if not final_url:
            episode_stream_id = episode_data.get('id') or episode_data.get('stream_id')
            container_extension = episode_data.get('container_extension')
            if episode_stream_id and container_extension:
                host = self.profile_data.get('host')
                username = self.profile_data.get('username')
                password = self.profile_data.get('password')
                final_url = f"{host}/series/{username}/{password}/{episode_stream_id}.{container_extension}"
                episode_stream_id_str = str(episode_stream_id)
                logging.debug(f"Manual URL created: {final_url} (Key: {episode_stream_id_str})")
            else:
                 logging.error(f"Critical error: 'id'/'stream_id' or 'container_extension' not found in episode data!")
                 self.show_toast(_("Error: Episode ID/Format not found."))
                 return
        if not final_url:
            logging.error("Could not create 'final_url' for playback.")
            return
        db_key_for_check = episode_stream_id_str if episode_stream_id_str else final_url
        logging.debug(f"Checking position (Key: {db_key_for_check})")
        try:
            saved_position = database.get_playback_position(db_key_for_check)
            logging.debug(f"Position found: {saved_position}")
            if saved_position:
                logging.info(f"Saved position found: {saved_position}s. Showing dialog.")
                minutes, seconds = divmod(int(saved_position), 60)
                time_str = f"{minutes}:{seconds:02d}"
                dialog = Adw.MessageDialog(
                    transient_for=self,
                    heading=_("Resume from Saved Position"),
                    body=_("You last left this episode at {}. Would you like to resume?").format(time_str)
                )
                dialog.add_css_class("resume-dialog")
                dialog.add_response("resume", _("Resume"))
                dialog.add_response("restart", _("Start Over"))
                dialog.set_default_response("resume")
                dialog.set_response_appearance("resume", Adw.ResponseAppearance.SUGGESTED)
                dialog.set_close_response("restart")
                dialog.connect("response", self._on_resume_episode_dialog_response, final_url, episode_data, saved_position)
                dialog.present()
            else:
                logging.info("Saved position not found or < 10s. Starting from beginning.")
                self._start_playback(url=final_url, media_type='vod', episode_data=episode_data)
        except Exception as e:
             logging.error(f"Error during position check/dialog: {e}", exc_info=True)
             logging.info("Starting episode from beginning due to error.")
             self._start_playback(url=final_url, media_type='vod', episode_data=episode_data)

    def _fetch_vod_categories_thread(self):
        """Worker thread to fetch VOD categories from the API."""
        categories = xtream_client.get_vod_categories(self.profile_data)
        GLib.idle_add(self._on_vod_categories_fetched, categories)

    def _on_vod_categories_fetched(self, categories):
        """Called on the main thread after VOD categories are fetched."""
        if categories:
            self.vod_categories_data = categories
            hidden_bouquets = database.get_hidden_bouquets()           
            category_names = [
                cat.get('category_name', _('Unknown')) 
                for cat in categories
                if cat.get('category_name') not in hidden_bouquets
            ]           
            self.vod_category_list.populate_bouquets_async(category_names)
            self.show_toast(
                _("{} VOD categories found!").format(len(categories))
            )
        else:
            self.show_toast(
                _("Could not fetch VOD categories or none found.")
            )

    def _fetch_vod_streams_thread(self, category_id):
        """Worker thread to fetch VOD streams from the API for a category."""
        all_vod_streams = xtream_client.get_vod_streams(self.profile_data)
        if category_id == "all" or not category_id:
            vod_list = all_vod_streams
        else:
            vod_list = [
                stream for stream in all_vod_streams
                if str(stream.get('category_id')) == str(category_id)
            ]
        GLib.idle_add(self._on_vod_streams_fetched, vod_list, category_id)

    def _on_vod_streams_fetched(self, vod_list, category_id):
        """Called on the main thread after the list of VOD streams is fetched."""
        self.loading_spinner.stop()
        if vod_list:
            self.media_search_entry.set_text("")
            self.media_grid_view.populate_async(vod_list, media_type="vod")
            self.main_content_stack.set_visible_child_name("library_view")
            self.back_button_box.set_visible(False)
            self.show_toast(
                _("Successfully fetched {} VOD items for category {}!").format(len(vod_list), category_id)
            )
        else:
            self.main_content_stack.set_visible_child_name("placeholder_view")
            self.show_toast(
                _("Could not fetch VOD streams for this category.")
            )

    def _move_cache_thread(self, old_path, new_path):
        """
        (Background Thread) Physically moves the cache folder.
        """
        try:
            shutil.move(old_path, new_path)
            GLib.idle_add(self._on_move_cache_success, new_path)
        except Exception as e:
            logging.error(f"ERROR moving cache: {e}")
            GLib.idle_add(self._on_move_cache_failed, str(e))

    def _on_move_cache_success(self, new_path):
        """
        (Main Thread) Runs when the move is successful.
        """
        logging.info(f"Cache successfully moved. Updating database: {new_path}")
        database.set_config_value('cache_path', new_path)
        self.get_root().set_sensitive(True)
        self.show_toast(
            _("Cache successfully moved and new path set.")
        )

    def _on_move_cache_failed(self, error_message):
        """
        (Main Thread) Runs when the move fails.
        """
        logging.error("Cache move failed. Retaining old path setting.")
        self.get_root().set_sensitive(True)
        self.show_toast(
            _("ERROR: Cache could not be moved. Check permissions.\nReason: {}").format(error_message)
        )

    def _on_tmdb_toggle_changed(self, switch_row, pspec):
        """Saves the setting to the database when the TMDb usage switch changes."""
        is_active = switch_row.get_active()
        database.set_config_value('use_tmdb_metadata', '1' if is_active else '0')
        if is_active:
            self.show_toast(
                _("TMDb metadata usage enabled.")
            )
            if not database.get_config_value("tmdb_api_key"):
                 self.show_toast(
                     _("Warning: You have not entered a TMDb API key yet.")
                 )
        else:
            self.show_toast(
                _("TMDb metadata usage disabled.")
            )

    def _on_poster_cache_toggle_changed(self, switch_row, pspec):
        """Saves the setting when the poster disk cache usage switch changes."""
        is_active = switch_row.get_active()
        database.set_config_value('use_poster_disk_cache', '1' if is_active else '0')
        if is_active:
            self.show_toast(
                _("Poster disk cache enabled.")
            )
        else:
            self.show_toast(
                 _("Poster disk cache disabled.")
            )

    def _on_media_search_changed(self, entry):
        """
        Triggers the filter as the media grid search bar changes.
        """
        search_text = entry.get_text()
        self.media_grid_view.set_search_text(search_text)

    def _mask_api_key(self, api_key):
        """Hides the middle of an API key, showing only the beginning and end."""
        if not api_key or len(api_key) < 8:
            return api_key
        masked_part = '*' * (len(api_key) - 7)
        return f"{api_key[:4]}{masked_part}{api_key[-3:]}"

    def _show_next_episode_prompt(self, episode_data):
        """Shows the next episode prompt and starts the hide timer."""
        if self.video_view.next_episode_box.is_visible():
            return
        if self.next_episode_prompt_timer_id:
            GLib.source_remove(self.next_episode_prompt_timer_id)
            self.next_episode_prompt_timer_id = None
        self.next_episode_data_to_play = episode_data
        prompt_box = self.video_view.next_episode_box
        prompt_label = self.video_view.next_episode_label
        title = episode_data.get('title', _('Next Episode'))
        season = episode_data.get('season', '')
        episode_num = episode_data.get('episode_num', '')
        prompt_label.set_markup(f"<small>{_('Next:')}</small>\n<b>S{season}E{episode_num} - {GLib.markup_escape_text(title)}</b>")
        prompt_box.set_visible(True)
        prompt_hide_delay = 120
        self.next_episode_prompt_timer_id = GLib.timeout_add_seconds(prompt_hide_delay, self._hide_next_episode_prompt)
        logging.debug(f"Next episode prompt shown, will hide in {prompt_hide_delay}s.")

    def _on_cancel_auto_play_clicked(self, button):
        """
        Cancels auto-play when the 'Cancel' button on the prompt is clicked
        AND marks the current episode as 'watched'.
        """
        logging.info("Auto-play to next episode cancelled (user request).")
        self.auto_play_cancelled = True
        self._hide_next_episode_prompt()
        media_path_to_finish = self.current_playing_media_path
        if media_path_to_finish:
            logging.info(f"'Cancel' used. Marking episode '{media_path_to_finish}' as finished (is_finished=1).")
            database.save_playback_progress(
                media_path_to_finish,
                position=0,
                is_finished=1
            )
            self.current_playing_media_path = None
            logging.debug("current_playing_media_path set to 'None' to prevent overwriting position save.")
        else:
            logging.warning("'Cancel' used but 'current_playing_media_path' (finished episode ID) not found.")

    def _on_skip_to_next_episode_clicked(self, button):
        """Runs when the 'Skip Now' button is clicked."""
        logging.critical("!!!! _on_skip_to_next_episode_clicked CALLED !!!!")
        logging.info("'Skip Now' button pressed.")
        media_path_to_finish = self.current_playing_media_path
        if media_path_to_finish:
            logging.info(f"'Skip Now' used. Marking episode '{media_path_to_finish}' as finished (is_finished=1).")
            database.save_playback_progress(
                media_path_to_finish,
                position=0,
                is_finished=1
            )
            self.current_playing_media_path = None
            logging.debug("current_playing_media_path set to 'None' to prevent overwriting position save.")
        else:
            logging.warning("'Skip Now' used but 'current_playing_media_path' (finished episode ID) not found.")
        if self.next_episode_data_to_play:
            self.currently_playing_episode_data = None
            self.auto_play_cancelled = False
            self._hide_next_episode_prompt()
            self.player.shutdown()
            self.play_next_series_episode(self.next_episode_data_to_play)
            self.next_episode_data_to_play = None
        else:
            logging.warning("'Skip Now' pressed but no next episode data was found.")
            self._hide_next_episode_prompt()

    def _hide_next_episode_prompt(self):
        """Stops the hide timer (if active) and hides the prompt."""
        if self.next_episode_prompt_timer_id:
            GLib.source_remove(self.next_episode_prompt_timer_id)
            self.next_episode_prompt_timer_id = None
            logging.debug("Next episode prompt hide timer stopped.")
        if hasattr(self, 'video_view') and hasattr(self.video_view, 'next_episode_box'):
             self.video_view.next_episode_box.set_visible(False)
        return GLib.SOURCE_REMOVE

    def on_trailer_requested(self, view, youtube_key):
        """Handles the trailer request from DetailView or SeriesDetailView."""
        logging.info(f"Trailer playback requested for YouTube key: {youtube_key}")
        youtube_url = f"https://www.youtube.com/watch?v={youtube_key}"
        self.return_view_after_trailer = self.main_content_stack.get_visible_child_name()
        self.is_playing_trailer = True
        logging.debug(f"Trailer mode activated. Will return to: {self.return_view_after_trailer}")
        self.show_toast(_("Trailer URL is being retrieved..."))
        self.set_sensitive(False)
        thread = threading.Thread(target=self._get_trailer_stream_url_thread, args=(youtube_url,), daemon=True)
        thread.start()

    def _get_trailer_stream_url_thread(self, youtube_watch_url):
        """(Background Thread) Uses yt-dlp to get the stream URL."""
        trailer_stream_url = None
        error_message = None
        try:
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios']
                    }
                },
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                },
                'geo_bypass': True,
                'ignoreerrors': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_watch_url, download=False)
                if info:
                    if 'url' in info:
                        trailer_stream_url = info['url']
                    elif 'entries' in info:
                        trailer_stream_url = info['entries'][0].get('url')
                    elif 'formats' in info:
                        trailer_stream_url = info['formats'][-1].get('url')
                if trailer_stream_url:
                    logging.info(f"Successfully extracted trailer stream URL: {trailer_stream_url[:50]}...")
                else:
                    logging.error("yt-dlp did not return a stream URL in 'url' key.")
                    error_message = _("Playable URL not found for trailer.")
        except yt_dlp.utils.DownloadError as e:
            logging.error(f"yt-dlp download error: {e}")
            error_message = _("Could not retrieve trailer (yt-dlp error).")
        except Exception as e:
            logging.exception(f"Unexpected error during yt-dlp trailer extraction: {e}")
            error_message = _("An unknown error occurred while retrieving the trailer.")
        GLib.idle_add(self._on_trailer_stream_url_received, trailer_stream_url, error_message)

    def _on_trailer_stream_url_received(self, stream_url, error):
        """(Main Thread) Handles the stream URL or error from the background thread."""
        self.set_sensitive(True)
        if error:
            self.show_toast(error)
            self.is_playing_trailer = False
            self.return_view_after_trailer = None
            controls = self.video_view.controls
            controls.set_stop_trailer_button_visibility(False)
        elif stream_url:
            self.show_toast(_("Playing trailer..."))
            self._start_playback(url=stream_url, media_type='vod', channel_data=None, start_position=None, is_trailer=True)
        else:
            self.show_toast(_("Error: A valid trailer URL could not be retrieved."))
            self.is_playing_trailer = False
            self.return_view_after_trailer = None
            controls = self.video_view.controls
            controls.set_stop_trailer_button_visibility(False)

    def on_stop_trailer_clicked(self, controls):
        """Handles the 'Stop Trailer' signal from PlayerControls."""
        logging.info("Stop Trailer button clicked. Returning to detail view.")
        if self.is_playing_trailer:
            self.player.shutdown()
            self.is_playing_trailer = False
            controls.set_stop_trailer_button_visibility(False)
            self.inhibitor.uninhibit()
            if self.return_view_after_trailer:
                self.main_content_stack.set_visible_child_name(self.return_view_after_trailer)
            else:
                self.main_content_stack.set_visible_child_name("placeholder_view")
            self.return_view_after_trailer = None

    def on_pip_requested(self, channel_list_widget, url):
        """Handles the PiP request from ChannelList and starts PiP."""
        logging.info(f"PiP requested via signal for URL: {url}")
        if self.pip_window:
            self.stop_pip()
        self.start_pip(url)

    def start_pip(self, url):
        """Starts the PiP window and player for the given URL."""
        if not url:
            logging.warning("start_pip called with empty URL.")
            return
        if not self.pip_window:
            try:
                from ui.pip_window import PipWindow
                self.pip_window = PipWindow()
                logging.info("PipWindow: set_transient_for(self) called.")
                def on_pip_close_request(win):
                    self.stop_pip(called_from_destroy=True)
                    return False              
                self.pip_window.connect("close-request", on_pip_close_request)
            except Exception as e:
                logging.exception(f"Error creating PiP window: {e}")
                self.show_toast(_("Error: Could not create PiP window."))
                return
        if self.pip_player: self.pip_player.shutdown()
        try:
             self.pip_player = Player()
             self.pip_player.connect("stream-started", self._on_pip_stream_started)
        except Exception as e:
             return
        if self.pip_window and hasattr(self.pip_window, 'set_paintable'):
            self.pip_player.connect("paintable-changed", self._on_pip_paintable_changed)
            self.pip_window.set_paintable(self.pip_player.paintable)
            self.pip_player.set_volume(0.0)
            logging.info("PiP player created, paintable linked, volume set to 0.")
        else:
             return
        self.pip_player.play_url(url)
        self.pip_player.play()
        self.pip_window.present()

    def _on_pip_paintable_changed(self, player, new_paintable):
        """Connects the new paintable from the PiP player to the PiP window."""
        if self.pip_window and hasattr(self.pip_window, 'set_paintable'):
            self.pip_window.set_paintable(new_paintable)

    def stop_pip(self, called_from_destroy=False):
        """Stops/closes the PiP player and window."""
        logging.info("Stopping PiP...")
        player_stopped = False
        if self.pip_player:
            self.pip_player.shutdown()
            self.pip_player = None
            player_stopped = True
        window_closed = False
        if self.pip_window:
            if not called_from_destroy:
                 self.pip_window.close()
            self.pip_window = None
            window_closed = True
        return player_stopped or window_closed

    def _on_pip_stream_started(self, player):
        """Resets the volume to zero when the PiP player starts playing."""
        if self.pip_player == player:
            logging.debug("PiP stream started, ensuring volume is 0.0 again.")
            self.pip_player.set_volume(0.0)
        else:
            logging.warning("_on_pip_stream_started called for unexpected player.")

    def on_collection_item_right_clicked(self, grid_view, item, widget):
        """
        Runs when an item in the library/collection grid is right-clicked.
        (e.g., "My Movies" folder)
        """
        menu_model = Gio.Menu()
        menu_model.append(_("Remove Library"), "item.remove_library")
        popover = Gtk.PopoverMenu.new_from_model(menu_model)
        popover.set_parent(widget)
        action_group = Gio.SimpleActionGroup()
        remove_action = Gio.SimpleAction.new("remove_library", None)
        remove_action.connect("activate", self._on_remove_library_action, item)
        action_group.add_action(remove_action)
        widget.insert_action_group("item", action_group)
        popover.popup()

    def _on_remove_library_action(self, action, value, item):
        """Shows the confirmation dialog when the 'Remove Library' menu action is selected."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_("Confirm Library Removal"),
            body=_("The library '{}' and all its media records will be removed from EngPlayer.\n\nNote: Your original files will NOT be deleted from disk.\n\nAre you sure?").format(item.props.name),
            modal=True
        )
        dialog.add_css_class("delete-confirm-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_remove_library_confirm, item)
        dialog.present()

    def _on_remove_library_confirm(self, dialog, response_id, item):
        """Runs when library deletion is confirmed."""
        if response_id == "remove":
            library_id = item.props.db_id
            logging.info(f"User confirmed library removal (ID: {library_id})...")
            if database.delete_library(library_id):
                self.show_toast(_("Library successfully removed."))
                active_button_key = self.media_sidebar.buttons["videos"]
                for key, btn in self.media_sidebar.buttons.items():
                    if btn.has_css_class("active-nav-button"):
                        active_button_key = key
                        break
                media_type = self.active_media_type
                libraries = database.get_libraries_by_type(media_type)
                self.collection_grid_view.populate_collections(libraries)
            else:
                self.show_toast(_("Error: An issue occurred while removing the library."))

    def on_media_item_right_clicked(self, grid_view, item, widget):
        """
        Runs when an item in the media (Video/Picture) grid is right-clicked.
        """
        menu_model = Gio.Menu()
        menu_model.append(_("Remove from Records"), "item.remove_media")
        popover = Gtk.PopoverMenu.new_from_model(menu_model)
        popover.set_parent(widget)
        action_group = Gio.SimpleActionGroup()
        remove_action = Gio.SimpleAction.new("remove_media", None)
        remove_action.connect("activate", self._on_remove_media_file_action, item)
        action_group.add_action(remove_action)
        widget.insert_action_group("item", action_group)
        popover.popup()

    def _on_remove_media_file_action(self, action, value, item):
        """Shows the confirmation dialog for the 'Remove from Records' (Video/Picture) menu action."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_("Confirm Media Record Removal"),
            body=_("The record for '{}' will be removed from EngPlayer.\n\nNote: Your original file will NOT be deleted from disk.\n\nAre you sure?").format(item.props.title),
            modal=True
        )
        dialog.add_css_class("delete-confirm-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_remove_media_file_confirm, item)
        dialog.present()

    def _on_remove_media_file_confirm(self, dialog, response_id, item):
        """Runs when Video/Picture record deletion is confirmed."""
        if response_id == "remove":
            file_path = item.props.path_or_url
            if database.delete_media_file_record(file_path):
                self.show_toast(_("Media record removed."))
                ok, pos = self.media_grid_view.model.find(item)
                if ok:
                    self.media_grid_view.model.remove(pos)
                else:
                    logging.warning(f"Deleted media ({file_path}) not found in UI model, refresh may be needed.")
            else:
                self.show_toast(_("Error: An issue occurred while removing the media record."))

    def on_track_item_right_clicked(self, track_view, item_data, row_widget):
        """
        Runs when an item in the track (Music) list is right-clicked.
        """
        menu_model = Gio.Menu()
        menu_model.append(_("Remove Track from Library"), "item.remove_track")
        popover = Gtk.PopoverMenu.new_from_model(menu_model)
        popover.set_parent(row_widget)
        action_group = Gio.SimpleActionGroup()
        remove_action = Gio.SimpleAction.new("remove_track", None)
        remove_action.connect("activate", self._on_remove_track_action, item_data, row_widget)
        action_group.add_action(remove_action)
        row_widget.insert_action_group("item", action_group)
        popover.popup()

    def _on_remove_track_action(self, action, value, item_data, row_widget):
        """Shows the confirmation dialog for the 'Remove Track' (Music) menu action."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_("Confirm Track Record Removal"),
            body=_("The record for '{}' will be removed from EngPlayer.\n\nNote: Your original file will NOT be deleted from disk.\n\nAre you sure?").format(item_data['title']),
            modal=True
        )
        dialog.add_css_class("delete-confirm-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_remove_track_confirm, item_data, row_widget)
        dialog.present()

    def _on_remove_track_confirm(self, dialog, response_id, item_data, row_widget):
        """Runs when track record deletion is confirmed."""
        if response_id == "remove":
            file_path = item_data['file_path']
            if database.delete_track_record(file_path):
                self.show_toast(_("Track record removed."))
                self.track_list_view.track_listbox.remove(row_widget)
                if item_data in self.track_list_view.current_tracks:
                    self.track_list_view.current_tracks.remove(item_data)
            else:
                self.show_toast(_("Error: An issue occurred while removing the track record."))

    def _on_remove_recording_record_action(self, action, value, item):
        """Shows the confirmation dialog for 'Remove from List' (Recorded Video) menu action."""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_("Confirm Removal from Recordings List"),
            body=_("The video record '{}' will be removed from the list.\n\nNote: Your original video file will NOT be deleted from disk.\n\nAre you sure?").format(os.path.basename(item.path_or_url)),
            modal=True
        )
        dialog.add_css_class("delete-confirm-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_remove_recording_record_confirm, item)
        dialog.present()

    def _on_remove_recording_record_confirm(self, dialog, response_id, item):
        """Runs when removal of a recorded video record from the LIST is confirmed."""
        if response_id == "remove":
            try:
                model = self.recordings_grid_view.model
                ok, pos = model.find(item)
                if ok:
                    model.remove(pos)
                    self.show_toast(_("Recording removed from list."))
                else:
                    logging.warning(f"Recording to be removed from list ({item.props.path_or_url}) not found in model.")
                    self.show_toast(_("Error: Recording not found in list."))
            except Exception as e:
                logging.error(f"Error while removing recording from list: {e}")
                self.show_toast(_("Error: Recording was not removed from list."))

    def _clean_key(self, text):
        if not text:
            return None
        name = text.lower().strip()
        match = re.match(r'^([a-z]{2,3})[| \-_]+(.*)', name)
        if match:
            lang_code = match.group(1)
            rest_of_name = match.group(2)
            common_codes = [
                "tr", "us", "uk", "fr", "de", "it", "es", "pt", "nl", "be", 
                "ru", "gr", "az", "ch", "at", "pl", "ro", "bg", "hu", "cz", 
                "sk", "al", "rs", "hr", "ba", "mk", "se", "no", "dk", "fi", 
                "ie", "ca", "au", "nz", "br", "ar", "mx", "ae", "sa", "eg",
                "tur", "usa", "gbr", "fra", "deu", "ita", "esp", "prt", "nld", "bel",
                "rus", "grc", "aze", "che", "aut", "pol", "rou", "bgr", "hun", "cze"
            ]           
            if lang_code in common_codes:
                name = f"{rest_of_name}.{lang_code}"
        try:
            name = unicodedata.normalize("NFKD", name)
            name = "".join([c for c in name if not unicodedata.combining(c)])
        except Exception:
             pass
        name = re.sub(r'(\(.*\))|(\[.*?\])|(".*?")|(\=.*)', ' ', name)
        name = re.sub(r'\b(HD|FHD|UHD|4K|8K|SD)\b', ' ', name, flags=re.IGNORECASE)
        name = re.sub(r'[^\w\d\s.]+', ' ', name)
        name = re.sub(r'\s+', '', name)       
        return name.strip().lower()

    def _build_logo_map(self, folder_path):
        if not folder_path or not os.path.isdir(folder_path):
            logging.warning(f"Could not build logo map: Invalid folder path: {folder_path}")
            return {}
        logging.info(f"Scanning '{folder_path}' to build logo map...")
        logo_map = {}
        try:
            for root, dirs, files in os.walk(folder_path):
                for filename in files:
                    if not filename.lower().endswith(('.png', '.svg')):
                        continue
                    name_raw = os.path.splitext(filename)[0]
                    clean_name_key = self._clean_key(name_raw)
                    if clean_name_key:
                        full_path = os.path.join(root, filename)
                        if clean_name_key not in logo_map:
                             logo_map[clean_name_key] = full_path
        except Exception as e:
            logging.error(f"Error occurred while building logo map: {e}")
        logging.info(f"Logo map built. {len(logo_map)} unique logos found.")
        logging.debug("\n[DEBUG] Logo Map Key Sample (first 5):")
        try:
            for i, key in enumerate(logo_map.keys()):
                if i >= 5:
                    break
                logging.debug(f"  -> Map Key: '{key}'")
        except Exception as e:
            logging.debug(f"  -> Could not print map keys: {e}")
        return logo_map

    def _on_theme_combo_changed(self, combo):
        """Saves the theme setting and forces a restart."""
        active_id = combo.get_active_id()
        database.set_config_value('app_theme', active_id)
        logging.info(f"Theme setting saved to: {active_id}")
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_("Restart Required"),
            body=_("Theme settings have been saved.\n\nThe application will now restart for the changes to take effect."),
            modal=True
        )
        dialog.add_response("restart", _("Restart Now"))
        dialog.set_default_response("restart")
        dialog.set_close_response("restart")
        dialog.set_response_appearance("restart", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_restart_dialog_response)
        dialog.present()

    def _on_restart_dialog_response(self, dialog, response_id):
        """Handles the response from the restart dialog."""
        dialog.close()
        logging.info("Restarting application to apply theme changes...")
        try:
            logging.info("Shutting down current resources...")
            self.on_destroy(self)
        except Exception as e:
            logging.error(f"Error during pre-restart cleanup: {e}")
        python_executable = sys.executable
        script_args = sys.argv
        logging.info(f"Issuing restart command: {python_executable} {' '.join(script_args)}")
        os.execv(python_executable, [python_executable] + script_args)

    def show_toast(self, message, is_urgent=False, duration=None):
        if not is_urgent and not database.get_notifications_enabled():
            return
        if duration is not None:
            timeout_sec = duration
        else:
            timeout_sec = database.get_notification_timeout()
        toast = Adw.Toast.new(message)
        toast.set_timeout(timeout_sec)       
        current_toast = self.toast_overlay.get_child()
        if hasattr(self, "current_active_toast") and self.current_active_toast:
            try:
                self.current_active_toast.dismiss()
            except:
                pass
        self.current_active_toast = toast
        toast.connect("dismissed", self._on_toast_dismissed)
        self.toast_overlay.add_toast(toast)

    def _on_toast_dismissed(self, toast):
        if hasattr(self, "current_active_toast") and self.current_active_toast == toast:
            self.current_active_toast = None

    def _on_notif_toggle_changed(self, switch_row, pspec):
        is_enabled = switch_row.get_active()
        val = '1' if is_enabled else '0'
        database.set_config_value('notifications_enabled', val)
        msg = _("Notifications enabled.") if is_enabled else _("Notifications disabled.")
        self.show_toast(msg, is_urgent=True)

    def _on_notif_duration_changed(self, spin_button):
        seconds = int(spin_button.get_value())
        database.set_config_value('notification_timeout', str(seconds))

    def on_media_item_watched_toggled(self, grid_view, item, is_watched):
        path_or_id = item.props.path_or_url
        if not path_or_id: return
        logging.info(f"Toggle watched status for '{item.props.title}' (ID: {path_or_id}) -> {is_watched}")
        if is_watched:
            database.save_playback_progress(path_or_id, position=0, is_finished=1)
        else:
            database.delete_playback_position(path_or_id)
            
    def apply_accent_color(self, color_str):
        if not color_str: return
        css_provider = Gtk.CssProvider()
        css_data = f"""
        @define-color accent_color {color_str}; 
        @define-color accent_bg_color {color_str}; 
        @define-color accent_fg_color #ffffff; 
        """       
        try:
            css_provider.load_from_data(css_data.encode())
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        except Exception as e:
            logging.error(f"Error applying accent color: {e}") 
            
    def on_open_video_settings_clicked(self, button):
        self.settings_popover.popdown()
        if self.video_settings_win:
            self.video_settings_win.present()
            return
        self.video_settings_win = VideoSettingsWindow(self.player)
        self.video_settings_win.set_transient_for(self)
        self.video_settings_win.connect("close-request", self._on_video_settings_close)       
        self.video_settings_win.present()
        
    def on_open_category_manager(self, button):
        self.settings_popover.popdown()
        live_cats = list(self.bouquets_data.keys()) if self.bouquets_data else []
        vod_cats = []
        if self.profile_data.get("type") == "xtream":
            vod_cats = [c.get('category_name') for c in self.vod_categories_data if c.get('category_name')]
        elif self.vod_data:
            vod_cats = list(self.vod_data.keys())
        series_cats = []
        if self.series_categories_data:
             series_cats = [c.get('category_name') for c in self.series_categories_data if c.get('category_name')]
        dialog = CategoryManagerDialog(self, live_cats, vod_cats, series_cats)
        dialog.connect("close-request", self._on_category_manager_closed)
        dialog.present()

    def _on_category_manager_closed(self, dialog):
        logging.info("Category manager closed. Refreshing lists...")      
        hidden_bouquets = database.get_hidden_bouquets()
        if self.bouquets_data:
            visible_bouquets = [b for b in self.bouquets_data.keys() if b not in hidden_bouquets]
            self.bouquet_list.populate_bouquets_async(visible_bouquets)
        self._refresh_vod_list()
        if self.series_categories_data:
             cats = [
                 c.get('category_name') for c in self.series_categories_data
                 if c.get('category_name') not in hidden_bouquets
             ]
             self.series_sidebar.populate_bouquets_async(cats)
        if self.is_immersive_fullscreen:
             self._populate_fullscreen_categories()         
        return False  

    def _on_video_settings_close(self, window):
        self.video_settings_win = None
        return False          
            
    def _on_open_color_picker(self, *args):
        self.settings_popover.popdown()
        dialog = Gtk.ColorChooserDialog(title=_("Select Accent Color"), transient_for=self)
        dialog.set_modal(True)
        current_color_str = database.get_config_value("app_accent_color") or "#3584e4"
        try:
            rgba = Gdk.RGBA()
            rgba.parse(current_color_str)
            dialog.set_rgba(rgba)
        except:
            pass
        dialog.connect("response", self._on_color_dialog_response)
        dialog.present()

    def _on_color_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            rgba = dialog.get_rgba()
            color_hex = "#{:02x}{:02x}{:02x}".format(
                int(rgba.red * 255),
                int(rgba.green * 255),
                int(rgba.blue * 255)
            )          
            logging.info(f"User selected new accent color: {color_hex}")
            database.set_config_value("app_accent_color", color_hex)
            self.apply_accent_color(color_hex)
            self.show_toast(_("Accent color updated!"))           
        dialog.destroy()  
        
    def on_podcast_list_back_clicked(self, widget):
        self.media_stack.set_visible_child_name("sidebar")
        for btn in self.media_sidebar.buttons.values():
            btn.remove_css_class("active-nav-button")

    def on_podcast_selected(self, widget, pod_id, title, url):
        logging.info(f"Podcast selected: {title} ({url})")
        self.main_content_stack.set_visible_child_name("podcast_detail_view")
        self.podcast_detail_view.show_loading()
        
        thread = threading.Thread(
            target=self._fetch_rss_thread,
            args=(url,),
            daemon=True
        )
        thread.start()

    def _fetch_rss_thread(self, url):
        data = rss_parser.parse_podcast_feed(url)
        GLib.idle_add(self._on_rss_fetched, data)

    def _on_rss_fetched(self, data):
        if data:
            self.podcast_detail_view.populate(data)
        else:
            self.show_toast(_("Error loading podcast feed."))
            self.main_content_stack.set_visible_child_name("placeholder_view")  
            
    def on_podcast_episode_clicked(self, view, url, title):
        logging.info(f"Podcast episode clicked: {title}")
        db_key = url     
        saved_position = database.get_playback_position(db_key)       
        if saved_position:
            minutes, seconds = divmod(int(saved_position), 60)
            time_str = f"{minutes}:{seconds:02d}"           
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=_("Resume Podcast"),
                body=_("You listened to this episode until {}. Resume?").format(time_str)
            )
            dialog.add_css_class("resume-dialog")
            dialog.add_response("resume", _("Resume"))
            dialog.add_response("restart", _("Start Over"))
            dialog.set_default_response("resume")
            dialog.set_response_appearance("resume", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_close_response("restart")
            dialog.connect("response", self._on_resume_podcast_response, url, title, saved_position)
            dialog.present()
        else:
            self._start_podcast_playback(url, title)

    def _on_resume_podcast_response(self, dialog, response_id, url, title, position):
        start_pos = position if response_id == "resume" else 0
        self._start_podcast_playback(url, title, start_pos)

    def _start_podcast_playback(self, url, title, start_pos=0):
        self.main_content_stack.set_visible_child_name("player_view")
        self._start_playback(
            url=url, 
            media_type='music', 
            channel_data={'name': title}, 
            start_position=start_pos
        )
        
    def on_podcast_feed_selected(self, widget, pod_id, title, url):
        logging.info(f"Opening podcast feed: {title}")
        self.media_stack.set_visible_child_name("podcast_episodes")
        self.podcast_episode_list.show_loading()
        thread = threading.Thread(
            target=self._fetch_rss_episodes_thread,
            args=(title, url),
            daemon=True
        )
        thread.start()
        
    def _fetch_rss_episodes_thread(self, title, url):
        episodes = rss_parser.parse_podcast_feed(url)
        GLib.idle_add(self._on_episodes_ready, title, episodes)

    def _on_episodes_ready(self, title, data):
        episode_list = []      
        if isinstance(data, dict):
            episode_list = data.get("episodes", [])
        elif isinstance(data, list):
            episode_list = data           
        if episode_list:
            self.podcast_episode_list.populate(title, episode_list)
        else:
            self.show_toast(_("Error: Could not load episodes (Empty list)."))
            self.media_stack.set_visible_child_name("podcasts_list")

    def on_episode_list_back_clicked(self, widget):
        self.player.pause()
        self.video_view.controls.set_playing_state(False)
        self.media_stack.set_visible_child_name("podcasts_list")
        self.main_content_stack.set_visible_child_name("placeholder_view")
        
    def on_episode_playing_requested(self, widget, url, title):
        logging.info(f"Playing episode (from list): {title}")
        db_key = url
        saved_position = database.get_playback_position(db_key)      
        if saved_position:
            minutes, seconds = divmod(int(saved_position), 60)
            time_str = f"{minutes}:{seconds:02d}"          
            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=_("Resume Podcast"),
                body=_("You listened to this episode until {}. Resume?").format(time_str)
            )
            dialog.add_css_class("resume-dialog")
            dialog.add_response("resume", _("Resume"))
            dialog.add_response("restart", _("Start Over"))
            dialog.set_default_response("resume")
            dialog.set_response_appearance("resume", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_close_response("restart")
            dialog.connect("response", self._on_resume_podcast_response, url, title, saved_position)
            dialog.present()
        else:
            self.main_content_stack.set_visible_child_name("player_view")
            self._start_playback(url=url, media_type='music', channel_data={'name': title}) 
        
    def on_podcast_list_right_clicked(self, widget, pod_id, title, row_widget):
        menu_model = Gio.Menu()
        menu_model.append(_("Move Up"), "app.pod_move_up")
        menu_model.append(_("Move Down"), "app.pod_move_down")
        menu_model.append(_("Delete Podcast"), "app.pod_delete")      
        popover = Gtk.PopoverMenu.new_from_model(menu_model)
        popover.set_parent(row_widget)
        popover.set_has_arrow(False)
        action_group = Gio.SimpleActionGroup()
        action_delete = Gio.SimpleAction.new("pod_delete", None)
        action_delete.connect("activate", self._on_podcast_delete_action, (pod_id, title))
        action_group.add_action(action_delete)
        action_up = Gio.SimpleAction.new("pod_move_up", None)
        action_up.connect("activate", self._on_podcast_move_action, (pod_id, "up"))
        action_group.add_action(action_up)
        action_down = Gio.SimpleAction.new("pod_move_down", None)
        action_down.connect("activate", self._on_podcast_move_action, (pod_id, "down"))
        action_group.add_action(action_down)      
        row_widget.insert_action_group("app", action_group)
        popover.popup()

    def _on_podcast_delete_action(self, action, param, data):
        pod_id, title = data
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_("Delete Podcast"),
            body=_("Are you sure you want to delete '{}'?").format(title),
            modal=True
        )
        dialog.add_css_class("delete-confirm-dialog")      
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")      
        dialog.connect("response", self._on_podcast_delete_confirm, pod_id)
        dialog.present()

    def _on_podcast_delete_confirm(self, dialog, response_id, pod_id):
        if response_id == "delete":
            if database.delete_podcast(pod_id):
                self.show_toast(_("Podcast deleted successfully."))
                podcasts = database.get_all_podcasts()
                self.podcast_feed_list.populate(podcasts)
            else:
                self.show_toast(_("Error deleting podcast."))

    def _on_podcast_move_action(self, action, param, data):
        pod_id, direction = data
        all_podcasts = database.get_all_podcasts() # [(id, title, url, ...), ...]
        current_index = -1
        for i, pod in enumerate(all_podcasts):
            if pod[0] == pod_id:
                current_index = i
                break      
        if current_index == -1: return        
        target_index = -1
        if direction == "up" and current_index > 0:
            target_index = current_index - 1
        elif direction == "down" and current_index < len(all_podcasts) - 1:
            target_index = current_index + 1          
        if target_index != -1:
            other_pod_id = all_podcasts[target_index][0]
            if database.swap_podcast_order(pod_id, other_pod_id):
                podcasts = database.get_all_podcasts()
                self.podcast_feed_list.populate(podcasts) 
                
    def _open_network_stream_dialog(self):
        dialog = Adw.MessageDialog.new(self, _("Open Network Stream"), _("Enter the URL to play directly."))
        dialog.add_css_class("add-podcast-dialog")
        dialog.set_modal(True)
        dialog.set_transient_for(self)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("https://example.com/video.mp4")
        content_box.append(url_entry)
        audio_switch_row = Adw.SwitchRow(title=_("Audio Only Mode"))
        audio_switch_row.set_subtitle(_("Enable this if the URL is a radio station or music file."))
        content_box.append(audio_switch_row)       
        dialog.set_extra_child(content_box)       
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("play", _("Play"))
        dialog.set_default_response("play")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_network_stream_response, url_entry, audio_switch_row)
        dialog.present()

    def _on_network_stream_response(self, dialog, response_id, url_entry, audio_switch):
        if response_id == "play":
            url = url_entry.get_text().strip()
            is_audio_only = audio_switch.get_active()           
            if url:
                if url.lower().endswith(('.m3u', '.m3u8')):
                    self._parse_and_show_m3u(url, is_music=is_audio_only)
                else:
                    media_type = 'music' if is_audio_only else 'video'
                    self.show_toast(_("Resolving stream URL..."))                   
                    thread = threading.Thread(
                        target=self._smart_stream_resolver_thread, 
                        args=(url, media_type), 
                        daemon=True
                    )
                    thread.start()
            else:
                self.show_toast(_("Please enter a valid URL."))       
        dialog.close()

    def _smart_stream_resolver_thread(self, url, media_type):
        final_url = None
        video_title = "Network Stream"
        if "github.com" in url and "/blob/" in url:
            old_url = url
            url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            logging.info(f"GitHub Blob URL corrected: {old_url} -> {url}")
        if url.lower().endswith(('.m3u', '.m3u8')):
            logging.info("M3U extension detected. Sending to playlist.")
            is_music = (media_type == 'music')
            GLib.idle_add(self._parse_and_show_m3u, url, is_music)
            return
        try:
            ydl_opts = {
                'format': 'best', 
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'live_from_start': True, 
            }          
            self.show_toast(_("Resolving stream URL..."))            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)              
                if info:
                    video_title = info.get('title', video_title)
                    if 'url' in info:
                        final_url = info['url']
                    elif 'entries' in info:
                        entry = info['entries'][0]
                        final_url = entry.get('url')
                        video_title = entry.get('title', video_title)
                    elif 'formats' in info:
                        final_url = info['formats'][-1].get('url')
                    if final_url:
                        logging.info(f"Media successfully resolved: {video_title}")
                        logging.debug(f"Stream URL: {final_url}")
        except Exception as e:
            logging.warning(f"Resolver (yt-dlp) error: {e}")
        if not final_url:
            if url.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.ts', '.mp3', '.m3u8', '.pls')):
                final_url = url
                try:
                    video_title = urllib.parse.unquote(url.rstrip('/').split('/')[-1])
                except: pass
            else:
                if "raw.githubusercontent.com" in url:
                    final_url = url
                else:
                    logging.error(f"URL could not be resolved and does not appear to be a media file: {url}")
                    GLib.idle_add(self.show_toast, _("Error: Video stream could not be extracted from this site."))
                    return
        
        def update_ui_list():
            self.is_temp_playlist_music = (media_type == 'music')
            channels = [(video_title, final_url)]           
            self._on_m3u_loaded(channels)
            self.show_toast(_("Added to playlist: {}").format(video_title))
        GLib.idle_add(update_ui_list)

    def _play_resolved_network_stream(self, url, media_type, title):
        if url:
            self.main_content_stack.set_visible_child_name("player_view")
            self._start_playback(url=url, media_type=media_type, channel_data={'name': title})
        else:
            self.show_toast(_("Error: Video stream could not be extracted from this site."))
                
    def _parse_and_show_m3u(self, url, is_music=False):
        self.show_toast(_("Loading playlist..."))
        self.is_temp_playlist_music = is_music
        thread = threading.Thread(target=self._m3u_loader_thread, args=(url,), daemon=True)
        thread.start()

    def _m3u_loader_thread(self, url):
        if "github.com" in url and "/blob/" in url:
            logging.info(f"Loader: GitHub Blob URL detected, converting to Raw format...")
            url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        channels = []
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8', errors='ignore')
            if "#EXT-X-STREAM-INF" in content:
                logging.info("Master Playlist detected. Adding to list as a single channel.")
                try:
                    parts = url.rstrip('/').split('/')
                    if 'm3u' in parts[-1].lower() and len(parts) > 1:
                        name = parts[-2]
                    else:
                        name = parts[-1]
                    name = name.replace("%20", " ").capitalize()
                except:
                    name = "Network Stream"               
                channels = [(name, url)]
                GLib.idle_add(self._on_m3u_loaded, channels)
                return
            current_name = None
            for line in content.splitlines():
                line = line.strip()
                if not line: continue               
                if line.startswith("#EXTINF"):
                    parts = line.split(",", 1)
                    if len(parts) > 1:
                        current_name = parts[1].strip()
                    else:
                        current_name = "Unknown Channel"
                elif not line.startswith("#"):
                    channel_url = line
                    name = current_name if current_name else "Channel"
                    channels.append((name, channel_url))
                    current_name = None 
            GLib.idle_add(self._on_m3u_loaded, channels)           
        except Exception as e:
            logging.error(f"M3U Load Error: {e}")
            GLib.idle_add(self.show_toast, _("Error loading playlist."))

    def _on_m3u_loaded(self, channels):
        if not channels:
            self.show_toast(_("No channels found in playlist."))
            return
        self.temp_playlist_view.populate(channels)
        for btn in self.top_buttons.values():
            btn.remove_css_class("active-nav-button")
        self.sidebar.list_stack.set_visible_child_name("temp_list")
        self.show_toast(_("{} channels loaded.").format(len(channels)))

    def on_temp_channel_selected(self, view, url, name):
        media_type = 'music' if self.is_temp_playlist_music else 'iptv'       
        self.main_content_stack.set_visible_child_name("player_view")
        self._start_playback(url=url, media_type=media_type, channel_data={'name': name})

    def on_temp_playlist_closed(self, view):
        self.on_nav_button_clicked(self.top_buttons["iptv"], "iptv")
        
    def on_fullscreen_back_clicked(self, widget):
        self._populate_fullscreen_categories()

    def _populate_fullscreen_categories(self):
        target_list = self.video_view.fullscreen_channel_list
        target_list.search_entry.set_text("")
        target_list.search_entry.set_visible(True)        
        show_locked = database.get_show_locked_bouquets_status()
        hidden_bouquets = database.get_hidden_bouquets()
        display_items = []
        is_favorites_mode = (self.sidebar.list_stack.get_visible_child_name() == "favorites")
        if is_favorites_mode:
            target_list.set_header(_("Favorite Groups"), show_back=False)
            items = database.get_all_favorite_lists()            
            for item in items:
                is_locked = database.get_favorite_list_lock_status(item['list_id'])
                if not show_locked and is_locked:
                    continue
                display_items.append({
                    'name': item['list_name'], 
                    'type': 'fav_group', 
                    'id': item['list_id'],
                    'is_locked': is_locked
                })
        else:
            target_list.set_header(_("Bouquets"), show_back=False)
            bouquet_names = list(self.bouquets_data.keys())            
            visible_bouquets = []
            for name in bouquet_names:
                if name in hidden_bouquets:
                    continue
                is_locked = database.get_bouquet_lock_status(name)
                if not show_locked and is_locked:
                    continue
                visible_bouquets.append({
                    'name': name, 
                    'type': 'bouquet', 
                    'id': name,
                    'is_locked': is_locked
                })         
            display_items = sorted(visible_bouquets, key=lambda x: x['name'])           
        target_list.populate_channels_async(display_items)
        target_list.channel_listbox.grab_focus()      
        if not hasattr(self, 'last_fullscreen_category_id') or not self.last_fullscreen_category_id:           
            if is_favorites_mode:
                 if hasattr(self.favorites_view.favorite_channels_list, 'active_list_id'):
                     self.last_fullscreen_category_id = self.favorites_view.favorite_channels_list.active_list_id
            else:
                 if self.current_playing_channel_data:
                     url = self.current_playing_channel_data.get('url')
                     if url:
                         found_bouquet = self._find_bouquet_name_by_url(url)
                         if found_bouquet:
                             self.last_fullscreen_category_id = found_bouquet
        if hasattr(self, 'last_fullscreen_category_id') and self.last_fullscreen_category_id:
            GLib.timeout_add(200, self._restore_fullscreen_category_selection) 
            
    def _restore_fullscreen_category_selection(self):
        if not hasattr(self, 'last_fullscreen_category_id') or self.last_fullscreen_category_id is None:
            return False
        target_list = self.video_view.fullscreen_channel_list.channel_listbox
        row = target_list.get_first_child()       
        found = False
        target_id_str = str(self.last_fullscreen_category_id)
        while row:
            if hasattr(row, 'channel_data'):
                row_id = row.channel_data.get('id')
                if row_id is not None and str(row_id) == target_id_str:
                    target_list.select_row(row)
                    row.grab_focus()
                    found = True
                    break
            row = row.get_next_sibling()
        if found:
            self.last_fullscreen_category_id = None           
        return False
        
    def on_fullscreen_list_item_activated(self, listbox, row):
        if not row: return 
        self.video_view.fullscreen_channel_list.search_entry.set_text("")      
        data = row.channel_data
        if 'type' in data:
            item_type = data['type']
            item_id = data['id']
            item_name = data['name']
            is_locked = False
            if item_type == 'bouquet':
                is_locked = database.get_bouquet_lock_status(item_id)
            elif item_type == 'fav_group':
                is_locked = database.get_favorite_list_lock_status(item_id)           
            password_is_set = database.get_config_value('app_password') is not None
            if is_locked and password_is_set:
                prompt = PasswordPromptDialog(self)
                prompt.connect("response", self._on_fullscreen_category_password_response, item_type, item_id, item_name)
                prompt.present()
                return 
            self._open_fullscreen_category(item_type, item_id, item_name)
            return
        correct_logo = getattr(row, 'correct_logo_path', data.get("logo"))
        channel_url = data.get("url")
        if channel_url and database.get_channel_lock_status(channel_url) and database.get_config_value('app_password'):
             prompt = PasswordPromptDialog(self)
             prompt.connect("response", self.on_password_prompt_response, data, correct_logo)
             prompt.present()
        else:
             self._play_channel(data, correct_logo) 
             
    def _on_fullscreen_category_password_response(self, dialog, response_id, item_type, item_id, item_name):
        if response_id == "ok":
            if database.check_password(dialog.get_password()):
                self._open_fullscreen_category(item_type, item_id, item_name)
            else:
                self.show_toast(_("Wrong Password!"))

    def _open_fullscreen_category(self, item_type, item_id, item_name):
        self.last_fullscreen_category_id = item_id
        channels = []
        if item_type == 'fav_group':
            channel_urls = database.get_channels_in_list(item_id)
            channels = [self.all_channels_map.get(url) for url in channel_urls if self.all_channels_map.get(url)]
        elif item_type == 'bouquet':
            channels = self.bouquets_data.get(item_id, [])
        self.video_view.fullscreen_channel_list.populate_channels_async(channels)
        self.video_view.fullscreen_channel_list.set_header(item_name, show_back=True) 
        
    def on_switch_profile_clicked(self, button):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=_("Switch Profile"),
            body=_("Are you sure you want to switch profiles? The application will restart."),
            modal=True
        )
        dialog.add_css_class("switch-profile-dialog")
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("switch", _("Switch"))
        dialog.set_default_response("switch")
        dialog.set_response_appearance("switch", Adw.ResponseAppearance.SUGGESTED)
        
        def _on_response(d, response_id):
            if response_id == "switch":
                logging.info("User requested profile switch. Clearing auto-login and restarting.")
                database.set_config_value('last_active_profile_id', '')
                self._on_restart_dialog_response(d, "restart")
            else:
                d.close()
        dialog.connect("response", _on_response)
        dialog.present()                                                                                                     

    def on_show_about_clicked(self, button):
        """Shows the 'About' dialog with License and TMDb attribution."""
        self.settings_popover.popdown()
        license_part = _(
            "EngPlayer Software License Agreement\n"
            "Copyright © 2025 Engin Eren. All Rights Reserved.\n\n"
            "By downloading, installing, or using this software (\"EngPlayer\"), you agree to the following terms:\n\n"
            "1. LICENSE GRANT\n"
            "This software is distributed as \"FREEWARE\". It may be downloaded, installed, and executed for personal use free of charge.\n\n"
            "2. RESTRICTIONS ON PORTING\n"
            "Without prior written permission from the copyright holder, it is STRICTLY PROHIBITED to port, adapt, or modify this software for use on other operating systems (Windows, macOS, Android, etc.).\n\n"
            "3. COMMERCIAL PROHIBITION\n"
            "This software may NOT be sold, rented, or included in any paid software bundle by any person or entity other than the copyright holder.\n\n"
            "4. NO CONTENT PROVIDED (DISCLAIMER)\n"
            "This software is a media player only. EngPlayer does NOT provide, include, or distribute any playlists, IPTV channels, video streams, or digital content.\n"
            "- Users are solely responsible for providing their own content (M3U files, Xtream codes, local files).\n"
            "- The developer assumes no liability for the content viewed by the user or for any copyright violations resulting from user-added content.\n\n"
            "5. DISCLAIMER OF WARRANTY\n"
            "This software is provided \"AS IS\". The copyright holder cannot be held responsible for any damages arising from the use of this software."
        )
        tmdb_notice_text = _("This product uses the TMDb API but is not endorsed or certified by TMDb.")
        full_license_text = f"{license_part}\n\n6. TMDB NOTICE\n{tmdb_notice_text}\n"
        about = Adw.AboutWindow(
            transient_for=self,
            application_name="EngPlayer",
            application_icon="io.github.falldaemon.engplayer",
            developer_name="Engin Eren",
            version=VERSION,
            copyright="© 2025 Engin Eren",
            website="https://github.com/Falldaemon/EngPlayer",
            issue_url="https://github.com/Falldaemon/EngPlayer/issues",
            license_type=Gtk.License.CUSTOM,
            license=full_license_text,
        )
        about.add_css_class("about-window")
        about.present()

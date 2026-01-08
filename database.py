# database.py

import sqlite3
import logging
import os
import hashlib
import secrets
import time
from gi.repository import GLib
import json
_MEMORY_CACHE_PATH = None

user_config_dir = GLib.get_user_config_dir()
APP_CONFIG_DIR = os.path.join(user_config_dir, "EngPlayer")
os.makedirs(APP_CONFIG_DIR, exist_ok=True)
CONFIG_DB_FILE = os.path.join(APP_CONFIG_DIR, "config.db")
LIBRARY_DB_FILE = os.path.join(APP_CONFIG_DIR, "library.db")
CURRENT_PROFILE_DB_FILE = None

def get_config_db_connection():
    """Connects to the global CONFIG database ('config.db')."""
    conn = sqlite3.connect(CONFIG_DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def get_library_db_connection():
    """Connects to the global LIBRARY database ('library.db')."""
    conn = sqlite3.connect(LIBRARY_DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def get_profile_db_connection():
    """Connects to the active PROFILE's database ('profile_HASH.db')."""
    if CURRENT_PROFILE_DB_FILE is None:
        logging.error("CRITICAL ERROR: Profile database path is not set. set_active_profile_db must be called first.")
        raise Exception("Database path not set. Call set_active_profile_db first.")
    conn = sqlite3.connect(CURRENT_PROFILE_DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _initialize_config_db():
    """Creates the global 'config.db' file and its tables."""
    try:
        conn = get_config_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        logging.info(f"Global config database ('{CONFIG_DB_FILE}') initialized successfully.")
    except sqlite3.Error as e:
        logging.error(f"Error initializing global config database: {e}")

def _initialize_library_db():
    """Creates the global 'library.db' file and its tables."""
    try:
        conn = get_library_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS libraries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL CHECK(type IN ('video', 'picture', 'music'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS media_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_id INTEGER NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                title TEXT,
                thumbnail_path TEXT,
                FOREIGN KEY (library_id) REFERENCES libraries (id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS media_metadata (
                media_path TEXT PRIMARY KEY,
                tmdb_id TEXT,
                title TEXT,
                overview TEXT,
                poster_path TEXT,
                release_date TEXT,
                rating REAL,
                director TEXT,
                cast_members TEXT,
                trailer_key TEXT,
                genres TEXT,
                countries TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist_id INTEGER,
                name TEXT NOT NULL,
                album_art_path TEXT,
                FOREIGN KEY (artist_id) REFERENCES artists (id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_id INTEGER NOT NULL,
            library_id INTEGER,
            title TEXT NOT NULL,
            track_number INTEGER,
            duration INTEGER,
            file_path TEXT NOT NULL UNIQUE,
            FOREIGN KEY (album_id) REFERENCES albums (id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS podcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                added_at INTEGER
            )
        """)
        try:
            cursor.execute("SELECT sort_order FROM podcasts LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Migrating 'podcasts' table: adding 'sort_order' column.")
            cursor.execute("ALTER TABLE podcasts ADD COLUMN sort_order INTEGER DEFAULT 0")
        try:
            cursor.execute("SELECT seasons_json FROM media_metadata LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Migrating 'media_metadata': adding 'seasons_json' column.")
            cursor.execute("ALTER TABLE media_metadata ADD COLUMN seasons_json TEXT")
        conn.commit()
        conn.close()
        logging.info(f"Global library database ('{LIBRARY_DB_FILE}') initialized successfully.")
    except sqlite3.Error as e:
        logging.error(f"Error initializing global library database: {e}")

def _initialize_profile_db():
    """Creates the active profile's 'profile_HASH.db' file and its tables."""
    if CURRENT_PROFILE_DB_FILE is None:
        logging.error("Failed to initialize profile database (path not set).")
        return
    try:
        conn = get_profile_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_properties (
                channel_url TEXT PRIMARY KEY,
                is_locked INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorite_lists (
                list_id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_name TEXT NOT NULL UNIQUE,
                sort_order INTEGER DEFAULT 0
            )
        """)
        try:
            cursor.execute("SELECT sort_order FROM favorite_lists LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Migrating 'favorite_lists' table: adding 'sort_order' column.")
            cursor.execute("ALTER TABLE favorite_lists ADD COLUMN sort_order INTEGER DEFAULT 0")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorite_channels (
                channel_url TEXT NOT NULL,
                list_id INTEGER NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(list_id) REFERENCES favorite_lists(list_id) ON DELETE CASCADE,
                PRIMARY KEY(channel_url, list_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bouquet_properties (
                bouquet_name TEXT PRIMARY KEY,
                is_locked INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorite_list_properties (
                list_id INTEGER PRIMARY KEY,
                is_locked INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                channel_url TEXT NOT NULL,
                start_time INTEGER NOT NULL,
                end_time INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL
            )
        """)
        try:
            cursor.execute("SELECT program_name FROM scheduled_recordings LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Migrating 'scheduled_recordings': adding 'program_name' column.")
            cursor.execute("ALTER TABLE scheduled_recordings ADD COLUMN program_name TEXT")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS playback_progress (
            media_path TEXT PRIMARY KEY,
            last_position INTEGER DEFAULT 0,
            last_watched INTEGER NOT NULL,
            is_finished INTEGER DEFAULT 0 NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trakt_auth (
            id INTEGER PRIMARY KEY,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_in INTEGER NOT NULL
        )
        """)
        conn.commit()
        conn.close()
        logging.info(f"Profile database ('{CURRENT_PROFILE_DB_FILE}') initialized successfully.")
    except sqlite3.Error as e:
        logging.error(f"Error initializing profile database: {e}")

def initialize_database():
    """
    Called when the application starts.
    Initializes only the GLOBAL databases (config.db and library.db).
    """
    _initialize_config_db()
    _initialize_library_db()

def set_active_profile_db(profile_id):
    """
    Sets which profile is active, determines the database path for that profile,
    and initializes/verifies that profile's database.
    """
    global CURRENT_PROFILE_DB_FILE
    safe_id = hashlib.md5(profile_id.encode()).hexdigest()
    new_db_path = os.path.join(APP_CONFIG_DIR, f"profile_{safe_id}.db")
    if CURRENT_PROFILE_DB_FILE == new_db_path:
        return
    CURRENT_PROFILE_DB_FILE = new_db_path
    logging.info(f"Active profile database path set to: {CURRENT_PROFILE_DB_FILE}")
    _initialize_profile_db()

def set_config_value(key, value):
    conn = get_config_db_connection()
    try:
        conn.execute("INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to set config value for key '{key}': {e}")
    finally:
        conn.close()

def get_config_value(key):
    conn = get_config_db_connection()
    value = conn.cursor().execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return value[0] if value else None

def set_password(password):
    salt = secrets.token_hex(16)
    hashed_password = hashlib.sha256((salt + password).encode()).hexdigest()
    set_config_value('app_password', f"{salt}:{hashed_password}")
    logging.info("Application password has been set/updated.")

def check_password(password):
    stored_value = get_config_value('app_password')
    if not stored_value:
        return False
    salt, stored_hash = stored_value.split(':')
    hashed_password_to_check = hashlib.sha256((salt + password).encode()).hexdigest()
    return hashed_password_to_check == stored_hash

def get_recordings_path():
    saved_path = get_config_value('recordings_path')
    if saved_path:
        return saved_path
    else:
        videos_path = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS)
        return videos_path

def get_cache_path():
    global _MEMORY_CACHE_PATH
    if _MEMORY_CACHE_PATH:
        return _MEMORY_CACHE_PATH
    saved_path = get_config_value('cache_path')
    if saved_path:
        _MEMORY_CACHE_PATH = saved_path
        return saved_path
    else:
        cache_dir = os.path.join(GLib.get_user_cache_dir(), "EngPlayer")
        _MEMORY_CACHE_PATH = cache_dir
        return cache_dir

def get_use_tmdb_status():
    value = get_config_value('use_tmdb_metadata')
    return value != '0'

def get_use_poster_disk_cache_status():
    value = get_config_value('use_poster_disk_cache')
    return value == '1'

def get_show_locked_bouquets_status():
    value = get_config_value('show_locked_bouquets')
    if value is None:
        return True
    return bool(int(value))

def add_library(path, library_type, name):
    conn = get_library_db_connection()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO libraries (path, type, name) VALUES (?, ?, ?)",
                (path, library_type, name)
            )
        logging.info(f"Successfully added '{path}' as a '{library_type}' library named '{name}'.")
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        logging.warning(f"Library path '{path}' already exists in the database.")
        return None
    except sqlite3.Error as e:
        logging.error(f"Failed to add library '{path}': {e}")
        return None
    finally:
        conn.close()

def get_all_libraries():
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM libraries")
    libraries = cursor.fetchall()
    conn.close()
    return libraries

def get_media_files_by_type(library_type):
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT mf.file_path, mf.title
        FROM media_files mf
        JOIN libraries l ON mf.library_id = l.id
        WHERE l.type = ?
    """, (library_type,))
    media_files = cursor.fetchall()
    conn.close()
    return media_files

def add_media_file(library_id, file_path):
    conn = get_library_db_connection()
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO media_files (library_id, file_path) VALUES (?, ?)",
                (library_id, file_path)
            )
    except sqlite3.Error as e:
        logging.error(f"Failed to add media file '{file_path}': {e}")
    finally:
        conn.close()

def media_library_is_empty(library_type):
    conn = get_library_db_connection()
    result = conn.execute("""
        SELECT EXISTS (
            SELECT 1 FROM media_files mf JOIN libraries l ON mf.library_id = l.id WHERE l.type = ?
        )
    """, (library_type,)).fetchone()
    conn.close()
    return result[0] == 0 

def save_metadata(media_path, metadata):
    if not metadata: return
    conn = get_library_db_connection()
    try:
        with conn:
            cast_with_pics_json = json.dumps(metadata.get("cast_with_pics", []))
            conn.execute("""
                INSERT INTO media_metadata (
                    media_path, tmdb_id, title, overview, poster_path,
                    release_date, rating, director, cast_members, trailer_key, genres,
                    countries 
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
                ON CONFLICT(media_path) DO UPDATE SET
                    tmdb_id=excluded.tmdb_id, title=excluded.title, overview=excluded.overview,
                    poster_path=excluded.poster_path, release_date=excluded.release_date,
                    rating=excluded.rating, director=excluded.director,
                    cast_members=excluded.cast_members,
                    trailer_key=excluded.trailer_key,
                    genres=excluded.genres,
                    countries=excluded.countries 
            """, (
                media_path, str(metadata.get("id", "")), metadata.get("title"),
                metadata.get("overview"), metadata.get("poster_path"), metadata.get("release_date"),
                metadata.get("vote_average"),
                metadata.get("director"),
                cast_with_pics_json,
                metadata.get("trailer_key"),
                metadata.get("genres"),
                metadata.get("countries")
            ))
    except sqlite3.Error as e:
        logging.error(f"Failed to save metadata for '{media_path}': {e}")
    finally:
        conn.close()

def get_metadata(media_path):
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM media_metadata WHERE media_path = ?", (media_path,))
    data = cursor.fetchone()
    conn.close()
    return data

def get_media_files_with_metadata_by_type(library_type):
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            mf.file_path,
            mf.title,
            meta.poster_path
        FROM media_files mf
        JOIN libraries l ON mf.library_id = l.id
        LEFT JOIN media_metadata meta ON mf.file_path = meta.media_path
        WHERE l.type = ?
    """, (library_type,))
    media_files = cursor.fetchall()
    conn.close()
    return media_files

def clear_metadata_for_path(media_path):
    conn = get_library_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM media_metadata WHERE media_path = ?", (media_path,))
        logging.info(f"Cleared cached metadata for '{media_path}'.")
    except sqlite3.Error as e:
        logging.error(f"Failed to clear metadata for '{media_path}': {e}")
    finally:
        conn.close()

def get_all_albums():
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            a.id as album_id, a.name as album_name, a.album_art_path, ar.name as artist_name
        FROM albums a
        JOIN artists ar ON a.artist_id = ar.id
        ORDER BY ar.name, a.name
    """)
    albums = cursor.fetchall()
    conn.close()
    return albums

def get_tracks_for_album(album_id):
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM tracks
        WHERE album_id = ?
        ORDER BY track_number
    """, (album_id,))
    tracks = cursor.fetchall()
    conn.close()
    return tracks

def get_album_details(album_id):
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.name as album_name, a.album_art_path, ar.name as artist_name
        FROM albums a
        JOIN artists ar ON a.artist_id = ar.id
        WHERE a.id = ?
    """, (album_id,))
    album = cursor.fetchone()
    conn.close()
    return album

def get_libraries_by_type(library_type):
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM libraries WHERE type = ? ORDER BY name",
        (library_type,)
    )
    libraries = cursor.fetchall()
    conn.close()
    return libraries

def get_media_files_by_library_id(library_id):
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            mf.file_path, mf.title, meta.poster_path
        FROM media_files mf
        JOIN libraries l ON mf.library_id = l.id
        LEFT JOIN media_metadata meta ON mf.file_path = meta.media_path
        WHERE l.id = ?
    """, (library_id,))
    media_files = cursor.fetchall()
    conn.close()
    return media_files

def get_albums_by_library_id(library_id):
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT
            a.id as album_id, a.name as album_name, a.album_art_path, ar.name as artist_name
        FROM albums a
        JOIN artists ar ON a.artist_id = ar.id
        JOIN tracks t ON a.id = t.album_id
        WHERE t.library_id = ?
        ORDER BY ar.name, a.name
    """, (library_id,))
    albums = cursor.fetchall()
    conn.close()
    return albums

def delete_library(library_id):
    conn = get_library_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tracks WHERE library_id = ?", (library_id,))
            logging.info(f"{cursor.rowcount} track records deleted for library (ID: {library_id}).")
            cursor.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
            logging.info(f"Library (ID: {library_id}) and associated media files deleted.")
            cursor.execute("DELETE FROM albums WHERE id NOT IN (SELECT DISTINCT album_id FROM tracks)")
            logging.info(f"{cursor.rowcount} orphan albums cleaned up.")
            cursor.execute("DELETE FROM artists WHERE id NOT IN (SELECT DISTINCT artist_id FROM albums)")
            logging.info(f"{cursor.rowcount} orphan artists cleaned up.")
        return True
    except sqlite3.Error as e:
        logging.error(f"Error deleting library (ID: {library_id}): {e}")
        return False
    finally:
        conn.close()

def delete_media_file_record(file_path):
    conn = get_library_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM media_files WHERE file_path = ?", (file_path,))
        logging.info(f"Media record deleted: {file_path}")
        return True
    except sqlite3.Error as e:
        logging.error(f"Error deleting media record: {e}")
        return False
    finally:
        conn.close()

def delete_track_record(file_path):
    conn = get_library_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tracks WHERE file_path = ?", (file_path,))
            cursor.execute("DELETE FROM albums WHERE id NOT IN (SELECT DISTINCT album_id FROM tracks)")
            cursor.execute("DELETE FROM artists WHERE id NOT IN (SELECT DISTINCT artist_id FROM albums)")
        logging.info(f"Track record deleted and cleaned up: {file_path}")
        return True
    except sqlite3.Error as e:
        logging.error(f"Error deleting track record: {e}")
        return False
    finally:
        conn.close()

def set_channel_lock_status(channel_url, is_locked):
    conn = get_profile_db_connection()
    try:
        conn.execute("""
            INSERT INTO channel_properties (channel_url, is_locked) VALUES (?, ?)
            ON CONFLICT(channel_url) DO UPDATE SET is_locked = excluded.is_locked
        """, (channel_url, int(is_locked)))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to set lock status for channel '{channel_url}': {e}")
    finally:
        conn.close()

def get_channel_lock_status(channel_url):
    conn = get_profile_db_connection()
    props = conn.cursor().execute("SELECT is_locked FROM channel_properties WHERE channel_url = ?", (channel_url,)).fetchone()
    conn.close()
    return bool(props["is_locked"]) if props else False

def is_channel_in_any_favorite(channel_url):
    conn = get_profile_db_connection()
    result = conn.cursor().execute("SELECT 1 FROM favorite_channels WHERE channel_url = ? LIMIT 1", (channel_url,)).fetchone()
    conn.close()
    return result is not None

def get_all_favorite_lists():
    conn = get_profile_db_connection()
    lists = conn.cursor().execute("SELECT list_id, list_name FROM favorite_lists ORDER BY sort_order ASC, list_name ASC").fetchall()
    conn.close()
    return lists

def create_favorite_list(list_name):
    conn = get_profile_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(sort_order) as max_order FROM favorite_lists")
        row = cursor.fetchone()
        new_order = (row['max_order'] or 0) + 1
        conn.execute("INSERT INTO favorite_lists (list_name, sort_order) VALUES (?, ?)", (list_name, new_order))
        conn.commit()
        logging.info(f"Created new favorite list: '{list_name}' with order {new_order}")
        return True
    except sqlite3.IntegrityError:
        logging.warning(f"Favorite list '{list_name}' already exists.")
        return False
    finally:
        conn.close()

def add_channel_to_list(channel_url, list_id):
    conn = get_profile_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(sort_order) as max_order FROM favorite_channels WHERE list_id = ?", (list_id,))
            result = cursor.fetchone()
            new_order = (result['max_order'] or 0) + 1
            conn.execute(
                "INSERT OR IGNORE INTO favorite_channels (channel_url, list_id, sort_order) VALUES (?, ?, ?)", 
                (channel_url, list_id, new_order)
            )
        logging.info(f"Channel '{channel_url}' added to list '{list_id}' with order {new_order}")
    except sqlite3.Error as e:
        logging.error(f"Failed to add channel '{channel_url}' to list '{list_id}': {e}")
    finally:
        conn.close()

def get_channels_in_list(list_id):
    conn = get_profile_db_connection()
    urls = conn.execute(
        "SELECT channel_url FROM favorite_channels WHERE list_id = ? ORDER BY sort_order ASC", 
        (list_id,)
    ).fetchall()
    conn.close()
    return [row['channel_url'] for row in urls]

def set_bouquet_lock_status(bouquet_name, is_locked):
    conn = get_profile_db_connection()
    try:
        conn.execute("""
            INSERT INTO bouquet_properties (bouquet_name, is_locked) VALUES (?, ?)
            ON CONFLICT(bouquet_name) DO UPDATE SET is_locked = excluded.is_locked
        """, (bouquet_name, int(is_locked)))
        conn.commit()
    finally:
        conn.close()

def get_bouquet_lock_status(bouquet_name):
    conn = get_profile_db_connection()
    props = conn.cursor().execute("SELECT is_locked FROM bouquet_properties WHERE bouquet_name = ?", (bouquet_name,)).fetchone()
    conn.close()
    return bool(props["is_locked"]) if props else False

def set_favorite_list_lock_status(list_id, is_locked):
    conn = get_profile_db_connection()
    try:
        conn.execute("""
            INSERT INTO favorite_list_properties (list_id, is_locked) VALUES (?, ?)
            ON CONFLICT(list_id) DO UPDATE SET is_locked = excluded.is_locked
        """, (list_id, int(is_locked)))
        conn.commit()
    finally:
        conn.close()

def get_favorite_list_lock_status(list_id):
    conn = get_profile_db_connection()
    props = conn.cursor().execute("SELECT is_locked FROM favorite_list_properties WHERE list_id = ?", (list_id,)).fetchone()
    conn.close()
    return bool(props["is_locked"]) if props else False 

def remove_channel_from_list(channel_url, list_id):
    conn = get_profile_db_connection()
    try:
        conn.execute("DELETE FROM favorite_channels WHERE channel_url = ? AND list_id = ?", (channel_url, list_id))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Failed to remove channel '{channel_url}' from list '{list_id}': {e}")
    finally:
        conn.close()

def delete_favorite_list(list_id):
    conn = get_profile_db_connection()
    try:
        conn.execute("DELETE FROM favorite_lists WHERE list_id = ?", (list_id,))
        conn.commit()
        logging.info(f"Deleted favorite list with id: {list_id}")
    except sqlite3.Error as e:
        logging.error(f"Failed to delete favorite list '{list_id}': {e}")
    finally:
        conn.close()

def is_channel_in_list(channel_url, list_id):
    conn = get_profile_db_connection()
    result = conn.cursor().execute("SELECT 1 FROM favorite_channels WHERE channel_url = ? AND list_id = ? LIMIT 1", (channel_url, list_id)).fetchone()
    conn.close()
    return result is not None

def add_scheduled_recording(profile_id, channel_name, channel_url, start_time, end_time, program_name=None):
    conn = get_profile_db_connection()
    try:
        with conn:
            conn.execute(
                """INSERT INTO scheduled_recordings
                   (profile_id, channel_name, channel_url, start_time, end_time, program_name, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (profile_id, channel_name, channel_url, int(start_time), int(end_time), program_name, int(time.time()))
            )
        logging.info(f"New scheduled recording added: {program_name or channel_name} @ {start_time}")
        return True
    except sqlite3.Error as e:
        logging.error(f"Failed to add scheduled recording: {e}")
        return False
    finally:
        conn.close()

def get_all_scheduled_recordings():
    conn = get_profile_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_recordings ORDER BY created_at DESC")
    recordings = cursor.fetchall()
    conn.close()
    return recordings

def get_pending_recordings_to_start():
    conn = get_profile_db_connection()
    cursor = conn.cursor()
    now = int(time.time())
    cursor.execute(
        "SELECT * FROM scheduled_recordings WHERE status = 'pending' AND start_time <= ?", (now,)
    )
    recordings = cursor.fetchall()
    conn.close()
    return recordings

def update_recording_status(recording_id, status):
    conn = get_profile_db_connection()
    try:
        with conn:
            conn.execute("UPDATE scheduled_recordings SET status = ? WHERE id = ?", (status, recording_id))
        logging.info(f"Recording ID {recording_id} status updated: {status}")
    except sqlite3.Error as e:
        logging.error(f"Failed to update recording status: {e}")
    finally:
        conn.close()

def delete_scheduled_recording(recording_id):
    conn = get_profile_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM scheduled_recordings WHERE id = ?", (recording_id,))
        logging.info(f"Scheduled recording deleted: ID {recording_id}")
    except sqlite3.Error as e:
        logging.error(f"Failed to delete scheduled recording: {e}")
    finally:
        conn.close()

def get_active_recordings():
    conn = get_profile_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scheduled_recordings WHERE status = 'recording'")
    recordings = cursor.fetchall()
    conn.close()
    return recordings

def get_all_favorite_channel_urls():
    conn = get_profile_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT channel_url FROM favorite_channels")
    urls = {row['channel_url'] for row in cursor.fetchall()}
    conn.close()
    return urls

def get_all_locked_channel_urls():
    conn = get_profile_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT channel_url FROM channel_properties WHERE is_locked = 1")
    urls = {row['channel_url'] for row in cursor.fetchall()}
    conn.close()
    return urls

def save_playback_progress(media_path, position, is_finished=0):
    conn = get_profile_db_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO playback_progress (media_path, last_position, last_watched, is_finished)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(media_path) DO UPDATE SET
                    last_position=excluded.last_position,
                    last_watched=excluded.last_watched,
                    is_finished=excluded.is_finished
            """, (media_path, int(position), int(time.time()), int(is_finished)))
    except sqlite3.Error as e:
        logging.error(f"Failed to save playback position '{media_path}': {e}")
    finally:
        conn.close()

def get_playback_position(media_path):
    conn = get_profile_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_position FROM playback_progress WHERE media_path = ? AND is_finished = 0", (media_path,))
    data = cursor.fetchone()
    conn.close()
    if data and data['last_position'] > 10:
        return data['last_position']
    return None

def delete_playback_position(media_path):
    conn = get_profile_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM playback_progress WHERE media_path = ?", (media_path,))
        logging.info(f"Playback position deleted: {media_path}")
    except sqlite3.Error as e:
        logging.error(f"Failed to delete playback position: {e}")
    finally:
        conn.close()

def get_watched_status_batch(media_paths):
    """
    Returns a set of media paths from the given list that are marked as
    'watched' (is_finished = 1).
    """
    if not media_paths:
        return set()
    conn = get_profile_db_connection()
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in media_paths)
    query = f"SELECT media_path FROM playback_progress WHERE media_path IN ({placeholders}) AND is_finished = 1"
    try:
        cursor.execute(query, media_paths)
        watched_set = {row['media_path'] for row in cursor.fetchall()}
        return watched_set
    except sqlite3.Error as e:
        logging.error(f"Failed to get batch watched status: {e}")
        return set()
    finally:
        conn.close()

def swap_favorite_channel_order(list_id, channel_url_1, channel_url_2):
    conn = get_profile_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sort_order FROM favorite_channels WHERE list_id = ? AND channel_url = ?", (list_id, channel_url_1))
            order1_row = cursor.fetchone()
            cursor.execute("SELECT sort_order FROM favorite_channels WHERE list_id = ? AND channel_url = ?", (list_id, channel_url_2))
            order2_row = cursor.fetchone()
            if not order1_row or not order2_row:
                logging.error("Failed to swap order: One of the channels was not found.")
                return False
            order1 = order1_row['sort_order']
            order2 = order2_row['sort_order']
            cursor.execute(
                "UPDATE favorite_channels SET sort_order = ? WHERE list_id = ? AND channel_url = ?",
                (order2, list_id, channel_url_1)
            )
            cursor.execute(
                "UPDATE favorite_channels SET sort_order = ? WHERE list_id = ? AND channel_url = ?",
                (order1, list_id, channel_url_2)
            )
        logging.info(f"Order swapped: '{channel_url_1}' (new: {order2}), '{channel_url_2}' (new: {order1})")
        return True
    except sqlite3.Error as e:
        logging.error(f"Error swapping channel order: {e}")
        return False
    finally:
        conn.close()

def save_trakt_token(token_data):
    """
    Saves the new Trakt.tv token to the database (deletes the old one).
    token_data is the full dictionary from the Trakt API.
    """
    conn = get_profile_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM trakt_auth")
            conn.execute(
                """INSERT INTO trakt_auth 
                   (access_token, refresh_token, created_at, expires_in) 
                   VALUES (?, ?, ?, ?)""",
                (
                    token_data['access_token'],
                    token_data['refresh_token'],
                    int(token_data['created_at']),
                    int(token_data['expires_in'])
                )
            )
        logging.info("Trakt.tv token successfully saved to database.")
        return True
    except sqlite3.Error as e:
        logging.error(f"Failed to save Trakt.tv token: {e}")
        return False
    finally:
        conn.close()

def get_trakt_token():
    """
    Gets the saved Trakt.tv token and its expiration date.
    """
    conn = get_profile_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trakt_auth LIMIT 1")
        token_row = cursor.fetchone()
        if token_row:
            created_at = token_row['created_at']
            expires_in = token_row['expires_in']
            expires_at = created_at + expires_in
            if time.time() >= expires_at:
                logging.warning("Trakt.tv token found but has expired. Refresh needed.")
                return dict(token_row)
            logging.debug("Valid Trakt.tv token retrieved from database.")
            return dict(token_row)
    except sqlite3.Error as e:
        logging.error(f"Failed to get Trakt.tv token: {e}")
    finally:
        conn.close()
    return None

def clear_trakt_token():
    """Deletes the Trakt.tv token from the database (Log Out)."""
    conn = get_profile_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM trakt_auth")
        logging.info("Trakt.tv token deleted (Logged out).")
    except sqlite3.Error as e:
        logging.error(f"Error deleting Trakt.tv token: {e}")
    finally:
        conn.close()

def get_paths_for_tmdb_ids(tmdb_id_list):
    """Returns the file paths corresponding to the given list of TMDb IDs."""
    if not tmdb_id_list:
        return []
    conn = get_library_db_connection()
    try:
        placeholders = ','.join('?' for _ in tmdb_id_list)
        query = f"SELECT media_path FROM media_metadata WHERE tmdb_id IN ({placeholders})"
        cursor = conn.cursor()
        cursor.execute(query, tmdb_id_list)
        paths = [row['media_path'] for row in cursor.fetchall()]
        return paths
    except sqlite3.Error as e:
        logging.error(f"Error getting paths from TMDb IDs: {e}")
        return []
    finally:
        conn.close()

def set_batch_watched_status_by_path(path_list):
    """
    Marks the given list of file paths as 'watched' (is_finished=1).
    Creates a record if it doesn't exist, updates if it does.
    """
    if not path_list:
        return 0
    conn = get_profile_db_connection()
    try:
        now = int(time.time())
        data_tuples = [(path, now, 1) for path in path_list]
        with conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO playback_progress (media_path, last_watched, is_finished, last_position)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(media_path) DO UPDATE SET
                    last_watched=excluded.last_watched,
                    is_finished=excluded.is_finished
                    WHERE playback_progress.is_finished = 0
            """, data_tuples)
            logging.info(f"Trakt Sync: {cursor.rowcount} local media items marked as 'watched'.")
            return cursor.rowcount
    except sqlite3.Error as e:
        logging.error(f"Error updating batch watched status (Trakt): {e}")
        return 0
    finally:
        conn.close()

def get_notifications_enabled():
    """Returns True if notifications are enabled (default: True)."""
    val = get_config_value('notifications_enabled')
    return val != '0'

def get_notification_timeout():
    """Returns notification timeout in seconds (default: 3)."""
    val = get_config_value('notification_timeout')
    if val and val.isdigit():
        return int(val)
    return 3

def swap_favorite_list_order(list_id_1, list_id_2):
    """
    Swaps the sort_order of two favorite lists.
    """
    conn = get_profile_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sort_order FROM favorite_lists WHERE list_id = ?", (list_id_1,))
            row1 = cursor.fetchone()
            cursor.execute("SELECT sort_order FROM favorite_lists WHERE list_id = ?", (list_id_2,))
            row2 = cursor.fetchone()
            if not row1 or not row2:
                logging.error("Failed to swap lists: One of the lists was not found.")
                return False
            order1 = row1['sort_order']
            order2 = row2['sort_order']
            if order1 == order2:
                order1 = list_id_1
                order2 = list_id_2
            cursor.execute("UPDATE favorite_lists SET sort_order = ? WHERE list_id = ?", (order2, list_id_1))
            cursor.execute("UPDATE favorite_lists SET sort_order = ? WHERE list_id = ?", (order1, list_id_2))          
        logging.info(f"Favorite lists swapped: ID {list_id_1} <-> ID {list_id_2}")
        return True
    except sqlite3.Error as e:
        logging.error(f"Error swapping favorite list order: {e}")
        return False
    finally:
        conn.close()

def update_season_data(media_path, seasons_json_str):
    """
    Updates ONLY the seasons_json column for a specific media item.
    Does not touch other metadata like title or poster.
    """
    conn = get_library_db_connection()
    try:
        with conn:
            conn.execute("INSERT OR IGNORE INTO media_metadata (media_path) VALUES (?)", (media_path,))
            conn.execute("UPDATE media_metadata SET seasons_json = ? WHERE media_path = ?", (seasons_json_str, media_path))
        logging.info(f"Seasons data updated for: {media_path}")
    except sqlite3.Error as e:
        logging.error(f"Failed to update season data for '{media_path}': {e}")
    finally:
        conn.close()
    
def delete_podcast(podcast_id):
    conn = get_library_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM podcasts WHERE id = ?", (podcast_id,))
        logging.info(f"Podcast deleted: ID {podcast_id}")
        return True
    except sqlite3.Error as e:
        logging.error(f"Failed to delete podcast: {e}")
        return False
    finally:
        conn.close()

def swap_podcast_order(podcast_id_1, podcast_id_2):
    conn = get_library_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sort_order FROM podcasts WHERE id = ?", (podcast_id_1,))
            row1 = cursor.fetchone()
            cursor.execute("SELECT sort_order FROM podcasts WHERE id = ?", (podcast_id_2,))
            row2 = cursor.fetchone()
            if not row1 or not row2:
                return False
            order1 = row1['sort_order'] if row1['sort_order'] is not None else 0
            order2 = row2['sort_order'] if row2['sort_order'] is not None else 0
            if order1 == order2:
                order1 = podcast_id_1
                order2 = podcast_id_2
            conn.execute("UPDATE podcasts SET sort_order = ? WHERE id = ?", (order2, podcast_id_1))
            conn.execute("UPDATE podcasts SET sort_order = ? WHERE id = ?", (order1, podcast_id_2))
        return True
    except sqlite3.Error as e:
        logging.error(f"Error swapping podcast order: {e}")
        return False
    finally:
        conn.close()

def migrate_podcast_images():
    conn = get_library_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT image_url FROM podcasts LIMIT 1")
    except sqlite3.OperationalError:
        logging.info("Migrating 'podcasts' table: adding 'image_url' column.")
        conn.execute("ALTER TABLE podcasts ADD COLUMN image_url TEXT")
        conn.commit()
    finally:
        conn.close()

def add_podcast(title, url, image_url=None):
    migrate_podcast_images()   
    conn = get_library_db_connection()
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM podcasts WHERE url = ?", (url,))
            if cursor.fetchone():
                return False
            conn.execute(
                "INSERT INTO podcasts (title, url, image_url, sort_order) VALUES (?, ?, ?, 0)",
                (title, url, image_url)
            )
        logging.info(f"Podcast added: {title}")
        return True
    except sqlite3.Error as e:
        logging.error(f"Failed to add podcast: {e}")
        return False
    finally:
        conn.close()

def get_all_podcasts():
    migrate_podcast_images()    
    conn = get_library_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, url, added_at, sort_order, image_url FROM podcasts ORDER BY sort_order ASC, id DESC")
    podcasts = cursor.fetchall()
    conn.close()
    return podcasts
    
def is_content_finished(media_path):
    conn = get_profile_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT is_finished FROM playback_progress WHERE media_path = ?", (media_path,))
        row = cursor.fetchone()
        if row and row['is_finished'] == 1:
            return True
        return False
    except sqlite3.Error as e:
        logging.error(f"Error checking is_content_finished: {e}")
        return False
    finally:
        conn.close()          

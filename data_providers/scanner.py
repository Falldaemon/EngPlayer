# data_providers/scanner.py

import os
import logging
import gettext
from database import get_library_db_connection, get_cache_path
from mutagen import File as MutagenFile
from mutagen.id3 import APIC
from gi.repository import GLib

import gettext
_ = gettext.gettext

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
PICTURE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
MUSIC_EXTENSIONS = {".mp3", ".flac", ".ogg", ".wav", ".m4a"}

def get_album_art_cache_dir():
    base_cache_dir = get_cache_path()
    cache_dir = os.path.join(base_cache_dir, "album_art")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def _extract_album_art(audio_file, artist, album):
    try:
        safe_name = f"{artist}_{album}".encode('utf-8').hex()
        cache_dir = get_album_art_cache_dir()
        art_path = os.path.join(cache_dir, f"{safe_name}.jpg")
        if os.path.exists(art_path):
            return art_path
        art_data = None
        if 'APIC:' in audio_file:
            art_data = audio_file['APIC:'].data
        elif hasattr(audio_file, 'pictures') and audio_file.pictures:
            art_data = audio_file.pictures[0].data
        if art_data:
            with open(art_path, 'wb') as f:
                f.write(art_data)
            return art_path
    except Exception as e:
        logging.warning(_("Could not extract album art: {}").format(e))
    return None

def scan_all_libraries():
    logging.info(_("Starting library scan..."))
    conn = get_library_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM libraries")
        libraries = cursor.fetchall()
        if not libraries:
            logging.info(_("No libraries in the database to scan."))
            conn.close()
            return
        for lib in libraries:
            path = lib["path"]
            if not os.path.isdir(path):
                logging.warning(_("Library path does not exist or is not a directory: {}").format(path))
                continue
            lib_type = lib["type"]
            logging.info(_("Scanning {} library at: {}").format(lib_type, path))
            if lib_type == "music":
                for root, dirs, files in os.walk(path):
                    for filename in files:
                        if any(filename.lower().endswith(ext) for ext in MUSIC_EXTENSIONS):
                            full_path = os.path.join(root, filename)
                            try:
                                audio = MutagenFile(full_path)
                                if not audio:
                                    logging.warning(_("Could not read metadata from: {}").format(filename))
                                    continue
                                album_artist_name = _('Unknown Artist')
                                if audio.get('albumartist'):
                                    album_artist_name = audio.get('albumartist')[0]
                                elif audio.get('artist'):
                                    album_artist_name = audio.get('artist')[0]
                                album_name_tag = audio.get('album', [''])[0].strip()
                                if album_name_tag:
                                    album_name = album_name_tag
                                else:
                                    album_name = os.path.basename(os.path.dirname(full_path))
                                track_title = audio.get('title', [os.path.splitext(filename)[0]])[0] if audio.get('title') else os.path.splitext(filename)[0]
                                track_number_tags = audio.get('tracknumber', ['0'])
                                track_number_str = track_number_tags[0].split('/')[0] if track_number_tags else '0'
                                track_number = int(track_number_str) if track_number_str.isdigit() else 0
                                duration = int(audio.info.length)
                                cursor.execute("INSERT OR IGNORE INTO artists (name) VALUES (?)", (album_artist_name,))
                                artist_id = cursor.execute("SELECT id FROM artists WHERE name = ?", (album_artist_name,)).fetchone()['id']
                                album_id_row = cursor.execute("SELECT id FROM albums WHERE name = ? AND artist_id = ?", (album_name, artist_id)).fetchone()
                                if not album_id_row:
                                    album_art_path = _extract_album_art(audio, album_artist_name, album_name)
                                    cursor.execute("INSERT INTO albums (name, artist_id, album_art_path) VALUES (?, ?, ?)",
                                                   (album_name, artist_id, album_art_path))
                                    album_id = cursor.lastrowid
                                else:
                                    album_id = album_id_row['id']
                                cursor.execute("""
                                    INSERT OR IGNORE INTO tracks (album_id, library_id, title, track_number, duration, file_path)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (album_id, lib["id"], track_title, track_number, duration, full_path))
                            except Exception as e:
                                logging.warning(_("Could not process music file {}: {}").format(full_path, e))
            else:
                extensions_to_scan = set()
                if lib_type == "video": extensions_to_scan = VIDEO_EXTENSIONS
                elif lib_type == "picture": extensions_to_scan = PICTURE_EXTENSIONS
                for root, dirs, files in os.walk(path):
                    for filename in files:
                        if any(filename.lower().endswith(ext) for ext in extensions_to_scan):
                            full_path = os.path.join(root, filename)
                            cursor.execute(
                                "INSERT OR IGNORE INTO media_files (library_id, file_path) VALUES (?, ?)",
                                (lib["id"], full_path)
                            )
    except Exception as e:
        logging.error(_("An error occurred during library scan: {}").format(e), exc_info=True)
    finally:
        conn.commit()
        conn.close()
        logging.info(_("Library scan finished."))

#utils/cache_cleaner.py

import os
import time
import logging
import database
from gi.repository import GLib

def _clean_directory(cache_dir, max_age_days):
    """
    Deletes files older than max_age_days from a specific folder.
    """
    if not os.path.isdir(cache_dir):
        return 0
    deleted_count = 0
    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 60 * 60
    try:
        for filename in os.listdir(cache_dir):
            file_path = os.path.join(cache_dir, filename)
            if not os.path.isfile(file_path):
                continue
            try:
                file_mtime = os.path.getmtime(file_path)
                if (current_time - file_mtime) > max_age_seconds:
                    os.remove(file_path)
                    deleted_count += 1
            except OSError:
                pass
        if deleted_count > 0:
            logging.info(f"Cache Cleaner: {deleted_count} old files deleted from '{cache_dir}'.")
        return deleted_count
    except Exception as e:
        logging.error(f"Cache Cleaner: Error while cleaning '{cache_dir}': {e}")
        return 0

def clean_all_caches(max_age_days=30):
    """
    Cleans all known image caches in the application.
    """
    logging.info(f"Cache cleanup started (files older than {max_age_days} days will be deleted)...")
    base_cache_dir = database.get_cache_path()
    poster_cache_dir = os.path.join(base_cache_dir, "poster_cache")
    grid_cache_dir = os.path.join(base_cache_dir, "grid_thumbnails")
    album_art_cache_dir = os.path.join(base_cache_dir, "album_art")
    total_deleted = 0
    total_deleted += _clean_directory(poster_cache_dir, max_age_days)
    total_deleted += _clean_directory(grid_cache_dir, max_age_days)
    total_deleted += _clean_directory(album_art_cache_dir, max_age_days)
    logging.info(f"Cache cleanup finished. Total {total_deleted} old files deleted.")

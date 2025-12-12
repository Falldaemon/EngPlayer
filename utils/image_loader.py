# utils/image_loader.py

import threading
import urllib.request
import logging
import os
import hashlib
from gi.repository import GLib, GdkPixbuf
import database
from background import image_download_pool

_failed_urls_memory = set()
_downloading_urls = set()

def load_image_async(url, widget, on_success_callback=None, on_failure=None):
    """
    Downloads an image from a URL, using a local disk cache to avoid
    re-downloading. Implements blacklist and race-condition prevention.
    """
    if not url or not widget:
        return
    if url in _failed_urls_memory:
        return
    if url in _downloading_urls:
        return
    _downloading_urls.add(url)

    def thread_func():
        try:
            base_cache_dir = database.get_cache_path()
            cache_dir = os.path.join(base_cache_dir, "poster_cache")
            os.makedirs(cache_dir, exist_ok=True)
            try:
                hash_name = hashlib.md5(url.encode()).hexdigest()
            except Exception:
                return
            cache_path = os.path.join(cache_dir, f"{hash_name}.jpg")
            if database.get_use_poster_disk_cache_status():
                if os.path.exists(cache_path):
                    try:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file(cache_path)
                        if pixbuf and on_success_callback:
                            GLib.idle_add(on_success_callback, widget, pixbuf)
                        return
                    except GLib.Error:
                        try: os.remove(cache_path)
                        except OSError: pass
            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            if data:
                loader = GdkPixbuf.PixbufLoader.new()
                loader.write(data)
                loader.close()
                pixbuf = loader.get_pixbuf()
                if pixbuf:
                    if database.get_use_poster_disk_cache_status():
                        try:
                            pixbuf.savev(cache_path, "jpeg", ["quality"], ["90"])
                        except GLib.Error:
                            pass
                    if on_success_callback:
                        GLib.idle_add(on_success_callback, widget, pixbuf)
                else:
                    raise Exception("Pixbuf error")
            else:
                raise Exception("Empty data")
        except Exception:
            _failed_urls_memory.add(url)
            if on_failure:
                GLib.idle_add(on_failure)
        finally:
            if url in _downloading_urls:
                _downloading_urls.remove(url)
    image_download_pool.submit(thread_func)

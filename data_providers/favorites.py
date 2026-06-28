import json
import os
import hashlib

class FavoritesManager:
    def __init__(self, cache_dir=None):
        if cache_dir is None:
            self.cache_dir = os.path.expanduser("~/.cache/EngPlayer/favorites_cache")
        else:
            self.cache_dir = cache_dir
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)        
        self.current_m3u_path = None
        self.save_path = None
        self.favorites = {"Default": []}

    def load_for_m3u(self, m3u_path):
        self.current_m3u_path = m3u_path
        path_hash = hashlib.md5(m3u_path.encode('utf-8')).hexdigest()
        base_name = os.path.basename(m3u_path).split('.')[0]
        self.save_path = os.path.join(self.cache_dir, f"fav_{base_name}_{path_hash[:8]}.json")      
        if os.path.exists(self.save_path):
            with open(self.save_path, 'r', encoding='utf-8') as f:
                self.favorites = json.load(f)
        else:
            self.favorites = {"Default": []}         
        return self.favorites

    def add_bucket(self, bucket_name):
        if bucket_name not in self.favorites:
            self.favorites[bucket_name] = []
            self.save()

    def add_to_bucket(self, bucket_name, channel_data):
        if bucket_name in self.favorites:
            self.favorites[bucket_name].append(channel_data)
            self.save()

    def save(self):
        if not self.save_path:
            return
        with open(self.save_path, 'w', encoding='utf-8') as f:
            json.dump(self.favorites, f, indent=4)

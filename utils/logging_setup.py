# utils/logging_setup.py

import logging
import sys
import os
import re
import threading
import traceback

class SafeLogFormatter(logging.Formatter):
    PUBLIC_HOSTS = ("themoviedb.org", "tmdb.org", "trakt.tv", "youtube.com", "youtu.be",
                    "googlevideo.com", "google.com", "googleapis.com", "github.com",
                    "githubusercontent.com", "github.io", "opensubtitles.com",
                    "opensubtitles.org", "localhost", "127.0.0.1")

    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.url_pattern = re.compile(r'(https?://[^/]+/(?:series|movie|timeshift|live)?/?(?:[a-zA-Z0-9_-]+/)?)([^/]+)/([^/]+)(/[0-9a-zA-Z._-]+)')
        self.timeshift_pattern = re.compile(r'(/timeshift/)[^/\s]+/[^/\s]+/')
        self.token_pattern = re.compile(r'(https?://[^\s]*?/)[A-Za-z0-9_\-=]{40,}')
        self.param_pattern = re.compile(r'\b(password|pass|username|user|api_key|token)=([^\s&]+)', re.IGNORECASE)
        self.host_pattern = re.compile(r'((?:https?|rtmp|rtsp)://)(?:[^/@\s]+@)?([^/\s:?#\'"]+)(:\d+)?', re.IGNORECASE)
        self.host_arg_pattern = re.compile(r"(host=')([^']+)(')")
        self.bare_host_pattern = re.compile(r"(LOGO SERVER BLOCKED: )(\S+)")
        self.media_user_pattern = re.compile(r"(/run/media/|/media/)[^/\s'\"]+")
        homes = {os.path.expanduser("~"), os.environ.get("USERPROFILE", ""), os.environ.get("HOME", "")}
        self.home_paths = sorted({v for h in homes if len(h) > 3 for v in (h, h.replace("\\", "/"))},
                                 key=len, reverse=True)

    def _is_public(self, host):
        host = host.lower()
        return any(host == h or host.endswith("." + h) for h in self.PUBLIC_HOSTS)

    def format(self, record):
        original_msg = super().format(record)
        
        def mask_url(match):
            base = match.group(1)
            stream_id = match.group(4)
            return f"{base}***/****{stream_id}"           
        safe_msg = self.timeshift_pattern.sub(r'\1***/****/', original_msg)
        safe_msg = self.token_pattern.sub(r'\1***', safe_msg)
        safe_msg = self.url_pattern.sub(mask_url, safe_msg)
        safe_msg = self.param_pattern.sub(r'\1=***', safe_msg)
        safe_msg = self.host_pattern.sub(
            lambda m: m.group(0) if self._is_public(m.group(2)) else f"{m.group(1)}<server>", safe_msg)
        safe_msg = self.host_arg_pattern.sub(
            lambda m: m.group(0) if self._is_public(m.group(2)) else f"{m.group(1)}<server>{m.group(3)}", safe_msg)
        safe_msg = self.bare_host_pattern.sub(
            lambda m: m.group(0) if self._is_public(m.group(2)) else f"{m.group(1)}<server>", safe_msg)
        for path in self.home_paths:
            safe_msg = safe_msg.replace(path, "~")
        safe_msg = self.media_user_pattern.sub(r"\1<user>", safe_msg)
        return safe_msg

_EXCEPTION_LOG_LIMIT = 3
_exception_counts = {}


def _log_uncaught(exc_type, exc_value, exc_tb, where):
    frame = traceback.extract_tb(exc_tb)[-1] if exc_tb else None
    key = (exc_type.__name__, frame.filename if frame else "", frame.lineno if frame else 0)
    count = _exception_counts.get(key, 0) + 1
    _exception_counts[key] = count
    if count <= _EXCEPTION_LOG_LIMIT:
        logging.error(f"Uncaught exception ({where}):", exc_info=(exc_type, exc_value, exc_tb))
    elif count == _EXCEPTION_LOG_LIMIT + 1:
        logging.error(f"Uncaught exception ({where}) keeps repeating: {exc_type.__name__} at "
                      f"{key[1]}:{key[2]}; further repeats are not logged.")


def _install_exception_hooks():
    default_excepthook = sys.excepthook

    def excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            default_excepthook(exc_type, exc_value, exc_tb)
            return
        try:
            _log_uncaught(exc_type, exc_value, exc_tb, "main thread")
        except Exception:
            default_excepthook(exc_type, exc_value, exc_tb)

    def thread_excepthook(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else "unknown"
        try:
            _log_uncaught(args.exc_type, args.exc_value, args.exc_traceback, f"thread {name}")
        except Exception:
            threading.__excepthook__(args)

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook


def setup_logging():
    is_debug = '--debug' in sys.argv
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'   
    root_logger = logging.getLogger()   
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler) 
    formatter = SafeLogFormatter(log_format)   
    if is_debug:
        log_level = logging.DEBUG
        root_logger.setLevel(log_level)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)      
        try:
            cache_dir = os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache"))
            app_log_dir = os.path.join(cache_dir, "EngPlayer")
            os.makedirs(app_log_dir, exist_ok=True)          
            log_file_path = os.path.join(app_log_dir, "debug.log")         
            file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)                  
            logging.info(f"Debug mode enabled. Log file path: {log_file_path}")
        except Exception as e:
            logging.error(f"Failed to setup log file: {e}")         
    else:
        log_level = logging.ERROR
        root_logger.setLevel(log_level)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(log_level)
        root_logger.addHandler(stream_handler)       
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)
    logging.getLogger("guessit").setLevel(logging.ERROR)
    logging.getLogger("rebulk").setLevel(logging.ERROR)
    _install_exception_hooks()

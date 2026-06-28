# utils/logging_setup.py

import logging
import sys
import os
import re

class SafeLogFormatter(logging.Formatter):
    
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.url_pattern = re.compile(r'(https?://[^/]+/(?:series|movie|timeshift|live)?/?(?:[a-zA-Z0-9_-]+/)?)([^/]+)/([^/]+)(/[0-9a-zA-Z._-]+)')
        self.param_pattern = re.compile(r'(password|pass|api_key|token)=([^\s&]+)', re.IGNORECASE)

    def format(self, record):
        original_msg = super().format(record)
        
        def mask_url(match):
            base = match.group(1)
            stream_id = match.group(4)
            return f"{base}***/****{stream_id}"           
        safe_msg = self.url_pattern.sub(mask_url, original_msg)
        safe_msg = self.param_pattern.sub(r'\1=***', safe_msg)       
        return safe_msg

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

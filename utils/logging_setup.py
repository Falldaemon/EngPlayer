# utils/logging_setup.py

import logging
import sys
import os 

def setup_logging():
    """
    Configures the application's logging system.
    """
    is_debug = '--debug' in sys.argv
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'   
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler) 
    formatter = logging.Formatter(log_format)
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

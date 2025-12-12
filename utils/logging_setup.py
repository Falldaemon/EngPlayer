# utils/logging_setup.py

import logging
import sys

def setup_logging():
    """
    Configures the application's logging system.
    """
    is_debug = '--debug' in sys.argv
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    root_logger = logging.getLogger()
    formatter = logging.Formatter(log_format)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    if is_debug:
        log_level = logging.DEBUG
        root_logger.setLevel(log_level)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)
        file_handler = logging.FileHandler("media_center_debug.log", mode='w')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        logging.info("Debug mode enabled. Logging to console and 'media_center_debug.log'")
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

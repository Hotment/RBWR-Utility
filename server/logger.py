import os
import sys
import logging
import re
from logging.handlers import RotatingFileHandler

class CustomConsoleFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: "\033[34m",
        logging.INFO: "\033[0m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[37;41m",
    }

    def format(self, record):
        log_color = self.LEVEL_COLORS.get(record.levelno, "\033[0m")
        log_message = super().format(record)
        return f"{log_color}{log_message.encode(errors='replace').decode()}\033[0m"

class PlainTextFormatter(logging.Formatter):
    """Strips ANSI escape color codes for clean, readable file logs."""
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def format(self, record):
        message = super().format(record)
        return self.ANSI_ESCAPE.sub('', message)

_initialized = False

def setup_logging(log_filename="server.log", max_bytes=5 * 1024 * 1024, backup_count=5):
    """
    Sets up a rotating file handler and console logger that captures
    all log messages and printed console output into rotating log files.
    """
    global _initialized
    if _initialized:
        return logging.getLogger()
    _initialized = True

    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, log_filename)

    log_format = '[%(asctime)s | %(levelname)s | %(name)s]: %(message)s'

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(CustomConsoleFormatter(log_format))
    stream_handler.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(PlainTextFormatter(log_format))
    file_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [stream_handler, file_handler]

    for lib in ["disnake", "disnake.http", "disnake.gateway", "disnake.client", "disnake.webhook", "disnake.state"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

    return root_logger
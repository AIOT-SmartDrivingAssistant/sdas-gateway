import os
import re
import sys

from datetime import datetime
from pytz import timezone

import logging
from logging.handlers import RotatingFileHandler

from colorama import init, Fore

class CustomLogger:
    _instance = None
    LOG_FORMAT = "%(message)s"
    DATE_FORMAT = "[%Y-%m-%d %H:%M:%S]"
    LOG_DIR = "logs"
    LOG_FILE = "backend"
    MAX_BYTES = 10 * 1024 * 1024  # 10MB
    BACKUP_COUNT = 5
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    LEVELNAME_WIDTH = 7
    LOCATION_WIDTH = 25

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            init(strip=True, convert=True)
            cls._instance._init_logger()
        return cls._instance
    
    def __init__(self):
        pass

    def _init_logger(self):
        if not hasattr(self, 'log'):
            class CustomFormatter(logging.Formatter):
                def format(self, record):
                    vn_timezone = timezone("Asia/Ho_Chi_Minh")
                    record.timestamp = datetime.now(vn_timezone).strftime(CustomLogger.DATE_FORMAT)

                    if record.pathname and record.lineno:
                        path_name = record.pathname.split(os.sep)[-1]
                        record.location = f"[{path_name}:{record.lineno}]"
                    else:
                        record.location = ""

                    level_color = None
                    if record.levelname == "DEBUG":
                        level_color = Fore.GREEN
                    elif record.levelname in ["WARNING", "WARN"]:
                        level_color = Fore.YELLOW
                    elif record.levelname == "ERROR":
                        level_color = Fore.RED
                    else:
                        level_color = Fore.BLUE

                    return (
                        f"{Fore.LIGHTGREEN_EX}{record.timestamp}{Fore.RESET} "
                        f"{level_color}{record.levelname:{CustomLogger.LEVELNAME_WIDTH}}{Fore.RESET} "
                        f"{Fore.WHITE}{record.location:{CustomLogger.LOCATION_WIDTH}}{Fore.RESET} "
                        f"{Fore.CYAN}| {Fore.RESET}{record.getMessage()}"
                    )

            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(CustomFormatter())

            if (self.ENVIRONMENT == "development"):
                if not os.path.exists(self.LOG_DIR):
                    os.makedirs(self.LOG_DIR)

                # Create file handler with rotation
                file_handler = RotatingFileHandler(
                    os.path.join(self.LOG_DIR, self.LOG_FILE + "_[" + datetime.now().strftime("%Y-%m-%d") + "].log"),
                    maxBytes=self.MAX_BYTES,
                    backupCount=self.BACKUP_COUNT
                )

                def strip_ansi_codes(text):
                    ansi_pattern = re.compile(r'\033\[[0-9;]*m')
                    return ansi_pattern.sub('', text)

                class FileFormatter(logging.Formatter):
                    def format(self, record):
                        vn_timezone = timezone("Asia/Ho_Chi_Minh")
                        record.timestamp = datetime.now(vn_timezone).strftime(CustomLogger.DATE_FORMAT)

                        if record.pathname and record.lineno:
                            path_name = record.pathname.split(os.sep)[-1]
                            record.location = f"[{path_name}:{record.lineno}]"
                        else:
                            record.location = ""

                        message = record.getMessage()
                        message = strip_ansi_codes(message)

                        return (
                            f"{record.timestamp} "
                            f"{record.levelname:{CustomLogger.LEVELNAME_WIDTH}} "
                            f"{record.location:{CustomLogger.LOCATION_WIDTH}} "
                            f"| {message}"
                        )

                file_handler.setFormatter(FileFormatter())

            logging.basicConfig(
                level=logging.INFO,
                format=self.LOG_FORMAT,
                handlers=[console_handler, file_handler] if (self.ENVIRONMENT == "development") else [console_handler],
            )

            # Set other loggers to WARNING level
            all_loggers = logging.Logger.manager.loggerDict.keys()
            for logger in all_loggers:
                logging.getLogger(logger).setLevel(logging.WARNING)

            self.log = logging.getLogger()

    def _get_logger(self):
        return self._instance.log
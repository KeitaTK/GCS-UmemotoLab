# logging_config.py
import logging
import logging.config
import os
from logging.handlers import RotatingFileHandler

# Ensure log directory exists
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',  # 実機運用時のコンソールはINFOにしてノイズを減らす（必要に応じDEBUG）
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
        'file': {
            'level': 'DEBUG', # ファイルには全てのデバッグ情報を残す
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(log_dir, 'gcs.log'),
            'maxBytes': 5 * 1024 * 1024,  # 5MBごとにローテーション
            'backupCount': 5,             # 過去5回分のログファイルを保持
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'DEBUG',
    },
}

def setup_logging():
    logging.config.dictConfig(LOGGING_CONFIG)

# logging_config.py
import logging
import logging.config
import os

# Ensure log directory exists
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

DEFAULT_CONFIG = {
    "level": "INFO",
    "console": {
        "enabled": True,
        "level": "INFO",
    },
    "file": {
        "enabled": True,
        "level": "DEBUG",
        "path": os.path.join("logs", "gcs.log"),
        "max_bytes": 5 * 1024 * 1024,
        "backup_count": 5,
    },
}


def build_handlers(config: dict) -> dict:
    """config の log セクションからハンドラ設定を動的に構築する"""
    log_cfg = config.get("log", {}) if config else {}
    console_cfg = log_cfg.get("console", {})
    file_cfg = log_cfg.get("file", {})

    # 全体レベルのフォールバック
    root_level = log_cfg.get("level", "INFO")

    handlers = {}

    # --- コンソールハンドラ ---
    if console_cfg.get("enabled", True):
        handlers["console"] = {
            "level": console_cfg.get("level", root_level),
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }

    # --- ファイルハンドラ ---
    if file_cfg.get("enabled", True):
        file_path = file_cfg.get("path", os.path.join("logs", "gcs.log"))
        file_dir = os.path.dirname(file_path)
        if file_dir and not os.path.exists(file_dir):
            os.makedirs(file_dir, exist_ok=True)
        handlers["file"] = {
            "level": file_cfg.get("level", "DEBUG"),
            "class": "logging.handlers.RotatingFileHandler",
            "filename": file_path,
            "maxBytes": file_cfg.get("max_bytes", 5 * 1024 * 1024),
            "backupCount": file_cfg.get("backup_count", 5),
            "formatter": "standard",
        }

    return handlers


def setup_logging(config: dict | None = None):
    """
    ロギング設定を適用する。

    Args:
        config: config.yml の内容（dict）。None の場合はデフォルト値で動作。
                config の log セクションからレベル / console / file を読み取る。
                log セクションがない場合やキーが不足している場合はデフォルト値で補完。
    """
    log_cfg = config.get("log", {}) if config else {}
    root_level = log_cfg.get("level", "INFO")

    handlers = build_handlers(config)

    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
            },
        },
        "handlers": handlers,
        "root": {
            "handlers": list(handlers.keys()),
            "level": root_level,
        },
    }

    logging.config.dictConfig(LOGGING_CONFIG)
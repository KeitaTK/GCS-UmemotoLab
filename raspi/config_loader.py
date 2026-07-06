"""
raspi/config_loader.py — Raspberry Pi 用 設定ローダー

優先順位:
  1. RASPI_CONFIG_PATH 環境変数（明示指定）
  2. raspi/config.yml（デフォルト）
"""

import os
import sys
from pathlib import Path


def load_raspi_config(explicit_path=None) -> dict:
    """raspi/config.yml を読み込み、Raspberry Pi 用設定を返す。

    Args:
        explicit_path: 明示的なパス（省略時は自動検出）

    Returns:
        dict: {
            'connection': {'type': str, 'serial_port': str,
                           'serial_baudrate': int, 'udp_listen_port': int},
            'rtcm': {'enabled': bool, 'host': str, 'port': int},
            'drones': [{'system_id': int, 'name': str}, ...],
            'log': {'level': str, 'stats_interval_sec': int},
        }
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML が必要です。 `pip install pyyaml` でインストールしてください。"
        )

    # 設定ファイルの候補を収集
    repo_root = Path(__file__).resolve().parent.parent  # リポジトリルート
    raspi_dir = repo_root / "raspi"

    candidates = []

    # 1. 明示指定
    if explicit_path:
        candidates.append(("explicit", Path(explicit_path)))

    # 2. 環境変数 RASPI_CONFIG_PATH
    env_path = os.environ.get("RASPI_CONFIG_PATH")
    if env_path:
        candidates.append(("env", Path(env_path)))

    # 3. デフォルト
    candidates.append(("default", raspi_dir / "config.yml"))

    # 存在するファイルを探す
    for label, candidate_path in candidates:
        resolved = candidate_path
        if not resolved.is_absolute():
            resolved = repo_root / resolved
        if resolved.exists():
            with open(resolved, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            return config

    raise FileNotFoundError(
        f"raspi/config.yml が見つかりません。"
        f" 検索パス: {[str(p) for _, p in candidates]}"
    )
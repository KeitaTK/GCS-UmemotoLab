from pathlib import Path
import os


def resolve_config_path(explicit_path=None):
    """Resolve the config file path with local overrides."""
    repo_root = Path(__file__).resolve().parent.parent

    if explicit_path:
        candidate = Path(explicit_path)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.exists():
            return str(candidate)
        raise FileNotFoundError(f"設定ファイルが見つかりません: {candidate}")

    env_path = os.environ.get("GCS_CONFIG_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
            repo_root / "config" / "gcs.user.local.yml",
            repo_root / "config" / "gcs_local.yml",
            repo_root / "config" / "gcs.yml",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError("利用可能な設定ファイルが見つかりません。config ディレクトリを確認してください。")
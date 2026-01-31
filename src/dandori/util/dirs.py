import os
import re
from pathlib import Path

DEFAULT_HOME = os.environ.get("DD_HOME_DIR", (Path.home() / ".dandori").as_posix())
DEFAULT_TASKS_PATH = (Path(DEFAULT_HOME) / "tasks.yaml").as_posix()
DEFAULT_ARCHIVE_PATH = (Path(DEFAULT_HOME) / "archive.yaml").as_posix()
DEFAULT_ENV_PATH = (Path(DEFAULT_HOME) / "config.env").as_posix()


def get_username(env: dict[str, str]) -> str:
    if (username := os.environ.get("DD_USERNAME")) is not None:
        return username.strip('"').strip("'")
    if (username := env.get("USERNAME")) is not None:
        return username.strip('"').strip("'")
    _msg = "CRITICAL: USERNAME is not set. Please set DD_USERNAME environment variable, "
    _msg += f"and create a config.env file in {DEFAULT_HOME} and set USERNAME in it."
    raise ValueError(_msg)


def ensure_dirs() -> None:
    _path = Path(DEFAULT_HOME)
    _path.mkdir(parents=True, exist_ok=True)


def load_env(path: str = DEFAULT_ENV_PATH) -> dict[str, str]:
    env: dict[str, str] = {}
    _path = Path(path)
    if _path.exists():
        with _path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"([^=]+)=(.*)", line)
                if m:
                    key = m.group(1).strip()
                    val = m.group(2).strip()
                    env[key] = val

    # ---- プロファイル対応 ---------------------------------------------
    #
    # PROFILE / DD_PROFILE が指定されている場合は、
    # ~/.dandori/<profile>/tasks.yaml, archive.yaml をデフォルトにする。
    #
    # 優先順位:
    #   1. OS 環境変数 DD_DATA_PATH / DD_ARCHIVE_PATH
    #   2. config.env 内の DATA_PATH / ARCHIVE_PATH
    #   3. PROFILE / DD_PROFILE に応じたパス
    #   4. 既存のデフォルト (~/.dandori/tasks.yaml 等)
    profile = os.environ.get("DD_PROFILE") or env.get("PROFILE")

    if profile:
        profile_home = Path(DEFAULT_HOME) / profile
        # プロファイル用ディレクトリを先に作っておく
        profile_home.mkdir(parents=True, exist_ok=True)
        profile_tasks_path = (profile_home / "tasks.yaml").as_posix()
        profile_archive_path = (profile_home / "archive.yaml").as_posix()
    else:
        profile_tasks_path = DEFAULT_TASKS_PATH
        profile_archive_path = DEFAULT_ARCHIVE_PATH

    # config.env に書かれていればそれを優先する
    default_data_path = env.get("DATA_PATH", profile_tasks_path)
    default_archive_path = env.get("ARCHIVE_PATH", profile_archive_path)

    # OS環境変数を上書き優先
    env.update(
        {
            "USERNAME": get_username(env),
            "DATA_PATH": os.environ.get("DD_DATA_PATH", default_data_path),
            "ARCHIVE_PATH": os.environ.get("DD_ARCHIVE_PATH", default_archive_path),
            "PROFILE": profile or "default",
        },
    )
    return env

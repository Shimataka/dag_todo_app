import os
import re
from pathlib import Path

DEFAULT_HOME = os.environ.get("DD_HOME_DIR", (Path.home() / ".dandori").as_posix())
DEFAULT_TASKS_PATH = (Path(DEFAULT_HOME) / "tasks.yaml").as_posix()
DEFAULT_ARCHIVE_PATH = (Path(DEFAULT_HOME) / "archive.yaml").as_posix()
DEFAULT_ENV_PATH = (Path(DEFAULT_HOME) / "config.env").as_posix()


def get_username(env: dict[str, str]) -> str:
    match env.get("USERNAME"):
        case None:
            match os.environ.get("DD_USERNAME"):
                case None:
                    _msg = "CRITICAL: USERNAME is not set. Please set DD_USERNAME environment variable, "
                    raise ValueError(_msg)
                case username:
                    return username
        case username:
            return username


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

    # OS環境変数を上書き優先
    env.update(
        {
            "USERNAME": get_username(env),
            "DATA_PATH": os.environ.get("DD_DATA_PATH", env.get("DATA_PATH", DEFAULT_TASKS_PATH)),
            "ARCHIVE_PATH": os.environ.get("DD_ARCHIVE_PATH", env.get("ARCHIVE_PATH", DEFAULT_ARCHIVE_PATH)),
        },
    )
    return env

import getpass
import os
from pathlib import Path


def default_username() -> str:
    """デフォルトのユーザー名を取得します。

    Returns:
        str: デフォルトのユーザー名
    """
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return "anonymous"


def get_username() -> str:
    """ユーザー名を取得します。

    Args:
        str: ユーザー名
    """
    username = os.environ.get("DD_USERNAME")
    if username is not None:
        return username
    return default_username()


def default_profile() -> str:
    """デフォルトのプロファイル名を取得します。

    Returns:
        str: デフォルトのプロファイル名
    """
    return "default"


def get_profile() -> str:
    """プロファイル名を取得します。

    Args:
        str: プロファイル名
    """
    profile = os.environ.get("DD_PROFILE")
    if profile is not None:
        return profile
    return default_profile()


def default_data_path() -> Path:
    """デフォルトのデータパスを取得します。

    Returns:
        Path: デフォルトのデータパス
    """
    if (profile := os.environ.get("DD_PROFILE")) is not None:
        return Path.home() / ".dandori" / profile / "tasks.yaml"
    return Path.home() / ".dandori" / "tasks.yaml"


def get_data_path() -> Path:
    """データパスを取得します。

    Args:
        Path: データパス
    """
    data_path_str = os.environ.get("DD_DATA_PATH")
    data_path = default_data_path() if data_path_str is None else Path(data_path_str)
    if not data_path.exists():
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.touch(exist_ok=False)
    if not data_path.is_file():
        _msg = f"Data path not a file: {data_path}"
        raise NotADirectoryError(_msg)
    return data_path


def default_archive_path() -> Path:
    """デフォルトのアーカイブパスを取得します。

    Returns:
        Path: デフォルトのアーカイブパス
    """
    if (profile := os.environ.get("DD_PROFILE")) is not None:
        return Path.home() / ".dandori" / profile / "archive.yaml"
    return Path.home() / ".dandori" / "archive.yaml"


def get_archive_path() -> Path:
    """アーカイブパスを取得します。

    Args:
        Path: アーカイブパス
    """
    archive_path_str = os.environ.get("DD_ARCHIVE_PATH")
    archive_path = Path(archive_path_str) if archive_path_str is not None else default_archive_path()
    if not archive_path.exists():
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.touch(exist_ok=False)
    if not archive_path.is_file():
        _msg = f"Archive path not a file: {archive_path}"
        raise NotADirectoryError(_msg)
    return archive_path


def default_home_dir() -> Path:
    """デフォルトのホームディレクトリを取得します。

    Returns:
        Path: デフォルトのホームディレクトリ
    """
    home_dir = Path.home() / ".dandori"
    if not home_dir.exists():
        home_dir.mkdir(parents=True, exist_ok=True)
    return home_dir


def load_config() -> dict[str, str]:
    """設定ファイルを読み込みます。

    Returns:
        dict[str, str]: 設定ファイルの設定内容
    """
    home_dir = default_home_dir()
    env_path = home_dir / "config.env"
    if not env_path.exists():
        return {}
    with env_path.open(encoding="utf-8") as f:
        return dict(line.strip().split("=", 1) for line in f if line.strip() and "=" in line)


def load_env() -> dict[str, str]:
    """環境変数を読み込みます。

    Returns:
        dict[str, str]: 環境変数の設定内容
    """
    # overwrite config with environment variables
    env: dict[str, str] = load_config() | {
        "USERNAME": get_username(),
        "PROFILE": get_profile(),
        "DATA_PATH": get_data_path().as_posix(),
        "ARCHIVE_PATH": get_archive_path().as_posix(),
    }
    return env

from dandori.storage.base import Store
from dandori.storage.sqlite3_store import StoreToSQLite
from dandori.storage.yaml_store import StoreToYAML
from dandori.util.dirs import load_env

__all__ = [
    "Store",
]


def get_store() -> Store:
    env = load_env()
    data_path = env["DATA_PATH"]
    archive_path = env["ARCHIVE_PATH"]
    if data_path.endswith(".yaml") and archive_path.endswith(".yaml"):
        return StoreToYAML()
    if data_path.endswith(".db") and archive_path.endswith(".db"):
        return StoreToSQLite()
    _msg = f"Invalid data path or archive path: {data_path} or {archive_path}"
    raise ValueError(_msg)

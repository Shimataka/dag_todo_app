import logging
from logging.handlers import TimedRotatingFileHandler

from dandori.util.dirs import default_home_dir


def setup_mode(*, is_debug: bool) -> None:
    if is_debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)


def setup_logger(
    name: str,
    *,
    is_stream: bool = True,
    is_file: bool = True,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if is_stream or not is_file:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    if is_file:
        time_rotate_file_handler = TimedRotatingFileHandler(
            (default_home_dir() / f"{name.lower()}.log").as_posix(),
            when="MIDNIGHT",
            interval=1,
            backupCount=7,
            encoding="utf-8",
        )
        time_rotate_file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        time_rotate_file_handler.setFormatter(formatter)
        logger.addHandler(time_rotate_file_handler)

    return logger

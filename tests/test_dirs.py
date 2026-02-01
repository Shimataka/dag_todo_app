import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

from dandori.util import dirs


class TestDefaultUsername(unittest.TestCase):
    def test_returns_str(self) -> None:
        assert isinstance(dirs.default_username(), str)
        assert len(dirs.default_username()) > 0

    def test_fallback_on_getuser_error(self) -> None:
        with mock.patch("dandori.util.dirs.getpass.getuser", side_effect=Exception):
            assert dirs.default_username() == "anonymous"


class TestGetUsername(unittest.TestCase):
    def setUp(self) -> None:
        self.original = os.environ.get("DD_USERNAME")

    def tearDown(self) -> None:
        if self.original is not None:
            os.environ["DD_USERNAME"] = self.original
        elif "DD_USERNAME" in os.environ:
            del os.environ["DD_USERNAME"]

    def test_uses_env_when_set(self) -> None:
        os.environ["DD_USERNAME"] = "env_user"
        assert dirs.get_username() == "env_user"

    def test_falls_back_when_env_unset(self) -> None:
        if "DD_USERNAME" in os.environ:
            del os.environ["DD_USERNAME"]
        out = dirs.get_username()
        assert isinstance(out, str)
        assert out in (dirs.default_username(), "anonymous") or len(out) > 0


class TestDefaultProfile(unittest.TestCase):
    def test_returns_default(self) -> None:
        assert dirs.default_profile() == "default"


class TestGetProfile(unittest.TestCase):
    def setUp(self) -> None:
        self.original = os.environ.get("DD_PROFILE")

    def tearDown(self) -> None:
        if self.original is not None:
            os.environ["DD_PROFILE"] = self.original
        elif "DD_PROFILE" in os.environ:
            del os.environ["DD_PROFILE"]

    def test_uses_env_when_set(self) -> None:
        os.environ["DD_PROFILE"] = "myprofile"
        assert dirs.get_profile() == "myprofile"

    def test_falls_back_when_env_unset(self) -> None:
        if "DD_PROFILE" in os.environ:
            del os.environ["DD_PROFILE"]
        assert dirs.get_profile() == "default"


class TestDefaultDataPath(unittest.TestCase):
    def setUp(self) -> None:
        self.original = os.environ.get("DD_PROFILE")
        self.fake_home = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        if self.original is not None:
            os.environ["DD_PROFILE"] = self.original
        elif "DD_PROFILE" in os.environ:
            del os.environ["DD_PROFILE"]
        with contextlib.suppress(OSError):
            self.fake_home.rmdir()

    def test_without_profile(self) -> None:
        if "DD_PROFILE" in os.environ:
            del os.environ["DD_PROFILE"]
        with mock.patch("pathlib.Path.home", return_value=self.fake_home):
            p = dirs.default_data_path()
        assert p == self.fake_home / ".dandori" / "tasks.yaml"

    def test_with_profile(self) -> None:
        os.environ["DD_PROFILE"] = "dev"
        with mock.patch("pathlib.Path.home", return_value=self.fake_home):
            p = dirs.default_data_path()
        assert p == self.fake_home / ".dandori" / "dev" / "tasks.yaml"


class TestGetDataPath(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")  # noqa: SIM115
        self.temp_file.close()
        self.original_data = os.environ.get("DD_DATA_PATH")
        self.original_profile = os.environ.get("DD_PROFILE")

    def tearDown(self) -> None:
        Path(self.temp_file.name).unlink(missing_ok=True)
        if self.original_data is not None:
            os.environ["DD_DATA_PATH"] = self.original_data
        elif "DD_DATA_PATH" in os.environ:
            del os.environ["DD_DATA_PATH"]
        if self.original_profile is not None:
            os.environ["DD_PROFILE"] = self.original_profile
        elif "DD_PROFILE" in os.environ:
            del os.environ["DD_PROFILE"]

    def test_uses_env_existing_file(self) -> None:
        os.environ["DD_DATA_PATH"] = self.temp_file.name
        p = dirs.get_data_path()
        assert p == Path(self.temp_file.name)
        assert p.is_file()

    def test_creates_file_when_missing(self) -> None:
        missing = self.temp_file.name + ".nonexistent"
        assert not Path(missing).exists()
        os.environ["DD_DATA_PATH"] = missing
        p = dirs.get_data_path()
        assert p == Path(missing)
        assert p.is_file()
        Path(missing).unlink(missing_ok=True)

    def test_raises_when_path_is_directory(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            os.environ["DD_DATA_PATH"] = tmpdir
            with pytest.raises(NotADirectoryError, match="Data path not a file"):
                dirs.get_data_path()
        finally:
            with contextlib.suppress(OSError):
                Path(tmpdir).rmdir()

    def test_uses_default_when_env_unset(self) -> None:
        if "DD_DATA_PATH" in os.environ:
            del os.environ["DD_DATA_PATH"]
        fake_home = Path(tempfile.mkdtemp())
        expected = fake_home / ".dandori" / "tasks.yaml"
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.touch()
        try:
            with mock.patch("pathlib.Path.home", return_value=fake_home):
                p = dirs.get_data_path()
            assert p == expected
        finally:
            expected.unlink(missing_ok=True)
            try:
                (fake_home / ".dandori").rmdir()
                fake_home.rmdir()
            except OSError:
                pass


class TestDefaultArchivePath(unittest.TestCase):
    def setUp(self) -> None:
        self.original = os.environ.get("DD_PROFILE")
        self.fake_home = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        if self.original is not None:
            os.environ["DD_PROFILE"] = self.original
        elif "DD_PROFILE" in os.environ:
            del os.environ["DD_PROFILE"]
        with contextlib.suppress(OSError):
            self.fake_home.rmdir()

    def test_without_profile(self) -> None:
        if "DD_PROFILE" in os.environ:
            del os.environ["DD_PROFILE"]
        with mock.patch("pathlib.Path.home", return_value=self.fake_home):
            p = dirs.default_archive_path()
        assert p == self.fake_home / ".dandori" / "archive.yaml"

    def test_with_profile(self) -> None:
        os.environ["DD_PROFILE"] = "dev"
        with mock.patch("pathlib.Path.home", return_value=self.fake_home):
            p = dirs.default_archive_path()
        assert p == self.fake_home / ".dandori" / "dev" / "archive.yaml"


class TestGetArchivePath(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")  # noqa: SIM115
        self.temp_file.close()
        self.original_archive = os.environ.get("DD_ARCHIVE_PATH")
        self.original_profile = os.environ.get("DD_PROFILE")

    def tearDown(self) -> None:
        Path(self.temp_file.name).unlink(missing_ok=True)
        if self.original_archive is not None:
            os.environ["DD_ARCHIVE_PATH"] = self.original_archive
        elif "DD_ARCHIVE_PATH" in os.environ:
            del os.environ["DD_ARCHIVE_PATH"]
        if self.original_profile is not None:
            os.environ["DD_PROFILE"] = self.original_profile
        elif "DD_PROFILE" in os.environ:
            del os.environ["DD_PROFILE"]

    def test_uses_env_existing_file(self) -> None:
        os.environ["DD_ARCHIVE_PATH"] = self.temp_file.name
        p = dirs.get_archive_path()
        assert p == Path(self.temp_file.name)
        assert p.is_file()

    def test_creates_file_when_missing(self) -> None:
        missing = self.temp_file.name + ".nonexistent"
        assert not Path(missing).exists()
        os.environ["DD_ARCHIVE_PATH"] = missing
        p = dirs.get_archive_path()
        assert p == Path(missing)
        assert p.is_file()
        Path(missing).unlink(missing_ok=True)

    def test_raises_when_path_is_directory(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            os.environ["DD_ARCHIVE_PATH"] = tmpdir
            with pytest.raises(NotADirectoryError, match="Archive path not a file"):
                dirs.get_archive_path()
        finally:
            with contextlib.suppress(OSError):
                Path(tmpdir).rmdir()

    def test_uses_default_when_env_unset(self) -> None:
        if "DD_ARCHIVE_PATH" in os.environ:
            del os.environ["DD_ARCHIVE_PATH"]
        fake_home = Path(tempfile.mkdtemp())
        expected = fake_home / ".dandori" / "archive.yaml"
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.touch()
        try:
            with mock.patch("pathlib.Path.home", return_value=fake_home):
                p = dirs.get_archive_path()
            assert p == expected
        finally:
            expected.unlink(missing_ok=True)
            try:
                (fake_home / ".dandori").rmdir()
                fake_home.rmdir()
            except OSError:
                pass


class TestDefaultHomeDir(unittest.TestCase):
    def test_returns_dandori_under_home(self) -> None:
        fake_home = Path(tempfile.mkdtemp())
        try:
            with mock.patch("pathlib.Path.home", return_value=fake_home):
                p = dirs.default_home_dir()
            assert p == fake_home / ".dandori"
            assert p.exists()
            assert p.is_dir()
        finally:
            try:
                (fake_home / ".dandori").rmdir()
                fake_home.rmdir()
            except OSError:
                pass

    def test_creates_dir_when_missing(self) -> None:
        fake_home = Path(tempfile.mkdtemp())
        dandori = fake_home / ".dandori"
        assert not dandori.exists()
        try:
            with mock.patch("pathlib.Path.home", return_value=fake_home):
                p = dirs.default_home_dir()
            assert p.exists()
            assert p.is_dir()
        finally:
            try:
                dandori.rmdir()
                fake_home.rmdir()
            except OSError:
                pass


class TestLoadConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_home = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        try:
            for f in (self.fake_home / ".dandori").iterdir():
                f.unlink(missing_ok=True)
            (self.fake_home / ".dandori").rmdir()
            self.fake_home.rmdir()
        except OSError:
            pass

    def test_returns_empty_when_no_config(self) -> None:
        with mock.patch("dandori.util.dirs.default_home_dir", return_value=self.fake_home / ".dandori"):
            (self.fake_home / ".dandori").mkdir(parents=True, exist_ok=True)
            cfg = dirs.load_config()
        assert cfg == {}

    def test_parses_config_env(self) -> None:
        (self.fake_home / ".dandori").mkdir(parents=True, exist_ok=True)
        env_path = self.fake_home / ".dandori" / "config.env"
        env_path.write_text("KEY1=val1\nKEY2=val2\n", encoding="utf-8")
        with mock.patch("dandori.util.dirs.default_home_dir", return_value=self.fake_home / ".dandori"):
            cfg = dirs.load_config()
        assert cfg == {"KEY1": "val1", "KEY2": "val2"}

    def test_skips_empty_lines(self) -> None:
        (self.fake_home / ".dandori").mkdir(parents=True, exist_ok=True)
        env_path = self.fake_home / ".dandori" / "config.env"
        env_path.write_text("A=1\n\nB=2\n", encoding="utf-8")
        with mock.patch("dandori.util.dirs.default_home_dir", return_value=self.fake_home / ".dandori"):
            cfg = dirs.load_config()
        assert cfg == {"A": "1", "B": "2"}


class TestLoadEnv(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_data = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")  # noqa: SIM115
        self.temp_archive = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")  # noqa: SIM115
        self.temp_data.close()
        self.temp_archive.close()
        self.orig_data = os.environ.get("DD_DATA_PATH")
        self.orig_archive = os.environ.get("DD_ARCHIVE_PATH")
        self.orig_username = os.environ.get("DD_USERNAME")
        self.orig_profile = os.environ.get("DD_PROFILE")

    def tearDown(self) -> None:
        Path(self.temp_data.name).unlink(missing_ok=True)
        Path(self.temp_archive.name).unlink(missing_ok=True)
        for key, val in [
            ("DD_DATA_PATH", self.orig_data),
            ("DD_ARCHIVE_PATH", self.orig_archive),
            ("DD_USERNAME", self.orig_username),
            ("DD_PROFILE", self.orig_profile),
        ]:
            if val is not None:
                os.environ[key] = val
            elif key in os.environ:
                del os.environ[key]

    def test_returns_username_profile_data_archive_paths(self) -> None:
        os.environ["DD_DATA_PATH"] = self.temp_data.name
        os.environ["DD_ARCHIVE_PATH"] = self.temp_archive.name
        env = dirs.load_env()
        assert "USERNAME" in env
        assert "PROFILE" in env
        assert env["DATA_PATH"] == Path(self.temp_data.name).as_posix()
        assert env["ARCHIVE_PATH"] == Path(self.temp_archive.name).as_posix()

    def test_overrides_config_with_env_values(self) -> None:
        os.environ["DD_DATA_PATH"] = self.temp_data.name
        os.environ["DD_ARCHIVE_PATH"] = self.temp_archive.name
        os.environ["DD_USERNAME"] = "testuser"
        os.environ["DD_PROFILE"] = "testprofile"
        env = dirs.load_env()
        assert env["USERNAME"] == "testuser"
        assert env["PROFILE"] == "testprofile"


if __name__ == "__main__":
    unittest.main()

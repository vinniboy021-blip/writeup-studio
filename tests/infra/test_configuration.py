# SPDX-License-Identifier: MIT
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("studio_setup", ROOT / "scripts/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_generates_private_config_without_secret_output(tmp_path, capsys):
    path = tmp_path / "test.env"
    assert setup.main(["--env-file", str(path)]) == 0
    assert path.stat().st_mode & 0o777 == 0o600
    values = setup.read_env(path)
    setup.validate(values, False)
    output = capsys.readouterr().out
    assert all(values[key] not in output for key in setup.REQUIRED)
    assert values["POSTGRES_PASSWORD"] in values["DATABASE_URL"]
    assert values["REDIS_PASSWORD"] in values["REDIS_URL"]
    assert values["S3_ACCESS_KEY"] != values["MINIO_ROOT_USER"]
    original = path.read_bytes()
    assert setup.main(["--env-file", str(path)]) == 0
    assert path.read_bytes() == original


def test_refuses_invalid_production_and_preserves_existing(tmp_path):
    path = tmp_path / "production.env"
    with pytest.raises(SystemExit):
        setup.main(["--production", "--origin", "http://example.org", "--env-file", str(path)])
    assert not path.exists()
    assert setup.main(["--production", "--origin", "https://example.org", "--env-file", str(path)]) == 0
    setup.validate(setup.read_env(path), True)
    path.chmod(0o644)
    with pytest.raises(SystemExit):
        setup.main(["--production", "--validate", "--env-file", str(path)])
    path.chmod(0o600)
    path.write_text("SECRET_KEY=weak\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        setup.main(["--env-file", str(path)])
    assert path.read_text() == "SECRET_KEY=weak\n"


def test_refuses_config_symlink_and_non_loopback_test_certificate(tmp_path):
    path = tmp_path / "existing.env"
    setup.write_private(path, "SECRET_KEY=protected\n")
    link = tmp_path / "link.env"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        setup.read_env(link)
    with pytest.raises(ValueError):
        setup.test_certificate("https://example.org", tmp_path / "certs")


def test_loopback_certificate_generates_private_key(tmp_path):
    import shutil
    if not shutil.which("openssl"):
        pytest.skip("openssl não disponível")
    setup.test_certificate("https://localhost", tmp_path)
    assert (tmp_path / "privkey.pem").stat().st_mode & 0o777 == 0o600
    assert "BEGIN CERTIFICATE" in (tmp_path / "fullchain.pem").read_text()
    with pytest.raises(ValueError):
        setup.test_certificate("https://localhost", tmp_path)

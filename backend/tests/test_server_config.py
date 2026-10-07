import shutil
import ssl
import subprocess

import pytest

from app import runtime, serve, server_db
from app.config import settings
from app.errors import ValidationError
from app.services import server_config, users

needs_openssl = pytest.mark.skipif(shutil.which("openssl") is None, reason="needs the openssl binary")


def make_cert(directory, name="server"):
    cert, key = directory / f"{name}.crt", directory / f"{name}.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=localhost",
         "-keyout", str(key), "-out", str(cert)],
        check=True,
        capture_output=True,
    )
    return cert, key


@pytest.fixture()
def certs(tmp_path):
    return make_cert(tmp_path)


@pytest.fixture(autouse=True)
def _no_runtime(monkeypatch):
    monkeypatch.setattr(runtime, "current", None)
    monkeypatch.setattr(settings, "port", None)
    monkeypatch.setattr(settings, "ssl_disabled", False)


# --- saving settings ---------------------------------------------------


def test_defaults(server_session):
    row = users.get_settings(server_session)
    assert (row.port, row.ssl_enabled, row.ssl_certfile, row.ssl_keyfile) == (8000, False, None, None)


@pytest.mark.parametrize("port", [0, -1, 65536, 100000])
def test_rejects_a_port_out_of_range(server_session, port):
    with pytest.raises(ValidationError, match="Port must be between 1 and 65535"):
        server_config.update(server_session, port=port)


def test_saves_a_port(server_session):
    assert server_config.update(server_session, port=8443).port == 8443
    assert users.get_settings(server_session).port == 8443


@needs_openssl
def test_enabling_ssl_saves_a_working_pair(server_session, certs):
    cert, key = certs
    row = server_config.update(
        server_session, ssl_enabled=True, ssl_certfile=f"  {cert} ", ssl_keyfile=str(key)
    )
    assert (row.ssl_enabled, row.ssl_certfile, row.ssl_keyfile) == (True, str(cert), str(key))


def test_enabling_ssl_needs_both_paths(server_session):
    with pytest.raises(ValidationError, match="certificate file and a key file"):
        server_config.update(server_session, ssl_enabled=True)
    with pytest.raises(ValidationError, match="certificate file and a key file"):
        server_config.update(server_session, ssl_enabled=True, ssl_certfile="/x.crt", ssl_keyfile="  ")
    assert users.get_settings(server_session).ssl_enabled is False


@needs_openssl
def test_enabling_ssl_refuses_files_that_cannot_serve(server_session, certs, tmp_path):
    cert, key = certs
    other_cert, other_key = make_cert(tmp_path, "other")
    junk = tmp_path / "junk.pem"
    junk.write_text("not a certificate")

    cases = [
        (str(tmp_path / "missing.crt"), str(key), "Certificate file not found"),
        (str(cert), str(tmp_path / "missing.key"), "Key file not found"),
        (str(tmp_path), str(key), "Certificate file not found"),  # a directory
        (str(junk), str(key), "can't be used together"),
        (str(cert), str(other_key), "can't be used together"),  # a key for a different cert
        ("relative.crt", str(key), "must be an absolute path"),
    ]
    for certfile, keyfile, message in cases:
        with pytest.raises(ValidationError, match=message):
            server_config.update(server_session, ssl_enabled=True, ssl_certfile=certfile, ssl_keyfile=keyfile)
    assert users.get_settings(server_session).ssl_enabled is False
    assert other_cert.exists()


def test_paths_can_be_saved_unchecked_while_ssl_is_off(server_session):
    # Lets the paths be filled in ahead of the files being put in place.
    row = server_config.update(server_session, ssl_certfile="/not/there.crt", ssl_keyfile="/not/there.key")
    assert row.ssl_enabled is False and row.ssl_certfile == "/not/there.crt"
    with pytest.raises(ValidationError, match="Certificate file not found"):
        server_config.update(server_session, ssl_enabled=True)


@needs_openssl
def test_disabling_ssl_keeps_the_paths(server_session, certs):
    cert, key = certs
    server_config.update(server_session, ssl_enabled=True, ssl_certfile=str(cert), ssl_keyfile=str(key))
    row = server_config.update(server_session, ssl_enabled=False)
    assert (row.ssl_enabled, row.ssl_certfile) == (False, str(cert))


# --- what the server starts with ---------------------------------------


def test_startup_uses_plain_http_on_the_saved_port(server_session):
    server_config.update(server_session, port=9001)
    assert server_config.resolve_startup(server_session) == runtime.Runtime(port=9001, ssl_certfile=None, ssl_keyfile=None)


@needs_openssl
def test_startup_uses_ssl_when_enabled(server_session, certs):
    cert, key = certs
    server_config.update(server_session, ssl_enabled=True, ssl_certfile=str(cert), ssl_keyfile=str(key))
    started = server_config.resolve_startup(server_session)
    assert started == runtime.Runtime(port=8000, ssl_certfile=str(cert), ssl_keyfile=str(key))
    assert started.ssl_enabled is True


@needs_openssl
@pytest.mark.parametrize("gone", ["cert", "key"])
def test_startup_fails_when_an_ssl_file_has_gone_missing(server_session, certs, gone):
    cert, key = certs
    server_config.update(server_session, ssl_enabled=True, ssl_certfile=str(cert), ssl_keyfile=str(key))
    (cert if gone == "cert" else key).unlink()
    with pytest.raises(server_config.StartupError, match="file not found"):
        server_config.resolve_startup(server_session)


@needs_openssl
def test_environment_can_override_port_and_switch_ssl_off(server_session, certs, monkeypatch):
    cert, key = certs
    server_config.update(server_session, ssl_enabled=True, ssl_certfile=str(cert), ssl_keyfile=str(key), port=9001)
    cert.unlink()  # the lock-out this escape hatch exists for
    monkeypatch.setattr(settings, "ssl_disabled", True)
    monkeypatch.setattr(settings, "port", 9100)
    assert server_config.resolve_startup(server_session) == runtime.Runtime(port=9100, ssl_certfile=None, ssl_keyfile=None)


# --- the launcher ------------------------------------------------------


@needs_openssl
def test_launcher_starts_uvicorn_with_the_saved_settings(files, certs, monkeypatch):
    cert, key = certs
    with server_db.SessionLocal() as sdb:
        server_config.update(sdb, ssl_enabled=True, ssl_certfile=str(cert), ssl_keyfile=str(key), port=8443)
    calls = []
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    monkeypatch.setattr(settings, "host", "0.0.0.0")

    serve.main()

    (app, kwargs), = calls
    assert kwargs == {"host": "0.0.0.0", "port": 8443, "ssl_certfile": str(cert), "ssl_keyfile": str(key)}
    assert runtime.current == runtime.Runtime(port=8443, ssl_certfile=str(cert), ssl_keyfile=str(key))
    # ...and the pair really is one uvicorn's TLS context will accept.
    ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(kwargs["ssl_certfile"], kwargs["ssl_keyfile"])


def test_launcher_starts_plain_http_on_a_fresh_server(files, monkeypatch):
    calls = []
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    serve.main()
    assert calls == [{"host": "127.0.0.1", "port": 8000}]
    assert (files / "server.db").exists()  # migrated before the settings were read


@needs_openssl
def test_launcher_refuses_to_start_when_the_certificate_is_missing(files, certs, monkeypatch, capsys):
    cert, key = certs
    with server_db.SessionLocal() as sdb:
        server_config.update(sdb, ssl_enabled=True, ssl_certfile=str(cert), ssl_keyfile=str(key))
    cert.unlink()
    started = []
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kwargs: started.append(kwargs))

    with pytest.raises(SystemExit) as exit_info:
        serve.main()

    assert exit_info.value.code == 1
    assert started == []
    message = capsys.readouterr().err
    assert "Certificate file not found" in message and str(cert) in message
    assert "BUDGETER_SSL_DISABLED" in message  # says how to get back in


# --- the data directory -------------------------------------------------


def test_launcher_announces_where_the_data_lives(files, monkeypatch, capsys):
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kwargs: None)
    serve.main()
    assert f"budgeter: data directory: {files}" in capsys.readouterr().err


def test_launcher_creates_a_missing_data_directory(tmp_path, monkeypatch):
    target = tmp_path / "mounted" / "budgeter"
    monkeypatch.setattr(settings, "data_dir", str(target))
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{target}/budgeter.db")
    server_db.reset()
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kwargs: None)
    try:
        serve.main()
        assert (target / "server.db").exists()
    finally:
        server_db.reset()


def test_launcher_refuses_to_start_on_a_data_directory_it_cannot_write(tmp_path, monkeypatch, capsys):
    # What a host directory mounted with the wrong ownership looks like.
    target = tmp_path / "readonly"
    target.mkdir()
    target.chmod(0o555)
    monkeypatch.setattr(settings, "data_dir", str(target))
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{target}/budgeter.db")
    server_db.reset()
    started = []
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kwargs: started.append(kwargs))
    try:
        with pytest.raises(SystemExit) as exit_info:
            serve.main()
    finally:
        target.chmod(0o755)
        server_db.reset()

    assert exit_info.value.code == 1
    assert started == []
    message = capsys.readouterr().err
    assert "can't write to the data directory" in message and str(target) in message
    assert list(target.iterdir()) == []  # nothing half-created

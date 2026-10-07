import subprocess

import pytest

from app import version


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    for name in ("BUDGETER_BUILD_SHA", "BUDGETER_BUILD_COMMIT_DATE", "BUDGETER_BUILD_DATE"):
        monkeypatch.delenv(name, raising=False)
    version.get_version.cache_clear()
    yield
    version.get_version.cache_clear()


def test_a_built_image_reports_what_was_baked_in(monkeypatch):
    monkeypatch.setenv("BUDGETER_BUILD_SHA", "5dcc9d3a1b2c3d4e5f60718293a4b5c6d7e8f901")
    monkeypatch.setenv("BUDGETER_BUILD_COMMIT_DATE", "2026-10-07T14:03:22-04:00")
    monkeypatch.setenv("BUDGETER_BUILD_DATE", "2026-10-08T09:15:00Z")
    # Never asks git when the build told it: the image has no repository.
    monkeypatch.setattr(version, "_git", lambda *args: pytest.fail("git was consulted"))

    info = version.get_version()

    assert info == version.VersionInfo(
        version="2026.10.07+5dcc9d3",
        sha="5dcc9d3a1b2c3d4e5f60718293a4b5c6d7e8f901",
        commit_date="2026-10-07T14:03:22-04:00",
        build_date="2026-10-08T09:15:00Z",
        dirty=False,
    )


def test_a_checkout_reports_its_commit_from_git(monkeypatch):
    answers = {
        ("rev-parse", "HEAD"): "0123456789abcdef0123456789abcdef01234567",
        ("log", "-1", "--format=%cI"): "2026-09-30T08:00:00+00:00",
        ("status", "--porcelain", "--untracked-files=no"): "",
    }
    monkeypatch.setattr(version, "_git", lambda *args: answers[args])

    info = version.get_version()

    assert info.version == "2026.09.30+0123456"
    assert info.sha == "0123456789abcdef0123456789abcdef01234567"
    assert info.commit_date == "2026-09-30T08:00:00+00:00"
    assert info.build_date is None  # nothing was built
    assert info.dirty is False


def test_uncommitted_changes_are_flagged(monkeypatch):
    answers = {
        ("rev-parse", "HEAD"): "0123456789abcdef0123456789abcdef01234567",
        ("log", "-1", "--format=%cI"): "2026-09-30T08:00:00+00:00",
        ("status", "--porcelain", "--untracked-files=no"): " M backend/app/main.py",
    }
    monkeypatch.setattr(version, "_git", lambda *args: answers[args])
    info = version.get_version()
    assert info.dirty is True
    assert info.version == "2026.09.30+0123456.dirty"


def test_unknown_when_neither_the_build_nor_git_can_say(monkeypatch):
    monkeypatch.setattr(version, "_git", lambda *args: None)
    assert version.get_version() == version.VersionInfo(
        version="unknown", sha=None, commit_date=None, build_date=None, dirty=False
    )


@pytest.mark.parametrize("placeholder", ["", "unknown"])
def test_placeholder_build_args_fall_back_to_git(monkeypatch, placeholder):
    # What the Containerfile's ARG defaults produce when built without the script.
    monkeypatch.setenv("BUDGETER_BUILD_SHA", placeholder)
    monkeypatch.setattr(version, "_git", lambda *args: None)
    assert version.get_version().version == "unknown"


def test_git_helper_survives_a_missing_binary_or_repository(monkeypatch, tmp_path):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)
    assert version._git("rev-parse", "HEAD") is None


def test_the_real_checkout_resolves_to_something_sensible():
    info = version.get_version()
    assert info.version == "unknown" or (info.sha and info.sha[:7] in info.version)


def test_version_endpoint_needs_a_login(client, auth_headers, monkeypatch):
    monkeypatch.setenv("BUDGETER_BUILD_SHA", "5dcc9d3a1b2c3d4e5f60718293a4b5c6d7e8f901")
    monkeypatch.setenv("BUDGETER_BUILD_COMMIT_DATE", "2026-10-07T14:03:22-04:00")
    monkeypatch.setenv("BUDGETER_BUILD_DATE", "2026-10-08T09:15:00Z")

    assert client.get("/api/version").status_code == 401
    resp = client.get("/api/version", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "version": "2026.10.07+5dcc9d3",
        "sha": "5dcc9d3a1b2c3d4e5f60718293a4b5c6d7e8f901",
        "commit_date": "2026-10-07T14:03:22-04:00",
        "build_date": "2026-10-08T09:15:00Z",
        "dirty": False,
    }


def test_version_is_in_the_admin_health_report_but_not_the_public_one(client, auth_headers, monkeypatch):
    monkeypatch.setenv("BUDGETER_BUILD_SHA", "5dcc9d3a1b2c3d4e5f60718293a4b5c6d7e8f901")
    monkeypatch.setenv("BUDGETER_BUILD_COMMIT_DATE", "2026-10-07T14:03:22-04:00")

    body = client.get("/api/admin/health", headers=auth_headers).json()
    assert body["version"]["version"] == "2026.10.07+5dcc9d3"
    assert "version" not in client.get("/health").json()

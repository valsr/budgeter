"""Which build of the app this is: a commit, its date, and when it was built.

There are no release numbers. A version is the commit's date plus its short
hash -- `2026.10.07+5dcc9d3` -- which sorts by time and names exactly one
state of the code.

A built image is told at build time (scripts/podman-build.sh passes the
values in as build args, which the Containerfile turns into the environment
variables below; the image has no .git to ask). A source checkout asks git.
"""

import os
import subprocess
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

_REPO_DIR = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class VersionInfo:
    version: str
    sha: str | None
    commit_date: str | None
    """When the commit was made, ISO 8601."""
    build_date: str | None
    """When the image was built, ISO 8601. None when running from source."""
    dirty: bool
    """Running from a checkout with uncommitted changes to tracked files."""

    def as_dict(self) -> dict:
        return asdict(self)


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    # "unknown" is the Containerfile's ARG default, for an image built
    # without the script that fills the values in.
    return None if value in ("", "unknown") else value


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO_DIR), *args], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None  # no git, or it hung
    return result.stdout.strip() if result.returncode == 0 else None


def _label(sha: str | None, commit_date: str | None, dirty: bool) -> str:
    if not sha:
        return "unknown"
    day = commit_date[:10].replace("-", ".") if commit_date else "0000.00.00"
    return f"{day}+{sha[:7]}" + (".dirty" if dirty else "")


@lru_cache(maxsize=1)
def get_version() -> VersionInfo:
    sha = _env("BUDGETER_BUILD_SHA")
    if sha:
        commit_date = _env("BUDGETER_BUILD_COMMIT_DATE")
        return VersionInfo(
            version=_label(sha, commit_date, False),
            sha=sha,
            commit_date=commit_date,
            build_date=_env("BUDGETER_BUILD_DATE"),
            dirty=False,
        )

    sha = _git("rev-parse", "HEAD") or None
    if not sha:
        return VersionInfo(version="unknown", sha=None, commit_date=None, build_date=None, dirty=False)
    commit_date = _git("log", "-1", "--format=%cI") or None
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    return VersionInfo(
        version=_label(sha, commit_date, dirty), sha=sha, commit_date=commit_date, build_date=None, dirty=dirty
    )

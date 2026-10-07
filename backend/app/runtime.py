"""What this process is actually serving with, as opposed to what is saved
in Settings → Server (which only takes effect at the next start)."""

from dataclasses import dataclass

from app.server_models import utcnow

STARTED_AT = utcnow()


@dataclass(frozen=True)
class Runtime:
    port: int
    ssl_certfile: str | None
    ssl_keyfile: str | None

    @property
    def ssl_enabled(self) -> bool:
        return self.ssl_certfile is not None


# Set by the launcher (app/serve.py) just before it starts serving. None
# when the app was started some other way -- `uvicorn app.main:app` in dev,
# the test client -- where the port and TLS are whatever that command chose
# and the saved settings were never consulted.
current: Runtime | None = None

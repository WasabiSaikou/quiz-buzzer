"""Settings loaded from .env (python-dotenv). Principle VI: no secrets in code or logs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_DB_PATH = "data/quizbuzzer.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


PASSCODE_MISSING = "TEACHER_PASSCODE is not set in .env."


class ConfigError(RuntimeError):
    """Configuration is missing or invalid. Messages name env vars, never secret contents."""


@dataclass(frozen=True)
class Settings:
    credentials_path: Path | None
    db_path: Path
    host: str
    port: int
    # Feature 002 (research R1): required; validated by load_settings() and create_app().
    # repr=False: the passcode must never appear in logs or tracebacks (Principle VI).
    teacher_passcode: str = field(default="", repr=False)

    @property
    def service_account_email(self) -> str:
        """The key file's client_email (not secret; shown to the teacher for sharing)."""
        if self.credentials_path is None:
            raise ConfigError("GOOGLE_APPLICATION_CREDENTIALS is not set in .env.")
        if not self.credentials_path.is_file():
            raise ConfigError(
                "The file named by GOOGLE_APPLICATION_CREDENTIALS does not exist."
            )
        try:
            data = json.loads(self.credentials_path.read_text(encoding="utf-8"))
            email = data["client_email"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ConfigError(
                "The file named by GOOGLE_APPLICATION_CREDENTIALS is not a service-account key "
                "(no client_email)."
            ) from exc
        if not isinstance(email, str) or not email:
            raise ConfigError("The service-account key has an empty client_email.")
        return email


def load_settings(env_file: str | os.PathLike[str] | None = ".env") -> Settings:
    """Read .env (if present) and the process environment into Settings."""
    if env_file is not None:
        load_dotenv(env_file, override=False)
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    port_text = os.environ.get("QUIZBUZZER_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ConfigError("QUIZBUZZER_PORT must be an integer.") from exc
    passcode = os.environ.get("TEACHER_PASSCODE", "").strip()
    if not passcode:
        raise ConfigError(PASSCODE_MISSING)
    return Settings(
        credentials_path=Path(creds) if creds else None,
        db_path=Path(os.environ.get("QUIZBUZZER_DB_PATH", "").strip() or DEFAULT_DB_PATH),
        host=os.environ.get("QUIZBUZZER_HOST", "").strip() or DEFAULT_HOST,
        port=port,
        teacher_passcode=passcode,
    )

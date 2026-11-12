"""Environment-validated settings, loaded once."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.errors import StartupError
from app.schemas import EMAIL_MAX, EMAIL_RE  # P18.2

ROOT = Path(__file__).resolve().parents[1]

# sha256 of the six official CSVs (raw bytes); same map as scripts/check_official.py.
OFFICIAL_SHA256 = {
    "knowledge_base.csv": "5122ef4691230fd629bc35372ba72cd53a4fb199fd30ef65eeed159e130a2df9",
    "sample_faq.csv": "c4cfde0f56d5daf9d8271dc85041fa4f01e5e1625c36cca55ff5ba8ea1b71cca",
    "role_scenarios.csv": "5d1f709ccd1e8b68d71444cd1bb97d9bf0e7793d5018a6e8a63de0b33c2be454",
    "suggested_learning_plan.csv": "ea73166be0a08487c82c2fcb3ee1c2cba5a63bfdf138314bf336e9e27cbfbd40",
    "sample_quiz.csv": "2a775c807d9dde2f0acc644236bbcfb57435cc36d130c7cef13499f41b9bfd2d",
    "JURY_TEST_CASES.csv": "420866950ebf8b201b7af1403c705afd30dcb82196fe53e8677525d2fc284fc0",
}

# A pinned OpenRouter model id: "vendor/name" (lowercase, optional ":variant"). OpenRouter auto-routing
# ("openrouter/auto" and every other "openrouter/..." id) is never allowed (plan §A4).
#: Admin password used when ADMIN_PASSWORD is not set (a demo default, written in the README).
DEMO_ADMIN_PASSWORD = "dada2026"

MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*(?::[a-z0-9._-]+)?$")


def check_model_id(value: str) -> str:
    """The model id unchanged, or ValueError with the fix (bad shape or auto-routing)."""
    v = value.strip()
    if not MODEL_ID_RE.match(v) or v.startswith("openrouter/"):
        raise ValueError(
            f"{value!r} is not a pinned vendor/model id (use e.g. deepseek/deepseek-v4.1-flash; never openrouter/...)"
        )
    return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openrouter_api_key: SecretStr | None = None
    llm_model: str = "deepseek/deepseek-v4.1-flash"
    llm_escalation_model: str | None = "z-ai/glm-5.3"
    llm_panel: bool = True
    llm_panel_accept: float = Field(default=0.7, ge=0, le=1)
    #: P14.2 Rumour Check model layer. On since the dev run showed 0 false `supported` and 0 false reds
    #: (`scripts/eval_factcheck.py`, results/factcheck_dev.csv); off = the offline rules in both modes.
    llm_check: bool = True
    llm_deadline_s: float = Field(default=5.0, gt=0, le=60)
    llm_agent_deadline_s: float = Field(default=1.5, gt=0, le=60)
    llm_max_retries: int = Field(default=0, ge=0, le=3)
    llm_budget_usd: float = Field(default=3.0, ge=0)
    llm_cache_path: Path = Path(".cache/llm.sqlite")
    llm_budget_path: Path = Path(".cache/budget.json")
    encoder_dir: Path = Path("models/e5")
    data_official: Path = Path("data/official")
    data_ours: Path = Path("data/ours")
    data_live: Path = Path("data/live")
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    offline: bool = False
    # Admin sign-in for the knowledge editor and the manager view. Unset = the documented demo
    # password (README); set ADMIN_PASSWORD in .env for anything beyond a demo.
    admin_password: SecretStr = SecretStr(DEMO_ADMIN_PASSWORD)
    admin_session_hours: float = Field(default=8.0, gt=0, le=72)

    store: Literal["auto", "local"] = "auto"
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_secret_key: SecretStr | None = None
    database_url: SecretStr | None = None

    # P18.2 email notifications (Gmail SMTP with an app password, STARTTLS). Unset user or password = no
    # email is sent (each event is recorded as `skipped`). MAIL_FROM defaults to SMTP_USER; ADMIN_EMAIL
    # receives the intern-side events and the admin's test email.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    mail_from: str | None = None
    admin_email: str | None = None
    # P21.1: a request's deadline reminder goes to the intern this many minutes before the deadline.
    reminder_minutes: int = Field(default=10, ge=1, le=120)

    @field_validator("llm_model")
    @classmethod
    def _model(cls, v: str) -> str:
        return check_model_id(v)

    @field_validator("admin_password", mode="before")
    @classmethod
    def _admin_password(cls, v: object) -> object:
        raw = v.get_secret_value() if isinstance(v, SecretStr) else v
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return SecretStr(DEMO_ADMIN_PASSWORD)  # empty in .env = the demo default
        if isinstance(raw, str) and not 4 <= len(raw.strip()) <= 64:
            raise ValueError("use 4 to 64 characters")
        return v

    @field_validator("smtp_host")
    @classmethod
    def _smtp_host(cls, v: str) -> str:
        host = (v or "").strip()
        if not host:
            return "smtp.gmail.com"  # empty in .env = the Gmail default
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
            raise ValueError("use a host name such as smtp.gmail.com")
        return host

    @field_validator("smtp_user", "mail_from", "admin_email", mode="before")
    @classmethod
    def _email_setting(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None  # empty in .env = not set
        if isinstance(v, str) and (len(v.strip()) > EMAIL_MAX or not EMAIL_RE.fullmatch(v.strip())):
            raise ValueError("use an email address such as name@gmail.com")
        return v.strip() if isinstance(v, str) else v

    @field_validator("smtp_password", mode="before")
    @classmethod
    def _smtp_password(cls, v: object) -> object:
        raw = v.get_secret_value() if isinstance(v, SecretStr) else v
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None  # empty in .env = not set
        return v

    @field_validator("log_level")
    @classmethod
    def _log_level(cls, v: str) -> str:
        level = v.strip().upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise ValueError("use one of DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return level

    @field_validator("llm_escalation_model")
    @classmethod
    def _escalation(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None  # empty = no escalation model (the panel then sends the verified flash draft)
        return check_model_id(v)

    @model_validator(mode="after")
    def _finish(self) -> Settings:
        for name in (
            "llm_cache_path",
            "llm_budget_path",
            "encoder_dir",
            "data_official",
            "data_ours",
            "data_live",
        ):
            p: Path = getattr(self, name)
            if not p.is_absolute():
                setattr(self, name, ROOT / p)
        key = self.openrouter_api_key
        if self.offline or (key is not None and not key.get_secret_value().strip()):
            self.openrouter_api_key = None
        return self


def settings_error(exc: ValidationError) -> StartupError:
    """One line naming the bad variable and the fix (never the value of a secret)."""
    errs = exc.errors()
    loc = ".".join(str(x) for x in errs[0]["loc"]) if errs else "settings"
    msg = str(errs[0]["msg"] if errs else "invalid value").removeprefix("Value error, ")
    return StartupError(f"Invalid setting {loc.upper()}: {msg}. Fix it in .env (see .env.example).")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process settings; a bad env value raises StartupError with a one-line fix."""
    try:
        return Settings()
    except ValidationError as exc:
        raise settings_error(exc) from None


def validate_startup(s: Settings) -> list[str]:
    """Check encoder files and official data; raise StartupError with the fix. Returns notes."""
    meta_path = s.encoder_dir / "encoder_meta.json"
    if not meta_path.exists():
        raise StartupError(
            f"Encoder files missing in {s.encoder_dir}: copy models/e5 from the release zip or repository."
        )
    try:
        meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        names = list(meta["sha256"])
    except (ValueError, KeyError, OSError):
        raise StartupError(
            f"{meta_path} is unreadable: restore models/e5 from the release zip or repository."
        ) from None
    for name in names:
        if not (s.encoder_dir / name).exists():
            raise StartupError(
                f"Encoder file {name} missing in {s.encoder_dir}: copy models/e5 from the release zip."
            )
    for name, sha in OFFICIAL_SHA256.items():
        path = s.data_official / name
        try:
            raw = path.read_bytes()
        except OSError:
            raise StartupError(
                f"Official CSV {name} is missing or unreadable: restore data/official from the release zip."
            ) from None
        if hashlib.sha256(raw).hexdigest() != sha:
            raise StartupError(
                f"Official CSV {name} sha256 mismatch: restore data/official from the release zip."
            )
    try:
        with (s.data_official / "knowledge_base.csv").open(encoding="utf-8-sig", newline="") as f:
            list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError, csv.Error):
        raise StartupError(
            "knowledge_base.csv cannot be parsed as UTF-8 CSV: restore data/official from the release zip."
        ) from None
    return []

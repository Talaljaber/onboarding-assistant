"""Environment-validated settings, loaded once."""

from __future__ import annotations

import csv
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.errors import StartupError

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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openrouter_api_key: SecretStr | None = None
    llm_model: str = "deepseek/deepseek-v4.1-flash"
    llm_escalation_model: str | None = None
    llm_deadline_s: float = 5.0
    llm_agent_deadline_s: float = 1.5
    llm_max_retries: int = 0
    llm_budget_usd: float = 3.0
    llm_cache_path: Path = Path(".cache/llm.sqlite")
    llm_budget_path: Path = Path(".cache/budget.json")
    encoder_dir: Path = Path("models/e5")
    data_official: Path = Path("data/official")
    data_ours: Path = Path("data/ours")
    data_live: Path = Path("data/live")
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8000
    offline: bool = False

    store: Literal["auto", "local"] = "auto"
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_secret_key: SecretStr | None = None
    database_url: SecretStr | None = None

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


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

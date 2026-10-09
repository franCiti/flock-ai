"""Typed settings loaded from environment variables (plan section 1.8)."""

import re
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_DURATION_PATTERN = re.compile(r"^\s*(\d+)\s*([smhd])\s*$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# Local development reads the repository's .env; in containers the file does not exist
# and the variables come from the environment.
_REPO_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


def parse_duration(value: object) -> object:
    """Accept compact durations such as "10s", "2m", "30m" or "1d"."""
    if not isinstance(value, str):
        return value
    match = _DURATION_PATTERN.match(value)
    if match is None:
        msg = f"invalid duration {value!r}: expected <number><s|m|h|d>, e.g. '2m'"
        raise ValueError(msg)
    amount, unit = match.groups()
    return timedelta(seconds=int(amount) * _UNIT_SECONDS[unit])


Duration = Annotated[timedelta, BeforeValidator(parse_duration), Field(gt=timedelta(0))]
PositiveInt = Annotated[int, Field(gt=0)]


class Settings(BaseSettings):
    """All configurable parameters of the agent service."""

    model_config = SettingsConfigDict(
        env_file=_REPO_ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Client certificate of this process (D17). Each container mounts only its own.
    tls_cert_file: Path | None = None
    tls_key_file: Path | None = None
    tls_ca_file: Path | None = None

    # PostgreSQL (plan section 7.3). The role must match the certificate CN mapping.
    postgres_host: str = "localhost"
    postgres_port: PositiveInt = 5433
    postgres_db: str = "flock_ai"
    postgres_user: str | None = None

    # Kafka (plan section 7.2)
    kafka_bootstrap_servers: str = "localhost:9093"

    # LLM (D08)
    openrouter_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_fast_model: str | None = None
    eval_judge_model: str | None = None

    # Agent behaviour (spec HU5, HU6, HU15)
    conversation_ttl: Duration = timedelta(days=1)
    answer_timeout: Duration = timedelta(minutes=2)
    first_token_target: Duration = timedelta(seconds=10)
    max_question_chars: PositiveInt = 2000
    max_requests_per_minute: PositiveInt = 30

    # Retrieval (plan section 4.8)
    retrieval_candidates: PositiveInt = 20
    retrieval_top_k: PositiveInt = 8
    referral_min_score: Annotated[float, Field(ge=0)] | None = None
    history_turns: PositiveInt = 6

    # Ingestion (spec HU4)
    knowledge_root: Path = Path("data/knowledge")
    max_file_mb: PositiveInt = 20

    # Embeddings (plan 5.5, D22). Changing the model re-indexes the whole knowledge base.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache_dir: Path = Path("data/models")
    embedding_batch_size: PositiveInt = 32

    @property
    def effective_fast_model(self) -> str | None:
        """The fast model defaults to the main model (plan section 4.7)."""
        return self.llm_fast_model or self.llm_model

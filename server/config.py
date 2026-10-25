"""Server configuration, loaded from the environment.

Two modes, selected automatically:

- demo: no Supabase configuration present. The API still runs as a real
  networked multi-user service, but credentials are issued by this server and
  stored locally. Every UI surface that uses it must label it as demo mode.
- supabase: CLEARCOMMIT_SUPABASE_URL is set. Tokens issued by Supabase Auth
  are verified server-side and the Supabase PostgreSQL is used for storage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when the environment cannot support the selected mode."""


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


@dataclass(frozen=True)
class Settings:
    mode: str
    database_url: str
    supabase_url: str | None
    supabase_anon_key: str | None
    supabase_jwt_secret: str | None
    supabase_jwks_url: str | None
    server_data_dir: Path
    token_ttl_minutes: int
    request_timeout_seconds: float
    rate_limit_per_minute: int

    @property
    def is_supabase(self) -> bool:
        return self.mode == "supabase"


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if env is None else env)

    supabase_url = _clean(env.get("CLEARCOMMIT_SUPABASE_URL"))
    supabase_anon_key = _clean(env.get("CLEARCOMMIT_SUPABASE_ANON_KEY"))
    jwt_secret = _clean(env.get("CLEARCOMMIT_SUPABASE_JWT_SECRET"))
    jwks_url = _clean(env.get("CLEARCOMMIT_SUPABASE_JWKS_URL"))
    database_url = _clean(env.get("CLEARCOMMIT_DATABASE_URL"))
    data_dir = Path(
        _clean(env.get("CLEARCOMMIT_SERVER_DATA_DIR"))
        or (Path(__file__).resolve().parent.parent / "server_data")
    )

    mode = "supabase" if supabase_url else "demo"

    if mode == "supabase":
        if not jwt_secret and not jwks_url:
            raise ConfigError(
                "Supabase mode requires CLEARCOMMIT_SUPABASE_JWT_SECRET or "
                "CLEARCOMMIT_SUPABASE_JWKS_URL so session tokens are verified server-side."
            )
        if not database_url:
            raise ConfigError(
                "Supabase mode requires CLEARCOMMIT_DATABASE_URL "
                "(the Supabase PostgreSQL connection string)."
            )

    if not database_url:
        data_dir.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{(data_dir / 'clearcommit-server.db').as_posix()}"

    try:
        token_ttl = int(_clean(env.get("CLEARCOMMIT_TOKEN_TTL_MINUTES")) or 720)
        request_timeout = float(_clean(env.get("CLEARCOMMIT_REQUEST_TIMEOUT_SECONDS")) or 15.0)
        rate_limit = int(_clean(env.get("CLEARCOMMIT_RATE_LIMIT_PER_MINUTE")) or 120)
    except ValueError as exc:
        raise ConfigError(f"Invalid numeric environment value: {exc}") from exc

    return Settings(
        mode=mode,
        database_url=database_url,
        supabase_url=supabase_url,
        supabase_anon_key=supabase_anon_key,
        supabase_jwt_secret=jwt_secret,
        supabase_jwks_url=jwks_url,
        server_data_dir=data_dir,
        token_ttl_minutes=token_ttl,
        request_timeout_seconds=request_timeout,
        rate_limit_per_minute=rate_limit,
    )

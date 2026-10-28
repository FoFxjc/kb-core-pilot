"""Settings from KB_CORE_* environment variables, or a gitignored .env (design §9).

This module is the only place that reads the process environment for kb-core settings: every runtime setting is a
field of `Settings`, filled by `load_settings`. Only names starting with KB_CORE_ are read; variables set in the
environment win over the .env file. Every name is spelled out in full below (a test checks .env.example lists them).

Model endpoints are configured by purpose: a default endpoint (KB_CORE_LLM_*) and per-purpose overrides for live
chat (KB_CORE_CHAT_*), the decision-plane judge (KB_CORE_JUDGE_*) and graph extraction (KB_CORE_EXTRACT_*), each
falling back to the default.
"""

import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PREFIX = "KB_CORE_"
ENVS = ("development", "production")
AUTH_MODES = ("none", "trusted_header")
LOOPBACK = ("127.0.0.1", "::1", "localhost")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Endpoint:
    """A model endpoint for one purpose (a chat-completions-compatible HTTP API)."""
    purpose: str
    enabled: bool = False
    base_url: str | None = None
    model: str | None = None
    api_key_var: str = "KB_CORE_LLM_API_KEY"
    api_key: str | None = field(default=None, repr=False)
    ca_certs: str | None = None
    timeout_s: int = 60

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    def httpx_options(self) -> dict:
        """Options for every httpx client of this purpose: an SSL context trusting its CA bundle (without one, httpx's
        default verification: its bundled CA set, or SSL_CERT_FILE / SSL_CERT_DIR) and the timeout. httpx honours
        HTTPS_PROXY / HTTP_PROXY / NO_PROXY from the process environment (trust_env)."""
        import ssl

        verify = ssl.create_default_context(cafile=self.ca_certs) if self.ca_certs else True
        return {"verify": verify, "timeout": self.timeout_s, "trust_env": True}

    def redacted(self) -> dict:
        out = asdict(self)
        out["api_key"] = "***" if self.api_key else None
        return out


@dataclass(frozen=True)
class Settings:
    pg_dsn: str
    es_url: str
    env: str = "development"
    es_user: str | None = None
    es_password: str | None = field(default=None, repr=False)
    es_api_key: str | None = field(default=None, repr=False)
    es_ca_certs: str | None = None
    index_prefix: str = "kbcore_"
    delivery_dir: Path | None = None
    store_dir: Path = Path("store")
    domain: str = "banking"
    # retrieval switches (evaluation sweeps; the defaults are the production behaviour)
    coverage_threshold: float | None = None   # None: config/ranking.yaml
    aliases: bool = True
    # access control (round 2 W3) and identity
    access_labels: Path | None = None         # default config/access_labels.yaml
    access_roles: Path | None = None          # default config/access_roles.yaml
    access_role_map: Path | None = None       # default config/access_role_map.yaml
    auth_mode: str = "none"
    auth_user_header: str | None = None
    auth_groups_header: str | None = None
    # test clock (development only)
    clock_override: bool = False
    now: datetime | None = None
    # model endpoints by purpose
    llm: Endpoint = field(default_factory=lambda: Endpoint("default"))
    chat: Endpoint = field(default_factory=lambda: Endpoint("chat", timeout_s=120))
    judge: Endpoint = field(default_factory=lambda: Endpoint("judge", timeout_s=30))
    extract: Endpoint = field(default_factory=lambda: Endpoint("extract", timeout_s=120))
    judge_max_calls_per_query: int = 2
    chat_max_tool_calls: int = 8
    chat_max_tokens: int = 4096
    chat_budget_calls: int | None = None
    host: str = "127.0.0.1"
    port: int = 8200

    @property
    def production(self) -> bool:
        return self.env == "production"

    @property
    def chat_enabled(self) -> bool:
        return self.chat.enabled

    @property
    def llm_enabled(self) -> bool:
        """Whether any model purpose is switched on (reported by GET /v1/admin/config)."""
        return self.chat.enabled or self.judge.enabled or self.extract.enabled

    def purposes(self) -> list[Endpoint]:
        return [self.chat, self.judge, self.extract]

    def redacted(self) -> dict:
        out = {k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(self).items()}
        for k in ("es_password", "es_api_key"):
            if out[k]:
                out[k] = "***"
        for k in ("llm", "chat", "judge", "extract"):
            out[k] = getattr(self, k).redacted()
        out["now"] = self.now.isoformat() if self.now else None
        out["pg_dsn"] = _redact_dsn(self.pg_dsn)
        out["es_url"] = _redact_url(self.es_url)
        return out


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.password is None:
        return url
    netloc = f"{parts.username}:***@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=netloc))


def _redact_dsn(dsn: str) -> str:
    """Mask the password of any DSN form psycopg accepts (URL, URL query, key=value)."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    try:
        parts = conninfo_to_dict(dsn)
    except Exception:
        return "***"  # unparseable: show nothing rather than risk the password
    if "password" in parts:
        parts["password"] = "***"
    return make_conninfo(**parts)


def read_dotenv(path: Path) -> dict[str, str]:
    """KB_CORE_* lines of a .env file: KEY=value, optional `export `, quotes, `#` comments."""
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        name, sep, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not name.startswith(PREFIX):
            continue
        if value[:1] in ("'", '"'):
            q = value[0]
            value = value[1:].split(q, 1)[0]
        else:
            value = value.split(" #", 1)[0].strip()
        out[name] = value
    return out


def _bool(name: str, value: str) -> bool:
    v = value.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off", ""):
        return False
    raise ConfigError(f"{name} must be true or false, got {value!r}")


def _int(name: str, value: str, lo: int) -> int:
    try:
        n = int(value)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from None
    if n < lo:
        raise ConfigError(f"{name} must be at least {lo}, got {n}")
    return n


def _float(name: str, value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {value!r}") from None


def _choice(name: str, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)}, got {value!r}")
    return value


def _time(name: str, value: str) -> datetime:
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConfigError(f"{name} must be an ISO-8601 time with an offset, got {value!r}") from None
    if t.tzinfo is None:
        raise ConfigError(f"{name} must carry a UTC offset, got {value!r}")
    return t.astimezone(UTC)


def _key_var(name: str, value: str) -> str:
    if not value.startswith(PREFIX):
        raise ConfigError(f"{name} must name a {PREFIX}* variable, got {value!r}")
    return value


def load_settings(env: Mapping[str, str] | None = None, env_file: Path | None = Path(".env")) -> Settings:
    env = os.environ if env is None else env
    values = read_dotenv(env_file) if env_file is not None and env_file.exists() else {}
    # an empty variable in the environment counts as unset: it never hides the .env value
    values.update({k: v for k, v in env.items() if k.startswith(PREFIX) and v != ""})

    def get(name: str) -> str | None:
        v = values.get(name)
        return v if v not in (None, "") else None

    for required in ("KB_CORE_PG_DSN", "KB_CORE_ES_URL"):
        if get(required) is None:
            raise ConfigError(f"{required} is not set (environment or .env)")
    kw: dict = {"pg_dsn": get("KB_CORE_PG_DSN"), "es_url": get("KB_CORE_ES_URL").rstrip("/")}

    strings = {"KB_CORE_ES_USER": "es_user", "KB_CORE_ES_PASSWORD": "es_password", "KB_CORE_ES_API_KEY": "es_api_key",
               "KB_CORE_ES_CA_CERTS": "es_ca_certs", "KB_CORE_INDEX_PREFIX": "index_prefix",
               "KB_CORE_DOMAIN": "domain", "KB_CORE_HOST": "host",
               "KB_CORE_AUTH_USER_HEADER": "auth_user_header", "KB_CORE_AUTH_GROUPS_HEADER": "auth_groups_header"}
    for name, attr in strings.items():
        if get(name) is not None:
            kw[attr] = get(name)
    paths = {"KB_CORE_DELIVERY_DIR": "delivery_dir", "KB_CORE_STORE_DIR": "store_dir",
             "KB_CORE_ACCESS_LABELS": "access_labels", "KB_CORE_ACCESS_ROLES": "access_roles",
             "KB_CORE_ACCESS_ROLE_MAP": "access_role_map"}
    for name, attr in paths.items():
        if get(name) is not None:
            kw[attr] = Path(get(name))
    ints = {"KB_CORE_PORT": ("port", 1), "KB_CORE_CHAT_MAX_TOOL_CALLS": ("chat_max_tool_calls", 1),
            "KB_CORE_CHAT_MAX_TOKENS": ("chat_max_tokens", 256), "KB_CORE_CHAT_BUDGET_CALLS": ("chat_budget_calls", 0),
            "KB_CORE_JUDGE_MAX_CALLS_PER_QUERY": ("judge_max_calls_per_query", 0)}
    for name, (attr, lo) in ints.items():
        if get(name) is not None:
            kw[attr] = _int(name, get(name), lo)

    if get("KB_CORE_ENV") is not None:
        kw["env"] = _choice("KB_CORE_ENV", get("KB_CORE_ENV"), ENVS)
    if get("KB_CORE_AUTH_MODE") is not None:
        kw["auth_mode"] = _choice("KB_CORE_AUTH_MODE", get("KB_CORE_AUTH_MODE"), AUTH_MODES)
    if get("KB_CORE_COVERAGE_THRESHOLD") is not None:
        kw["coverage_threshold"] = _float("KB_CORE_COVERAGE_THRESHOLD", get("KB_CORE_COVERAGE_THRESHOLD"))
    if get("KB_CORE_ALIASES") is not None:
        kw["aliases"] = _choice("KB_CORE_ALIASES", get("KB_CORE_ALIASES"), ("on", "off")) == "on"
    if get("KB_CORE_ALLOW_CLOCK_OVERRIDE") is not None:
        kw["clock_override"] = _choice("KB_CORE_ALLOW_CLOCK_OVERRIDE",
                                       get("KB_CORE_ALLOW_CLOCK_OVERRIDE").lower(), ("true", "false")) == "true"
    if get("KB_CORE_NOW") is not None:
        kw["now"] = _time("KB_CORE_NOW", get("KB_CORE_NOW"))

    kw.update(_endpoints(get, values))

    prefix = kw.get("index_prefix", Settings.index_prefix)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", prefix):
        raise ConfigError(f"KB_CORE_INDEX_PREFIX must be lowercase letters, digits, '_', '-' or '.', got {prefix!r}")
    s = Settings(**kw)
    _check(s)
    return s


_PURPOSES = {
    "chat": ("KB_CORE_CHAT_ENABLED", "KB_CORE_CHAT_BASE_URL", "KB_CORE_CHAT_MODEL", "KB_CORE_CHAT_API_KEY_VAR",
             "KB_CORE_CHAT_CA_CERTS", "KB_CORE_CHAT_TIMEOUT_S", 120),
    "judge": ("KB_CORE_JUDGE_ENABLED", "KB_CORE_JUDGE_BASE_URL", "KB_CORE_JUDGE_MODEL", "KB_CORE_JUDGE_API_KEY_VAR",
              "KB_CORE_JUDGE_CA_CERTS", "KB_CORE_JUDGE_TIMEOUT_S", 30),
    "extract": ("KB_CORE_EXTRACT_ENABLED", "KB_CORE_EXTRACT_BASE_URL", "KB_CORE_EXTRACT_MODEL",
                "KB_CORE_EXTRACT_API_KEY_VAR", "KB_CORE_EXTRACT_CA_CERTS", "KB_CORE_EXTRACT_TIMEOUT_S", 120),
}


def _endpoints(get, values: Mapping[str, str]) -> dict:
    """The default endpoint and the three purposes; each purpose setting falls back to the default's.
    A purpose's timeout falls back to KB_CORE_LLM_TIMEOUT_S, then to the purpose's own default."""
    default_var = _key_var("KB_CORE_LLM_API_KEY_VAR", get("KB_CORE_LLM_API_KEY_VAR") or "KB_CORE_LLM_API_KEY")
    default_timeout = (_int("KB_CORE_LLM_TIMEOUT_S", get("KB_CORE_LLM_TIMEOUT_S"), 1)
                       if get("KB_CORE_LLM_TIMEOUT_S") is not None else None)
    llm = Endpoint("default", base_url=get("KB_CORE_LLM_BASE_URL"), model=get("KB_CORE_LLM_MODEL"),
                   api_key_var=default_var, api_key=values.get(default_var) or None,
                   ca_certs=get("KB_CORE_LLM_CA_CERTS"), timeout_s=default_timeout or 60)
    out: dict = {"llm": llm}
    for purpose, (en, url, model, var, ca, timeout, purpose_timeout) in _PURPOSES.items():
        key_var = _key_var(var, get(var)) if get(var) is not None else llm.api_key_var
        out[purpose] = Endpoint(
            purpose,
            enabled=_bool(en, get(en)) if get(en) is not None else False,
            base_url=(get(url) or llm.base_url or "").rstrip("/") or None, model=get(model) or llm.model,
            api_key_var=key_var, api_key=values.get(key_var) or None,
            ca_certs=get(ca) or llm.ca_certs,
            timeout_s=(_int(timeout, get(timeout), 1) if get(timeout) is not None
                       else default_timeout or purpose_timeout))
        if out[purpose].enabled and not out[purpose].configured:
            raise ConfigError(f"{en} is true but no base URL or model is set "
                              f"({url} / {model}, or KB_CORE_LLM_BASE_URL / KB_CORE_LLM_MODEL)")
    return out


def _check(s: Settings) -> None:
    """Rules that tie settings together. Production refuses the development conveniences outright."""
    if s.auth_mode == "trusted_header" and not s.auth_user_header:
        raise ConfigError("KB_CORE_AUTH_MODE=trusted_header needs KB_CORE_AUTH_USER_HEADER")
    if s.production:
        problems = []
        if s.auth_mode == "none":
            problems.append("KB_CORE_AUTH_MODE=none (identity must come from the SSO gateway: trusted_header)")
        if s.clock_override or s.now is not None:
            problems.append("the test clock (KB_CORE_NOW / KB_CORE_ALLOW_CLOCK_OVERRIDE) is configured")
        for e in [s.llm, *s.purposes()]:
            if not e.api_key_var.startswith(PREFIX):
                problems.append(f"the {e.purpose} key variable {e.api_key_var!r} is not a {PREFIX}* name")
        if problems:
            raise ConfigError("KB_CORE_ENV=production refuses: " + "; ".join(problems))
    elif s.auth_mode == "none" and s.host not in LOOPBACK:
        raise ConfigError(f"KB_CORE_AUTH_MODE=none serves without identity and may bind only to a loopback address, "
                          f"not KB_CORE_HOST={s.host!r} (behind the SSO gateway use KB_CORE_ENV=production and "
                          f"KB_CORE_AUTH_MODE=trusted_header)")


# --- the settings of the running process ---------------------------------------------------------------------------

_current: Settings | None = None


def use(settings: Settings | None) -> None:
    """Make `settings` the running process's settings (retrieval context init, CLI commands, tests)."""
    global _current
    _current = settings


def current() -> Settings | None:
    """The running process's settings, or None outside a configured process (code then uses the defaults)."""
    return _current

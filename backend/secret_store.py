"""
Persisted server secrets.

Why this exists: auth.py used to fall back to a hard-coded, publicly known JWT
secret when JWT_SECRET_KEY was unset, which let anyone mint valid tokens. The
admin JWT secret fell back to a random value per process, which logged
everyone out on every restart. Both now fall back to a random secret that is
generated once and kept in DATA_DIR/.secrets/ (mode 0600).
"""
import logging
import os
import secrets
from pathlib import Path

from config import DATA_DIR

logger = logging.getLogger(__name__)

# Values that ship in .env.example / old defaults. Treat them as "unset":
# they are public, so a token signed with them proves nothing.
_PLACEHOLDER_PREFIXES = ("change_me", "change_this")


def _secrets_dir() -> Path:
    return DATA_DIR / ".secrets"


def get_or_create_secret(name: str, env_var: str) -> str:
    """Return the secret from `env_var`, or a persisted random one.

    The env var wins when it is set to a real value. Otherwise a 64-hex-char
    secret is read from DATA_DIR/.secrets/<name>, creating it on first use.
    """
    value = os.getenv(env_var, "").strip()
    if value and not value.lower().startswith(_PLACEHOLDER_PREFIXES):
        return value

    path = _secrets_dir() / name
    if path.exists():
        stored = path.read_text().strip()
        if stored:
            return stored

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass

    new_secret = secrets.token_hex(32)
    try:
        # O_EXCL: if two workers race, only one writes; the loser reads it back.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(new_secret)
    except FileExistsError:
        return path.read_text().strip()

    if value:
        logger.warning(
            f"{env_var} is set to a placeholder value; ignoring it and using a "
            f"generated secret stored at {path}"
        )
    else:
        logger.warning(
            f"{env_var} is not set; generated a random secret and stored it at {path}. "
            f"Set {env_var} explicitly if several machines must share tokens."
        )
    return new_secret

"""Persistent app settings and eligibility check.

Storage location:
    * Windows: ``C:\\ProgramData\\CACBarScanner\\`` — the canonical
      Windows location for machine-wide application data. Shared by
      every user on the kiosk PC. The folder is provisioned during
      the one-time admin install (see ``start_menu.install_for_machine``),
      which grants Authenticated Users Modify access via icacls so
      any operator can read and write.
    * Linux/macOS: ``~/.cac_scanner/`` — kiosk deployment is Windows-
      only and there is no good cross-user shared location without root.

The schema is forward-compatible: unknown keys are ignored; missing
keys fall back to defaults so older save files load cleanly when new
fields are added.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import os
import secrets
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Tuple

from cac_decoder import BRANCHES, CATEGORIES


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        programdata = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(programdata) / "CACBarScanner"
    return Path.home() / ".cac_scanner"


SETTINGS_DIR = _default_data_dir()
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

DEFAULT_OPEN = "00:00"
DEFAULT_CLOSE = "00:00"  # open == close => 24-hour rolling window
DEFAULT_MAX_DRINKS = 3

# Admin password — gates every settings tab, the manual reset, and the
# backup import. Stored as a PBKDF2-SHA256 hash with a per-record salt
# in settings.json; an empty hash means "no password set, accept the
# default" so a fresh install is usable without an extra setup dance.
DEFAULT_ADMIN_PASSWORD = "admin"
PBKDF2_ITERATIONS = 200_000
MIN_PASSWORD_LEN = 4


def hash_password(plain: str) -> str:
    """Hash ``plain`` with PBKDF2-HMAC-SHA256 + 16-byte random salt and
    return a self-describing string of the form
    ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``. The iteration
    count and salt travel with the hash so verification doesn't depend
    on the constants used at hash time."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return (
        f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
        f"{base64.urlsafe_b64encode(salt).decode('ascii')}$"
        f"{base64.urlsafe_b64encode(digest).decode('ascii')}"
    )


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verify ``plain`` against a previously-stored hash.
    Returns False for malformed hashes rather than raising."""
    try:
        algo, iters_str, salt_b64, digest_b64 = hashed.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters_str)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        digest = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, iters
    )
    return hmac.compare_digest(candidate, digest)

TRACKING_HOURS = "hours"      # operating-hours session window
TRACKING_ROLLING = "rolling"  # last-N-hours sliding window
TRACKING_MODES = (TRACKING_HOURS, TRACKING_ROLLING)
DEFAULT_TRACKING_MODE = TRACKING_HOURS
DEFAULT_ROLLING_HOURS = 24
MIN_ROLLING_HOURS = 1
MAX_ROLLING_HOURS = 168


def parse_hhmm(s: str) -> time:
    """Lenient HH:MM parser — accepts 'H:MM' or 'HH:MM' with surrounding spaces."""
    s = (s or "").strip()
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError(f"expected HH:MM, got {s!r}")
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"non-numeric time component in {s!r}") from None
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"out-of-range time in {s!r}")
    return time(hour=h, minute=m)


def fmt_time(t: time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def ordinal(n: int) -> str:
    if n < 0:
        return str(n)
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _default_categories() -> Tuple[str, ...]:
    return tuple(CATEGORIES.keys())


def _default_branches() -> Tuple[str, ...]:
    return tuple(BRANCHES.keys())


@dataclass(frozen=True)
class Ban:
    """A single ban entry. ``expires`` is an ISO date 'YYYY-MM-DD' string or
    None for a permanent ban (the default)."""
    edipi: str
    expires: str | None = None

    @property
    def expires_date(self) -> date | None:
        return date.fromisoformat(self.expires) if self.expires else None

    def is_active(self, today: date | None = None) -> bool:
        if self.expires is None:
            return True
        today = today or date.today()
        return today <= self.expires_date

    def describe(self, today: date | None = None) -> str:
        if self.expires is None:
            return f"{self.edipi}  •  permanent"
        today = today or date.today()
        suffix = " (EXPIRED)" if today > self.expires_date else ""
        return f"{self.edipi}  •  until {self.expires}{suffix}"


@dataclass(frozen=True)
class Settings:
    open_time: str = DEFAULT_OPEN
    close_time: str = DEFAULT_CLOSE
    max_drinks: int = DEFAULT_MAX_DRINKS
    allowed_categories: Tuple[str, ...] = field(default_factory=_default_categories)
    allowed_branches: Tuple[str, ...] = field(default_factory=_default_branches)
    bans: Tuple[Ban, ...] = ()
    tracking_mode: str = DEFAULT_TRACKING_MODE
    rolling_hours: int = DEFAULT_ROLLING_HOURS
    admin_password_hash: str = ""  # empty => accept DEFAULT_ADMIN_PASSWORD

    def __post_init__(self) -> None:
        # Group bans by EDIPI so ``active_ban_for`` is O(1) at scan time.
        # ``dataclasses.asdict`` ignores non-field attributes, so this
        # cache doesn't leak into settings.json.
        grouped: dict[str, list[Ban]] = {}
        for b in self.bans:
            grouped.setdefault(b.edipi, []).append(b)
        object.__setattr__(self, "_bans_by_edipi", grouped)

    def active_ban_for(
        self, edipi: str, today: date | None = None
    ) -> Ban | None:
        """Return the currently-active Ban for ``edipi`` or None. Expired
        entries are skipped even if they are the only ones recorded."""
        today = today or date.today()
        bans_for_edipi: list[Ban] = self._bans_by_edipi.get(edipi, [])
        return next((b for b in bans_for_edipi if b.is_active(today)), None)

    # ----------------------------------------------------- admin password

    def verify_admin_password(self, plain: str) -> bool:
        """True iff ``plain`` matches the stored admin password. With no
        password set (fresh install), the constant default is accepted
        so the app is usable out of the box."""
        if not self.admin_password_hash:
            return plain == DEFAULT_ADMIN_PASSWORD
        return verify_password(plain, self.admin_password_hash)

    def with_admin_password(self, new_plain: str) -> "Settings":
        return dataclasses.replace(
            self, admin_password_hash=hash_password(new_plain)
        )

    # ------------------------------------------------------------ hours

    @property
    def open_t(self) -> time:
        return parse_hhmm(self.open_time)

    @property
    def close_t(self) -> time:
        return parse_hhmm(self.close_time)

    @property
    def crosses_midnight(self) -> bool:
        return self.close_t <= self.open_t

    def current_session(
        self, now: datetime | None = None
    ) -> tuple[datetime, datetime] | None:
        """Return (start, end) of the open window containing now, in local
        time. None if currently outside operating hours."""
        if now is None:
            now = datetime.now().astimezone()
        ot, ct = self.open_t, self.close_t
        today = now.date()
        tz = now.tzinfo
        today_open = datetime.combine(today, ot, tzinfo=tz)
        if ct > ot:
            today_close = datetime.combine(today, ct, tzinfo=tz)
        else:
            today_close = datetime.combine(today + timedelta(days=1), ct, tzinfo=tz)

        if today_open <= now <= today_close:
            return today_open, today_close
        prev_open = today_open - timedelta(days=1)
        prev_close = today_close - timedelta(days=1)
        if prev_open <= now <= prev_close:
            return prev_open, prev_close
        return None

    def describe_hours(self) -> str:
        midnight = " (crosses midnight)" if self.crosses_midnight else ""
        if self.open_t == self.close_t:
            return f"24 h, day starts at {fmt_time(self.open_t)}"
        return f"{fmt_time(self.open_t)} – {fmt_time(self.close_t)}{midnight}"

    # ----------------------------------------------------- tracking mode

    @property
    def is_rolling(self) -> bool:
        return self.tracking_mode == TRACKING_ROLLING

    def current_window(
        self, now: datetime | None = None
    ) -> tuple[datetime, datetime] | None:
        """Return (start, end) of the counting window in local time.

        In rolling mode this is always ``(now - rolling_hours, now)``; the
        bar is never "closed" by clock. In hours mode it falls back to
        ``current_session``, which is None when outside operating hours."""
        if now is None:
            now = datetime.now().astimezone()
        if self.is_rolling:
            return (now - timedelta(hours=self.rolling_hours), now)
        return self.current_session(now)

    def describe_window(self) -> str:
        if self.is_rolling:
            return f"Rolling {self.rolling_hours}-hour window"
        return self.describe_hours()


@dataclass(frozen=True)
class EligibilityResult:
    allowed: bool
    reason: str = ""
    new_count: int = 0  # count INCLUDING this scan, if allowed


def check_eligibility(
    edipi: str,
    category_code: str,
    category_name: str,
    branch_code: str,
    branch_name: str,
    current_count: int,
    settings: Settings,
    in_session: bool,
    today: date | None = None,
) -> EligibilityResult:
    """Decide whether this scan should be allowed.

    Priority order: banned > closed > category > branch > limit.
    ``current_count`` is the count BEFORE this scan. Expired bans are
    skipped — a ban with a date in the past no longer denies."""
    today = today or date.today()
    active_ban = settings.active_ban_for(edipi, today)
    if active_ban is not None:
        if active_ban.expires:
            return EligibilityResult(
                False, f"This DoD ID is banned until {active_ban.expires}"
            )
        return EligibilityResult(False, "This DoD ID is permanently banned")
    if not in_session:
        return EligibilityResult(False, "Bar is closed (outside operating hours)")
    if category_code not in settings.allowed_categories:
        return EligibilityResult(
            False, f"{category_name} ({category_code}) not allowed"
        )
    if branch_code not in settings.allowed_branches:
        return EligibilityResult(
            False, f"{branch_name} ({branch_code}) not allowed"
        )
    if current_count >= settings.max_drinks:
        word = "drink" if current_count == 1 else "drinks"
        return EligibilityResult(
            False,
            f"You've had {current_count} {word} today (limit {settings.max_drinks})",
        )
    return EligibilityResult(True, "", current_count + 1)


# ------------------------------------------------------------ persistence

def _default_settings() -> Settings:
    return Settings()


def _parse_ban_item(item: Any) -> Ban | None:
    """Parse a single ban entry, accepting either the legacy string form
    (a bare EDIPI = permanent ban) or the new dict form ``{"edipi", "expires"}``.
    Returns None if the item is malformed."""
    if isinstance(item, str):
        return Ban(edipi=item, expires=None) if item.isdigit() else None
    if isinstance(item, dict):
        edipi = str(item.get("edipi", "")).strip()
        if not edipi.isdigit():
            return None
        expires = item.get("expires")
        if expires is not None:
            try:
                date.fromisoformat(str(expires))
            except ValueError:
                expires = None
        return Ban(edipi=edipi, expires=str(expires) if expires else None)
    return None


def from_dict(data: dict) -> Settings:
    """Parse a settings dict (the JSON form) into a Settings object.

    Forward-compatible: unknown keys are ignored, missing keys fall back
    to defaults, and the legacy ``banned_edipis`` shape is migrated to
    the new ``bans`` shape. Raises ``TypeError`` or ``ValueError`` if a
    required field is malformed in a way that can't be recovered."""
    defaults = _default_settings()
    # Bans live under "bans"; old saves used "banned_edipis" as a list of
    # bare EDIPI strings. Read either; future saves write "bans".
    raw_bans = data.get("bans")
    if raw_bans is None:
        raw_bans = data.get("banned_edipis", ())
    bans = tuple(b for b in (_parse_ban_item(it) for it in raw_bans) if b)

    tracking_mode = str(data.get("tracking_mode", defaults.tracking_mode))
    if tracking_mode not in TRACKING_MODES:
        tracking_mode = defaults.tracking_mode

    try:
        rolling_hours = int(data.get("rolling_hours", defaults.rolling_hours))
    except (TypeError, ValueError):
        rolling_hours = defaults.rolling_hours
    rolling_hours = max(MIN_ROLLING_HOURS, min(MAX_ROLLING_HOURS, rolling_hours))

    s = Settings(
        open_time=str(data.get("open_time", defaults.open_time)),
        close_time=str(data.get("close_time", defaults.close_time)),
        max_drinks=int(data.get("max_drinks", defaults.max_drinks)),
        allowed_categories=tuple(
            data.get("allowed_categories", defaults.allowed_categories)
        ),
        allowed_branches=tuple(
            data.get("allowed_branches", defaults.allowed_branches)
        ),
        bans=bans,
        tracking_mode=tracking_mode,
        rolling_hours=rolling_hours,
        admin_password_hash=str(
            data.get("admin_password_hash", defaults.admin_password_hash)
        ),
    )
    s.open_t  # noqa: B018  — validate HH:MM
    s.close_t  # noqa: B018
    return s


def load() -> Settings:
    defaults = _default_settings()
    if not SETTINGS_FILE.exists():
        return defaults
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    try:
        return from_dict(data)
    except (TypeError, ValueError):
        return defaults


def save(settings: Settings) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")

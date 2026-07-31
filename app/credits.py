"""
credits.py
----------
Anonymous, code-based credit ledger.

Flow:
  1. User picks a credit pack on the frontend.
  2. Backend creates a Stripe Checkout session; on success Stripe hits
     /stripe/webhook.
  3. The webhook mints a random 16-char code with N credits and returns it
     to the frontend via the success redirect.
  4. User pastes the code into the app; every /interpret call decrements
     credits by 1.

No email, no login, no PII. If the user loses the code, they lose the credits
— trade-off for zero-friction UX and no auth infrastructure. Codes are stored
in a small SQLite DB so state survives restarts.

Path is configurable via CREDITS_DB_PATH so Render's persistent disk (if
enabled) or a local path in dev both work. Falls back to /tmp on Render's
free tier (ephemeral; codes reset when the dyno restarts — acceptable for
soft-launch, upgrade to Postgres before scaling).
"""

import os
import secrets
import sqlite3
import string
import tempfile
import threading
from contextlib import contextmanager
from typing import Optional


def _default_db_path() -> str:
    """
    Cross-platform default for the credits SQLite DB.
    - Linux/Render free tier: /tmp/credits.sqlite3 (ephemeral — resets on dyno restart, fine for soft-launch).
    - Windows dev: %TEMP%\\credits.sqlite3.
    Override with CREDITS_DB_PATH for a persistent-disk mount (e.g. /var/data/credits.sqlite3).
    """
    return os.path.join(tempfile.gettempdir(), "credits.sqlite3")


DB_PATH = os.environ.get("CREDITS_DB_PATH", _default_db_path())
# Ensure the parent directory exists — sqlite3.connect() will not create it
# for us, and a missing dir raises OperationalError at import time.
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

_db_lock = threading.Lock()

_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LEN = 16


def _init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_codes (
                code TEXT PRIMARY KEY,
                credits_remaining INTEGER NOT NULL,
                credits_issued INTEGER NOT NULL,
                stripe_session_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )


_init_db()


@contextmanager
def _db():
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def generate_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))


def mint_code(credits: int, stripe_session_id: Optional[str] = None) -> str:
    """Create a fresh code with `credits` uses; store and return it."""
    if credits <= 0:
        raise ValueError("credits must be positive")
    for _ in range(5):
        code = generate_code()
        with _db() as conn:
            try:
                conn.execute(
                    "INSERT INTO credit_codes (code, credits_remaining, credits_issued, stripe_session_id) "
                    "VALUES (?, ?, ?, ?)",
                    (code, credits, credits, stripe_session_id),
                )
                return code
            except sqlite3.IntegrityError:
                continue
    raise RuntimeError("Could not generate a unique credit code after 5 attempts")


def check_credits(code: str) -> Optional[int]:
    """Return remaining credits for a code, or None if the code is invalid."""
    with _db() as conn:
        row = conn.execute(
            "SELECT credits_remaining FROM credit_codes WHERE code = ?",
            (code.upper().strip(),),
        ).fetchone()
    return None if row is None else int(row[0])


def redeem_one(code: str) -> int:
    """
    Atomically decrement a code by 1 and return the new remaining count.
    Raises PermissionError if the code is invalid or exhausted.
    """
    normalized = code.upper().strip()
    with _db() as conn:
        row = conn.execute(
            "SELECT credits_remaining FROM credit_codes WHERE code = ?",
            (normalized,),
        ).fetchone()
        if row is None:
            raise PermissionError("Invalid credit code.")
        remaining = int(row[0])
        if remaining <= 0:
            raise PermissionError("Credit code exhausted. Please buy more credits.")
        conn.execute(
            "UPDATE credit_codes SET credits_remaining = credits_remaining - 1 WHERE code = ?",
            (normalized,),
        )
        return remaining - 1


def session_id_already_processed(stripe_session_id: str) -> bool:
    """Idempotency check for the Stripe webhook — don't mint two codes for the same session."""
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM credit_codes WHERE stripe_session_id = ? LIMIT 1",
            (stripe_session_id,),
        ).fetchone()
    return row is not None


# --- Pricing ---------------------------------------------------------------
# Kept here (not in api.py) so the frontend + webhook share one source of truth.
# Prices are in the smallest currency unit for Stripe (paise / cents).

CURRENCY = os.environ.get("CREDITS_CURRENCY", "inr").lower()

PACKS = {
    "starter": {"credits": 5, "amount": 9900, "label": "Starter — 5 questions"},
    "regular": {"credits": 15, "amount": 24900, "label": "Regular — 15 questions"},
    "deep_dive": {"credits": 40, "amount": 59900, "label": "Deep Dive — 40 questions"},
}


def pack_by_id(pack_id: str) -> dict:
    if pack_id not in PACKS:
        raise ValueError(f"Unknown pack id: {pack_id!r}")
    return {"id": pack_id, **PACKS[pack_id], "currency": CURRENCY}


def all_packs() -> list:
    return [{"id": pid, **p, "currency": CURRENCY} for pid, p in PACKS.items()]

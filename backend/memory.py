"""
Persistent, cross-conversation memory — a small store of durable facts the
user has explicitly asked to be remembered ("remember that I'm allergic to
penicillin"), surfaced back into every future conversation regardless of
which chat it started in.

Deliberately NOT automatic background summarization of every conversation:
that would mean an extra LLM call after every single turn on hardware
that's already slow for the one call chat already needs (see this
project's own build notes on CPU/GPU inference time), and it would decide
on the user's behalf what's worth remembering rather than the user doing
so explicitly. Detection is a plain regex (extract_remember_request,
mirroring the existing *_REQUEST_RE intent-detection pattern already used
in app.js for image generation/editing) — cheap, deterministic, and the
user can always add or remove an entry directly from the sidebar too.

Encrypted at rest the same way agents.json is (see agents.py's own
docstring) — every write goes straight to ciphertext when encryption is
on. Memory entries are exactly the kind of thing "lock this drive with a
passphrase" exists to protect (allergies, personal details, anything
someone chose to have remembered), so this needed the same treatment as
conversations/documents/agents, not an oversight left in plaintext.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

MEMORY_FILE = ROOT / "memory.json"
_lock = threading.Lock()

# "remember/keep in mind/note (that) <fact>", start-of-message only — a
# mid-sentence "remember" ("that reminds me, remember when...") shouldn't
# quietly get filed away as a fact to recall forever.
REMEMBER_RE = re.compile(
    r"^(?:please\s+)?(?:remember|keep in mind|note)(?:\s+that)?\s*[:,]?\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def load_memory() -> list[dict]:
    """Raises RuntimeError("locked") if encryption is on but the session
    isn't unlocked — same contract as agents.py's _read(), so callers
    already handling that (see server.py's api_chat, which degrades to an
    empty hits list on the equivalent document-retrieval failure) can
    treat this the same way rather than needing a special case."""
    if not MEMORY_FILE.exists():
        return []
    raw = MEMORY_FILE.read_bytes()
    import security as security_mod
    if security_mod.is_enabled():
        if not security_mod.is_unlocked():
            raise RuntimeError("locked")
        raw = security_mod.decrypt_bytes(raw)
    try:
        return json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return []


def _save(entries: list[dict]) -> None:
    payload = json.dumps(entries, indent=2).encode("utf-8")
    import security as security_mod
    if security_mod.is_enabled():
        if not security_mod.is_unlocked():
            raise RuntimeError("locked")
        payload = security_mod.encrypt_bytes(payload)
    MEMORY_FILE.write_bytes(payload)


def add_entry(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("Nothing to remember.")
    with _lock:
        entries = load_memory()
        entry = {"id": uuid.uuid4().hex[:12], "text": text, "created_at": time.time()}
        entries.append(entry)
        _save(entries)
    return entry


def delete_entry(entry_id: str) -> bool:
    with _lock:
        entries = load_memory()
        remaining = [e for e in entries if e["id"] != entry_id]
        if len(remaining) == len(entries):
            return False
        _save(remaining)
        return True


def extract_remember_request(user_text: str) -> str | None:
    """Returns the fact to remember if user_text opens with a "remember
    that X" style request, else None."""
    m = REMEMBER_RE.match(user_text.strip())
    if not m:
        return None
    return m.group(1).strip().rstrip(".").strip()

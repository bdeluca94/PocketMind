"""User-defined custom agents: a name, optional custom instructions, and a
set of categories to prioritize when this agent is selected in the persona
dropdown.

Stored as a single JSON file (agents.json) rather than one file per agent
like conversations/ — the expected count is a handful, not hundreds, so
there's nothing to gain from fragmenting into multiple files, and a single
file means listing never needs to glob a directory.

Encrypted at rest the same way conversations are: every write goes straight
to ciphertext when encryption is on, so there's no separate "working copy"
to manage and no extra hook needed in security.py's lock/unlock — only in
enable()/disable(), which migrate whatever's already on disk. Imports of
`security` are lazy for the same reason as conversations.py: security.py
itself needs to import this module to encrypt/decrypt agents.json when
encryption is turned on or off, and a top-level circular import would break
module loading.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

AGENTS_PATH = ROOT / "agents.json"

MAX_NAME_LEN = 40
MAX_INSTRUCTIONS_LEN = 2000
MAX_CATEGORIES_PER_AGENT = 20


def _read() -> list[dict]:
    if not AGENTS_PATH.exists():
        return []
    raw = AGENTS_PATH.read_bytes()
    import security as security_mod
    if security_mod.is_enabled():
        if not security_mod.is_unlocked():
            raise RuntimeError("locked")
        raw = security_mod.decrypt_bytes(raw)
    try:
        data = json.loads(raw)
    except Exception:
        return []  # a corrupt file shouldn't take the whole feature down
    return data if isinstance(data, list) else []


def _write(agents: list[dict]) -> None:
    payload = json.dumps(agents, indent=2).encode("utf-8")
    import security as security_mod
    if security_mod.is_enabled():
        if not security_mod.is_unlocked():
            raise RuntimeError("locked")
        payload = security_mod.encrypt_bytes(payload)
    AGENTS_PATH.write_bytes(payload)


def _clean_name(name: str, existing: list[dict], exclude_id: str | None = None) -> str:
    # Collapse whitespace for the same reason categories do: this name
    # ends up as an <option> label and inside SSE frames, where a stray
    # newline would be either confusing or (in the SSE case) truncate the
    # message outright.
    name = " ".join((name or "").split())
    if not name:
        raise ValueError("Give the agent a name.")
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f"That name is too long — keep it under {MAX_NAME_LEN} characters.")
    if any(a["name"].lower() == name.lower() and a["id"] != exclude_id for a in existing):
        raise ValueError(f"You already have an agent called “{name}”.")
    return name


def list_agents() -> list[dict]:
    return _read()


def get_agent(agent_id: str | None) -> dict | None:
    if not agent_id:
        return None
    return next((a for a in _read() if a["id"] == agent_id), None)


def create_agent(name: str, category_ids: list[str], instructions: str = "") -> dict:
    # `isinstance(c, str) and c` alone lets a whitespace-only string like
    # "  " through, since a non-empty string is truthy regardless of what's
    # in it — .strip() first is what actually catches that.
    category_ids = [c.strip() for c in (category_ids or []) if isinstance(c, str) and c.strip()]
    if not category_ids:
        raise ValueError("Pick at least one category for the agent to prioritize.")

    agents = _read()
    clean_name = _clean_name(name, agents)
    agent = {
        "id": uuid.uuid4().hex[:12],
        "name": clean_name,
        "instructions": (instructions or "").strip()[:MAX_INSTRUCTIONS_LEN],
        # dict.fromkeys dedupes while preserving the order the person picked
        # them in, which is nicer to redisplay than an arbitrary re-sort.
        "category_ids": list(dict.fromkeys(category_ids))[:MAX_CATEGORIES_PER_AGENT],
    }
    agents.append(agent)
    _write(agents)
    return agent


def update_agent(agent_id: str, name: str | None = None,
                 category_ids: list[str] | None = None,
                 instructions: str | None = None) -> dict:
    agents = _read()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if agent is None:
        raise ValueError("That agent no longer exists.")

    if name is not None:
        agent["name"] = _clean_name(name, agents, exclude_id=agent_id)
    if category_ids is not None:
        cleaned = [c.strip() for c in category_ids if isinstance(c, str) and c.strip()]
        if not cleaned:
            raise ValueError("Pick at least one category for the agent to prioritize.")
        agent["category_ids"] = list(dict.fromkeys(cleaned))[:MAX_CATEGORIES_PER_AGENT]
    if instructions is not None:
        agent["instructions"] = instructions.strip()[:MAX_INSTRUCTIONS_LEN]

    _write(agents)
    return agent


def delete_agent(agent_id: str) -> None:
    agents = _read()
    remaining = [a for a in agents if a["id"] != agent_id]
    if len(remaining) != len(agents):
        _write(remaining)

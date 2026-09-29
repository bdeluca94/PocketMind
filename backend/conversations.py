"""Save/load chat conversations as JSON files on the drive.

Transparently encrypted at rest when the optional passphrase-lock feature
(security.py) is turned on — see that module for details. Imports of
`security` are done lazily inside functions rather than at module load
time, since security.py itself needs to import this module (to encrypt
existing conversations when encryption is first turned on) and a
top-level circular import would break module loading.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
import uuid
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

CONV_DIR = ROOT / "conversations"


def _safe_id(raw: str) -> str:
    """Strips a conversation id down to characters that are safe in a
    filename. May legitimately return an empty string — an id of "???" has
    nothing left after stripping.

    Callers must treat "" as "no usable id" rather than passing it through.
    An empty id builds the path `conversations/.json`, which is a real
    (hidden) file that EVERY such id collides on: two conversations saved
    that way silently overwrite each other, and neither can be loaded back
    afterwards because listing reports the stem of `.json` as `.json`,
    which sanitises to a different id again."""
    return re.sub(r"[^a-zA-Z0-9_-]", "", raw or "")[:40]


def _read(path: Path) -> dict:
    raw = path.read_bytes()
    import security as security_mod
    if security_mod.is_enabled():
        if not security_mod.is_unlocked():
            raise RuntimeError("locked")
        raw = security_mod.decrypt_bytes(raw)
    return json.loads(raw)


def _write(path: Path, data: dict) -> None:
    payload = json.dumps(data, indent=2).encode("utf-8")
    import security as security_mod
    if security_mod.is_enabled():
        if not security_mod.is_unlocked():
            raise RuntimeError("locked")
        payload = security_mod.encrypt_bytes(payload)
    path.write_bytes(payload)


def list_conversations() -> list[dict]:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    import security as security_mod
    if security_mod.is_enabled() and not security_mod.is_unlocked():
        return []  # caller checks /api/security/status separately to show a lock screen

    items = []
    for f in CONV_DIR.glob("*.json"):
        try:
            data = _read(f)
            items.append({
                "id": f.stem,
                "title": data.get("title", "Untitled chat"),
                "updated_at": data.get("updated_at", ""),
            })
        except Exception:
            continue
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return items


def save_conversation(conv_id: str | None, title: str, messages: list) -> str:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    # `or` rather than a truthiness check on the raw input: an id like "???"
    # is truthy but sanitises to nothing, and treating that as a filename is
    # what causes the silent-overwrite case described in _safe_id.
    conv_id = _safe_id(conv_id) or uuid.uuid4().hex[:10]
    path = CONV_DIR / f"{conv_id}.json"
    _write(path, {
        "title": title[:80] if title else "Untitled chat",
        "updated_at": datetime.datetime.now().isoformat(),
        "messages": messages,
    })
    return conv_id


def load_conversation(conv_id: str) -> dict | None:
    safe = _safe_id(conv_id)
    if not safe:
        return None  # nothing usable left after sanitising — not a real id
    path = CONV_DIR / f"{safe}.json"
    if not path.exists():
        return None
    return _read(path)


def delete_conversation(conv_id: str) -> None:
    safe = _safe_id(conv_id)
    if not safe:
        return  # never let an empty id resolve to the `.json` path
    path = CONV_DIR / f"{safe}.json"
    path.unlink(missing_ok=True)


def search_conversations(query: str, limit: int = 50) -> list[dict]:
    """Case-insensitive substring search across every saved conversation's
    title and message content. Returns one result per matching message
    (title-only matches get one result with no message attached), each
    carrying enough to jump straight to it — most-recently-updated first,
    same ordering as the sidebar list.

    Reads every conversation file on every call, same as list_conversations
    — fine at the scale this app expects (a personal chat history, not a
    shared server), and keeps this in step with whatever's actually on disk
    rather than needing a separate index to maintain."""
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    import security as security_mod
    if security_mod.is_enabled() and not security_mod.is_unlocked():
        return []  # caller checks /api/security/status separately to show a lock screen

    q = query.strip().lower()
    if not q:
        return []

    results = []
    for f in CONV_DIR.glob("*.json"):
        try:
            data = _read(f)
        except Exception:
            continue
        conv_id = f.stem
        title = data.get("title", "Untitled chat")
        updated_at = data.get("updated_at", "")
        matched_any = False

        for i, m in enumerate(data.get("messages", [])):
            content = m.get("content", "") or ""
            idx = content.lower().find(q)
            if idx == -1:
                continue
            matched_any = True
            start = max(0, idx - 40)
            end = min(len(content), idx + len(q) + 40)
            snippet = content[start:end].strip()
            results.append({
                "conversation_id": conv_id,
                "title": title,
                "updated_at": updated_at,
                "message_index": i,
                "role": m.get("role", "user"),
                "snippet": snippet,
            })

        if not matched_any and q in title.lower():
            results.append({
                "conversation_id": conv_id,
                "title": title,
                "updated_at": updated_at,
                "message_index": None,
                "role": None,
                "snippet": "",
            })

    results.sort(key=lambda r: r["updated_at"], reverse=True)
    return results[:limit]


def export_text(data: dict, fmt: str = "md") -> str:
    """Formats a loaded conversation as plain text or Markdown."""
    title = data.get("title", "Untitled chat")
    lines: list[str] = []

    if fmt == "txt":
        lines.append(title)
        lines.append("=" * len(title))
        lines.append("")
        for m in data.get("messages", []):
            role = m.get("role", "user")
            label = "You" if role == "user" else "Assistant" if role == "assistant" else role.title()
            lines.append(f"{label}: {m.get('content', '')}")
            lines.append("")
    else:
        lines.append(f"# {title}")
        lines.append("")
        for m in data.get("messages", []):
            role = m.get("role", "user")
            label = "You" if role == "user" else "Assistant" if role == "assistant" else role.title()
            lines.append(f"**{label}:**")
            lines.append("")
            lines.append(m.get("content", ""))
            lines.append("")

    return "\n".join(lines)

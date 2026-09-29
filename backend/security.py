"""
Optional passphrase-based encryption at rest for saved conversations and
the PDF document database.

Threat model: this protects data if the USB drive is lost, stolen, or
examined while the app isn't actively unlocked and running. It is NOT
protection against someone with access to a live, unlocked session — the
whole point of the app is to use that data locally once unlocked. The
passphrase itself is never stored anywhere; only a salt and a small
"canary" value (used to verify a passphrase attempt without needing to
successfully decrypt real data) are kept on disk.

Conversations are encrypted individually, per file, the moment encryption
is turned on, and stay encrypted at rest permanently after that — every
save writes ciphertext directly, so there's no "working copy" of them to
worry about.

The PDF document database (documents/index.db) is different: it's a live
SQLite file that needs to be plaintext on disk while actively queried.
For that one, "encrypted at rest" means: encrypted as a single file
between sessions. Unlocking decrypts a working copy for the session to
use; locking (or normal app shutdown) re-encrypts it and removes the
plaintext copy. A hard crash while unlocked would leave that working copy
in plaintext until the next lock/unlock cycle — worth knowing, not a
crash-safe guarantee.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = ROOT / "security.json"
KDF_ITERATIONS = 390_000

_key: bytes | None = None  # in-memory only for the life of the process — never written to disk
_lock = threading.Lock()


def is_enabled() -> bool:
    if not CONFIG_PATH.exists():
        return False
    try:
        return bool(json.loads(CONFIG_PATH.read_text()).get("enabled", False))
    except Exception:
        return False


def is_unlocked() -> bool:
    return _key is not None


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=KDF_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def encrypt_bytes(data: bytes) -> bytes:
    if _key is None:
        raise RuntimeError("Locked — can't encrypt without an unlocked session.")
    return Fernet(_key).encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    if _key is None:
        raise RuntimeError("Locked — can't decrypt without an unlocked session.")
    return Fernet(_key).decrypt(data)


def enable(passphrase: str) -> None:
    """Turns encryption on for the first time with a new passphrase.
    Immediately encrypts any existing conversations and the documents
    database so nothing is left exposed after enabling."""
    global _key
    if not passphrase or len(passphrase) < 4:
        raise ValueError("Choose a passphrase that's at least 4 characters.")

    salt = os.urandom(16)
    key = _derive_key(passphrase, salt)
    canary = Fernet(key).encrypt(b"pocketmind-canary")

    with _lock:
        _key = key

    _encrypt_existing_conversations()
    _encrypt_existing_agents()
    _encrypt_existing_memory()
    # delete_plaintext=False: the session stays unlocked after enabling
    # (the passphrase was just set, nothing has locked yet), and the app
    # keeps needing a plaintext working copy to keep functioning through
    # the rest of this session. This just writes the initial encrypted
    # backup — see _encrypt_documents_db's docstring for what went wrong
    # when this used to delete the plaintext here too.
    _encrypt_documents_db(delete_plaintext=False)

    # Write the config only after the migration succeeds, so a failure
    # partway through doesn't leave us claiming to be encrypted when
    # some files weren't actually converted.
    CONFIG_PATH.write_text(json.dumps({
        "enabled": True,
        "salt": base64.b64encode(salt).decode("ascii"),
        "canary": canary.decode("ascii"),
    }))


def unlock(passphrase: str) -> bool:
    """Attempts to unlock with a passphrase. Returns True/False; never raises
    for a wrong passphrase."""
    global _key
    if not CONFIG_PATH.exists():
        return False
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        salt = base64.b64decode(cfg["salt"])
        key = _derive_key(passphrase, salt)
        Fernet(key).decrypt(cfg["canary"].encode("ascii"))
    except Exception:
        return False

    with _lock:
        _key = key
    _decrypt_documents_db()
    return True


def lock() -> None:
    """Ends the unlocked session: re-encrypts the documents database and
    drops the key from memory. Conversations need no action here since
    they're already stored encrypted at all times once enabled. Safe to
    call anytime, including when encryption was never turned on or the
    session was never unlocked — it's a no-op in that case rather than an
    error, since "lock" is meaningful to call defensively/idempotently."""
    global _key
    if _key is not None:
        _encrypt_documents_db()
    with _lock:
        _key = None


def disable(passphrase: str) -> bool:
    """Turns encryption back off, decrypting everything back to plaintext.
    Requires the correct passphrase. Returns False if the passphrase is
    wrong or encryption wasn't enabled."""
    if not is_enabled():
        return False
    if not unlock(passphrase):
        return False

    _decrypt_existing_conversations()
    _decrypt_existing_agents()
    _decrypt_existing_memory()
    # Documents DB: unlock() already decrypted it to a plaintext working
    # copy for the session, which is exactly the state we want to leave
    # it in once encryption is off — nothing further needed there.

    global _key
    CONFIG_PATH.unlink(missing_ok=True)
    with _lock:
        _key = None
    return True


def _encrypt_existing_conversations() -> None:
    import conversations as conversations_mod
    conversations_mod.CONV_DIR.mkdir(parents=True, exist_ok=True)
    for f in conversations_mod.CONV_DIR.glob("*.json"):
        raw = f.read_bytes()
        try:
            json.loads(raw)  # succeeds only if it's still plaintext
        except Exception:
            continue  # already encrypted (ciphertext won't parse as JSON on its own)
        f.write_bytes(encrypt_bytes(raw))


def _decrypt_existing_conversations() -> None:
    import conversations as conversations_mod
    for f in conversations_mod.CONV_DIR.glob("*.json"):
        raw = f.read_bytes()
        try:
            json.loads(raw)
            continue  # already plaintext
        except Exception:
            pass
        try:
            f.write_bytes(decrypt_bytes(raw))
        except InvalidToken:
            continue  # leave anything that fails to decrypt untouched, rather than corrupt it


def _encrypt_existing_agents() -> None:
    # Same one-shot migration as conversations, just for a single file
    # instead of a directory of them — agents.json holds a JSON array, not
    # one file per agent.
    import agents as agents_mod
    if not agents_mod.AGENTS_PATH.exists():
        return
    raw = agents_mod.AGENTS_PATH.read_bytes()
    try:
        json.loads(raw)
    except Exception:
        return  # already encrypted
    agents_mod.AGENTS_PATH.write_bytes(encrypt_bytes(raw))


def _decrypt_existing_agents() -> None:
    import agents as agents_mod
    if not agents_mod.AGENTS_PATH.exists():
        return
    raw = agents_mod.AGENTS_PATH.read_bytes()
    try:
        json.loads(raw)
        return  # already plaintext
    except Exception:
        pass
    try:
        agents_mod.AGENTS_PATH.write_bytes(decrypt_bytes(raw))
    except InvalidToken:
        return  # leave it untouched rather than corrupt it


def _encrypt_existing_memory() -> None:
    # Same one-shot migration as agents.json just above, for memory.json.
    import memory as memory_mod
    if not memory_mod.MEMORY_FILE.exists():
        return
    raw = memory_mod.MEMORY_FILE.read_bytes()
    try:
        json.loads(raw)
    except Exception:
        return  # already encrypted
    memory_mod.MEMORY_FILE.write_bytes(encrypt_bytes(raw))


def _decrypt_existing_memory() -> None:
    import memory as memory_mod
    if not memory_mod.MEMORY_FILE.exists():
        return
    raw = memory_mod.MEMORY_FILE.read_bytes()
    try:
        json.loads(raw)
        return  # already plaintext
    except Exception:
        pass
    try:
        memory_mod.MEMORY_FILE.write_bytes(decrypt_bytes(raw))
    except InvalidToken:
        return  # leave it untouched rather than corrupt it


def _encrypt_documents_db(delete_plaintext: bool = True) -> None:
    """Writes an encrypted backup of the documents database.

    delete_plaintext controls whether the working copy is removed
    afterward, and this matters more than it looks: enable() calls this
    with delete_plaintext=False, because turning encryption on does NOT
    lock the session — the passphrase was just set and the app is still
    unlocked, still actively using this file. Deleting it there (the
    original bug) meant the very next database read — which happens
    immediately, since the frontend refreshes the document list right
    after enabling — found no file, and SQLite's own behavior of silently
    creating a fresh empty database at a missing path took over from
    there. Everything after that point operated on the empty database, and
    the FIRST lock() then encrypted that empty state over the real backup,
    permanently losing whatever was there. Only lock() (where the session
    is genuinely ending) should ever pass delete_plaintext=True.
    """
    if _key is None:
        return  # nothing we can do without a key — caller should already guard this, but be safe
    import rag as rag_mod
    # Same lock rag.py's own operations (ingest, category CRUD, retrieval)
    # already hold while touching this file — without it, this read could
    # race a write-in-progress and capture a torn snapshot, or (worse, when
    # delete_plaintext=True) delete the file out from under a connection
    # another thread still has open.
    with rag_mod._db_lock:
        db = rag_mod.DB_PATH
        if db.exists():
            raw = db.read_bytes()
            (db.parent / "index.db.enc").write_bytes(encrypt_bytes(raw))
            if delete_plaintext:
                db.unlink()


def _decrypt_documents_db() -> None:
    import rag as rag_mod
    with rag_mod._db_lock:
        enc = rag_mod.DB_PATH.parent / "index.db.enc"
        if enc.exists() and _key is not None:
            raw = decrypt_bytes(enc.read_bytes())
            rag_mod.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            rag_mod.DB_PATH.write_bytes(raw)
            enc.unlink()

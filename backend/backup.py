"""Backup/restore for everything the user could actually lose: saved
conversations, custom agents, and the documents library (categories +
uploaded files). Deliberately excludes installed models (large and
re-downloadable, not the user's own data) and security.json (restoring a
stranger's lock state, or a different passphrase's encrypted blob, would
either brick access or silently create an unusable copy — see
restore_backup's own guard for the one related case that IS handled).

The backup is a zip of the same files PocketMind already keeps on disk,
copied byte-for-byte — plaintext or ciphertext, whatever their current
at-rest state is. Restoring never needs to know a passphrase itself; it's
just putting the same bytes back, with one safety check: if the backup's
files are encrypted and the drive is currently unlocked, they're
decrypt-checked against the *current* key before anything is written, so
restoring a backup made under a different passphrase fails loudly instead
of leaving permanently-undecryptable files on disk. See the encryption-state
matrix in restore_backup for the rest of the cases.
"""

from __future__ import annotations

import datetime
import io
import json
import sys
import zipfile
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

FORMAT = "pocketmind-backup"
VERSION = 1


class InvalidBackup(Exception):
    """Raised for anything wrong with a backup file itself — corrupt zip,
    not a PocketMind backup, wrong-passphrase ciphertext, or an encryption
    state that can't be safely reconciled with the current drive. Always
    caught and shown to the user as a plain message; never a 500."""


def create_backup() -> bytes:
    import agents as agents_mod
    import conversations as conversations_mod
    import rag as rag_mod

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        conversations_mod.CONV_DIR.mkdir(parents=True, exist_ok=True)
        conv_count = 0
        for f in sorted(conversations_mod.CONV_DIR.glob("*.json")):
            zf.write(f, f"conversations/{f.name}")
            conv_count += 1

        if agents_mod.AGENTS_PATH.exists():
            zf.write(agents_mod.AGENTS_PATH, "agents.json")

        with rag_mod._db_lock:
            if rag_mod.DB_PATH.exists():
                zf.write(rag_mod.DB_PATH, "documents/index.db")
            enc_path = rag_mod.DB_PATH.parent / "index.db.enc"
            if enc_path.exists():
                zf.write(enc_path, "documents/index.db.enc")

        # Outside the lock above: list_documents()/list_categories() take
        # rag_mod._db_lock themselves, which isn't reentrant.
        doc_count = len(rag_mod.list_documents())
        cat_count = len(rag_mod.list_categories())

        manifest = {
            "format": FORMAT,
            "version": VERSION,
            "created_at": datetime.datetime.now().isoformat(),
            "counts": {"conversations": conv_count, "documents": doc_count, "categories": cat_count},
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buf.getvalue()


def read_manifest(zip_bytes: bytes) -> dict:
    """Validates that `zip_bytes` looks like a real PocketMind backup and
    returns its manifest — used both to show the user what they're about to
    restore before they confirm, and as restore_backup's own first check."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        raw = zf.read("manifest.json")
        manifest = json.loads(raw)
    except Exception:
        raise InvalidBackup("That doesn't look like a PocketMind backup file.")
    if manifest.get("format") != FORMAT:
        raise InvalidBackup("That doesn't look like a PocketMind backup file.")
    if manifest.get("version", 0) > VERSION:
        raise InvalidBackup("This backup was made with a newer version of PocketMind. Update the app first.")
    return manifest


def _looks_like_plaintext_json(data: bytes) -> bool:
    try:
        json.loads(data)
        return True
    except Exception:
        return False


def restore_backup(zip_bytes: bytes) -> dict:
    """Replaces conversations, custom agents, and the documents library with
    the contents of a backup made by create_backup(). Fully replaces rather
    than merges — anything not in the backup (e.g. a conversation started
    since) is gone afterward, by design: "restore" means "go back to this
    snapshot," not "merge it in."

    Encryption-state matrix (backup encrypted? x drive encrypted/unlocked?):
      backup plain,  drive off              -> write as-is
      backup plain,  drive on+unlocked      -> re-encrypt with the *current*
                                                key before writing, so the
                                                "always ciphertext once
                                                encryption is on" invariant
                                                holds after restore too
      backup plain,  drive on+locked        -> refused (can't encrypt
                                                without a key)
      backup encrypted, drive off           -> refused (would leave
                                                unreadable ciphertext on an
                                                unencrypted drive)
      backup encrypted, drive on+unlocked   -> checked against the current
                                                key first; written as-is if
                                                it matches, refused if not
      backup encrypted, drive on+locked     -> refused (nothing to check
                                                the passphrase against yet)

    Everything is validated before anything is written, so a corrupt upload
    or a passphrase mismatch fails loudly with nothing touched, rather than
    leaving a half-restored drive."""
    import agents as agents_mod
    import conversations as conversations_mod
    import rag as rag_mod
    import security as security_mod

    manifest = read_manifest(zip_bytes)  # raises InvalidBackup if unusable
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = set(zf.namelist())

    conv_files = {n: zf.read(n) for n in sorted(names) if n.startswith("conversations/") and n.endswith(".json")}
    agents_bytes = zf.read("agents.json") if "agents.json" in names else None
    docs_plain = zf.read("documents/index.db") if "documents/index.db" in names else None
    docs_enc = zf.read("documents/index.db.enc") if "documents/index.db.enc" in names else None

    if docs_enc is not None:
        backup_encrypted = True
    elif docs_plain is not None:
        backup_encrypted = False
    elif conv_files:
        backup_encrypted = not _looks_like_plaintext_json(next(iter(conv_files.values())))
    elif agents_bytes is not None:
        backup_encrypted = not _looks_like_plaintext_json(agents_bytes)
    else:
        backup_encrypted = False  # a genuinely empty backup — nothing to be encrypted

    current_enabled = security_mod.is_enabled()
    current_unlocked = security_mod.is_unlocked()

    if backup_encrypted and not current_enabled:
        raise InvalidBackup(
            "This backup is encrypted, but this drive's encryption is currently off. "
            "Turn on encryption first, then restore."
        )
    if current_enabled and not current_unlocked:
        raise InvalidBackup("This drive is locked. Unlock it first, then restore.")
    if backup_encrypted and current_unlocked:
        sample = docs_enc if docs_enc is not None else next(iter(conv_files.values()), agents_bytes)
        if sample is not None:
            try:
                security_mod.decrypt_bytes(sample)
            except Exception:
                raise InvalidBackup(
                    "This backup was made with a different passphrase. Unlock with that "
                    "passphrase, or turn off encryption, then try restoring again."
                )

    # --- Everything validated — now actually apply it. ---
    reencrypt = current_enabled  # implies current_unlocked, given the guard above

    def prepare(data: bytes) -> bytes:
        if reencrypt and _looks_like_plaintext_json(data):
            return security_mod.encrypt_bytes(data)
        return data

    conversations_mod.CONV_DIR.mkdir(parents=True, exist_ok=True)
    for f in conversations_mod.CONV_DIR.glob("*.json"):
        f.unlink()
    for name, data in conv_files.items():
        (conversations_mod.CONV_DIR / Path(name).name).write_bytes(prepare(data))

    if agents_bytes is not None:
        agents_mod.AGENTS_PATH.write_bytes(prepare(agents_bytes))
    else:
        agents_mod.AGENTS_PATH.unlink(missing_ok=True)

    with rag_mod._db_lock:
        enc_path = rag_mod.DB_PATH.parent / "index.db.enc"
        rag_mod.DB_PATH.unlink(missing_ok=True)
        enc_path.unlink(missing_ok=True)
        rag_mod.DOCS_DIR.mkdir(parents=True, exist_ok=True)
        if docs_plain is not None:
            rag_mod.DB_PATH.write_bytes(docs_plain)
        elif docs_enc is not None:
            enc_path.write_bytes(docs_enc)

    return manifest

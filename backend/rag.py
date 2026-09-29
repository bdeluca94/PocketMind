"""
Lets the AI use uploaded PDFs as reference material ("digest a document").

Approach (kept deliberately simple so it runs offline on modest hardware):
  1. Extract text from the PDF (pypdf).
  2. Split into overlapping chunks (~180 words).
  3. Embed each chunk with a small local embedding GGUF model.
  4. Store chunks + embedding vectors in a SQLite file on the drive.
  5. At chat time, embed the user's question, compare against stored
     vectors with cosine similarity, and pull in the best-matching chunks
     as extra context for the model.

No external vector database, no cloud calls — just SQLite + numpy.
"""

from __future__ import annotations

import json
import hashlib
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import sys

import numpy as np
from pypdf import PdfReader

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

DOCS_DIR = ROOT / "documents"
DB_PATH = DOCS_DIR / "index.db"

EMBED_MODEL = {
    "filename": "embed-nomic-embed-text-v1.5.Q4_K_M.gguf",
    "url": "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q4_K_M.gguf",
    "size_gb": 0.1,
}

# --- Category routing tuning -------------------------------------------------
# These four numbers govern how aggressively documents get auto-filed and how
# much a question gets steered toward one category. They're starting values
# picked to fail safe (when in doubt, do nothing and search everything), not
# values derived from a benchmark — the right settings depend on how distinct
# a given user's categories actually are. Raising the two MIN_SIMILARITY
# values makes the app more cautious; raising CATEGORY_BOOST makes routing
# more decisive at the cost of occasionally burying a good cross-category hit.
CATEGORY_BOOST = 0.05        # added to a chunk's score when it's in the routed category
ROUTE_MIN_SIMILARITY = 0.28  # a category must match the question at least this well to be picked
ROUTE_MIN_MARGIN = 0.04      # ...and beat the runner-up category by at least this much
SUGGEST_MIN_SIMILARITY = 0.32  # a document must match this well to be auto-filed on upload
SUGGEST_MIN_MARGIN = 0.02      # ...and beat the runner-up category by at least this much

# Seeded once, on first run only (tracked in the meta table, so deleting them
# doesn't bring them back). Empty categories are hidden from the sidebar until
# something lands in them, so these cost nothing visually — they exist so the
# very first upload has something to be matched against.
DEFAULT_CATEGORIES = ["Finance", "Medical", "Legal", "Work", "Technical", "Personal"]

_embedder = None
_embedder_lock = threading.Lock()
_embedder_last_used = 0.0
_embedder_idle_seconds = 300  # unload the embedding model after 5 min of no use
_unload_watcher_started = False
_db_lock = threading.Lock()

# The chat model and this embedding model are two independent llama.cpp
# contexts loaded in the same process — nothing about llama_cpp_lock or
# _embedder_lock stops one from actually running inference at the same
# moment the other is (they're different locks guarding different models).
# Two ggml-cpu compute kernels genuinely running concurrently on separate
# threads in one process is the kind of thing that isn't guaranteed safe by
# ggml's CPU backend and crashed the app (0xc0000005 access violation in
# ggml-cpu.dll) — most easily hit by pasting a large block of text and
# asking about it right away, since that's exactly "embedding starts, chat
# generation starts moments later" on two separate threads. Server.py's
# chat-streaming loop and this module's _embed() both hold this lock for
# their actual native call, so only one of the two models is ever doing
# real inference at a time — a paste and a chat reply now simply take
# turns instead of racing.
NATIVE_INFERENCE_LOCK = threading.Lock()
_cancel_event = threading.Event()

# Cache for retrieve_with_routing's chunk-vector matrix (see
# _finish_vector_cache below). None means "needs rebuilding on next use."
_vector_cache_lock = threading.Lock()
_vector_cache: tuple[list[str], list[str], np.ndarray] | None = None

# Progress for the PDF currently being ingested (chunked + embedded).
# Read by /api/documents/upload-status so the UI can show real progress
# instead of a static "Reading…" message — matters once documents get
# large, since embedding runs one chunk at a time on CPU and can take a
# while.
ingest_progress = {
    "active": False, "filename": None,
    "chunks_done": 0, "total_chunks": 0, "error": None, "cancelled": False,
}


class IngestCancelled(Exception):
    """Internal signal that a user cancelled an in-progress document ingest
    via cancel_ingest(). Never escapes ingest_document() — it's caught there
    and turned into a normal {"cancelled": True} return value."""


def cancel_ingest() -> None:
    """Requests cancellation of whichever ingest_document() call is
    currently running. Cooperative — the embedder can't be interrupted
    mid-embedding, so this takes effect at the next per-chunk checkpoint,
    typically within a second or two rather than instantly. A no-op if
    nothing is running."""
    _cancel_event.set()


def _connect():
    """Opens the documents database — but only if it's actually safe to.
    If encryption is enabled and the session is locked, the real database
    only exists as an encrypted blob (index.db.enc); sqlite3.connect()
    would otherwise silently create a fresh EMPTY database at DB_PATH,
    which could then get written to and, on the next unlock, be
    overwritten by the real decrypted data — silently losing whatever was
    added while locked. So: refuse outright instead."""
    import security as security_mod
    if security_mod.is_enabled() and not security_mod.is_unlocked():
        raise RuntimeError("locked")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, filename TEXT, added_at TEXT, num_chunks INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY, doc_id TEXT, text TEXT, vector TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT,
            sort_order INTEGER DEFAULT 0,
            name_vector TEXT
        )"""
    )
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    _migrate_schema(conn)
    return conn


def _migrate_schema(conn) -> None:
    """Brings an older documents/index.db up to the current shape.

    This lives inside _connect() rather than in a startup hook on purpose:
    when encryption is on, the real database doesn't exist as readable
    SQLite until the user unlocks, so there's no single moment at boot when
    a migration could run. _connect() already refuses while locked, so
    hanging the migration off it means it runs at exactly the first safe
    opportunity in both the encrypted and unencrypted cases, with no
    separate code path for either."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    if "category_id" not in existing:
        conn.execute("ALTER TABLE documents ADD COLUMN category_id TEXT")
    if "centroid" not in existing:
        conn.execute("ALTER TABLE documents ADD COLUMN centroid TEXT")
    if "content_hash" not in existing:
        conn.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
    if "conversation_id" not in existing:
        # NULL here means "a real, filed document" (uploaded PDFs — visible
        # in the sidebar, searched everywhere). Non-NULL means "text pasted
        # or dropped into the chat bar for one conversation" — searchable
        # only while chatting in that conversation, never listed in the
        # sidebar, deleted along with the conversation. See
        # ingest_text_snippet and retrieve_with_routing's conversation_id
        # handling below.
        conn.execute("ALTER TABLE documents ADD COLUMN conversation_id TEXT")
    # Enforced at the database level, not just checked in Python: SQLite
    # treats every NULL as distinct from every other NULL, so this coexists
    # fine with old documents that predate hashing (content_hash IS NULL) —
    # it only ever rejects two rows that both have the *same real* hash.
    # The WHERE clause keeps those NULL rows out of the index entirely rather
    # than indexing them for no benefit.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_content_hash "
        "ON documents(content_hash) WHERE content_hash IS NOT NULL"
    )

    seeded = conn.execute("SELECT value FROM meta WHERE key = 'categories_seeded'").fetchone()
    if not seeded:
        import datetime
        now = datetime.datetime.now().isoformat()
        for i, name in enumerate(DEFAULT_CATEGORIES):
            conn.execute(
                "INSERT OR IGNORE INTO categories (id, name, created_at, sort_order) VALUES (?, ?, ?, ?)",
                (uuid.uuid4().hex[:12], name, now, i),
            )
        conn.execute("INSERT INTO meta (key, value) VALUES ('categories_seeded', '1')")

    _backfill_centroids(conn)
    conn.commit()


def _control_char_ratio(text: str) -> float:
    """Fraction of characters that are control codes (ASCII C0/C1, other
    than \\n/\\r/\\t) — the signature of a PDF page rendered through a
    broken or non-standard embedded font with no Unicode mapping, where
    pypdf's extract_text() returns raw internal glyph/character codes
    instead of real text rather than failing outright. Genuine extracted
    text, in any language, essentially never contains these — a
    non-breaking space, a bullet-glyph private-use character, accented or
    CJK text, none of that trips this check; only actual control bytes do.
    Measured at 0.0000-0.0007 across a random sample of otherwise-normal
    documents in this app's own library, versus 0.74 for one genuinely
    broken PDF found there — a wide enough margin that GARBAGE_TEXT_RATIO
    below doesn't need to be tuned precisely."""
    if not text:
        return 0.0
    bad = sum(
        1 for c in text
        if (ord(c) < 32 and c not in "\n\r\t") or (0x7F <= ord(c) <= 0x9F)
    )
    return bad / len(text)


# See _control_char_ratio's docstring for how this was chosen.
GARBAGE_TEXT_RATIO = 0.15


def _load_vector(raw) -> list[float] | None:
    """Parses a stored vector, returning None instead of raising if the row is
    unusable.

    This matters more than it looks. _backfill_centroids runs inside
    _connect(), so an exception there doesn't fail one query — it fails every
    single database operation the app makes, permanently, and the app becomes
    unusable until the file is hand-edited. One truncated write (a yanked USB
    drive mid-commit is the realistic cause here) shouldn't be able to do
    that. Skipping the bad row costs a little retrieval quality; refusing to
    open the database costs everything."""
    if not raw:
        return None
    try:
        v = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(v, list) or not v:
        return None
    try:
        return [float(x) for x in v]
    except (ValueError, TypeError):
        return None


def invalidate_vector_cache() -> None:
    """Drops the cached chunk-vector matrix built by _finish_vector_cache.

    Called after anything that changes which chunk rows exist or what they
    embed to — ingesting or deleting a document, or clearing a
    conversation's scoped snippets. Category reassignment does NOT need
    this: retrieve_with_routing re-reads each chunk's current filename/
    category/conversation straight from the documents table on every call
    (a cheap per-document lookup, not per-chunk), so a document moved to a
    different category is reflected immediately without touching this
    cache at all."""
    global _vector_cache
    with _vector_cache_lock:
        _vector_cache = None


def _fetch_chunk_rows_if_needed(conn) -> list | None:
    """Returns raw (text, vector_json, doc_id) rows fetched fresh from
    SQLite if the vector cache needs (re)building, or None if it's already
    warm. Called while the caller still holds _db_lock and an open
    connection; the caller is expected to release both afterward and then
    call _finish_vector_cache(rows) — see that function's docstring for why
    the fetch and the parsing are deliberately split across the lock."""
    with _vector_cache_lock:
        if _vector_cache is not None:
            return None
    return conn.execute("SELECT text, vector, doc_id FROM chunks").fetchall()


def _finish_vector_cache(rows: list | None) -> tuple[list[str], list[str], np.ndarray]:
    """Parses raw chunk rows (from _fetch_chunk_rows_if_needed) into the
    cached (texts, doc_ids, matrix) tuple retrieve_with_routing searches
    against, and stores it for reuse. Pass rows=None to just return
    whatever's already cached — the common case once warm, and also how a
    second caller that raced _fetch_chunk_rows_if_needed to a cold cache
    ends up here too (see below).

    Before this cache existed, retrieve_with_routing re-fetched and
    re-json.loads'd every chunk's vector out of SQLite on every single chat
    message, regardless of which chat model was selected — fine for a
    library of a few hundred chunks, but a library that grows into the
    hundreds of thousands (a few hundred books' worth of PDFs) turns that
    into tens of seconds of redundant disk I/O and JSON parsing before the
    chat model even starts generating a token, every single message.
    Measured on a ~200K-chunk library: close to a minute per message,
    almost entirely in this parsing step rather than the SQL fetch itself.
    Building it once and reusing it until invalidate_vector_cache() is
    called (see there) turns that into one rebuild per library change
    instead of one per message.

    This function deliberately runs with NO database lock held — only the
    SQL fetch that produced `rows` needed one (see
    _fetch_chunk_rows_if_needed and its callers: retrieve_with_routing and
    warm_vector_cache). Every other database operation in the app — listing
    documents, ingesting, a different chat's own retrieval — shares that
    same lock; holding it through this parsing too would stall all of them
    for as long as the very first build takes, including this app's own
    sidebar document/category lists on startup, which is exactly when
    warm_vector_cache's background warm-up would otherwise be running. A
    second caller that also saw a cold cache just redoes this same
    fetch-and-parse once more instead of blocking on the first — rare
    enough (only the very first call after a fresh start or a library
    change can ever race here) that the occasional duplicate work is worth
    not adding a second lock just to prevent it.

    doc_id is kept instead of resolved metadata (filename/category_id/
    conversation_id) so a document rename, re-categorization, or category
    deletion never needs to invalidate this — the caller re-resolves that
    small, per-document metadata fresh on every call instead."""
    global _vector_cache
    if rows is None:
        with _vector_cache_lock:
            if _vector_cache is not None:
                return _vector_cache
        rows = []  # shouldn't normally happen — treated as an empty library
    texts = [r[0] for r in rows]
    doc_ids = [r[2] for r in rows]
    parsed = [_load_vector(r[1]) for r in rows]
    usable = [i for i, v in enumerate(parsed) if v is not None]
    if len(usable) < len(rows):
        texts = [texts[i] for i in usable]
        doc_ids = [doc_ids[i] for i in usable]
    vectors = [parsed[i] for i in usable]
    # Same mixed-dimension guard retrieve_with_routing always had (e.g.
    # the local embedding model was reinstalled/upgraded at some point
    # and left old chunks with a different vector length behind) — done
    # once here at cache-build time instead of on every call.
    if vectors:
        dim_counts: dict[int, int] = {}
        for v in vectors:
            dim_counts[len(v)] = dim_counts.get(len(v), 0) + 1
        expected_dim = max(dim_counts, key=dim_counts.get)
        keep = [i for i, v in enumerate(vectors) if len(v) == expected_dim]
        if len(keep) < len(vectors):
            texts = [texts[i] for i in keep]
            doc_ids = [doc_ids[i] for i in keep]
            vectors = [vectors[i] for i in keep]
    matrix = np.array(vectors, dtype=np.float32) if vectors else np.zeros((0, 0), dtype=np.float32)
    with _vector_cache_lock:
        _vector_cache = (texts, doc_ids, matrix)
        return _vector_cache


def warm_vector_cache() -> None:
    """Builds the chunk-vector cache proactively — called on a background
    thread at server startup (see server.py) so the one-time cost described
    in _finish_vector_cache's docstring happens while the app is still
    loading, instead of delaying whichever chat message happens to be
    first. Silently does nothing if the drive is locked (nothing to warm
    yet — a normal retrieve_with_routing call after unlocking builds it the
    same way this would have)."""
    with _db_lock:
        try:
            conn = _connect()
        except RuntimeError:
            return  # locked — nothing to warm yet
        try:
            raw_rows = _fetch_chunk_rows_if_needed(conn)
        finally:
            conn.close()
    _finish_vector_cache(raw_rows)


def _backfill_centroids(conn) -> None:
    """Computes the mean chunk vector for any document that doesn't have one
    yet — i.e. everything uploaded before categories existed.

    Deliberately reuses the vectors already sitting in the chunks table
    rather than re-embedding, so this needs no model loaded, no network, and
    no re-upload: it's arithmetic over data that's already on disk. Runs once
    (the WHERE clause finds nothing afterwards)."""
    pending = conn.execute(
        "SELECT id FROM documents WHERE centroid IS NULL"
    ).fetchall()
    if not pending:
        return
    for (doc_id,) in pending:
        rows = conn.execute("SELECT vector FROM chunks WHERE doc_id = ?", (doc_id,)).fetchall()
        centroid = _mean_vector([v for v in (_load_vector(r[0]) for r in rows) if v])
        # A document with no chunks (or unparseable ones) gets an empty
        # marker rather than staying NULL — otherwise it would be retried on
        # every single connection forever.
        conn.execute("UPDATE documents SET centroid = ? WHERE id = ?", (json.dumps(centroid), doc_id))


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    """Mean of equal-length vectors, normalized to unit length. Vectors whose
    dimension doesn't match the majority are dropped, same as in retrieve() —
    a database that's seen two different embedding models shouldn't be able
    to crash this."""
    vectors = [v for v in vectors if v]
    if not vectors:
        return []
    dim_counts: dict[int, int] = {}
    for v in vectors:
        dim_counts[len(v)] = dim_counts.get(len(v), 0) + 1
    expected = max(dim_counts, key=dim_counts.get)
    usable = [v for v in vectors if len(v) == expected]
    if not usable:
        return []
    mean = np.mean(np.array(usable, dtype=np.float32), axis=0)
    norm = float(np.linalg.norm(mean))
    if norm == 0:
        return []
    return (mean / norm).astype(np.float32).tolist()


def embedding_model_path() -> Path | None:
    p = ROOT / "models" / EMBED_MODEL["filename"]
    return p if p.exists() else None


def get_embedder():
    """Lazily load the (small) local embedding model. Once loaded, a
    background watcher unloads it again after a period of inactivity —
    a user might reference a PDF once and then chat for an hour without
    touching documents again, and there's no reason to keep the embedding
    model's RAM reserved for that whole time."""
    global _embedder, _embedder_last_used, _unload_watcher_started
    with _embedder_lock:
        if _embedder is None:
            from llama_cpp import Llama

            model_path = embedding_model_path()
            if model_path is None:
                raise RuntimeError(
                    "The document-reading model isn't installed yet. "
                    "Upload a PDF again to install it (~100MB, one-time)."
                )
            # n_gpu_layers=-1 offloads everything to GPU if one is available
            # and llama-cpp-python was built with GPU support — same flag
            # server.py's get_llm() uses for the chat model; silently falls
            # back to CPU-only otherwise. This was never wired up here
            # before, meaning every PDF upload embedded on CPU regardless of
            # hardware, even on a GPU-accelerated build.
            #
            # flash_attn=True still helps an embedding-only context (still
            # doing full attention over each chunk's tokens), but the
            # type_k/type_v KV-cache quantization server.py's get_llm() sets
            # is deliberately skipped here: embedding is a single forward
            # pass per chunk with no autoregressive KV cache growth to speak
            # of, so there's nothing meaningful for it to save, and this is
            # the wrong place to try an untested combination for the first
            # time — retrieval quality depends on these vectors.
            _embedder = Llama(model_path=str(model_path), embedding=True, n_gpu_layers=-1,
                               flash_attn=True, verbose=False)
            if not _unload_watcher_started:
                _unload_watcher_started = True
                threading.Thread(target=_embedder_idle_watcher, daemon=True).start()
        _embedder_last_used = time.time()
        return _embedder


def _embedder_idle_watcher():
    """Runs for the life of the process once the embedder has been loaded
    at least once. Checks periodically and drops the model reference after
    it's sat unused past the idle timeout, freeing its RAM; the native
    llama.cpp memory is released when Python garbage-collects the object.
    get_embedder() will transparently reload it on the next PDF upload or
    document-backed question."""
    global _embedder
    while True:
        time.sleep(30)
        with _embedder_lock:
            if _embedder is not None and (time.time() - _embedder_last_used) > _embedder_idle_seconds:
                _embedder = None


def _embed(text: str, task: str) -> list[float]:
    """Runs text through the local embedding model.

    task is required, not optional, on purpose. nomic-embed-text (the model
    this app installs) was trained with a task-specific prefix prepended to
    every input, and its model card is explicit that skipping it isn't a
    minor quality hit — the model is then operating completely outside the
    regime it was calibrated for. In practice that showed up as almost every
    uploaded PDF auto-filing into the same one category regardless of
    content: with no prefix, the category name-probe vectors and the
    document centroids being compared against them weren't meaningfully
    separated from each other, so whichever candidate had a marginal
    numerical edge — for reasons having nothing to do with topic — ended up
    winning nearly every comparison. Making `task` mandatory means a new
    call site added later fails loudly (TypeError) instead of silently
    reintroducing the same collapse.

    Use "search_document" for anything that belongs to the retrievable
    corpus — PDF chunks, and the "Documents about X" text that stands in for
    a category before it has real members — and "search_query" for a live
    question being used to search against that corpus. This is nomic's own
    asymmetric retrieval convention: a query and the passage that answers it
    are different enough in length and shape that the model was trained to
    treat them as distinct roles, not interchangeable text.
    """
    if task not in ("search_document", "search_query"):
        raise ValueError(f"Unknown embedding task {task!r}")
    llm = get_embedder()
    with NATIVE_INFERENCE_LOCK:
        out = llm.create_embedding(f"{task}: {text}")
    return out["data"][0]["embedding"]


def _split_into_paragraphs(text: str) -> list[str]:
    """pypdf extraction doesn't preserve heading styles, but it does keep
    blank-line breaks in most PDFs — use those as paragraph boundaries."""
    paras = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paras if p.strip()]


def _split_long_paragraph(paragraph: str, max_words: int) -> list[str]:
    """Break an oversized paragraph on sentence boundaries instead of mid-word."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces, current, current_words = [], [], 0
    for sentence in sentences:
        w = len(sentence.split())
        if w > max_words:
            # This "sentence" (or the whole paragraph, if it had no
            # sentence-ending punctuation at all — common with garbled PDF
            # text extraction) is itself too long to fit in one chunk.
            # Sentence-splitting can't help here, so fall back to a plain
            # word window for just this piece.
            if current:
                pieces.append(" ".join(current))
                current, current_words = [], 0
            pieces.extend(_chunk_by_words(sentence, max_words, overlap=0))
            continue
        if current_words + w > max_words and current:
            pieces.append(" ".join(current))
            current, current_words = [], 0
        current.append(sentence)
        current_words += w
    if current:
        pieces.append(" ".join(current))
    return pieces


def _chunk_by_words(text: str, words_per_chunk: int, overlap: int) -> list[str]:
    """Fallback for text with no paragraph structure at all (some PDFs
    extract as one giant blob with no blank lines) — old fixed-window
    behavior."""
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(words_per_chunk - overlap, 1)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + words_per_chunk])
        if chunk.strip():
            chunks.append(chunk)
        if i + words_per_chunk >= len(words):
            break
    return chunks


def _chunk_text(text: str, words_per_chunk: int = 180, overlap: int = 30) -> list[str]:
    """Pack paragraphs together up to ~words_per_chunk instead of slicing
    fixed-width word windows, so a chunk doesn't get cut off mid-sentence.
    A paragraph much longer than the target is split on sentence
    boundaries; a short trailing paragraph is carried forward as overlap
    so retrieval doesn't lose context right at a chunk edge."""
    paragraphs = []
    for para in _split_into_paragraphs(text):
        if len(para.split()) > words_per_chunk * 1.5:
            paragraphs.extend(_split_long_paragraph(para, words_per_chunk))
        else:
            paragraphs.append(para)

    if not paragraphs:
        return _chunk_by_words(text, words_per_chunk, overlap)

    chunks = []
    current, current_words = [], 0
    for para in paragraphs:
        w = len(para.split())
        if current_words + w > words_per_chunk and current:
            chunks.append("\n\n".join(current))
            tail = current[-1]
            if len(tail.split()) <= overlap:
                current, current_words = [tail], len(tail.split())
            else:
                current, current_words = [], 0
        current.append(para)
        current_words += w
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _find_duplicate(conn, content_hash: str) -> dict | None:
    row = conn.execute(
        "SELECT id, filename FROM documents WHERE content_hash = ?", (content_hash,)
    ).fetchone()
    return {"id": row[0], "filename": row[1]} if row else None


SUPPORTED_DOCUMENT_EXTENSIONS = {"pdf", "docx", "xlsx", "pptx"}

# pypdf output shorter than this from a whole PDF is treated as "no real
# text layer" rather than "a very short document" — a genuinely tiny PDF
# is rare enough that OCR-ing it too (slower, but still correct) is a
# better failure mode than the reverse: skipping OCR on a scanned page
# that happened to yield a few stray characters from a logo or watermark.
OCR_FALLBACK_MIN_CHARS = 20

_ocr_engine = None
_ocr_lock = threading.Lock()


def _get_ocr_engine():
    """Lazily loads RapidOCR's models — unlike the chat/embedding/image
    models (multi-GB, worth unloading when idle — see get_embedder() and
    imagegen.py's get_sd()), these are a few tens of MB bundled directly
    inside the pip package itself (no internet download at runtime, same
    offline guarantee as everything else here), so there's no real memory
    pressure to unload them again once loaded."""
    global _ocr_engine
    with _ocr_lock:
        if _ocr_engine is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        return _ocr_engine


def _ocr_pdf(file_bytes: bytes) -> str:
    """Falls back to OCR for a PDF pypdf couldn't pull real text out of —
    almost always a scanned or photographed page rather than one produced
    digitally, the exact case ingest_document's own error message already
    named as a known gap before this existed. Renders each page to a
    bitmap with pypdfium2 (pure-Python bindings, prebuilt wheel, no
    external binary needed — unlike poppler/pdftoppm) and reads the text
    back with RapidOCR.

    Deliberately doesn't take NATIVE_INFERENCE_LOCK: this is ONNX Runtime,
    an entirely different native inference engine from the ggml backend
    llama.cpp and stable-diffusion.cpp both share — the documented crash
    that lock exists for (see its own docstring) was specifically two
    ggml contexts running at once, not "any two native calls." Treated
    the same as pypdf's own extract_text() just above, which never took
    this lock either: text extraction is a pre-processing step before the
    embedding call that actually needs it, not a native call in its own
    right.

    Returns "" (never raises) if rapidocr-onnxruntime/pypdfium2 aren't
    actually installed — both ship in requirements.txt and the exe always
    bundles them, but a script-launcher install from before this feature
    existed won't have them until its venv is reinstalled. The caller
    (extract_document_text) already treats an OCR pass that found nothing
    the same as one that was never attempted, falling through to the
    original, still-accurate "couldn't find any readable text" error —
    better than this surfacing as a confusing, unrelated-looking
    ImportError several calls up in a file-upload endpoint."""
    import io

    try:
        import pypdfium2 as pdfium
        ocr = _get_ocr_engine()
    except ImportError:
        return ""

    # PdfDocument/PdfPage/PdfBitmap all wrap native pdfium buffers that
    # aren't released by Python's garbage collector on their own — only
    # PdfDocument even implements __exit__, and none of the three define
    # __del__, so skipping explicit .close() here would leak native memory
    # for as long as the process runs, growing with every scanned page a
    # user ever uploads across a whole session.
    parts = []
    with pdfium.PdfDocument(io.BytesIO(file_bytes)) as pdf:
        for page in pdf:
            try:
                # scale=2.0 -> ~144 DPI off a standard page: legible enough
                # for OCR without spending CPU time on resolution a scanned
                # page rarely actually has.
                bitmap = page.render(scale=2.0)
                try:
                    result, _ = ocr(np.array(bitmap.to_pil()))
                    if result:
                        parts.append("\n".join(line[1] for line in result))
                finally:
                    bitmap.close()
            finally:
                page.close()
    return "\n\n".join(parts)


def extract_document_text(file_bytes: bytes, filename: str) -> str:
    """Pulls plain text out of a PDF, Word doc, Excel sheet, or PowerPoint
    file — the one place all four formats' extraction quirks live, shared
    by both the permanent Documents upload (ingest_document) and the chat
    bar's conversation-scoped file drop (see /api/documents/upload-scoped
    in server.py). Raises ValueError for an unsupported extension, same as
    a document with no readable text — both are just "can't use this file"
    to whoever's handling the error."""
    import io

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        if len(text.strip()) < OCR_FALLBACK_MIN_CHARS:
            # Falls through to returning the (near-)empty text as-is if OCR
            # also comes up empty — ingest_document's existing "couldn't
            # find any readable text" error already covers that case
            # correctly, no need to duplicate it here.
            ocr_text = _ocr_pdf(file_bytes)
            if ocr_text.strip():
                return ocr_text
        return text

    if ext == "docx":
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        parts = [p.text for p in doc.paragraphs if p.text]
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text for c in row.cells if c.text]
                if cells:
                    parts.append("\t".join(cells))
        return "\n".join(parts)

    if ext == "xlsx":
        from openpyxl import load_workbook
        # read_only streams rows instead of loading the whole sheet into
        # memory — matters once a spreadsheet runs to tens of thousands of
        # rows. data_only=True reads a formula's last-calculated value
        # instead of the formula text itself, since that's what a person
        # reading the sheet actually sees.
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        parts = []
        for sheet in wb.worksheets:
            parts.append(f"# {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    parts.append("\t".join(cells))
        return "\n".join(parts)

    if ext == "pptx":
        from pptx import Presentation
        prs = Presentation(io.BytesIO(file_bytes))
        parts = []
        for i, slide in enumerate(prs.slides, 1):
            parts.append(f"# Slide {i}")
            for shape in slide.shapes:
                if shape.has_text_frame and shape.text_frame.text:
                    parts.append(shape.text_frame.text)
        return "\n".join(parts)

    raise ValueError(f"\".{ext}\" isn't a supported document type.")


def ingest_document(file_bytes: bytes, filename: str) -> dict:
    # Matching is by content, not filename — deliberately. A renamed copy of
    # a document you already have is still the same document and shouldn't
    # cost a second round of embedding; two different files that happen to
    # share a name are NOT duplicates and shouldn't be blocked. Hashing raw
    # bytes (already fully in memory from the upload) is essentially free,
    # so this check runs first, before text extraction or any embedding —
    # a repeat upload is rejected without doing any of the expensive work.
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    with _db_lock:
        conn = _connect()
        try:
            existing = _find_duplicate(conn, content_hash)
        finally:
            conn.close()
    if existing:
        return {"duplicate": True, "filename": filename,
                "existing_id": existing["id"], "existing_filename": existing["filename"]}

    full_text = extract_document_text(file_bytes, filename)

    # Distinct from the empty-text check below: a PDF with a broken/
    # non-standard embedded font can extract plenty of "text" — it just
    # isn't real, being raw internal character codes instead of actual
    # letters (see _control_char_ratio). That's worse than an empty result,
    # not better: it passes the emptiness check, then quietly fills the
    # library with meaningless chunks that can still score deceptively high
    # similarity against unrelated questions later, rather than just failing
    # visibly at upload time the way a scanned image-only PDF does.
    if _control_char_ratio(full_text) > GARBAGE_TEXT_RATIO:
        raise ValueError(
            "This file's text came out unreadable rather than as real text "
            "— likely a broken or non-standard font embedded in the PDF. "
            "Try a different copy of this file if one's available."
        )

    chunks = _chunk_text(full_text)
    if not chunks:
        raise ValueError("Couldn't find any readable text in that file, even after trying OCR on it as a scanned document — it may be blank, too low-quality to read, or empty.")

    doc_id = uuid.uuid4().hex[:12]
    suggested = None

    _cancel_event.clear()  # a stale cancel from a previous upload shouldn't affect this one
    ingest_progress.update(active=True, filename=filename, chunks_done=0,
                            total_chunks=len(chunks), error=None, cancelled=False)
    try:
        with _db_lock:
            conn = _connect()
            try:
                import datetime
                try:
                    conn.execute(
                        "INSERT INTO documents (id, filename, added_at, num_chunks, content_hash) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (doc_id, filename, datetime.datetime.now().isoformat(),
                         len(chunks), content_hash),
                    )
                except sqlite3.IntegrityError:
                    # The check above already covers the ordinary case; this
                    # only fires if a second upload of the identical file
                    # landed in the narrow gap between that check and this
                    # insert (two requests arriving at nearly the same
                    # instant). The single-active-upload guard the API layer
                    # already enforces makes that vanishingly rare from the
                    # app's own UI, but the unique index makes it impossible
                    # to end up with two stored copies either way — this just
                    # turns the rare case into the same graceful response
                    # instead of a raw database error reaching the user.
                    conn.rollback()
                    row = _find_duplicate(conn, content_hash)
                    return {"duplicate": True, "filename": filename,
                            "existing_id": row["id"] if row else None,
                            "existing_filename": row["filename"] if row else None}
                vectors = []
                for chunk in chunks:
                    if _cancel_event.is_set():
                        raise IngestCancelled()
                    vector = _embed(chunk, task="search_document")
                    vectors.append(vector)
                    conn.execute(
                        "INSERT INTO chunks (id, doc_id, text, vector) VALUES (?, ?, ?, ?)",
                        (uuid.uuid4().hex[:12], doc_id, chunk, json.dumps(vector)),
                    )
                    ingest_progress["chunks_done"] += 1

                # The document's own centroid — computed here because the
                # vectors are already in hand and the embedder is already
                # loaded, so it costs one array mean rather than a second pass.
                centroid = _mean_vector(vectors)
                conn.execute("UPDATE documents SET centroid = ? WHERE id = ?",
                             (json.dumps(centroid), doc_id))

                if centroid:
                    cat_vecs = _category_vectors(conn, want_dim=len(centroid))
                    # The margin here is smaller than the query-routing one —
                    # filing is visible and one click to change, so it can
                    # afford to be bolder. But it isn't zero: with several
                    # near-identical scores the winner is effectively whichever
                    # one numpy happened to sort first, and a coin-flip
                    # presented as a decision is worse than leaving the
                    # document in Uncategorized where it's obviously unfiled.
                    picked, _score = _pick_category(
                        np.array(centroid, dtype=np.float32), cat_vecs,
                        SUGGEST_MIN_SIMILARITY, SUGGEST_MIN_MARGIN,
                    )
                    if picked:
                        conn.execute("UPDATE documents SET category_id = ? WHERE id = ?", (picked, doc_id))
                        row = conn.execute("SELECT name FROM categories WHERE id = ?", (picked,)).fetchone()
                        suggested = {"id": picked, "name": row[0] if row else None}
                conn.commit()
                invalidate_vector_cache()
            except IngestCancelled:
                # Discard whatever partial document/chunk rows this
                # transaction inserted — a half-written document would
                # otherwise show up in the list with a wrong chunk count
                # and gaps in retrieval.
                conn.rollback()
                ingest_progress["cancelled"] = True
                return {"cancelled": True, "filename": filename}
            finally:
                conn.close()
    except Exception as e:
        ingest_progress["error"] = str(e) if isinstance(e, (ValueError, RuntimeError)) else "Something went wrong while reading the PDF."
        raise
    finally:
        ingest_progress["active"] = False
        _cancel_event.clear()

    return {"id": doc_id, "filename": filename, "num_chunks": len(chunks),
            "category": suggested}


def ingest_text_snippet(text: str, filename: str, conversation_id: str) -> dict:
    """Chunks and embeds raw text pasted or dropped directly into the chat
    bar (e.g. a large error message or log dump), scoped to one
    conversation only. The resulting chunks are searchable while chatting
    in that conversation via retrieve_with_routing's conversation_id filter,
    but never appear in the Documents sidebar (list_documents excludes
    them) and are removed by delete_documents_for_conversation when the
    conversation itself is deleted.

    Deliberately simpler than ingest_document: text extraction (if any —
    see /api/documents/upload-scoped in server.py, which extracts a
    dropped PDF/Word/Excel/PowerPoint file before calling this) already
    happened by the time this runs, so there's no category auto-filing (a
    session-scoped snippet isn't part of the filed library, so there's
    nothing to file it into), and no progress-polling/cancellation
    machinery — a pasted snippet or single file is small enough next to a
    multi-page PDF scan that this runs synchronously within the request
    instead.

    The dedup hash is namespaced with conversation_id (unlike
    ingest_document's, which hashes raw file bytes alone) specifically so
    the same text pasted
    into two different conversations doesn't collide against the single
    global content_hash unique index — each conversation's copy needs to be
    able to exist independently."""
    content_hash = hashlib.sha256(f"{conversation_id}:{text}".encode("utf-8")).hexdigest()
    with _db_lock:
        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT id FROM documents WHERE content_hash = ? AND conversation_id = ?",
                (content_hash, conversation_id),
            ).fetchone()
            if existing:
                return {"duplicate": True, "id": existing[0], "filename": filename}

            # Same broken-embedded-font failure mode ingest_document guards
            # against — a PDF/Word/Excel/PowerPoint file dropped onto the
            # chat bar goes through the same extract_document_text() before
            # reaching this function (see /api/documents/upload-scoped in
            # server.py), so it's just as able to produce raw glyph-code
            # garbage instead of real text. Plain pasted text essentially
            # never trips this.
            if _control_char_ratio(text) > GARBAGE_TEXT_RATIO:
                raise ValueError(
                    "This file's text came out unreadable rather than as "
                    "real text — likely a broken or non-standard font "
                    "embedded in the PDF. Try a different copy of this "
                    "file if one's available."
                )

            chunks = _chunk_text(text)
            if not chunks:
                raise ValueError("There's no readable text in that.")

            doc_id = uuid.uuid4().hex[:12]
            import datetime
            conn.execute(
                "INSERT INTO documents (id, filename, added_at, num_chunks, content_hash, conversation_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, filename, datetime.datetime.now().isoformat(), len(chunks), content_hash, conversation_id),
            )
            for chunk in chunks:
                vector = _embed(chunk, task="search_document")
                conn.execute(
                    "INSERT INTO chunks (id, doc_id, text, vector) VALUES (?, ?, ?, ?)",
                    (uuid.uuid4().hex[:12], doc_id, chunk, json.dumps(vector)),
                )
            conn.commit()
            invalidate_vector_cache()
        finally:
            conn.close()

    return {"id": doc_id, "filename": filename, "num_chunks": len(chunks)}


def delete_documents_for_conversation(conversation_id: str) -> None:
    """Cleans up every chat-bar text snippet tied to one conversation —
    called when that conversation itself is deleted, so scoped chunks don't
    outlive the conversation they can only ever be searched from."""
    with _db_lock:
        try:
            conn = _connect()
        except RuntimeError:
            return  # locked — nothing safe to do; these rows just sit unused until unlock
        try:
            doc_ids = [r[0] for r in conn.execute(
                "SELECT id FROM documents WHERE conversation_id = ?", (conversation_id,)
            ).fetchall()]
            for doc_id in doc_ids:
                conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE conversation_id = ?", (conversation_id,))
            conn.commit()
            if doc_ids:
                invalidate_vector_cache()
        finally:
            conn.close()


def list_documents() -> list[dict]:
    with _db_lock:
        try:
            conn = _connect()
        except RuntimeError:
            return []  # locked — caller checks /api/security/status separately for a lock screen
        rows = conn.execute(
            "SELECT id, filename, added_at, num_chunks, category_id FROM documents "
            "WHERE conversation_id IS NULL ORDER BY added_at DESC"
        ).fetchall()
        conn.close()
    return [{"id": r[0], "filename": r[1], "added_at": r[2], "num_chunks": r[3],
             "category_id": r[4]} for r in rows]


def delete_document(doc_id: str) -> None:
    with _db_lock:
        conn = _connect()
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        conn.commit()
        conn.close()
    invalidate_vector_cache()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
def _clean_name(name: str) -> str:
    """Validates and normalizes a category name.

    Collapsing internal whitespace isn't cosmetic: the name travels to the
    browser inside a server-sent-events frame, where a bare newline would
    terminate the event early and truncate the message. It also stops
    "Tax  Returns" and "Tax Returns" from reading as two different
    categories in a list."""
    name = " ".join((name or "").split())
    if not name:
        raise ValueError("A category needs a name.")
    if len(name) > 40:
        raise ValueError("That name is too long — keep it under 40 characters.")
    return name


def list_categories() -> list[dict]:
    with _db_lock:
        try:
            conn = _connect()
        except RuntimeError:
            return []  # locked
        rows = conn.execute(
            """SELECT c.id, c.name, COUNT(d.id)
               FROM categories c LEFT JOIN documents d ON d.category_id = c.id
               GROUP BY c.id, c.name ORDER BY c.sort_order, c.name COLLATE NOCASE"""
        ).fetchall()
        conn.close()
    return [{"id": r[0], "name": r[1], "count": r[2]} for r in rows]


def create_category(name: str) -> dict:
    name = _clean_name(name)
    import datetime
    cat_id = uuid.uuid4().hex[:12]
    with _db_lock:
        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT id FROM categories WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            if existing:
                raise ValueError(f"You already have a category called “{name}”.")
            next_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories").fetchone()[0]
            conn.execute(
                "INSERT INTO categories (id, name, created_at, sort_order) VALUES (?, ?, ?, ?)",
                (cat_id, name, datetime.datetime.now().isoformat(), next_order),
            )
            conn.commit()
        finally:
            conn.close()
    return {"id": cat_id, "name": name, "count": 0}


def rename_category(cat_id: str, name: str) -> dict:
    name = _clean_name(name)
    with _db_lock:
        conn = _connect()
        try:
            if not conn.execute("SELECT id FROM categories WHERE id = ?", (cat_id,)).fetchone():
                raise ValueError("That category no longer exists.")
            clash = conn.execute(
                "SELECT id FROM categories WHERE name = ? COLLATE NOCASE AND id != ?", (name, cat_id)
            ).fetchone()
            if clash:
                raise ValueError(f"You already have a category called “{name}”.")
            # The cached name vector describes the OLD name, so it has to go —
            # otherwise a category renamed from "Medical" to "Recipes" would
            # keep attracting medical questions.
            conn.execute("UPDATE categories SET name = ?, name_vector = NULL WHERE id = ?", (name, cat_id))
            conn.commit()
        finally:
            conn.close()
    return {"id": cat_id, "name": name}


def delete_category(cat_id: str) -> None:
    """Deletes a category and returns its documents to Uncategorized. The
    documents themselves are never touched — deleting a folder shouldn't be a
    way to accidentally delete files."""
    with _db_lock:
        conn = _connect()
        try:
            conn.execute("UPDATE documents SET category_id = NULL WHERE category_id = ?", (cat_id,))
            conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
            conn.commit()
        finally:
            conn.close()


def set_document_category(doc_id: str, cat_id: str | None) -> None:
    with _db_lock:
        conn = _connect()
        try:
            if not conn.execute("SELECT id FROM documents WHERE id = ?", (doc_id,)).fetchone():
                raise ValueError("That document no longer exists.")
            if cat_id and not conn.execute("SELECT id FROM categories WHERE id = ?", (cat_id,)).fetchone():
                raise ValueError("That category no longer exists.")
            conn.execute("UPDATE documents SET category_id = ? WHERE id = ?", (cat_id or None, doc_id))
            conn.commit()
        finally:
            conn.close()


def _category_vectors(conn, want_dim: int | None = None) -> dict[str, list[float]]:
    """Returns a representative vector per category, for matching against.

    Two sources, in order of preference:
      1. The mean centroid of the documents already filed in it. This is the
         better signal — it describes what the category actually contains
         rather than what it's called.
      2. Failing that (an empty category), an embedding of the category name.
         This is what lets a brand-new or seeded category attract its first
         document instead of sitting empty forever waiting for a member it
         can't get. Cached in the DB since it only changes on rename.

    want_dim drops any vector whose dimension doesn't match the current
    embedding model — the same stale-model guard used in retrieve().
    """
    result: dict[str, list[float]] = {}
    rows = conn.execute("SELECT id, name, name_vector FROM categories").fetchall()
    for cat_id, name, cached_name_vec in rows:
        members = conn.execute(
            "SELECT centroid FROM documents WHERE category_id = ? AND centroid IS NOT NULL", (cat_id,)
        ).fetchall()
        centroid = _mean_vector([v for v in (_load_vector(m[0]) for m in members) if v])
        if centroid and (want_dim is None or len(centroid) == want_dim):
            result[cat_id] = centroid
            continue

        vec = _load_vector(cached_name_vec)
        if vec and want_dim is not None and len(vec) != want_dim:
            vec = None  # cached under a different embedding model — recompute
        if not vec:
            try:
                # Embedding a bare label like "Legal" against 180-word document
                # chunks is a lopsided comparison; the surrounding phrasing
                # gives the vector something closer to document-shaped context.
                vec = _embed(f"Documents about {name}", task="search_document")
            except Exception:
                continue  # embedder unavailable — skip this category, don't fail the query
            conn.execute("UPDATE categories SET name_vector = ? WHERE id = ?", (json.dumps(vec), cat_id))
            conn.commit()
        if vec and (want_dim is None or len(vec) == want_dim):
            result[cat_id] = vec
    return result


def _pick_category(query_vec: np.ndarray, cat_vecs: dict[str, list[float]],
                   min_similarity: float, min_margin: float) -> tuple[str | None, float]:
    """Picks the single best-matching category, or nothing.

    Requires both an absolute floor and a clear margin over the runner-up.
    The margin is the important half: if a question matches "Finance" and
    "Work" almost equally, picking either one is a coin flip, and a coin flip
    is exactly the case where steering the search does more harm than leaving
    it alone."""
    if not cat_vecs:
        return None, 0.0
    ids = list(cat_vecs.keys())
    matrix = np.array([cat_vecs[i] for i in ids], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1.0
    q_norm = float(np.linalg.norm(query_vec)) or 1.0
    scores = (matrix @ query_vec) / (norms * q_norm)

    order = np.argsort(scores)[::-1]
    best = float(scores[order[0]])
    runner_up = float(scores[order[1]]) if len(order) > 1 else -1.0
    if best < min_similarity or (best - runner_up) < min_margin:
        return None, best
    return ids[order[0]], best


def _category_payload(cat_id, name, auto):
    return {"id": cat_id, "name": name, "auto": auto} if cat_id else None


def retrieve(query: str, top_k: int = 4, min_similarity: float = 0.3) -> list[dict]:
    """Return the best-matching chunks for a query, across all documents.

    Computes cosine similarity as one batched matrix multiply against every
    stored vector rather than looping row-by-row in Python — the same
    scaling behavior a proper vector index gives you, without adding a new
    dependency. This comfortably handles tens of thousands of chunks; if a
    library's document collection ever grows past that, an ANN index like
    FAISS becomes worth the added complexity, but it isn't needed yet."""
    return retrieve_with_routing(query, top_k, min_similarity)["hits"]


def retrieve_with_routing(query: str, top_k: int = 4, min_similarity: float = 0.3,
                          category_id: str | None = None,
                          auto_route: bool = True,
                          boost_category_ids: list[str] | None = None,
                          conversation_id: str | None = None) -> dict:
    """retrieve(), plus optional category scoping. Returns
    {"hits": [...], "category": {"id", "name", "auto"} | None,
     "priority": {"ids": [...], "names": [...]} | None}.

    conversation_id additionally scopes which rows are even eligible: every
    real (filed) document has conversation_id NULL and is always eligible;
    a chat-bar text snippet has it set and is eligible only while chatting
    in that same conversation. This runs before any of the category
    scoping below, as a straight SQL filter on the candidate row set.

    Three scoping behaviors, in priority order:

    - An explicit category_id is a HARD filter. The user asked for one
      folder; give them that folder. boost_category_ids and auto_route are
      both ignored when this is set — there's nothing left to boost against
      once the row set is already narrowed to one category.

    - boost_category_ids (a custom agent's fixed, user-chosen set) is a SOFT
      boost applied to every chunk in ANY of those categories, and — same
      reasoning as auto-routing below — it REPLACES auto-detection rather
      than layering on top of it. The agent's own choice is more specific
      than a per-question guess, and running both would mean a single
      question's routing behavior depends on which of two different signals
      happened to win, which is exactly the kind of thing that's hard to
      explain when it goes wrong. If none of the given ids resolve to a
      category that still exists (e.g. deleted since the agent was made),
      this falls through to a plain unboosted search — not to auto-routing —
      since the agent's specific intent (use MY categories) shouldn't
      silently get replaced by a per-question guess it never asked for.

    - Automatic routing (no explicit scope, no agent boost) is the original
      per-question soft boost — see the note below.

    A soft boost, wherever it comes from, works the same way: matching
    chunks get CATEGORY_BOOST added to their score, and everything else
    stays in the running. This is the whole safety argument for boosting
    instead of filtering: when the boost target is wrong, a hard filter
    would silently remove the one chunk that actually answers the question,
    and the model would confidently answer from the wrong folder with no
    sign anything went wrong. A boost degrades instead — a strongly-matching
    chunk elsewhere still wins on merit, and the worst case is a mild
    reordering rather than a confidently wrong answer.

    Note that min_similarity is applied to the RAW similarity, before any
    boost. A boost is allowed to reorder results; it isn't allowed to drag a
    chunk over the relevance floor that wouldn't have cleared it on its own.
    """
    with _db_lock:
        conn = _connect()
        try:
            routed_id, routed_name, routed_auto = None, None, False
            priority_ids, priority_names = [], []

            # Resolved before the empty-result check on purpose: if the user
            # scoped to a category that happens to hold nothing, the UI still
            # needs to be able to say "no matches in Legal" rather than
            # silently showing an unscoped-looking empty answer.
            if category_id:
                row = conn.execute("SELECT name FROM categories WHERE id = ?", (category_id,)).fetchone()
                if row:
                    routed_id, routed_name = category_id, row[0]

            # Per-document metadata (filename/category/conversation scoping)
            # is small — one row per document, not per chunk — so it's read
            # fresh here every call rather than cached alongside the chunk
            # vectors below. That's what lets a category reassignment,
            # rename, or category deletion show up immediately without ever
            # needing to invalidate the much larger chunk-vector cache.
            doc_meta = {
                r[0]: (r[1], r[2], r[3])
                for r in conn.execute(
                    "SELECT id, filename, category_id, conversation_id FROM documents"
                ).fetchall()
            }

            if not doc_meta:
                # Nothing uploaded at all — skip the chunk fetch and the
                # embedding call below entirely rather than searching an
                # empty table.
                priority_payload = {"ids": priority_ids, "names": priority_names} if priority_ids else None
                return {"hits": [], "category": _category_payload(routed_id, routed_name, routed_auto),
                        "priority": priority_payload}

            # Which categories currently have at least one document — computed
            # once and used to gate BOTH routing paths below. _category_vectors
            # deliberately gives an empty category a usable vector too (via a
            # name-probe embedding), because that's what lets a brand-new
            # category attract its first document during ingest-time
            # suggestion. But that same fallback would let query-time routing
            # or an agent's boost list "match" a category that can't actually
            # contain the answer to anything — reporting "Searched: Legal" or
            # "Prioritized: Legal" when Legal has zero documents describes a
            # decision that had no possible effect on the retrieval, which is
            # worse than not reporting anything.
            nonempty_cat_ids = {
                cat_id for _filename, cat_id, _conv_id in doc_meta.values() if cat_id is not None
            }

            # boost_category_ids validated here, against the same connection,
            # rather than trusted as-is: an agent's stored list can reference
            # a category that was renamed (fine, we just re-read the current
            # name) or deleted (not fine — that id has to be dropped, or a
            # stale UUID would silently boost nothing while claiming to).
            # Resolved before the rows-empty check for the same reason
            # category_id's name is resolved early above.
            if not category_id and boost_category_ids:
                placeholders = ",".join("?" * len(boost_category_ids))
                found = conn.execute(
                    f"SELECT id, name FROM categories WHERE id IN ({placeholders})",
                    list(boost_category_ids),
                ).fetchall()
                # Preserve the agent's own ordering rather than the SQL
                # result's, so the UI note lists them the way the person
                # arranged them, not however SQLite happened to return rows.
                found_map = {r[0]: r[1] for r in found}
                for cid in boost_category_ids:
                    if cid in found_map and cid in nonempty_cat_ids:
                        priority_ids.append(cid)
                        priority_names.append(found_map[cid])

            # The expensive part: every chunk's text + embedding vector. Only
            # the SQL fetch (when the cache needs rebuilding at all) happens
            # here, while the lock is held — the slow parsing runs after
            # it's released, below. See _finish_vector_cache's docstring for
            # why that split matters.
            raw_chunk_rows = _fetch_chunk_rows_if_needed(conn)

            # Computed once here, inside the lock (only when there's actually
            # something to search — embedding costs nothing to skip on an
            # empty library, already ruled out by the doc_meta check above),
            # and reused below both for the auto-route decision and for
            # final scoring against the row set.
            q_vec = np.array(_embed(query, task="search_query"), dtype=np.float32)

            if not category_id and not boost_category_ids and auto_route:
                cat_vecs = _category_vectors(conn, want_dim=len(q_vec))
                picked, _score = _pick_category(q_vec, cat_vecs, ROUTE_MIN_SIMILARITY, ROUTE_MIN_MARGIN)
                if picked and picked in nonempty_cat_ids:
                    row = conn.execute("SELECT name FROM categories WHERE id = ?", (picked,)).fetchone()
                    routed_id, routed_name, routed_auto = picked, (row[0] if row else None), True
        finally:
            conn.close()

    # Parsing ~200K JSON vectors into a matrix runs here, deliberately
    # outside the lock just released above — see _finish_vector_cache.
    texts_all, doc_ids_all, matrix_all = _finish_vector_cache(raw_chunk_rows)

    # conversation_id eligibility (a real filed document is always eligible;
    # a chat-bar snippet only while chatting in the same conversation) and an
    # explicit category_id hard filter both apply here, against the small
    # per-document metadata captured above — equivalent to the SQL WHERE
    # clause this replaced, just run in Python against the cached chunk list
    # instead of re-fetched from SQLite on every call.
    keep_idx = [
        i for i, doc_id in enumerate(doc_ids_all)
        if doc_id in doc_meta
        and (doc_meta[doc_id][2] is None or doc_meta[doc_id][2] == conversation_id)
        and (not category_id or doc_meta[doc_id][1] == category_id)
    ]

    priority_payload = {"ids": priority_ids, "names": priority_names} if priority_ids else None

    if not keep_idx:
        return {"hits": [], "category": _category_payload(routed_id, routed_name, routed_auto),
                "priority": priority_payload}

    texts = [texts_all[i] for i in keep_idx]
    filenames = [doc_meta[doc_ids_all[i]][0] for i in keep_idx]
    cat_ids = [doc_meta[doc_ids_all[i]][1] for i in keep_idx]
    matrix = matrix_all[keep_idx]  # (N, D)

    # One unified boost set regardless of source: an agent's priority list
    # (several categories) or auto-routing's own guess (exactly one). Scoring
    # below doesn't need to know which produced it.
    boost_set = set(priority_ids) if priority_ids else ({routed_id} if routed_auto and routed_id else set())

    q_norm = np.linalg.norm(q_vec) or 1.0

    doc_norms = np.linalg.norm(matrix, axis=1)
    doc_norms[doc_norms == 0] = 1.0

    sims = (matrix @ q_vec) / (doc_norms * q_norm)

    # A boost applies only when boost_set is non-empty — from either an
    # agent's priority categories or auto-routing's single guess, never both
    # at once (see the docstring). An explicit category_id already filtered
    # the rows above, so there'd be nothing left to boost against in that
    # case — every surviving chunk is already in that one category.
    if boost_set:
        boost = np.array([CATEGORY_BOOST if c in boost_set else 0.0 for c in cat_ids], dtype=np.float32)
        ranking = sims + boost
    else:
        ranking = sims

    # Apply the relevance floor first, then rank what's left. Doing it in this
    # order matters: once scores are boosted, the ranking is no longer sorted
    # by raw similarity, so the old "break on the first below-floor result"
    # shortcut would be wrong — an unboosted chunk can sort behind a boosted
    # one that scored lower on its own merits. Masking with numpy keeps the
    # early exit's efficiency without depending on that assumption.
    eligible = np.nonzero(sims >= min_similarity)[0]
    if eligible.size == 0:
        return {"hits": [], "category": _category_payload(routed_id, routed_name, routed_auto),
                "priority": priority_payload}
    order = eligible[np.argsort(ranking[eligible])[::-1]]

    results = []
    for i in order:
        sim = float(sims[i])
        results.append({
            "text": texts[i],
            "filename": filenames[i],
            "similarity": sim,
            "boosted": cat_ids[i] in boost_set,
        })
        if len(results) >= top_k:
            break

    return {"hits": results, "category": _category_payload(routed_id, routed_name, routed_auto),
            "priority": priority_payload}

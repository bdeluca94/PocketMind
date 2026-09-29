"""
Keeps a chat request inside the model's context window.

Especially relevant now that PDFs can be large: a handful of retrieved
excerpts plus a long-running conversation can add up to more tokens than
the model can accept in one call. Rather than let that error out or get
silently cut off mid-response, this trims — oldest conversation history
first, then lowest-relevance document excerpts — so every request that
goes to the model is guaranteed to fit.
"""

from __future__ import annotations

RESPONSE_RESERVE = 1024   # tokens left free for the model's reply
SAFETY_MARGIN = 64        # extra headroom for role/formatting overhead
MIN_BUDGET = 256          # never trim below this, even on tiny context sizes
DOC_CONTEXT_SHARE = 0.35  # document excerpts get at most this fraction of the budget
MEMORY_CONTEXT_SHARE = 0.15  # remembered facts get at most this fraction of the budget
PER_MESSAGE_OVERHEAD = 4  # rough token cost of role/formatting wrapper per message

MERMAID_CAPABILITY_NOTE = (
    "You can draw diagrams — flowcharts, sequence diagrams, simple charts — "
    "by writing Mermaid syntax inside a ```mermaid code fence. It renders as "
    "an actual diagram, not as visible code. Use this when asked to "
    "visualize a process, flow, or relationship, or when a diagram would "
    "genuinely make an answer clearer."
)


def count_tokens(llm, text: str) -> int:
    """Exact token count using the loaded model's own tokenizer, with a
    rough character-based fallback if that ever fails for some reason
    (e.g. an unusual llama-cpp-python version) — never raises."""
    try:
        return len(llm.tokenize(text.encode("utf-8", errors="ignore"), add_bos=False, special=False))
    except Exception:
        return max(len(text) // 3, 1)


def _context_budget(llm) -> int:
    try:
        ctx_size = llm.n_ctx()
    except Exception:
        ctx_size = 4096
    return max(ctx_size - RESPONSE_RESERVE - SAFETY_MARGIN, MIN_BUDGET)


def truncate_for_summary(llm, text: str) -> str:
    """Keeps `text` within the model's context budget, dropping from the
    front if it doesn't fit — used when compacting a conversation that's
    itself grown too long to summarize in one call. Keeps the tail rather
    than the head, same "most recent survives" rule fit_to_context uses for
    ordinary history trimming: the newest part of a conversation is more
    useful to a summary than the oldest."""
    budget = _context_budget(llm)
    if count_tokens(llm, text) <= budget:
        return text
    # A rough character-based cut, not an exact token boundary — good
    # enough for something about to be fed to a summarizer, not something
    # a person reads verbatim.
    approx_chars = budget * 3
    return "…" + text[-approx_chars:]


def fit_to_context(
    llm,
    persona_message: dict,
    doc_hits: list[dict],
    history: list[dict],
    memory_entries: list[dict] | None = None,
) -> list[dict]:
    """Builds the final message list to send to the model, guaranteed to
    fit inside its context window.

    - persona_message and any document context are combined into ONE
      leading system message, not two separate ones. Two consecutive
      system-role messages is a non-standard structure — most chat
      templates (the ones baked into a GGUF model, applied by
      create_chat_completion) are built around exactly one system message
      followed by strictly alternating user/assistant turns, and simpler
      templates in particular can silently drop, misplace, or garble a
      second one. A small/weak model insisting it "can't access documents"
      even when the excerpts were genuinely retrieved and included is the
      visible symptom of exactly this — the content was in the request,
      but not somewhere the model's own template reliably surfaces to it.
    - doc_hits (already sorted best-match first by rag.retrieve) are
      included greedily up to a capped share of the budget, so a few
      large PDF excerpts can't crowd out the actual conversation.
    - memory_entries (see memory.py) are durable facts the user has asked
      to be remembered across conversations — small and few enough in
      practice that, unlike doc_hits, there's no retrieval/ranking step:
      every entry is included up to its own share of the budget, oldest
      dropped first if it ever somehow doesn't fit.
    - history is kept from most-recent backwards; older messages are
      dropped first. The single most recent message is always kept even
      if it has to be truncated to fit alone, so the current question
      never silently vanishes.
    """
    budget = _context_budget(llm)

    system_parts = [persona_message["content"], MERMAID_CAPABILITY_NOTE]
    budget -= count_tokens(llm, persona_message["content"]) + count_tokens(llm, MERMAID_CAPABILITY_NOTE)
    budget -= 2 * PER_MESSAGE_OVERHEAD

    if memory_entries:
        mem_budget = max(int(budget * MEMORY_CONTEXT_SHARE), 0)
        included, used = [], 0
        # Oldest dropped first, so a fact remembered a long time ago is the
        # one that goes missing if the list ever somehow outgrows its
        # share — a newer entry is more likely to be why the user is
        # asking right now.
        for entry in reversed(memory_entries):
            t = count_tokens(llm, entry["text"]) + 10
            if used + t > mem_budget:
                continue
            included.append(entry)
            used += t
        if included:
            included.reverse()
            memory_block = (
                "The user has asked you to remember the following facts "
                "about them across conversations. Treat them as already-"
                "known context, the same way you would something they just "
                "told you this conversation:\n\n" +
                "\n".join(f"- {e['text']}" for e in included)
            )
            system_parts.append(memory_block)
            budget -= count_tokens(llm, memory_block) + PER_MESSAGE_OVERHEAD

    if doc_hits:
        doc_budget = max(int(budget * DOC_CONTEXT_SHARE), 0)
        included, used = [], 0
        for h in doc_hits:
            t = count_tokens(llm, h["text"]) + 10
            if used + t > doc_budget:
                continue  # this one doesn't fit — keep checking the rest, they're smaller/less relevant anyway
            included.append(h)
            used += t
        if included:
            context = "\n\n".join(f"[From {h['filename']}]: {h['text']}" for h in included)
            # Framed as information the model already has, not something it
            # needs to go fetch — the phrasing matters for smaller models in
            # particular, which are more prone to falling back on a rote "I
            # can't access files" disclaimer if the framing leaves any doubt
            # about whether the content below is genuinely already at hand.
            #
            # The first version of this framing (a single paragraph before
            # the excerpts, no explicit mention of the disclaimer itself)
            # wasn't enough on its own: confirmed directly against the
            # Fast & Light (1.5B) model that it would open a reply with "I
            # don't have direct access to the PDF you uploaded" and THEN
            # correctly quote the excerpt anyway — the content was used
            # right, but the reflexive disclaimer in front of it read as a
            # flat "no" to anyone not reading the rest of the sentence. Two
            # changes fixed that in testing: naming the exact disclaimer and
            # forbidding it outright (small models pattern-match on the
            # surface phrasing of "I can't access files" more than they
            # reason about whether it's true), and repeating a short
            # reminder AFTER the excerpts too, closer to where generation
            # actually starts — a small model weights instructions near the
            # end of its context more heavily than ones several paragraphs
            # earlier.
            doc_block = (
                "The following are excerpts from documents the user has "
                "already uploaded. They are included in full below — this "
                "is information you already have, not something external "
                "you'd need to fetch. Do not say you don't have access to "
                "the file, can't open it, or can't read it: that is false "
                "whenever this section is present, since the real text is "
                "right here. Answer using it the same way you would your "
                "own knowledge. If part of it doesn't apply to the current "
                "question, simply don't use that part.\n\n" + context +
                "\n\nReminder: the text above is the actual content of the "
                "document(s) named in brackets, already provided to you. "
                "Answer directly from it — don't claim you can't access, "
                "open, or read the file."
            )
            system_parts.append(doc_block)
            budget -= count_tokens(llm, doc_block) + PER_MESSAGE_OVERHEAD

    final = [{"role": "system", "content": "\n\n".join(system_parts)}]

    kept = []
    running = 0
    for m in reversed(history):
        t = count_tokens(llm, m.get("content", "")) + PER_MESSAGE_OVERHEAD
        if running + t > budget:
            if not kept:
                # Nothing fits yet and this is the most recent message —
                # truncate rather than drop it entirely.
                approx_chars = max(budget * 3, 200)
                content = m.get("content", "")
                trimmed = content[:approx_chars]
                if len(trimmed) < len(content):
                    trimmed += "…"
                kept.append({**m, "content": trimmed})
            break
        kept.append(m)
        running += t
    kept.reverse()

    final += kept
    return final

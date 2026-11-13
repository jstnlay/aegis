"""
Retrieval over the school's own documents.

What this is for
----------------
The assistant could look up a student's grade and read a learning resource's
title, but it had nothing to say about the school itself: a rule, a
schedule, a policy, a procedure. Asked any of those it fell back to a
generic line, and — worse — when a model *was* available it would answer
from its own general knowledge of how schools usually work, which is not
this school's policy. A confident answer about a school the model has never
seen is the accuracy failure the client reported.

Retrieval is the fix: the assistant answers from quoted passages of the
school's published documents, cites which document each answer came from,
and says it does not know when nothing in the corpus covers the question.
The last part is the point. A retrieval system that always returns
*something* is a hallucination with extra steps.

Why the scoring is hand-written
-------------------------------
The obvious choices were a vector index (pgvector plus an embedding model)
or PostgreSQL full-text search. Both were rejected for a specific reason:

- PostgreSQL full-text search is Postgres-only, and this project's test
  suite runs on SQLite (`config/settings/test.py`), so the code path that
  decides what a student is told would be the one path the suite cannot
  exercise.
- pgvector needs an extension installed on the database and an embedding
  model, and the school's current API key has an exhausted quota. A
  feature that silently degrades to "no retrieval" when a third-party quota
  runs out is not a safety improvement.

So the scorer is ~40 lines of lexical overlap: every query term is looked
up with `icontains`, which is portable, and then ranked in Python by term
frequency, an inverse-document-frequency weight from the candidate pool,
and bonuses for a title hit and for the query appearing as a phrase. It
handles no synonyms and no paraphrase. That is a real limitation, stated
in the code rather than hidden, and it is the correct trade at this corpus
size: the school has tens of documents, not millions.

`shortcut: lexical-only retrieval, no synonyms or embeddings. Upgrade to a
vector index when the corpus outgrows a few thousand chunks, or when a
question that means the same thing as a document's words becomes common.`
"""

from __future__ import annotations

import math
import re

from django.db.models import Q

from apps.chatbot.models import KnowledgeChunk, KnowledgeDocument

# Words that carry no retrieval signal. Kept small and English: the corpus is
# English school documents, and a longer list is more to maintain than it is
# worth at this size.
STOPWORDS = frozenset(
    """
    a about above after again all am an and any are as at be because been
    before being below between both but by can cannot could did do does doing
    down during each few for from further had has have having he her here hers
    him his how i if in into is it its itself just me more most my no nor not
    now of off on once only or other our out over own same she should so some
    such than that the their them then there these they this those through to
    too under until up very was we were what when where which while who whom
    why will with would you your yours
    """.split()
)

MIN_TERM_LENGTH = 3
MAX_QUERY_TERMS = 12
CHUNK_CHARS = 1200
MAX_CHUNKS_PER_DOCUMENT = 400
# How many rows the SQL pre-filter may hand to the Python scorer. Bounded so a
# two-word query against a large corpus cannot pull the whole table into memory.
CANDIDATE_POOL = 400
EXCERPT_CHARS = 240

# A term in the document's title is a stronger signal than the same term
# buried in a paragraph, and a phrase hit is stronger than scattered words.
TITLE_BONUS = 1.5
LABEL_BONUS = 0.75
PHRASE_MULTIPLIER = 2.0


def _normalize(word: str) -> str:
    """
    Fold a plural onto its singular.

    "grades" has to match a document that says "grade". This is not stemming
    and does not pretend to be: it strips one trailing "s" from a word long
    enough for that to be safe, and leaves everything else alone.
    """
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> list[str]:
    """Every content token of `text`, repeats kept (term frequency needs them)."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [
        _normalize(word)
        for word in words
        if len(word) >= MIN_TERM_LENGTH and word not in STOPWORDS
    ]


def query_terms(query: str) -> list[str]:
    """The ordered, de-duplicated terms a query is scored on."""
    terms: list[str] = []
    for term in _tokens(query):
        if term not in terms:
            terms.append(term)
        if len(terms) >= MAX_QUERY_TERMS:
            break
    return terms


def chunk_text(
    body: str,
    *,
    max_chars: int = CHUNK_CHARS,
    max_chunks: int = MAX_CHUNKS_PER_DOCUMENT,
) -> list[str]:
    """
    Split a document body into passages.

    Blank lines separate paragraphs and are the preferred boundary. A single
    paragraph longer than `max_chars` is split on sentence ends instead — a
    chunk cut mid-sentence reads as a misquote when it is shown to a student.
    """
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    chunks: list[str] = []
    current = ""
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if len(block) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_block(block, max_chars))
            continue
        if not current:
            current = block
        elif len(current) + len(block) + 2 <= max_chars:
            current = f"{current}\n\n{block}"
        else:
            chunks.append(current)
            current = block
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()][:max_chunks]


def _split_long_block(block: str, max_chars: int) -> list[str]:
    """Pack a long paragraph into sentence-aligned pieces."""
    sentences = [s.strip() for s in re.findall(r"[^.!?]+[.!?]*", block) if s.strip()]
    if not sentences:
        return [block]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
        elif len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}"
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    # A single sentence longer than max_chars is emitted whole. Half a rule is
    # worse than a long passage.
    return pieces


def excerpt(content: str, terms: list[str], *, width: int = EXCERPT_CHARS) -> str:
    """
    A readable window around the query terms, for citation in the reply.

    Snap to word boundaries and keep the ellipsis honest: it is only added
    when text was actually cut.
    """
    text = " ".join((content or "").split())
    if len(text) <= width:
        return text

    lowered = text.lower()
    positions = [lowered.find(term) for term in terms]
    positions = [position for position in positions if position >= 0]
    if positions:
        start = max(0, min(positions) - width // 3)
    else:
        start = 0
    end = min(len(text), start + width)

    if start > 0:
        space = text.find(" ", start)
        if 0 <= space < start + 20:
            start = space + 1
    if end < len(text):
        space = text.rfind(" ", start, end)
        if space > start:
            end = space

    piece = text[start:end].strip()
    return (
        ("…" if start > 0 else "")
        + piece
        + ("…" if end < len(text) else "")
    )


def index_document(document: KnowledgeDocument, body: str | None = None) -> int:
    """
    Replace a document's passages with the chunks of `body`.

    `body` is the document's text. It is a required argument rather than a
    field on the row because the text is stored as chunks, not on the
    document. Re-indexing deletes the old chunks: a document whose passages
    were edited must not be retrievable in two versions at once.
    """
    text = body or ""
    pieces = chunk_text(text)
    document.chunks.all().delete()
    KnowledgeChunk.objects.bulk_create(
        [
            KnowledgeChunk(document=document, ordinal=index, content=piece)
            for index, piece in enumerate(pieces, start=1)
        ]
    )
    return len(pieces)


def retrieve(query: str, *, limit: int = 3, category: str | None = None) -> list[dict]:
    """
    The best passages for `query`, best first.

    Returns an empty list when nothing matches. Callers must treat that as a
    real answer — "I don't have that" — and not substitute a guess.
    """
    terms = query_terms(query)
    if not terms:
        return []

    condition = Q()
    for term in terms:
        # The title is searched too. A school document titled "Uniform Policy"
        # is about uniforms even when that exact word never appears in its body,
        # and a title match is the strongest signal there is.
        condition |= Q(content__icontains=term) | Q(document__title__icontains=term)

    rows = KnowledgeChunk.objects.filter(
        document__is_active=True,
        **({} if category is None else {"document__category": category}),
    )
    rows = rows.filter(condition).select_related("document")[:CANDIDATE_POOL]
    candidates = list(rows)
    if not candidates:
        return []

    # Document frequency, measured over the candidate pool rather than the
    # whole corpus. It is an approximation, but it is deterministic and it
    # costs one pass over rows the query already selected.
    lowered_contents = [row.content.lower() for row in candidates]
    frequency = {
        term: sum(1 for text in lowered_contents if term in text) for term in terms
    }

    phrase = " ".join(query.lower().split())
    scored: list[tuple[float, KnowledgeChunk]] = []
    for row, lowered in zip(candidates, lowered_contents):
        title = (row.document.title or "").lower()
        label = (row.document.source_label or "").lower()
        score = 0.0
        hits = 0
        title_hit = False
        for term in terms:
            count = lowered.count(term)
            in_title = term in title
            in_label = term in label
            if not (count or in_title or in_label):
                continue
            hits += 1
            if count:
                # Logarithmic term frequency: the tenth mention is not ten
                # times the signal of the first.
                score += (1.0 + math.log(count)) * (
                    1.0 / math.log(2.0 + frequency.get(term, 0))
                )
            if in_title:
                score += TITLE_BONUS
                title_hit = True
            if in_label:
                score += LABEL_BONUS
                title_hit = True
        if not hits:
            continue
        # A one-word question that matches one word is a real hit. A longer
        # question that touches only one of its words is usually noise, so it
        # needs a second matched term — or a term in the document's own title —
        # before it is allowed to be quoted back as the answer. Without this a
        # question about late enrolment cited the passage about uniforms.
        if hits < min(2, len(terms)) and not title_hit:
            continue
        if phrase and phrase in lowered:
            score *= PHRASE_MULTIPLIER
        scored.append((score, row))

    if not scored:
        return []

    # Ties broken by identity, never by insertion order: the same question
    # must retrieve the same passages twice.
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].document_id), pair[1].ordinal))

    passages = []
    for score, row in scored[:limit]:
        if score <= 0:
            continue
        passages.append(
            {
                "chunk_id": str(row.id),
                "document_id": str(row.document_id),
                "title": row.document.title,
                "category": row.document.category,
                "source_label": row.document.source_label,
                "source_url": row.document.source_url,
                "content": row.content,
                "excerpt": excerpt(row.content, terms),
                "score": round(score, 4),
            }
        )
    return passages

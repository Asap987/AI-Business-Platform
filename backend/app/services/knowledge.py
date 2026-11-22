"""Knowledge base: splitting documents into chunks and finding the chunks that answer a question.

Search is keyword based (no embeddings, so no extra AI provider and no document text sent anywhere
to be indexed). Every query is scoped to one business and to published documents only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import KnowledgeChunk, KnowledgeDocument

CHUNK_TARGET = 700  # characters; paragraphs are kept whole where possible
MAX_TERMS = 8
CANDIDATES = 300
STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i if in is it its me my of on or our so that the their there "
    "this to us was we what when where which who will with you your".split()
)


def chunk_text(content: str) -> list[str]:
    """Split on blank lines, then pack paragraphs into pieces of about CHUNK_TARGET characters."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content.replace("\r\n", "\n")) if p.strip()]
    pieces: list[str] = []
    for para in paragraphs:
        while len(para) > CHUNK_TARGET * 1.5:  # a very long paragraph is cut at a sentence or space
            cut = max(para.rfind(". ", 0, CHUNK_TARGET), para.rfind(" ", 0, CHUNK_TARGET))
            cut = cut + 1 if cut > CHUNK_TARGET // 3 else CHUNK_TARGET
            pieces.append(para[:cut].strip())
            para = para[cut:].strip()
        if para:
            pieces.append(para)
    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + len(piece) + 2 <= CHUNK_TARGET:
            chunks[-1] += "\n\n" + piece
        else:
            chunks.append(piece)
    return chunks


def search_terms(query: str) -> list[str]:
    seen: list[str] = []
    for w in re.findall(r"[\w'-]+", query.lower()):
        w = w.strip("'-")
        if len(w) >= 2 and w not in STOPWORDS and w not in seen:
            seen.append(w)
    return seen[:MAX_TERMS]


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def replace_chunks(db: AsyncSession, doc: KnowledgeDocument) -> None:
    for old in (await db.execute(select(KnowledgeChunk).where(
            KnowledgeChunk.document_id == doc.id, KnowledgeChunk.business_id == doc.business_id))).scalars():
        await db.delete(old)
    await db.flush()
    for i, text in enumerate(chunk_text(doc.content)):
        db.add(KnowledgeChunk(business_id=doc.business_id, document_id=doc.id, position=i, text=text))


@dataclass
class Hit:
    document_id: UUID
    title: str
    category: str | None
    text: str
    score: float


async def search(db: AsyncSession, business_id: UUID, query: str, limit: int = 3) -> list[Hit]:
    terms = search_terms(query)
    if not terms:
        return []
    lowered = func.lower(KnowledgeChunk.text)
    title_l = func.lower(KnowledgeDocument.title)
    match = or_(*[lowered.like(f"%{_escape(t)}%", escape="\\") for t in terms],
                *[title_l.like(f"%{_escape(t)}%", escape="\\") for t in terms])
    rows = (await db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeChunk.business_id == business_id, KnowledgeDocument.business_id == business_id,
               KnowledgeDocument.status == "published", match)
        .limit(CANDIDATES))).all()
    hits: list[Hit] = []
    for chunk, doc in rows:
        body, title = chunk.text.lower(), doc.title.lower()
        present = [t for t in terms if t in body]
        score = len(present) * 2.0 + sum(min(body.count(t), 3) for t in present) * 0.5
        score += sum(1.5 for t in terms if t in title)
        if score > 0:
            hits.append(Hit(doc.id, doc.title, doc.category, chunk.text, score))
    hits.sort(key=lambda h: (-h.score, h.title))
    return hits[:limit]

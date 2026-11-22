"""Knowledge base documents. Everything is scoped to the caller's business."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.customers import like_escape
from app.api.v1.deps import Principal, get_db, require
from app.database.models import KnowledgeChunk, KnowledgeDocument
from app.services import knowledge as kb

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
MAX_CONTENT = 50_000

Status = Literal["published", "archived"]


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class DocIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    category: str | None = Field(default=None, max_length=60)
    content: str = Field(min_length=3, max_length=MAX_CONTENT)
    status: Status = "published"
    _s = field_validator("title", "category", "content", mode="before")(_strip)


class DocPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    category: str | None = Field(default=None, max_length=60)
    content: str | None = Field(default=None, min_length=3, max_length=MAX_CONTENT)
    status: Status | None = None
    _s = field_validator("title", "category", "content", mode="before")(_strip)


def _out(d: KnowledgeDocument, *, full: bool = False, chunks: int | None = None) -> dict:
    out = {"id": str(d.id), "title": d.title, "category": d.category or None, "status": d.status,
           "characters": len(d.content), "created_at": d.created_at.isoformat(), "updated_at": d.updated_at.isoformat()}
    if full:
        out["content"] = d.content
    if chunks is not None:
        out["chunks"] = chunks
    return out


async def _doc(db, p, doc_id) -> KnowledgeDocument:
    d = (await db.execute(select(KnowledgeDocument).where(
        KnowledgeDocument.id == doc_id, KnowledgeDocument.business_id == p.business_id))).scalar_one_or_none()
    if d is None:
        raise HTTPException(404, "Document not found")
    return d


async def _chunk_count(db, d) -> int:
    return (await db.execute(select(func.count()).select_from(KnowledgeChunk).where(
        KnowledgeChunk.document_id == d.id, KnowledgeChunk.business_id == d.business_id))).scalar_one()


@router.post("", status_code=201)
async def create_document(body: DocIn, p: Principal = Depends(require("knowledge:write")), db: AsyncSession = Depends(get_db)):
    d = KnowledgeDocument(business_id=p.business_id, created_by=p.user.id, **body.model_dump())
    d.category = d.category or None
    db.add(d)
    await db.flush()
    await kb.replace_chunks(db, d)
    await db.commit()
    return _out(d, full=True, chunks=await _chunk_count(db, d))


@router.get("")
async def list_documents(q: str | None = Query(None, max_length=100), status: Status | None = None,
                         page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                         p: Principal = Depends(require("knowledge:read")), db: AsyncSession = Depends(get_db)):
    where = [KnowledgeDocument.business_id == p.business_id]
    if status:
        where.append(KnowledgeDocument.status == status)
    if q and q.strip():
        pat = f"%{like_escape(q.strip().lower())}%"
        where.append(or_(func.lower(KnowledgeDocument.title).like(pat, escape="\\"),
                         func.lower(func.coalesce(KnowledgeDocument.category, "")).like(pat, escape="\\")))
    total = (await db.execute(select(func.count()).select_from(KnowledgeDocument).where(*where))).scalar_one()
    rows = (await db.execute(select(KnowledgeDocument).where(*where).order_by(KnowledgeDocument.updated_at.desc())
                             .limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return {"items": [_out(d) for d in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/search")
async def search_documents(q: str = Query(min_length=2, max_length=300), p: Principal = Depends(require("knowledge:read")),
                           db: AsyncSession = Depends(get_db)):
    """Shows what the AI assistant would find for a question, so staff can check their documents."""
    hits = await kb.search(db, p.business_id, q)
    return {"items": [{"document_id": str(h.document_id), "title": h.title, "category": h.category, "text": h.text,
                       "score": round(h.score, 2)} for h in hits]}


@router.get("/{doc_id}")
async def read_document(doc_id: UUID, p: Principal = Depends(require("knowledge:read")), db: AsyncSession = Depends(get_db)):
    d = await _doc(db, p, doc_id)
    return _out(d, full=True, chunks=await _chunk_count(db, d))


@router.patch("/{doc_id}")
async def update_document(doc_id: UUID, body: DocPatch, p: Principal = Depends(require("knowledge:write")),
                          db: AsyncSession = Depends(get_db)):
    d = await _doc(db, p, doc_id)
    changes = body.model_dump(exclude_unset=True)
    for required in ("title", "content", "status"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required} cannot be empty")
    for key, value in changes.items():
        setattr(d, key, (value or None) if key == "category" else value)
    if "content" in changes:
        await kb.replace_chunks(db, d)
    await db.commit()
    return _out(d, full=True, chunks=await _chunk_count(db, d))


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: UUID, p: Principal = Depends(require("knowledge:write")), db: AsyncSession = Depends(get_db)):
    d = await _doc(db, p, doc_id)
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == d.id, KnowledgeChunk.business_id == p.business_id))
    await db.delete(d)
    await db.commit()

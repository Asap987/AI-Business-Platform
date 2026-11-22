"""Read-only dashboard endpoints. Every query is filtered by principal.business_id."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case as sql_case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import Principal, current_principal, get_db
from app.database.models import Agent, Case, Conversation, Customer, Department

router = APIRouter(tags=["dashboard"])

ACTIVE_CASE = ("open", "in_progress", "waiting_customer", "waiting_department")
CHANNELS = {"whatsapp", "sms", "email", "phone", "web_chat", "other"}


def _page(total: int, items: list, page: int, size: int) -> dict:
    return {"items": items, "total": total, "page": page, "page_size": size}


@router.get("/dashboard/kpis")
async def kpis(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    async def count(model, *where):
        stmt = select(func.count()).select_from(model).where(model.business_id == p.business_id, *where)
        return (await db.execute(stmt)).scalar_one()

    # ai_resolution_rate and average_response_seconds need definitions (what counts as AI-resolved,
    # when the clock starts) and data that is not recorded yet, so they are reported as "no data".
    return {
        "total_calls": {"value": await count(Conversation, Conversation.channel == "phone")},
        "total_sms_conversations": {"value": await count(Conversation, Conversation.channel == "sms")},
        "active_cases": {"value": await count(Case, Case.status.in_(ACTIVE_CASE))},
        "pending_department_requests": {"value": await count(Case, Case.status == "waiting_department")},
        "ai_resolution_rate": {"value": None},
        "average_response_seconds": {"value": None},
    }


@router.get("/dashboard/case-overview")
async def case_overview(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Case.status, func.count()).where(Case.business_id == p.business_id).group_by(Case.status)
    )).all()
    by = dict(rows)
    # "resolved" counts resolved cases only; closed cases are archived and not shown here.
    return {k: by.get(k, 0) for k in ("open", "in_progress", "waiting_department", "resolved")}


@router.get("/dashboard/department-activity")
async def department_activity(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                              p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count()).select_from(Department).where(Department.business_id == p.business_id))).scalar_one()
    open_ = func.coalesce(func.sum(sql_case((Case.status.in_(("open", "in_progress", "waiting_customer")), 1), else_=0)), 0)
    pending = func.coalesce(func.sum(sql_case((Case.status == "waiting_department", 1), else_=0)), 0)
    stmt = (
        select(Department.id, Department.name, open_, pending)
        .outerjoin(Case, (Case.department_id == Department.id) & (Case.business_id == p.business_id))
        .where(Department.business_id == p.business_id)
        .group_by(Department.id, Department.name).order_by(Department.name)
        .limit(page_size).offset((page - 1) * page_size)
    )
    items = [{"id": str(i), "name": n, "open_cases": int(o), "pending_requests": int(pe)} for i, n, o, pe in (await db.execute(stmt)).all()]
    return _page(total, items, page, page_size)


@router.get("/conversations")
async def conversations(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                        sort: str = Query("-started_at", pattern="^-?started_at$"),
                        p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count()).select_from(Conversation).where(Conversation.business_id == p.business_id))).scalar_one()
    order = Conversation.started_at.desc() if sort.startswith("-") else Conversation.started_at.asc()
    stmt = (
        select(Conversation, Customer.full_name)
        .join(Customer, (Customer.id == Conversation.customer_id) & (Customer.business_id == p.business_id))
        .where(Conversation.business_id == p.business_id)
        .order_by(order).limit(page_size).offset((page - 1) * page_size)
    )
    items = [
        {"id": str(c.id), "channel": c.channel, "status": c.status, "customer_name": name,
         "summary": c.summary, "started_at": c.started_at.isoformat()}
        for c, name in (await db.execute(stmt)).all()
    ]
    return _page(total, items, page, page_size)


@router.get("/agents")
async def agents(page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
                 p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count()).select_from(Agent).where(Agent.business_id == p.business_id))).scalar_one()
    last = func.max(Conversation.started_at)
    stmt = (
        select(Agent, last)
        .outerjoin(Conversation, (Conversation.agent_id == Agent.id) & (Conversation.business_id == p.business_id))
        .where(Agent.business_id == p.business_id).group_by(Agent.id).order_by(Agent.name)
        .limit(page_size).offset((page - 1) * page_size)
    )
    items = []
    for agent, last_at in (await db.execute(stmt)).all():
        cfg = agent.config if isinstance(agent.config, dict) else {}
        channels = [c for c in cfg.get("channels", []) if c in CHANNELS] if isinstance(cfg.get("channels"), list) else []
        items.append({
            "id": str(agent.id), "name": agent.name, "status": agent.status, "channels": channels,
            "last_activity_at": last_at.isoformat() if last_at else None,
            # "configured" means the agent has written instructions; other readiness checks come later.
            "configured": bool(str(cfg.get("instructions", "")).strip()),
        })
    return _page(total, items, page, page_size)


@router.get("/notifications/summary")
async def notifications(p: Principal = Depends(current_principal)):
    # No notifications table exists yet, so there is honestly nothing to report.
    return {"unread_total": 0, "unread_conversations": 0, "items": []}

"""Departments and employees. Every query is scoped to the caller's business."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.customers import EMAIL_PATTERN, like_escape
from app.api.v1.deps import Principal, get_db, require
from app.database.models import Business, Case, Department, Employee
from app.services.telephony.schedule import is_open, validate_hours, valid_timezone

departments = APIRouter(prefix="/departments", tags=["departments"])
employees = APIRouter(prefix="/employees", tags=["employees"])

EmployeeStatus = Literal["active", "on_leave", "inactive"]
OPEN_CASE = ("open", "in_progress", "waiting_customer", "waiting_department")


def _strip(v):
    return v.strip() if isinstance(v, str) else v


# ---------------------------------------------------------------- departments
Hours = dict[str, list[list[str]]]


class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    hours: Hours | None = None  # None = always open; see app.services.telephony.schedule
    timezone: str | None = Field(default=None, max_length=60)
    fallback_department_id: UUID | None = None
    accepts_transfers: bool = True
    _s = field_validator("name", "description", mode="before")(_strip)


class DepartmentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    hours: Hours | None = None
    timezone: str | None = Field(default=None, max_length=60)
    fallback_department_id: UUID | None = None
    accepts_transfers: bool | None = None
    _s = field_validator("name", "description", mode="before")(_strip)


def dept_out(d: Department, employee_count: int | None = None, open_cases: int | None = None) -> dict:
    out = {"id": str(d.id), "name": d.name, "description": d.description, "created_at": d.created_at.isoformat(), "hours": d.hours,
           "timezone": d.timezone, "fallback_department_id": str(d.fallback_department_id) if d.fallback_department_id else None,
           "accepts_transfers": d.accepts_transfers}
    if employee_count is not None:
        out.update(employee_count=employee_count, open_cases=open_cases)
    return out


async def _department(db, p, department_id) -> Department:
    d = (await db.execute(select(Department).where(Department.id == department_id, Department.business_id == p.business_id))).scalar_one_or_none()
    if d is None:
        raise HTTPException(404, "Department not found")
    return d


async def _name_taken(db, p, name, except_id=None) -> bool:
    stmt = select(Department.id).where(Department.business_id == p.business_id, func.lower(Department.name) == name.lower())
    if except_id:
        stmt = stmt.where(Department.id != except_id)
    return (await db.execute(stmt)).first() is not None


async def _counts(db, p, department_id) -> tuple[int, int]:
    emps = (await db.execute(select(func.count()).select_from(Employee).where(
        Employee.business_id == p.business_id, Employee.department_id == department_id))).scalar_one()
    cases = (await db.execute(select(func.count()).select_from(Case).where(
        Case.business_id == p.business_id, Case.department_id == department_id, Case.status.in_(OPEN_CASE)))).scalar_one()
    return emps, cases


async def _check_routing(db, p, hours, timezone_name, fallback_id, own_id=None) -> None:
    problem = validate_hours(hours)
    if problem:
        raise HTTPException(422, problem)
    if not valid_timezone(timezone_name):
        raise HTTPException(422, "Unknown time zone. Use a name such as Africa/Accra.")
    if fallback_id is not None:
        if own_id is not None and fallback_id == own_id:
            raise HTTPException(422, "A department cannot be its own fallback.")
        found = (await db.execute(select(Department.id).where(Department.id == fallback_id, Department.business_id == p.business_id))).first()
        if found is None:
            raise HTTPException(422, "That fallback department does not exist.")


@departments.post("", status_code=201)
async def create_department(body: DepartmentIn, p: Principal = Depends(require("departments:write")), db: AsyncSession = Depends(get_db)):
    if await _name_taken(db, p, body.name):
        raise HTTPException(409, "A department with that name already exists")
    await _check_routing(db, p, body.hours, body.timezone, body.fallback_department_id)
    d = Department(business_id=p.business_id, **body.model_dump())
    db.add(d)
    await db.commit()
    return dept_out(d, 0, 0)


@departments.get("")
async def list_departments(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                           p: Principal = Depends(require("departments:read")), db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count()).select_from(Department).where(Department.business_id == p.business_id))).scalar_one()
    rows = (await db.execute(select(Department).where(Department.business_id == p.business_id)
                             .order_by(Department.name).limit(page_size).offset((page - 1) * page_size))).scalars().all()
    items = [dept_out(d, *await _counts(db, p, d.id)) for d in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@departments.get("/{department_id}")
async def read_department(department_id: UUID, p: Principal = Depends(require("departments:read")), db: AsyncSession = Depends(get_db)):
    d = await _department(db, p, department_id)
    return dept_out(d, *await _counts(db, p, d.id))


@departments.patch("/{department_id}")
async def update_department(department_id: UUID, body: DepartmentPatch, p: Principal = Depends(require("departments:write")),
                            db: AsyncSession = Depends(get_db)):
    d = await _department(db, p, department_id)
    if "name" in body.model_fields_set:
        if body.name is None:
            raise HTTPException(422, "name cannot be empty")
        if await _name_taken(db, p, body.name, d.id):
            raise HTTPException(409, "A department with that name already exists")
        d.name = body.name
    if "description" in body.model_fields_set:
        d.description = body.description
    sent = body.model_fields_set
    if "accepts_transfers" in sent and body.accepts_transfers is None:
        raise HTTPException(422, "accepts_transfers cannot be empty")
    await _check_routing(db, p, body.hours if "hours" in sent else None, body.timezone if "timezone" in sent else None,
                         body.fallback_department_id if "fallback_department_id" in sent else None, d.id)
    for field in ("hours", "timezone", "fallback_department_id", "accepts_transfers"):
        if field in sent:
            setattr(d, field, getattr(body, field))
    await db.commit()
    return dept_out(d, *await _counts(db, p, d.id))


@departments.get("/{department_id}/availability")
async def department_availability(department_id: UUID, p: Principal = Depends(require("departments:read")), db: AsyncSession = Depends(get_db)):
    """Whether a transfer could be tried right now, and why not. Counts only; no names or numbers."""
    d = await _department(db, p, department_id)
    tz = d.timezone or (await db.execute(select(Business.timezone).where(Business.id == p.business_id))).scalar_one_or_none() or "UTC"
    reachable = (await db.execute(select(func.count()).select_from(Employee).where(
        Employee.business_id == p.business_id, Employee.department_id == d.id, Employee.status == "active", Employee.available.is_(True),
        Employee.phone.is_not(None), Employee.phone != ""))).scalar_one()
    open_now = is_open(d.hours, tz)
    return {"department_id": str(d.id), "open_now": open_now, "timezone": tz, "accepts_transfers": d.accepts_transfers, "reachable_staff": reachable,
            "can_transfer_now": bool(d.accepts_transfers and open_now and reachable),
            "fallback_department_id": str(d.fallback_department_id) if d.fallback_department_id else None}


@departments.delete("/{department_id}", status_code=204)
async def delete_department(department_id: UUID, p: Principal = Depends(require("departments:write")), db: AsyncSession = Depends(get_db)):
    d = await _department(db, p, department_id)
    # The database would quietly detach staff and cases; that would lose routing, so refuse instead.
    emps = (await db.execute(select(func.count()).select_from(Employee).where(
        Employee.business_id == p.business_id, Employee.department_id == d.id))).scalar_one()
    cases = (await db.execute(select(func.count()).select_from(Case).where(
        Case.business_id == p.business_id, Case.department_id == d.id))).scalar_one()
    if emps or cases:
        raise HTTPException(409, f"This department still has {emps} employee(s) and {cases} case(s). Move them first.")
    await db.delete(d)
    await db.commit()


# ------------------------------------------------------------------ employees
class EmployeeIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    phone: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=100)
    department_id: UUID | None = None
    status: EmployeeStatus = "active"
    extension: str | None = Field(default=None, max_length=20, pattern=r"^[0-9*#]+$")
    available: bool = True
    routing_priority: int = Field(default=100, ge=1, le=1000)  # lower is tried first
    _s = field_validator("full_name", "email", "phone", "job_title", "extension", mode="before")(_strip)


class EmployeePatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    phone: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=100)
    department_id: UUID | None = None
    status: EmployeeStatus | None = None
    extension: str | None = Field(default=None, max_length=20, pattern=r"^[0-9*#]+$")
    available: bool | None = None
    routing_priority: int | None = Field(default=None, ge=1, le=1000)
    _s = field_validator("full_name", "email", "phone", "job_title", "extension", mode="before")(_strip)


def emp_out(e: Employee) -> dict:
    return {"id": str(e.id), "full_name": e.full_name, "email": e.email, "phone": e.phone, "job_title": e.job_title,
            "department_id": str(e.department_id) if e.department_id else None, "status": e.status,
            "has_login": e.user_id is not None, "extension": e.extension, "available": e.available, "routing_priority": e.routing_priority, "created_at": e.created_at.isoformat()}


async def _employee(db, p, employee_id) -> Employee:
    e = (await db.execute(select(Employee).where(Employee.id == employee_id, Employee.business_id == p.business_id))).scalar_one_or_none()
    if e is None:
        raise HTTPException(404, "Employee not found")
    return e


async def _require_department(db, p, department_id) -> None:
    if department_id is None:
        return
    found = (await db.execute(select(Department.id).where(Department.id == department_id, Department.business_id == p.business_id))).first()
    if found is None:
        raise HTTPException(422, "That department does not exist.")


@employees.post("", status_code=201)
async def create_employee(body: EmployeeIn, p: Principal = Depends(require("employees:write")), db: AsyncSession = Depends(get_db)):
    await _require_department(db, p, body.department_id)
    e = Employee(business_id=p.business_id, **body.model_dump())
    db.add(e)
    await db.commit()
    return emp_out(e)


@employees.get("")
async def list_employees(q: str | None = Query(None, max_length=100), department_id: UUID | None = None,
                         status: EmployeeStatus | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                         p: Principal = Depends(require("employees:read")), db: AsyncSession = Depends(get_db)):
    where = [Employee.business_id == p.business_id]
    if department_id:
        where.append(Employee.department_id == department_id)
    if status:
        where.append(Employee.status == status)
    if q and q.strip():
        pat = f"%{like_escape(q.strip().lower())}%"
        where.append(or_(*[func.lower(c).like(pat, escape="\\") for c in (Employee.full_name, Employee.email, Employee.job_title)]))
    total = (await db.execute(select(func.count()).select_from(Employee).where(*where))).scalar_one()
    rows = (await db.execute(select(Employee).where(*where).order_by(Employee.full_name, Employee.id)
                             .limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return {"items": [emp_out(e) for e in rows], "total": total, "page": page, "page_size": page_size}


@employees.get("/{employee_id}")
async def read_employee(employee_id: UUID, p: Principal = Depends(require("employees:read")), db: AsyncSession = Depends(get_db)):
    return emp_out(await _employee(db, p, employee_id))


@employees.patch("/{employee_id}")
async def update_employee(employee_id: UUID, body: EmployeePatch, p: Principal = Depends(require("employees:write")),
                          db: AsyncSession = Depends(get_db)):
    e = await _employee(db, p, employee_id)
    sent = body.model_fields_set
    for required in ("full_name", "status", "available", "routing_priority"):
        if required in sent and getattr(body, required) is None:
            raise HTTPException(422, f"{required} cannot be empty")
    if "department_id" in sent:
        await _require_department(db, p, body.department_id)
    if body.status == "inactive" and e.status != "inactive":
        open_cases = (await db.execute(select(func.count()).select_from(Case).where(
            Case.business_id == p.business_id, Case.assigned_employee_id == e.id, Case.status.in_(OPEN_CASE)))).scalar_one()
        if open_cases:
            raise HTTPException(409, f"This employee still has {open_cases} open case(s). Reassign them first.")
    for field in sent:
        setattr(e, field, getattr(body, field))
    await db.commit()
    return emp_out(e)

from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.security import hash_password
from app.database.models import Business, Case, CaseEvent, Conversation, Department, Employee, Role, User
from tests.api.conftest import make_client, register

API = "/api/v1"


async def signup(env, name, email):
    app, factory, _ = env
    c = make_client(app)
    await c.__aenter__()
    me = (await register(c, business_name=name, email=email)).json()
    return c, UUID(me["business"]["id"]), factory


async def two(env):
    a, a_id, factory = await signup(env, "Alpha", "a@a.test")
    b, b_id, _ = await signup(env, "Beta", "b@b.test")
    return a, a_id, b, b_id, factory


async def add_user(factory, business_id, role_name, perms, email):
    async with factory() as db:
        role = Role(business_id=business_id, name=role_name, permissions=perms)
        db.add(role)
        await db.flush()
        db.add(User(business_id=business_id, role_id=role.id, email=email, password_hash=hash_password("a-long-passphrase"), full_name=role_name))
        await db.commit()


async def login(env, email):
    c = make_client(env[0])
    await c.__aenter__()
    r = await c.post(f"{API}/auth/login", json={"email": email, "password": "a-long-passphrase"})
    assert r.status_code == 200, r.text
    return c


async def mk_customer(c, name="Kwame Asante", **kw):
    r = await c.post(f"{API}/customers", json={"full_name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


async def mk_case(c, customer_id, **kw):
    r = await c.post(f"{API}/cases", json={"customer_id": customer_id, "title": "Parcel arrived damaged", **kw})
    assert r.status_code == 201, r.text
    return r.json()


async def seed_department(factory, business_id, name="Delivery"):
    async with factory() as db:
        d = Department(business_id=business_id, name=name)
        db.add(d)
        await db.commit()
        return str(d.id)


async def seed_employee(factory, business_id, status="active"):
    async with factory() as db:
        e = Employee(business_id=business_id, full_name="Efua Owusu", status=status)
        db.add(e)
        await db.commit()
        return str(e.id)


# ----------------------------------------------------------------- customers
async def test_customer_crud_and_whitespace_cleanup(env):
    a, _, b, _, _ = await two(env)
    try:
        c = await mk_customer(a, "  Kwame Asante ", email=" kwame@x.test ", phone=" 0244000111 ")
        assert c["full_name"] == "Kwame Asante" and c["email"] == "kwame@x.test" and c["phone"] == "0244000111"
        assert (await a.get(f"{API}/customers/{c['id']}")).json()["full_name"] == "Kwame Asante"
        r = await a.patch(f"{API}/customers/{c['id']}", json={"email": None, "phone": "0201"})
        assert r.json()["email"] is None and r.json()["phone"] == "0201" and r.json()["full_name"] == "Kwame Asante"
        assert (await a.patch(f"{API}/customers/{c['id']}", json={"full_name": None})).status_code == 422
        assert (await a.post(f"{API}/customers", json={"full_name": "", })).status_code == 422
        assert (await a.post(f"{API}/customers", json={"full_name": "X", "email": "bad"})).status_code == 422
    finally:
        await a.aclose(), await b.aclose()


async def test_customers_with_the_same_phone_are_never_merged(env):
    a, _, b, _, _ = await two(env)
    try:
        c1 = await mk_customer(a, "Person One", phone="0244000111")
        c2 = await mk_customer(a, "Person Two", phone="0244000111")
        assert c1["id"] != c2["id"] and (await a.get(f"{API}/customers")).json()["total"] == 2
    finally:
        await a.aclose(), await b.aclose()


async def test_customer_search_pagination_and_wildcards_are_literal(env):
    a, _, b, _, _ = await two(env)
    try:
        for n, ph in (("Ama Mensah", "0244111"), ("Kofi 100% Sure", "0555222"), ("Yaw Boateng", "0266333")):
            await mk_customer(a, n, phone=ph)
        r = (await a.get(f"{API}/customers", params={"q": "mensah"})).json()
        assert [i["full_name"] for i in r["items"]] == ["Ama Mensah"]
        assert [i["full_name"] for i in (await a.get(f"{API}/customers", params={"q": "0555"})).json()["items"]] == ["Kofi 100% Sure"]
        assert (await a.get(f"{API}/customers", params={"q": "%"})).json()["total"] == 1  # "%" matches only the literal percent sign
        assert (await a.get(f"{API}/customers", params={"q": "_"})).json()["total"] == 0
        page = (await a.get(f"{API}/customers", params={"page_size": 2, "page": 2})).json()
        assert page["total"] == 3 and len(page["items"]) == 1
        assert (await a.get(f"{API}/customers", params={"page_size": 101})).status_code == 422
    finally:
        await a.aclose(), await b.aclose()


async def test_customers_are_invisible_and_untouchable_across_businesses(env):
    a, _, b, _, _ = await two(env)
    try:
        mine = await mk_customer(a, "ALPHA-ONLY")
        assert "ALPHA-ONLY" not in (await b.get(f"{API}/customers")).text
        assert "ALPHA-ONLY" not in (await b.get(f"{API}/customers", params={"q": "alpha"})).text
        assert (await b.get(f"{API}/customers/{mine['id']}")).status_code == 404
        assert (await b.patch(f"{API}/customers/{mine['id']}", json={"full_name": "hacked"})).status_code == 404
        assert (await a.get(f"{API}/customers/{mine['id']}")).json()["full_name"] == "ALPHA-ONLY"
        assert (await b.get(f"{API}/customers/{uuid4()}")).status_code == 404
    finally:
        await a.aclose(), await b.aclose()


async def test_customer_permissions(env):
    a, a_id, b, _, factory = await two(env)
    try:
        await add_user(factory, a_id, "Viewer", ["customers:read"], "viewer@a.test")
        await add_user(factory, a_id, "Nobody", [], "nobody@a.test")
        v, n = await login(env, "viewer@a.test"), await login(env, "nobody@a.test")
        cust = await mk_customer(a)
        assert (await v.get(f"{API}/customers")).status_code == 200
        assert (await v.get(f"{API}/customers/{cust['id']}")).status_code == 200
        assert (await v.post(f"{API}/customers", json={"full_name": "x"})).status_code == 403
        assert (await v.patch(f"{API}/customers/{cust['id']}", json={"full_name": "x"})).status_code == 403
        assert (await n.get(f"{API}/customers")).status_code == 403
        await v.aclose(), await n.aclose()
    finally:
        await a.aclose(), await b.aclose()


# --------------------------------------------------------------------- cases
async def test_create_case_records_history_and_validates_references(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        cust, dept = await mk_customer(a), await seed_department(factory, a_id)
        case = await mk_case(a, cust["id"], priority="high", department_id=dept)
        assert case["status"] == "open" and case["priority"] == "high" and case["customer_name"] is None
        ev = (await a.get(f"{API}/cases/{case['id']}/events")).json()["items"]
        assert [(e["kind"], e["actor_kind"]) for e in ev] == [("created", "user")] and ev[0]["actor_user_id"]
        # another business's customer or department cannot be used
        other_cust, other_dept = await mk_customer(b, "BETA-CUST"), await seed_department(factory, b_id, "Sales")
        assert (await a.post(f"{API}/cases", json={"customer_id": other_cust["id"], "title": "Sneaky"})).status_code == 404
        assert (await a.post(f"{API}/cases", json={"customer_id": cust["id"], "title": "Sneaky", "department_id": other_dept})).status_code == 422
        assert (await a.post(f"{API}/cases", json={"customer_id": cust["id"], "title": "ab"})).status_code == 422
        assert (await a.post(f"{API}/cases", json={"customer_id": cust["id"], "title": "Fine title", "priority": "huge"})).status_code == 422
        assert (await a.get(f"{API}/cases")).json()["total"] == 1
    finally:
        await a.aclose(), await b.aclose()


async def test_conversation_must_belong_to_the_same_customer_and_business(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        c1, c2 = await mk_customer(a, "One"), await mk_customer(a, "Two")
        async with factory() as db:
            conv = Conversation(business_id=a_id, customer_id=UUID(c1["id"]), channel="phone")
            db.add(conv)
            await db.commit()
            conv_id = str(conv.id)
        assert (await a.post(f"{API}/cases", json={"customer_id": c1["id"], "title": "Linked ok", "conversation_id": conv_id})).status_code == 201
        assert (await a.post(f"{API}/cases", json={"customer_id": c2["id"], "title": "Wrong customer", "conversation_id": conv_id})).status_code == 422
        bc = await mk_customer(b, "Bee")
        assert (await b.post(f"{API}/cases", json={"customer_id": bc["id"], "title": "Foreign conv", "conversation_id": conv_id})).status_code == 422
    finally:
        await a.aclose(), await b.aclose()


async def test_cases_are_invisible_and_untouchable_across_businesses(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        cust = await mk_customer(a)
        case = await mk_case(a, cust["id"], description="ALPHA secret description")
        assert "ALPHA" not in (await b.get(f"{API}/cases")).text
        assert "secret" not in (await b.get(f"{API}/cases", params={"q": "secret"})).text
        for method, url, kw in (("get", f"{API}/cases/{case['id']}", {}), ("get", f"{API}/cases/{case['id']}/events", {}),
                                ("patch", f"{API}/cases/{case['id']}", {"json": {"title": "hijacked!"}})):
            assert (await getattr(b, method)(url, **kw)).status_code == 404, url
        assert (await a.get(f"{API}/cases/{case['id']}")).json()["title"] == "Parcel arrived damaged"
        # filtering by an id from another business gives nothing, not an error that confirms it exists
        assert (await b.get(f"{API}/cases", params={"customer_id": cust["id"]})).json()["total"] == 0
    finally:
        await a.aclose(), await b.aclose()


async def test_list_filters_search_and_pagination(env):
    a, a_id, b, _, factory = await two(env)
    try:
        cust, dept = await mk_customer(a), await seed_department(factory, a_id)
        await mk_case(a, cust["id"], title="Late delivery", priority="low")
        urgent = await mk_case(a, cust["id"], title="Broken screen", priority="urgent", department_id=dept)
        await mk_case(a, cust["id"], title="100% refund request")
        got = lambda **p: a.get(f"{API}/cases", params=p)  # noqa: E731
        assert (await got(priority="urgent")).json()["items"][0]["id"] == urgent["id"]
        assert (await got(department_id=dept)).json()["total"] == 1
        assert (await got(q="SCREEN")).json()["total"] == 1
        assert (await got(q="%")).json()["total"] == 1  # literal percent only
        assert (await got(status="resolved")).json()["total"] == 0
        assert (await got(status="not_a_status")).status_code == 422
        assert (await got(page_size=2, page=2)).json()["total"] == 3
        assert len((await got(page_size=2, page=2)).json()["items"]) == 1
        assert (await got()).json()["items"][0]["customer_name"] == "Kwame Asante"
    finally:
        await a.aclose(), await b.aclose()


async def test_status_workflow(env):
    a, a_id, b, _, _ = await two(env)
    try:
        case = await mk_case(a, (await mk_customer(a))["id"])
        url = f"{API}/cases/{case['id']}"
        patch = lambda **j: a.patch(url, json=j)  # noqa: E731
        assert (await patch(status="closed")).status_code == 409  # cannot skip straight to closed
        assert (await patch(status="in_progress")).json()["status"] == "in_progress"
        assert (await patch(status="waiting_department")).json()["status"] == "waiting_department"
        r = await patch(status="resolved")
        assert r.status_code == 422 and "resolution notes" in r.json()["detail"]  # notes are required
        r = await patch(status="resolved", resolution_notes="Replacement sent")
        assert r.status_code == 200 and r.json()["resolved_at"] is not None
        assert (await patch(status="in_progress")).json()["resolved_at"] is None  # reopened
        await patch(status="resolved")
        assert (await patch(status="closed")).json()["status"] == "closed"
        assert (await patch(title="Too late now")).status_code == 409  # closed is final
        assert (await patch(status="open")).status_code == 409
        kinds = [e["kind"] for e in (await a.get(f"{url}/events")).json()["items"]]
        assert kinds == ["created", "status_changed", "status_changed", "status_changed", "status_changed", "status_changed", "status_changed"]
        assert (await a.patch(url, json={"status": None})).status_code == 422
    finally:
        await a.aclose(), await b.aclose()


async def test_a_rejected_update_changes_nothing(env):
    a, _, b, _, _ = await two(env)
    try:
        case = await mk_case(a, (await mk_customer(a))["id"])
        url = f"{API}/cases/{case['id']}"
        r = await a.patch(url, json={"priority": "urgent", "title": "Changed title", "status": "closed"})
        assert r.status_code == 409
        now = (await a.get(url)).json()
        assert now["priority"] == "medium" and now["title"] == "Parcel arrived damaged"
        assert [e["kind"] for e in (await a.get(f"{url}/events")).json()["items"]] == ["created"]
        for bad in ({"title": None}, {"priority": None}, {"status": None}):
            assert (await a.patch(url, json=bad)).status_code == 422
    finally:
        await a.aclose(), await b.aclose()


async def test_assignment_rules_and_unassigning(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        case = await mk_case(a, (await mk_customer(a))["id"])
        url = f"{API}/cases/{case['id']}"
        mine, inactive = await seed_employee(factory, a_id), await seed_employee(factory, a_id, "inactive")
        foreign = await seed_employee(factory, b_id)
        assert (await a.patch(url, json={"assigned_employee_id": foreign})).status_code == 422
        assert (await a.patch(url, json={"assigned_employee_id": inactive})).status_code == 422
        assert (await a.patch(url, json={"assigned_employee_id": str(uuid4())})).status_code == 422
        r = await a.patch(url, json={"assigned_employee_id": mine})
        assert r.json()["assigned_employee_id"] == mine
        assert (await a.get(f"{API}/cases", params={"assigned_employee_id": mine})).json()["total"] == 1
        assert (await a.patch(url, json={"assigned_employee_id": None})).json()["assigned_employee_id"] is None
        ev = (await a.get(f"{url}/events")).json()["items"]
        assert [e["kind"] for e in ev] == ["created", "assigned", "assigned"]
        assert ev[1]["detail"]["assigned_employee_id"] == [None, mine]
    finally:
        await a.aclose(), await b.aclose()


async def test_history_does_not_copy_case_text(env):
    a, _, b, _, _ = await two(env)
    try:
        case = await mk_case(a, (await mk_customer(a))["id"], description="Customer phone 0244 and address")
        await a.patch(f"{API}/cases/{case['id']}", json={"description": "SENSITIVE-NEW-TEXT", "title": "SENSITIVE-NEW-TITLE"})
        text = (await a.get(f"{API}/cases/{case['id']}/events")).text
        assert "SENSITIVE" not in text and "0244" not in text and "fields_changed" in text
    finally:
        await a.aclose(), await b.aclose()


async def test_case_permissions_and_default_roles(env):
    a, a_id, b, _, factory = await two(env)
    try:
        await add_user(factory, a_id, "Auditor", ["cases:read", "customers:read"], "aud@a.test")
        await add_user(factory, a_id, "Staff", ["cases:write", "customers:write"], "emp@a.test")
        aud, emp = await login(env, "aud@a.test"), await login(env, "emp@a.test")
        cust = await mk_customer(a)
        case = await mk_case(emp, cust["id"])  # an Employee can log and work cases
        assert (await aud.get(f"{API}/cases/{case['id']}")).status_code == 200
        assert (await aud.get(f"{API}/cases/{case['id']}/events")).status_code == 200
        assert (await aud.post(f"{API}/cases", json={"customer_id": cust["id"], "title": "Not allowed"})).status_code == 403
        assert (await aud.patch(f"{API}/cases/{case['id']}", json={"status": "in_progress"})).status_code == 403
        assert (await emp.patch(f"{API}/cases/{case['id']}", json={"status": "in_progress"})).status_code == 200
        await aud.aclose(), await emp.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_everything_needs_a_session_and_an_allowed_origin(env, client):
    for method, path in (("get", "/cases"), ("get", "/customers"), ("get", f"/cases/{uuid4()}"), ("get", f"/cases/{uuid4()}/events")):
        assert (await getattr(client, method)(API + path)).status_code == 401, path
    for path in ("/cases", "/customers"):
        assert (await client.post(API + path, json={})).status_code == 401
    async with make_client(env[0], origin="https://evil.example") as evil:
        assert (await evil.post(API + "/cases", json={})).status_code == 403
        assert (await evil.patch(API + f"/cases/{uuid4()}", json={})).status_code == 403


import os  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs PostgreSQL with migration 0003 applied")
async def test_postgres_refuses_to_rewrite_case_history(env):
    a, a_id, b, _, factory = await two(env)
    try:
        case = await mk_case(a, (await mk_customer(a))["id"])
        async with factory() as db:
            with pytest.raises(Exception, match="append-only"):
                await db.execute(text("UPDATE case_events SET kind = 'forged' WHERE case_id = :c"), {"c": UUID(case["id"])})
    finally:
        await a.aclose(), await b.aclose()

from uuid import uuid4

from tests.api.conftest import make_client
from tests.api.test_customers_cases import add_user, login, mk_case, mk_customer, two

API = "/api/v1"


async def mk_dept(c, name="Delivery", **kw):
    r = await c.post(f"{API}/departments", json={"name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


async def mk_emp(c, name="Efua Owusu", **kw):
    r = await c.post(f"{API}/employees", json={"full_name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- departments
async def test_department_crud_with_counts_and_name_rules(env):
    a, _, b, _, _ = await two(env)
    try:
        d = await mk_dept(a, "  Delivery ", description="Parcels")
        assert d["name"] == "Delivery" and d["employee_count"] == 0 and d["open_cases"] == 0
        assert (await a.post(f"{API}/departments", json={"name": "delivery"})).status_code == 409  # case-insensitive
        assert (await b.post(f"{API}/departments", json={"name": "Delivery"})).status_code == 201  # other business may reuse it
        other = await mk_dept(a, "Sales")
        assert (await a.patch(f"{API}/departments/{other['id']}", json={"name": "DELIVERY"})).status_code == 409
        r = await a.patch(f"{API}/departments/{other['id']}", json={"name": "Sales & Quotes", "description": None})
        assert r.json()["name"] == "Sales & Quotes" and r.json()["description"] is None
        assert (await a.patch(f"{API}/departments/{other['id']}", json={"name": "Sales & Quotes"})).status_code == 200  # own name is fine
        assert (await a.patch(f"{API}/departments/{other['id']}", json={"name": None})).status_code == 422
        assert (await a.post(f"{API}/departments", json={"name": "x"})).status_code == 422
        listing = (await a.get(f"{API}/departments")).json()
        assert [i["name"] for i in listing["items"]] == ["Delivery", "Sales & Quotes"] and listing["total"] == 2
    finally:
        await a.aclose(), await b.aclose()


async def test_department_counts_reflect_staff_and_only_open_cases(env):
    a, _, b, _, _ = await two(env)
    try:
        d = await mk_dept(a)
        await mk_emp(a, department_id=d["id"])
        cust = await mk_customer(a)
        c1 = await mk_case(a, cust["id"], department_id=d["id"])
        c2 = await mk_case(a, cust["id"], department_id=d["id"])
        await a.patch(f"{API}/cases/{c2['id']}", json={"status": "resolved", "resolution_notes": "done"})
        got = (await a.get(f"{API}/departments/{d['id']}")).json()
        assert got["employee_count"] == 1 and got["open_cases"] == 1
    finally:
        await a.aclose(), await b.aclose()


async def test_department_delete_is_refused_while_it_is_in_use(env):
    a, _, b, _, _ = await two(env)
    try:
        used_by_emp, used_by_case, empty = await mk_dept(a, "Staffed"), await mk_dept(a, "Cased"), await mk_dept(a, "Empty")
        emp = await mk_emp(a, department_id=used_by_emp["id"])
        await mk_case(a, (await mk_customer(a))["id"], department_id=used_by_case["id"])
        assert (await a.delete(f"{API}/departments/{used_by_emp['id']}")).status_code == 409
        assert (await a.delete(f"{API}/departments/{used_by_case['id']}")).status_code == 409
        assert (await a.get(f"{API}/employees/{emp['id']}")).json()["department_id"] == used_by_emp["id"]  # not silently detached
        assert (await a.delete(f"{API}/departments/{empty['id']}")).status_code == 204
        assert (await a.get(f"{API}/departments/{empty['id']}")).status_code == 404
    finally:
        await a.aclose(), await b.aclose()


async def test_departments_are_isolated_between_businesses(env):
    a, _, b, _, _ = await two(env)
    try:
        d = await mk_dept(a, "ALPHA-DEPT")
        assert "ALPHA-DEPT" not in (await b.get(f"{API}/departments")).text
        for call in (b.get(f"{API}/departments/{d['id']}"), b.patch(f"{API}/departments/{d['id']}", json={"name": "hijacked"}),
                     b.delete(f"{API}/departments/{d['id']}")):
            assert (await call).status_code == 404
        assert (await a.get(f"{API}/departments/{d['id']}")).json()["name"] == "ALPHA-DEPT"
    finally:
        await a.aclose(), await b.aclose()


# ------------------------------------------------------------------ employees
async def test_employee_crud_validation_and_search(env):
    a, _, b, _, _ = await two(env)
    try:
        d = await mk_dept(a)
        e = await mk_emp(a, " Efua Owusu ", email=" efua@x.test ", job_title="Dispatcher", department_id=d["id"])
        assert e["full_name"] == "Efua Owusu" and e["email"] == "efua@x.test" and e["status"] == "active" and e["has_login"] is False
        await mk_emp(a, "Yaw Boateng", job_title="Driver")
        await mk_emp(a, "Ama 100% Sure", status="on_leave")
        got = lambda **p: a.get(f"{API}/employees", params=p)  # noqa: E731
        assert [i["full_name"] for i in (await got(q="dispatch")).json()["items"]] == ["Efua Owusu"]
        assert (await got(q="%")).json()["total"] == 1 and (await got(q="_")).json()["total"] == 0
        assert (await got(department_id=d["id"])).json()["total"] == 1
        assert [i["full_name"] for i in (await got(status="on_leave")).json()["items"]] == ["Ama 100% Sure"]
        assert (await got(status="retired")).status_code == 422
        r = await a.patch(f"{API}/employees/{e['id']}", json={"email": None, "department_id": None, "job_title": "Lead"})
        assert r.json()["email"] is None and r.json()["department_id"] is None and r.json()["job_title"] == "Lead"
        assert (await a.patch(f"{API}/employees/{e['id']}", json={"full_name": None})).status_code == 422
        assert (await a.patch(f"{API}/employees/{e['id']}", json={"status": None})).status_code == 422
        assert (await a.post(f"{API}/employees", json={"full_name": "A"})).status_code == 422
        assert (await a.post(f"{API}/employees", json={"full_name": "Valid Name", "email": "nope"})).status_code == 422
    finally:
        await a.aclose(), await b.aclose()


async def test_employee_cannot_be_placed_in_another_businesss_department(env):
    a, _, b, _, _ = await two(env)
    try:
        foreign = await mk_dept(b, "BETA-DEPT")
        assert (await a.post(f"{API}/employees", json={"full_name": "Valid Name", "department_id": foreign["id"]})).status_code == 422
        e = await mk_emp(a)
        assert (await a.patch(f"{API}/employees/{e['id']}", json={"department_id": foreign["id"]})).status_code == 422
        assert (await a.patch(f"{API}/employees/{e['id']}", json={"department_id": str(uuid4())})).status_code == 422
    finally:
        await a.aclose(), await b.aclose()


async def test_employees_are_isolated_between_businesses(env):
    a, _, b, _, _ = await two(env)
    try:
        e = await mk_emp(a, "ALPHA-PERSON")
        assert "ALPHA-PERSON" not in (await b.get(f"{API}/employees")).text
        assert "ALPHA" not in (await b.get(f"{API}/employees", params={"q": "alpha"})).text
        assert (await b.get(f"{API}/employees/{e['id']}")).status_code == 404
        assert (await b.patch(f"{API}/employees/{e['id']}", json={"full_name": "Hijacked"})).status_code == 404
        assert (await a.get(f"{API}/employees/{e['id']}")).json()["full_name"] == "ALPHA-PERSON"
    finally:
        await a.aclose(), await b.aclose()


async def test_deactivating_an_employee_needs_their_open_cases_reassigned(env):
    a, _, b, _, _ = await two(env)
    try:
        e1, e2 = await mk_emp(a, "Employee One"), await mk_emp(a, "Employee Two")
        case = await mk_case(a, (await mk_customer(a))["id"])
        await a.patch(f"{API}/cases/{case['id']}", json={"assigned_employee_id": e1["id"]})
        r = await a.patch(f"{API}/employees/{e1['id']}", json={"status": "inactive"})
        assert r.status_code == 409 and "1 open case" in r.json()["detail"]
        assert (await a.patch(f"{API}/employees/{e1['id']}", json={"status": "on_leave"})).status_code == 200  # leave is allowed
        await a.patch(f"{API}/employees/{e1['id']}", json={"status": "active"})
        await a.patch(f"{API}/cases/{case['id']}", json={"assigned_employee_id": e2["id"]})
        assert (await a.patch(f"{API}/employees/{e1['id']}", json={"status": "inactive"})).json()["status"] == "inactive"
        # and an inactive or on-leave employee cannot be given new cases
        assert (await a.patch(f"{API}/cases/{case['id']}", json={"assigned_employee_id": e1["id"]})).status_code == 422
    finally:
        await a.aclose(), await b.aclose()


async def test_resolved_cases_do_not_block_deactivation(env):
    a, _, b, _, _ = await two(env)
    try:
        e = await mk_emp(a)
        case = await mk_case(a, (await mk_customer(a))["id"])
        await a.patch(f"{API}/cases/{case['id']}", json={"assigned_employee_id": e["id"]})
        await a.patch(f"{API}/cases/{case['id']}", json={"status": "resolved", "resolution_notes": "fixed"})
        assert (await a.patch(f"{API}/employees/{e['id']}", json={"status": "inactive"})).status_code == 200
    finally:
        await a.aclose(), await b.aclose()


# ------------------------------------------------------------------ permissions
async def test_organization_permissions(env):
    a, a_id, b, _, factory = await two(env)
    try:
        await add_user(factory, a_id, "Reader", ["departments:read", "employees:read"], "r@a.test")
        await add_user(factory, a_id, "Nothing", [], "n@a.test")
        await add_user(factory, a_id, "Org Manager", ["departments:write", "employees:write"], "m@a.test")
        r, n, m = await login(env, "r@a.test"), await login(env, "n@a.test"), await login(env, "m@a.test")
        d, e = await mk_dept(a), await mk_emp(a)
        assert (await r.get(f"{API}/departments")).status_code == 200 and (await r.get(f"{API}/employees/{e['id']}")).status_code == 200
        for call in (r.post(f"{API}/departments", json={"name": "Nope"}), r.patch(f"{API}/departments/{d['id']}", json={"name": "Nope"}),
                     r.delete(f"{API}/departments/{d['id']}"), r.post(f"{API}/employees", json={"full_name": "Nope Nope"}),
                     r.patch(f"{API}/employees/{e['id']}", json={"job_title": "x"}),
                     n.get(f"{API}/departments"), n.get(f"{API}/employees")):
            assert (await call).status_code == 403
        assert (await m.post(f"{API}/departments", json={"name": "Made by manager"})).status_code == 201  # write implies read
        assert (await m.get(f"{API}/employees")).status_code == 200
        await r.aclose(), await n.aclose(), await m.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_registered_default_roles_cover_the_organization_screens(env, client):
    from tests.api.conftest import register
    await register(client)
    assert (await client.post(f"{API}/departments", json={"name": "Customer Service"})).status_code == 201  # Administrator
    assert (await client.get(f"{API}/employees")).status_code == 200


async def test_requires_session_and_origin(env, client):
    for path in ("/departments", "/employees", f"/departments/{uuid4()}", f"/employees/{uuid4()}"):
        assert (await client.get(API + path)).status_code == 401, path
    async with make_client(env[0], origin="https://evil.example") as evil:
        assert (await evil.post(API + "/departments", json={"name": "x"})).status_code == 403
        assert (await evil.delete(API + f"/departments/{uuid4()}")).status_code == 403

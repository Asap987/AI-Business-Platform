from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import token_digest
from app.database.models import AuthSession, UserInvite
from tests.api.conftest import make_client
from tests.api.test_customers_cases import add_user, login, two

API = "/api/v1"


async def roles(c):
    return {r["name"]: r for r in (await c.get(f"{API}/roles")).json()["items"]}


async def invite(c, email="kofi@a.test", role="Employee", **kw):
    rs = await roles(c)
    r = await c.post(f"{API}/users/invites", json={"email": email, "role_id": rs[role]["id"], **kw})
    return r


async def _id(c, email):
    return {u["email"]: u["id"] for u in (await c.get(f"{API}/users")).json()["items"]}[email]


async def accept(env, token, password="a-long-passphrase", **kw):
    c = make_client(env[0])
    await c.__aenter__()
    r = await c.post(f"{API}/auth/accept-invite", json={"token": token, "password": password, **kw})
    return c, r


async def test_invite_accept_flow_and_single_use(env):
    a, a_id, b, _, factory = await two(env)
    try:
        r = await invite(a, " Kofi@A.test ")
        assert r.status_code == 201, r.text
        body = r.json()
        token = body["token"]
        assert body["email"] == "kofi@a.test"
        async with factory() as db:  # only a hash is stored
            inv = (await db.execute(select(UserInvite))).scalar_one()
            assert inv.token_hash == token_digest(token) and token not in inv.token_hash
        listed = (await a.get(f"{API}/users/invites")).json()["items"]
        assert len(listed) == 1 and "token" not in listed[0] and listed[0]["role"]["name"] == "Employee"
        pub = make_client(env[0])
        info = await pub.post(f"{API}/auth/invite-info", json={"token": token})
        assert info.json() == {"email": "kofi@a.test", "business_name": "Alpha", "role_name": "Employee", "suggested_name": None}
        c, r = await accept(env, token, full_name="Kofi Boateng")
        assert r.status_code == 201, r.text
        me = (await c.get(f"{API}/auth/me")).json()
        assert me["user"]["email"] == "kofi@a.test" and me["user"]["role"]["name"] == "Employee" and me["business"]["name"] == "Alpha"
        assert (await a.get(f"{API}/users/invites")).json()["items"] == []
        assert len((await a.get(f"{API}/users")).json()["items"]) == 2
        # single use
        _, again = await accept(env, token, full_name="Someone Else")
        assert again.status_code == 404
        assert (await pub.post(f"{API}/auth/invite-info", json={"token": token})).status_code == 404
        # the new login works with a password, and an Employee cannot manage staff
        assert (await c.get(f"{API}/users")).status_code == 403
        assert (await c.post(f"{API}/users/invites", json={"email": "x@a.test", "role_id": me["user"]["role"]["id"]})).status_code == 403
        await c.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_invite_links_employee_profile_and_rejects_bad_input(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        emp = (await a.post(f"{API}/employees", json={"full_name": "Efua Owusu"})).json()
        other_emp = (await b.post(f"{API}/employees", json={"full_name": "Beta Person"})).json()
        # another business's employee or role is refused without revealing it exists
        assert (await invite(a, "e@a.test", employee_id=other_emp["id"])).status_code == 422
        rs_b = await roles(b)
        r = await a.post(f"{API}/users/invites", json={"email": "e@a.test", "role_id": rs_b["Administrator"]["id"]})
        assert r.status_code == 422
        assert (await a.post(f"{API}/users/invites", json={"email": "not-an-email", "role_id": rs_b["Employee"]["id"]})).status_code == 422
        r = await invite(a, "efua@a.test", employee_id=emp["id"])
        assert r.status_code == 201
        pub = make_client(env[0])
        assert (await pub.post(f"{API}/auth/invite-info", json={"token": r.json()["token"]})).json()["suggested_name"] == "Efua Owusu"
        c, acc = await accept(env, r.json()["token"])  # name defaults to the employee's
        assert acc.status_code == 201 and acc.json()["user"]["full_name"] == "Efua Owusu"
        listed = (await a.get(f"{API}/employees")).json()["items"]
        assert [e for e in listed if e["id"] == emp["id"]][0]["has_login"] is True
        assert (await invite(a, "again@a.test", employee_id=emp["id"])).status_code == 409  # already has a login
        # weak password / missing name
        r2 = await invite(a, "new@a.test")
        _, bad = await accept(env, r2.json()["token"], password="short", full_name="Newbie")
        assert bad.status_code == 422
        _, noname = await accept(env, r2.json()["token"])
        assert noname.status_code == 422
        await c.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_duplicate_and_cross_tenant_emails_get_one_answer(env):
    a, a_id, b, _, _ = await two(env)
    try:
        existing = await invite(a, "a@a.test")  # already a user in this business
        other = await invite(a, "b@b.test")  # a user in ANOTHER business
        assert existing.status_code == other.status_code == 409 and existing.json() == other.json()
        assert (await invite(a, "new@a.test")).status_code == 201
        assert (await invite(a, "NEW@a.test")).status_code == 409  # pending already
        assert (await invite(b, "new@a.test")).status_code == 201  # a different business may invite the same address
    finally:
        await a.aclose(), await b.aclose()


async def test_expired_and_revoked_invites_do_not_work(env):
    a, a_id, b, _, factory = await two(env)
    try:
        t1 = (await invite(a, "old@a.test")).json()
        async with factory() as db:
            inv = (await db.execute(select(UserInvite))).scalar_one()
            inv.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await db.commit()
        _, r = await accept(env, t1["token"], full_name="Old Timer")
        assert r.status_code == 404
        assert (await a.get(f"{API}/users/invites")).json()["items"][0]["expired"] is True
        again = await invite(a, "old@a.test")  # expired invitation can be replaced
        assert again.status_code == 201
        # revoke
        assert (await b.delete(f"{API}/users/invites/{again.json()['id']}")).status_code == 404  # not B's
        assert (await a.delete(f"{API}/users/invites/{again.json()['id']}")).status_code == 204
        _, r = await accept(env, again.json()["token"], full_name="Old Timer")
        assert r.status_code == 404
        assert (await a.delete(f"{API}/users/invites/{again.json()['id']}")).status_code == 404
    finally:
        await a.aclose(), await b.aclose()


async def test_role_changes_and_disabling(env):
    a, a_id, b, _, factory = await two(env)
    try:
        t = (await invite(a, "staff@a.test")).json()["token"]
        c, _ = await accept(env, t, full_name="Staff Member")
        users = {u["email"]: u for u in (await a.get(f"{API}/users")).json()["items"]}
        staff, admin = users["staff@a.test"], users["a@a.test"]
        rs = await roles(a)
        assert (await c.get(f"{API}/departments")).status_code == 200
        # promote: takes effect on the very next request
        r = await a.patch(f"{API}/users/{staff['id']}", json={"role_id": rs["Administrator"]["id"]})
        assert r.status_code == 200 and r.json()["role"]["name"] == "Administrator"
        assert (await c.get(f"{API}/users")).status_code == 200
        # disable: signed out everywhere, cannot log back in
        assert (await a.patch(f"{API}/users/{staff['id']}", json={"status": "disabled"})).status_code == 200
        assert (await c.get(f"{API}/auth/me")).status_code == 401
        async with factory() as db:
            assert (await db.execute(select(AuthSession).where(AuthSession.user_id.is_not(None)))).scalars().all() != []
            assert not [s for s in (await db.execute(select(AuthSession))).scalars() if str(s.user_id) == staff["id"]]
        login_try = make_client(env[0])
        assert (await login_try.post(f"{API}/auth/login", json={"email": "staff@a.test", "password": "a-long-passphrase"})).status_code == 401
        # re-enable
        assert (await a.patch(f"{API}/users/{staff['id']}", json={"status": "active"})).status_code == 200
        # validation
        assert (await a.patch(f"{API}/users/{staff['id']}", json={"status": "invited"})).status_code == 422
        assert (await a.patch(f"{API}/users/{staff['id']}", json={"role_id": None})).status_code == 422
        assert (await a.patch(f"{API}/users/{staff['id']}", json={"role_id": (await roles(b))["Employee"]["id"]})).status_code == 422
        await c.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_self_and_last_admin_guards(env):
    a, a_id, b, _, factory = await two(env)
    try:
        me = (await a.get(f"{API}/auth/me")).json()["user"]
        rs = await roles(a)
        assert (await a.patch(f"{API}/users/{me['id']}", json={"status": "disabled"})).status_code == 409
        assert (await a.patch(f"{API}/users/{me['id']}", json={"role_id": rs["Employee"]["id"]})).status_code == 409
        # a second admin can demote the first, but not leave the business without any admin
        t = (await invite(a, "two@a.test", role="Administrator")).json()["token"]
        c, _ = await accept(env, t, full_name="Second Admin")
        assert (await c.patch(f"{API}/users/{me['id']}", json={"role_id": rs["Employee"]["id"]})).status_code == 200
        assert (await a.get(f"{API}/users")).status_code == 403  # demoted: effect is immediate
        await c.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_each_guard_holds_on_its_own(env):
    a, a_id, b, _, factory = await two(env)
    try:
        me = (await a.get(f"{API}/auth/me")).json()["user"]
        rs = await roles(a)
        # self guard alone: a second admin exists, so the last-admin rule is not what stops this
        t = (await invite(a, "two@a.test", role="Administrator")).json()["token"]
        c, _ = await accept(env, t, full_name="Second Admin")
        assert (await a.patch(f"{API}/users/{me['id']}", json={"status": "disabled"})).status_code == 409
        await c.aclose()
        await a.patch(f"{API}/users/{(await _id(a, 'two@a.test'))}", json={"status": "disabled"})
        # last-admin guard alone: a non-admin with users:write acts on the only admin
        await add_user(factory, a_id, "HR", ["users:write"], "hr@a.test")
        hr = await login(env, "hr@a.test")
        for change in ({"status": "disabled"}, {"role_id": rs["Employee"]["id"]}):
            r = await hr.patch(f"{API}/users/{me['id']}", json=change)
            assert r.status_code == 409 and "administrator" in r.json()["detail"]
        await hr.aclose()
    finally:
        await a.aclose(), await b.aclose()


async def test_users_are_tenant_isolated_and_need_permission(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        for c in (a, b):
            users = (await c.get(f"{API}/users")).json()["items"]
            assert len(users) == 1
        b_user = (await b.get(f"{API}/users")).json()["items"][0]
        assert (await a.patch(f"{API}/users/{b_user['id']}", json={"status": "disabled"})).status_code == 404
        assert (await b.get(f"{API}/auth/me")).status_code == 200
        await add_user(factory, a_id, "Reader", ["users:read"], "reader@a.test")
        r = await login(env, "reader@a.test")
        assert (await r.get(f"{API}/users")).status_code == 200
        assert (await r.get(f"{API}/roles")).status_code == 200
        assert (await r.post(f"{API}/users/invites", json={"email": "z@a.test", "role_id": (await roles(a))["Employee"]["id"]})).status_code == 403
        assert (await r.patch(f"{API}/users/{b_user['id']}", json={"status": "disabled"})).status_code == 403
        await r.aclose()
        unauth = make_client(env[0])
        assert (await unauth.get(f"{API}/users")).status_code == 401
        assert (await unauth.post(f"{API}/users/invites", json={})).status_code == 401
    finally:
        await a.aclose(), await b.aclose()


async def test_accept_endpoints_are_rate_limited_and_csrf_checked(env):
    pub = make_client(env[0])
    codes = [(await pub.post(f"{API}/auth/invite-info", json={"token": "x" * 30})).status_code for _ in range(7)]
    assert codes[:5] == [404] * 5 and codes[-1] == 429
    nohdr = make_client(env[0], origin=None)
    assert (await nohdr.post(f"{API}/auth/accept-invite", json={"token": "x" * 30, "password": "a-long-passphrase"})).status_code == 403

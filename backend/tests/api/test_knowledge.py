from uuid import uuid4

from sqlalchemy import select

from app.database.models import KnowledgeChunk
from app.services.knowledge import chunk_text, search_terms
from app.services.voice.database_gateway import DatabaseBusinessGateway
from tests.api.test_customers_cases import add_user, login, two

API = "/api/v1"
HOURS = "We are open Monday to Friday, 8am to 5pm. Closed on public holidays."
REFUNDS = "Refunds are issued within 14 days of a returned parcel.\n\nDamaged parcels need a photo as proof."


async def mk(c, title="Opening hours", content=HOURS, **kw):
    r = await c.post(f"{API}/knowledge", json={"title": title, "content": content, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_chunking_and_terms():
    assert chunk_text("") == [] and chunk_text("  \n\n ") == []
    assert chunk_text("One.\n\nTwo.") == ["One.\n\nTwo."]  # short paragraphs are packed together
    long = "word " * 600
    parts = chunk_text(long)
    assert len(parts) > 1 and all(len(p) <= 1100 for p in parts) and "".join(parts).replace(" ", "") == long.replace(" ", "")
    assert search_terms("What are your opening HOURS on Saturday?") == ["opening", "hours", "saturday"]
    assert search_terms("the a of") == [] and len(search_terms(" ".join(f"term{i}" for i in range(20)))) == 8


async def test_crud_and_chunks(env):
    a, a_id, b, _, factory = await two(env)
    try:
        d = await mk(a, "  Refund policy ", REFUNDS, category="Policies")
        assert d["title"] == "Refund policy" and d["status"] == "published" and d["chunks"] == 1 and d["content"] == REFUNDS
        assert (await a.get(f"{API}/knowledge/{d['id']}")).json()["category"] == "Policies"
        listing = (await a.get(f"{API}/knowledge")).json()
        assert listing["total"] == 1 and "content" not in listing["items"][0]
        assert (await a.get(f"{API}/knowledge", params={"q": "polic"})).json()["total"] == 1
        assert (await a.get(f"{API}/knowledge", params={"q": "%"})).json()["total"] == 0
        r = await a.patch(f"{API}/knowledge/{d['id']}", json={"content": "x" * 2000, "category": ""})
        assert r.status_code == 200 and r.json()["category"] is None and r.json()["chunks"] >= 2
        assert (await a.patch(f"{API}/knowledge/{d['id']}", json={"title": None})).status_code == 422
        assert (await a.post(f"{API}/knowledge", json={"title": "x", "content": "short"})).status_code == 422
        assert (await a.post(f"{API}/knowledge", json={"title": "Big", "content": "x" * 50_001})).status_code == 422
        assert (await a.delete(f"{API}/knowledge/{d['id']}")).status_code == 204
        assert (await a.get(f"{API}/knowledge/{d['id']}")).status_code == 404
        async with factory() as db:
            assert (await db.execute(select(KnowledgeChunk))).scalars().all() == []  # chunks go with the document
    finally:
        await a.aclose(), await b.aclose()


async def test_search_finds_the_right_passage_and_only_published(env):
    a, a_id, b, _, factory = await two(env)
    try:
        await mk(a)
        refunds = await mk(a, "Refund policy", REFUNDS)
        hits = (await a.get(f"{API}/knowledge/search", params={"q": "When are you open on friday?"})).json()["items"]
        assert hits and hits[0]["title"] == "Opening hours"
        hits = (await a.get(f"{API}/knowledge/search", params={"q": "refund for damaged parcel"})).json()["items"]
        assert hits[0]["title"] == "Refund policy" and len(hits) <= 3
        assert (await a.get(f"{API}/knowledge/search", params={"q": "zebra"})).json()["items"] == []
        assert (await a.get(f"{API}/knowledge/search", params={"q": "%%"})).json()["items"] == []
        await a.patch(f"{API}/knowledge/{refunds['id']}", json={"status": "archived"})
        assert (await a.get(f"{API}/knowledge/search", params={"q": "refund"})).json()["items"] == []
        await a.patch(f"{API}/knowledge/{refunds['id']}", json={"status": "published"})
        assert (await a.get(f"{API}/knowledge/search", params={"q": "refund"})).json()["items"] != []
    finally:
        await a.aclose(), await b.aclose()


async def test_tenant_isolation(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        secret = await mk(a, "Alpha internal", "The vault code procedure is confidential to Alpha.")
        assert (await b.get(f"{API}/knowledge/{secret['id']}")).status_code == 404
        assert (await b.patch(f"{API}/knowledge/{secret['id']}", json={"title": "Hijacked"})).status_code == 404
        assert (await b.delete(f"{API}/knowledge/{secret['id']}")).status_code == 404
        assert (await b.get(f"{API}/knowledge")).json()["total"] == 0
        assert (await b.get(f"{API}/knowledge/search", params={"q": "vault code"})).json()["items"] == []
        assert (await a.get(f"{API}/knowledge/{secret['id']}")).json()["title"] == "Alpha internal"
        gw = DatabaseBusinessGateway(factory, lambda *_: None)
        mine = await gw.execute(business_id=a_id, session_id=uuid4(), tool_name="search_knowledge", arguments={"query": "vault code"})
        theirs = await gw.execute(business_id=b_id, session_id=uuid4(), tool_name="search_knowledge", arguments={"query": "vault code"})
        assert "confidential to Alpha" in mine.summary and mine.data["results"] == ["Alpha internal"]
        assert "No matching information" in theirs.summary and theirs.data == {"results": []}
    finally:
        await a.aclose(), await b.aclose()


async def test_gateway_tool_is_bounded_and_validates(env):
    a, a_id, b, _, factory = await two(env)
    try:
        for i in range(6):
            await mk(a, f"Parcel note {i}", "parcel " * 400)
        gw = DatabaseBusinessGateway(factory, lambda *_: None)
        res = await gw.execute(business_id=a_id, session_id=uuid4(), tool_name="search_knowledge", arguments={"query": "parcel"})
        assert res.ok and len(res.data["results"]) == 3 and len(res.summary) <= 3 * 900 + 4
        bad = await gw.execute(business_id=a_id, session_id=uuid4(), tool_name="search_knowledge", arguments={"query": "x"})
        assert not bad.ok
    finally:
        await a.aclose(), await b.aclose()


async def test_permissions(env):
    a, a_id, b, _, factory = await two(env)
    try:
        d = await mk(a)
        await add_user(factory, a_id, "Reader", ["knowledge:read"], "r@a.test")
        await add_user(factory, a_id, "Nobody", ["cases:read"], "n@a.test")
        r, n = await login(env, "r@a.test"), await login(env, "n@a.test")
        assert (await r.get(f"{API}/knowledge")).status_code == 200
        assert (await r.get(f"{API}/knowledge/search", params={"q": "hours"})).status_code == 200
        assert (await r.post(f"{API}/knowledge", json={"title": "Nope", "content": "not allowed"})).status_code == 403
        assert (await r.patch(f"{API}/knowledge/{d['id']}", json={"title": "Nope"})).status_code == 403
        assert (await r.delete(f"{API}/knowledge/{d['id']}")).status_code == 403
        assert (await n.get(f"{API}/knowledge")).status_code == 403
        assert (await n.get(f"{API}/knowledge/search", params={"q": "hours"})).status_code == 403
        await r.aclose(), await n.aclose()
    finally:
        await a.aclose(), await b.aclose()

from app.api.v1.voice import _business_context
from app.services.voice.business_context import MAX_CHARS, build_business_context, describe_hours
from tests.api.test_business_profile import FULL
from tests.api.test_customers_cases import two

API = "/api/v1"
PROFILE = {**FULL, "timezone": "Africa/Accra", "contact_email": "hello@alpha.test"}


def test_hours_in_plain_words():
    assert describe_hours(None) is None
    assert describe_hours({}) == "closed every day"
    assert describe_hours({"mon": [["08:00", "12:00"], ["13:00", "17:00"]]}) == "Monday 08:00 to 12:00 and 13:00 to 17:00"


def test_context_contains_profile_and_department_hours():
    t = build_business_context(name="Alpha", profile=PROFILE, departments=[
        {"name": "Sales", "hours": None, "timezone": None}, {"name": "Accounts", "hours": {"tue": [["09:00", "10:00"]]}, "timezone": "Africa/Accra"}])
    for want in ("Alpha", "We sell phones.", "Twi", "Monday 08:00 to 17:00", "hello@alpha.test", "Refunds", "Within 7 days", "friendly",
                 "- Sales (always open)", "- Accounts (Tuesday 09:00 to 10:00, Africa/Accra time)"):
        assert want in t, want


def test_unstated_hours_are_not_invented():
    t = build_business_context(name="Alpha", profile={**PROFILE, "hours": None}, departments=[])
    assert "Business hours" not in t


def test_contact_masking_removes_phone_and_email_everywhere():
    t = build_business_context(name="Alpha", profile={**PROFILE, "description": "Call 0241234567 or mail me@x.com"}, departments=[], redact_contacts=True)
    for leak in ("hello@alpha.test", "233 24 123 4567", "233201112222", "0241234567", "me@x.com"):
        assert leak not in t, leak
    assert "Oxford St" in t   # addresses are business-authored and stay


def test_card_numbers_are_removed_even_with_masking_off():
    t = build_business_context(name="A", profile={"description": "Pay to 4111 1111 1111 1111"}, departments=[])
    assert "4111" not in t


def test_context_is_capped():
    t = build_business_context(name="A", profile={"policies": [{"title": f"P{i}", "text": "x" * 1500} for i in range(30)]}, departments=[])
    assert len(t) <= MAX_CHARS + 80


def test_staff_and_other_private_data_have_no_way_in():
    t = build_business_context(name="A", profile=PROFILE, departments=[{"name": "Sales", "hours": None, "timezone": None, "employees": ["Kwame"], "extension": "123"}])
    assert "Kwame" not in t and "extension" not in t.lower()


async def test_context_comes_from_own_business_only(env):
    a, a_id, b, b_id, factory = await two(env)
    try:
        assert (await a.put(f"{API}/business/profile", json=PROFILE)).status_code == 200
        async with factory() as db:
            ca = await _business_context(db, a_id, "Alpha Trading")
            cb = await _business_context(db, b_id, "Beta")
        assert "We sell phones." in ca and "Refunds" in ca
        assert "Beta" in cb and "phones" not in cb and "Refunds" not in cb and "Alpha" not in cb
    finally:
        await a.aclose(); await b.aclose()

"""
Builds the business information the assistant is given, from the organisation profile and its departments.

Data minimisation: only what the business itself wrote for customers goes in (name, what it does, languages, hours,
branches, policies, service preferences, department names and hours). Staff names, extensions, phone numbers of
employees, customers and callbacks are never included. Contact details of the business are left out when the business
has switched on contact-detail masking, and the finished text is passed through the same redaction used for caller speech.
The text is capped so a very long policy cannot crowd out the safety rules.
"""

from __future__ import annotations

from typing import Any

from app.services.voice.privacy import redact_for_provider

MAX_CHARS = 6000
_DAYS = (("mon", "Monday"), ("tue", "Tuesday"), ("wed", "Wednesday"), ("thu", "Thursday"), ("fri", "Friday"), ("sat", "Saturday"), ("sun", "Sunday"))


def describe_hours(hours: Any) -> str | None:
    """Plain words for stored hours. None means the business never stated any, so nothing is quoted."""
    if hours is None:
        return None
    if not isinstance(hours, dict):
        return None
    parts = []
    for key, label in _DAYS:
        spans = hours.get(key) or []
        if spans:
            parts.append(f"{label} " + " and ".join(f"{s[0]} to {s[1]}" for s in spans))
    return "; ".join(parts) if parts else "closed every day"


def build_business_context(
    *, name: str, profile: dict[str, Any] | None, departments: list[dict[str, Any]], redact_contacts: bool = False,
) -> str:
    p = profile or {}
    lines = [f"Business name: {name}."]
    if p.get("industry"):
        lines.append(f"Industry: {p['industry']}.")
    if p.get("description"):
        lines.append(f"About the business: {p['description']}")
    if p.get("languages"):
        lines.append("Customers use: " + ", ".join(p["languages"]) + ".")
    hours = describe_hours(p.get("hours"))
    if hours:
        lines.append(f"Business hours ({p.get('timezone') or 'UTC'} time): {hours}.")
    if not redact_contacts:
        contact = [f"{label} {p[k]}" for k, label in (("contact_phone", "phone"), ("contact_email", "email"), ("website", "website")) if p.get(k)]
        if contact:
            lines.append("Business contact: " + ", ".join(contact) + ".")
    if p.get("address"):
        lines.append(f"Main address: {p['address']}.")
    for b in p.get("branches") or []:
        extra = ", ".join(x for x in (b.get("address"), None if redact_contacts else b.get("phone")) if x)
        lines.append(f"Branch {b['name']}" + (f": {extra}." if extra else "."))
    if departments:
        lines.append("Departments:")
        for d in departments:
            dh = "always open" if d.get("hours") is None else describe_hours(d["hours"])
            tz = f", {d['timezone']} time" if d.get("timezone") and d.get("hours") is not None else ""
            lines.append(f"- {d['name']} ({dh}{tz})")
    for pol in p.get("policies") or []:
        lines.append(f"Policy, {pol['title']}: {pol['text']}")
    pref = p.get("preferences") or {}
    if pref.get("tone"):
        lines.append(f"Speak in a {pref['tone']} tone.")
    if pref.get("greeting"):
        lines.append(f"Preferred greeting: {pref['greeting']}")
    if pref.get("after_hours_message"):
        lines.append(f"When the business is closed, say: {pref['after_hours_message']}")
    if pref.get("escalation_note"):
        lines.append(f"When to bring in a person: {pref['escalation_note']}")
    text = redact_for_provider("\n".join(lines), contact_details=redact_contacts)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS].rsplit("\n", 1)[0] + "\n(Some details were left out because they were too long.)"

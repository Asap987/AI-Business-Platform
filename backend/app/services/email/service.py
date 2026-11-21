"""Email the platform sends, built on a swappable provider.

Rules: a failed email never fails the action that triggered it (the caller gets False); the log line names the
template and the provider only, never an address, a token or a body; links carry tokens in the URL fragment so
they are not sent to servers in referrers or access logs.
"""

from __future__ import annotations

import logging
from html import escape

from app.core.config import Settings
from app.services.email.base import EmailError, EmailMessage, EmailProvider
from app.services.email.resend import ResendProvider

log = logging.getLogger("app.email")


class EmailService:
    def __init__(self, provider: EmailProvider | None, sender: str | None, base_url: str, *, product: str = "KASORA AI"):
        self._provider = provider
        self._sender = sender
        self._base = base_url.rstrip("/")
        self._product = product

    @property
    def enabled(self) -> bool:
        return self._provider is not None and bool(self._sender)

    async def _send(self, template: str, message: EmailMessage) -> bool:
        if not self.enabled:
            log.info("email %s not sent: email provider is not configured", template)
            return False
        try:
            await self._provider.send(self._sender, message)  # type: ignore[union-attr]
        except EmailError as exc:
            log.warning("email %s failed via %s: %s", template, self._provider.name, exc)  # type: ignore[union-attr]
            return False
        log.info("email %s sent via %s", template, self._provider.name)  # type: ignore[union-attr]
        return True

    def _wrap(self, heading: str, paragraphs: list[str], button: tuple[str, str] | None, footer: str) -> tuple[str, str]:
        text = "\n\n".join([heading, *paragraphs] + ([f"{button[0]}: {button[1]}"] if button else []) + [footer])
        body = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
        btn = (f'<p><a href="{escape(button[1], quote=True)}" style="display:inline-block;padding:10px 18px;background:#0f3d3e;'
               f'color:#fff;border-radius:8px;text-decoration:none">{escape(button[0])}</a></p>'
               f'<p style="font-size:12px;color:#555">If the button does not work, copy this link into your browser:<br>{escape(button[1])}</p>') if button else ""
        html = (f'<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#111"><h2>{escape(heading)}</h2>'
                f'{body}{btn}<p style="font-size:12px;color:#555">{escape(footer)}</p></div>')
        return text, html

    async def send_invite(self, to: str, business_name: str, role_name: str, token: str, days: int) -> bool:
        link = f"{self._base}/accept-invite#token={token}"
        text, html = self._wrap(
            f"Join {business_name} on {self._product}",
            [f"You have been invited to join {business_name} as {role_name}.", f"This invitation works once and expires in {days} days."],
            ("Accept invitation", link), "If you were not expecting this, ignore this email.")
        return await self._send("invite", EmailMessage(to, f"You're invited to {business_name} on {self._product}", text, html))

    async def send_password_reset(self, to: str, token: str, minutes: int) -> bool:
        link = f"{self._base}/reset-password#token={token}"
        text, html = self._wrap(
            "Reset your password",
            ["Someone asked to reset the password for this account.", f"The link works once and expires in {minutes} minutes."],
            ("Choose a new password", link), "If this was not you, ignore this email; your password has not changed.")
        return await self._send("password_reset", EmailMessage(to, f"Reset your {self._product} password", text, html))

    async def send_password_changed_notice(self, to: str) -> bool:
        text, html = self._wrap(
            "Your password was changed",
            ["The password for your account was just changed and you were signed out everywhere.",
             "If you did not do this, use \"Forgot password\" at once and tell your administrator."],
            None, f"This is a security notice from {self._product}.")
        return await self._send("password_changed", EmailMessage(to, f"Your {self._product} password was changed", text, html))


def build_email_service(settings: Settings) -> EmailService:
    """Off unless EMAIL_PROVIDER=resend, RESEND_API_KEY and EMAIL_FROM (a verified sending domain) are all set."""
    provider: EmailProvider | None = None
    if settings.email_provider == "resend" and settings.resend_api_key is not None:
        provider = ResendProvider(settings.resend_api_key.get_secret_value(), timeout=settings.email_timeout_seconds)
    return EmailService(provider, settings.email_from, settings.app_base_url)

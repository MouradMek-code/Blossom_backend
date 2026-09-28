"""Plain emails through Brevo (the service that already sends sign-up codes).
Sent after the response; never raises - a failed email must not break the
action that sent it."""
import logging
import os

import sib_api_v3_sdk

log = logging.getLogger(__name__)
SENDER = {"name": "Blossom", "email": "mourad.meknioui@gmail.com"}


def send_email(to: str, subject: str, html: str, reply_to: dict = None) -> bool:
    api_key = os.getenv("BREVO_API_KEY")
    if not to or not api_key:
        log.warning("Email to %s not sent: %s", to, "no address" if not to else "no BREVO_API_KEY")
        return False
    try:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key["api-key"] = api_key
        api = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        email = sib_api_v3_sdk.SendSmtpEmail(to=[{"email": to}], sender=SENDER, subject=subject, html_content=html)
        if reply_to:
            email.reply_to = reply_to  # "Reply" answers the person who wrote
        api.send_transac_email(email)
        return True
    except Exception as exc:  # network, quota, bad address...
        log.warning("Email to %s failed: %s", to, exc)
        return False


def card(title: str, paragraphs, button=None) -> str:
    """The Blossom-styled email body: a title, paragraphs (HTML allowed),
    an optional (label, url) button."""
    body = "".join(f'<p style="margin:0 0 14px;font-size:15px;line-height:1.55;color:#3a302b;">{p}</p>' for p in paragraphs)
    cta = ""
    if button:
        label, url = button
        cta = (f'<p style="margin:22px 0 6px;"><a href="{url}" style="background:#c1466b;color:#fff;'
               f'text-decoration:none;padding:13px 22px;border-radius:999px;font-weight:bold;">{label}</a></p>')
    return (
        '<div style="background:#fbf1f4;padding:28px 14px;font-family:Arial,sans-serif;">'
        '<div style="max-width:560px;margin:auto;background:#fff;border-radius:18px;padding:32px 26px;">'
        '<div style="font-size:34px;">🌸</div>'
        f'<h1 style="color:#c1466b;font-size:22px;margin:8px 0 18px;">{title}</h1>'
        f"{body}{cta}"
        '<p style="margin:26px 0 0;font-size:12px;color:#8a7e76;">Blossom · blossom-date.com</p>'
        "</div></div>"
    )

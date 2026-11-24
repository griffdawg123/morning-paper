"""Email the EPUB to Send to Kindle.

Amazon only accepts mail from addresses on the account's "Approved Personal
Document E-mail List" (Manage Content & Devices > Preferences > Personal
Document Settings). EPUB is accepted directly; the limit is 50 MB.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

log = logging.getLogger(__name__)


def can_send(cfg: dict) -> bool:
    d = cfg["delivery"]
    return bool(d.get("smtp_user") and d.get("smtp_password") and d.get("to"))


def send(cfg: dict, path: Path, subject: str) -> None:
    d = cfg["delivery"]
    msg = EmailMessage()
    msg["From"] = d.get("from") or d["smtp_user"]
    msg["To"] = ", ".join(d["to"])
    msg["Subject"] = subject
    msg.set_content(f"{subject}\n\nAttached: {path.name}\n")
    msg.add_attachment(path.read_bytes(), maintype="application", subtype="epub+zip", filename=path.name)

    host, port = d["smtp_host"], int(d["smtp_port"])
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=60) as s:
            s.login(d["smtp_user"], d["smtp_password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=context)
            s.login(d["smtp_user"], d["smtp_password"])
            s.send_message(msg)
    log.info("deliver: sent %s to %d recipient(s)", path.name, len(d["to"]))

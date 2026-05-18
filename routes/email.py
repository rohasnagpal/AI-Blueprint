import email
import imaplib
import json
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import database
from routes.chats import _get_persona, _parse_sse, _stream_general, _stream_local, _stream_openai

router = APIRouter()


class DraftIn(BaseModel):
    persona_id: str | None = None
    doc_context: str = "none"
    instructions: str = ""


class SendIn(BaseModel):
    draft_body: str | None = None
    approved: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _body_from_message(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in (part.get("Content-Disposition") or ""):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
        for part in msg.walk():
            if part.get_content_type() == "text/html" and "attachment" not in (part.get("Content-Disposition") or ""):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
        return ""
    payload = msg.get_payload(decode=True)
    if not payload:
        return str(msg.get_payload() or "").strip()
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace").strip()


def _format_email(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "from_email": row["from_email"],
        "to_email": row["to_email"],
        "subject": row["subject"],
        "body": row["body"],
        "received_at": row["received_at"],
        "status": row["status"],
        "persona_id": row["persona_id"],
        "doc_context": row["doc_context"],
        "draft_body": row["draft_body"],
        "sent_at": row["sent_at"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _settings() -> dict:
    settings = database.get_all_settings()
    for key in database.API_KEY_FIELDS:
        settings[key] = database.get_setting(key)
    return settings


@router.get("/email/messages")
async def list_email_messages():
    conn = database.get_connection()
    rows = conn.execute(
        "SELECT * FROM email_messages ORDER BY received_at DESC, created_at DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return [_format_email(row) for row in rows]


@router.post("/email/poll")
async def poll_email():
    settings = _settings()
    host = settings.get("email_imap_host", "").strip()
    username = settings.get("email_imap_username", "").strip()
    password = settings.get("email_imap_password", "")
    folder = settings.get("email_imap_folder", "INBOX") or "INBOX"
    port = int(settings.get("email_imap_port") or 993)
    if not host or not username or not password:
        raise HTTPException(400, detail="IMAP host, username, and password are required.")

    imported = 0
    now = _now()
    try:
        with imaplib.IMAP4_SSL(host, port) as imap:
            imap.login(username, password)
            imap.select(folder)
            typ, data = imap.uid("search", None, "UNSEEN")
            if typ != "OK":
                raise RuntimeError("IMAP search failed.")
            uids = (data[0] or b"").split()[-25:]
            for uid in uids:
                typ, msg_data = imap.uid("fetch", uid, "(RFC822)")
                if typ != "OK" or not msg_data:
                    continue
                raw = next((part[1] for part in msg_data if isinstance(part, tuple)), None)
                if not raw:
                    continue
                msg = email.message_from_bytes(raw)
                message_id = msg.get("Message-ID") or f"{host}:{uid.decode()}"
                conn = database.get_connection()
                exists = conn.execute("SELECT id FROM email_messages WHERE message_id = ?", (message_id,)).fetchone()
                if exists:
                    conn.close()
                    continue
                from_email = ", ".join(addr for _, addr in getaddresses([msg.get("From", "")]))
                to_email = ", ".join(addr for _, addr in getaddresses([msg.get("To", "")]))
                subject = _decode(msg.get("Subject"))
                try:
                    received_at = parsedate_to_datetime(msg.get("Date")).astimezone(timezone.utc).isoformat()
                except Exception:
                    received_at = now
                conn.execute(
                    """
                    INSERT INTO email_messages
                    (id, imap_uid, message_id, from_email, to_email, subject, body, received_at, status,
                     persona_id, doc_context, draft_body, sent_at, error, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        uid.decode(),
                        message_id,
                        from_email,
                        to_email,
                        subject,
                        _body_from_message(msg)[:100_000],
                        received_at,
                        settings.get("email_persona_id", ""),
                        settings.get("email_doc_context", "none"),
                        now,
                        now,
                    ),
                )
                conn.commit()
                conn.close()
                imported += 1
            imap.logout()
    except Exception as exc:
        raise HTTPException(400, detail=f"Email poll failed: {exc}")

    return {"imported": imported}


@router.post("/email/messages/{message_id}/draft")
async def draft_email(message_id: str, body: DraftIn):
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM email_messages WHERE id = ?", (message_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, detail="Email not found")

    settings = _settings()
    persona_id = body.persona_id if body.persona_id is not None else (row["persona_id"] or settings.get("email_persona_id", ""))
    doc_context = body.doc_context or row["doc_context"] or settings.get("email_doc_context", "none")
    persona = _get_persona(persona_id)
    prompt = (
        "Draft a professional email reply. Do not invent facts. If the email asks for something that requires "
        "human approval, say what should be reviewed before sending. Return only the email body.\n\n"
        f"From: {row['from_email']}\n"
        f"Subject: {row['subject']}\n\n"
        f"Incoming email:\n{row['body']}\n"
    )
    if body.instructions:
        prompt += f"\nAdditional drafting instructions:\n{body.instructions}\n"

    use_documents = doc_context != "none"
    doc_ids = None if doc_context in ("all", "none") else [d.strip() for d in doc_context.split(",") if d.strip()]
    provider_name = settings.get("rag_provider", "openai")

    content = []
    sources = []
    try:
        if not use_documents:
            stream = _stream_general(prompt, settings, persona)
        elif provider_name == "openai":
            stream = _stream_openai({"id": message_id, "thread_id": None}, prompt, settings, doc_ids, persona)
        else:
            stream = _stream_local(prompt, settings, doc_ids, persona)
        async for event in stream:
            data = _parse_sse(event)
            if not data:
                continue
            if data.get("type") == "token":
                content.append(data.get("content", ""))
            elif data.get("type") == "source":
                sources.append(data)
            elif data.get("type") == "error":
                raise RuntimeError(data.get("content", "Draft failed."))
    except Exception as exc:
        now = _now()
        conn = database.get_connection()
        conn.execute("UPDATE email_messages SET error = ?, updated_at = ? WHERE id = ?", (str(exc), now, message_id))
        conn.commit()
        conn.close()
        raise HTTPException(400, detail=str(exc))

    draft = "".join(content).strip()
    now = _now()
    conn = database.get_connection()
    conn.execute(
        """
        UPDATE email_messages
        SET draft_body = ?, status = 'drafted', persona_id = ?, doc_context = ?, error = NULL, updated_at = ?
        WHERE id = ?
        """,
        (draft, persona_id or "", doc_context, now, message_id),
    )
    conn.commit()
    conn.close()
    return {"draft_body": draft, "sources": sources}


@router.post("/email/messages/{message_id}/send")
async def send_email(message_id: str, body: SendIn):
    if not body.approved:
        raise HTTPException(400, detail="Human approval is required before sending email.")
    settings = _settings()
    smtp_host = settings.get("email_smtp_host", "mail.smtp2go.com").strip()
    smtp_port = int(settings.get("email_smtp_port") or 2525)
    verify_tls = settings.get("email_smtp_verify_tls", "true") != "false"
    smtp_username = settings.get("email_smtp_username", "").strip()
    smtp_password = settings.get("email_smtp_password", "")
    from_address = settings.get("email_from_address", "").strip() or smtp_username
    if not smtp_host or not smtp_username or not smtp_password or not from_address:
        raise HTTPException(400, detail="SMTP2GO host, username, password, and from address are required.")

    conn = database.get_connection()
    row = conn.execute("SELECT * FROM email_messages WHERE id = ?", (message_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, detail="Email not found")
    draft = (body.draft_body or row["draft_body"] or "").strip()
    if not draft:
        raise HTTPException(400, detail="Draft body is empty.")

    msg = EmailMessage()
    msg["From"] = from_address
    msg["To"] = row["from_email"]
    msg["Subject"] = row["subject"] if (row["subject"] or "").lower().startswith("re:") else f"Re: {row['subject'] or ''}".strip()
    msg.set_content(draft)

    try:
        context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.starttls(context=context)
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(msg)
    except Exception as exc:
        now = _now()
        conn = database.get_connection()
        conn.execute("UPDATE email_messages SET error = ?, updated_at = ? WHERE id = ?", (str(exc), now, message_id))
        conn.commit()
        conn.close()
        raise HTTPException(400, detail=str(exc))

    now = _now()
    conn = database.get_connection()
    conn.execute(
        "UPDATE email_messages SET draft_body = ?, status = 'sent', sent_at = ?, error = NULL, updated_at = ? WHERE id = ?",
        (draft, now, now, message_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/email/messages/{message_id}")
async def delete_email_message(message_id: str):
    conn = database.get_connection()
    row = conn.execute("SELECT id FROM email_messages WHERE id = ?", (message_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, detail="Email not found")
    conn.execute("DELETE FROM email_messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

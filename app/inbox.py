"""IMAP email listener for draft approvals and mobile reply edits."""
import email
import email.message
from email.header import decode_header
import imaplib
import logging
import re

from app.config import get_settings
from app.db import Draft, DraftStatus, session

log = logging.getLogger(__name__)

# Keywords for simple approvals/rejections
APPROVE_KEYWORDS = {"yes", "y", "approve", "approved", "ok", "okay", "post", "post it", "publish", "lgtm", "done"}
REJECT_KEYWORDS = {"no", "n", "reject", "rejected", "skip", "cancel", "dont post", "don't post"}


def _decode_str(header_val: str) -> str:
    """Decode encoded email headers (e.g. UTF-8 / Base64)."""
    if not header_val:
        return ""
    parts = decode_header(header_val)
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded)


def _extract_reply_text(body: str) -> str:
    """Strip quoted email thread history, signatures, and dividers."""
    if not body:
        return ""

    # Split on multiline reply dividers like "On ... wrote:" or "-----Original Message-----"
    split_patterns = [
        r"(?:\r?\n)+\s*On\s+[\s\S]*?wrote:\s*",
        r"(?:\r?\n)+[-_\s]*Original Message[-_\s]*",
        r"(?:\r?\n)+_{10,}",
        r"(?:\r?\n)+Sent from my (?:iPhone|iPad|Galaxy|phone|Android)",
        r"(?:\r?\n)+Get Outlook for (?:iOS|Android)",
    ]
    cleaned = body
    for pat in split_patterns:
        cleaned = re.split(pat, cleaned, flags=re.IGNORECASE)[0]

    # Strip any remaining lines starting with '>' (quoted text)
    lines = []
    for line in cleaned.splitlines():
        trimmed = line.strip()
        if trimmed.startswith(">"):
            continue
        lines.append(line)

    return "\n".join(lines).strip()


def _get_body_from_message(msg: email.message.Message) -> str:
    """Extract plain text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def check_email_replies() -> list[dict]:
    """Connect to Gmail IMAP, search for unseen replies to daily drafts, and update database.

    Actions:
      - Reply 'YES' / 'APPROVE' -> Status becomes APPROVED
      - Reply 'NO' / 'REJECT' -> Status becomes REJECTED
      - Reply with modified text (15+ words) -> Updates draft text with phone edits and sets status to APPROVED!
      - Reply with feedback instruction -> Rewrites draft via Ollama and sends back revised email!
    """
    settings = get_settings()
    username = settings.gmail_address
    password = settings.gmail_app_password

    if not username or not password:
        log.debug("Gmail credentials not configured. Skipping IMAP reply check.")
        return []

    results = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=15)
        mail.login(username, password)
        mail.select("INBOX")

        # Search for unseen emails
        status, search_data = mail.search(None, "UNSEEN")
        if status != "OK" or not search_data or not search_data[0]:
            mail.logout()
            return []

        message_ids = search_data[0].split()
        log.info("Found %d unread email(s) in Gmail inbox", len(message_ids))

        for msg_id in message_ids:
            res, msg_data = mail.fetch(msg_id, "(RFC822)")
            if res != "OK" or not msg_data:
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            subject = _decode_str(msg.get("Subject", ""))
            sender = _decode_str(msg.get("From", ""))

            # Check if this email is a reply to a draft
            match = re.search(r"#(\d+)", subject)
            if not match:
                continue

            draft_id = int(match.group(1))
            raw_body = _get_body_from_message(msg)
            reply_text = _extract_reply_text(raw_body)

            if not reply_text:
                continue

            log.info("Received reply for Draft #%d from %s: %r", draft_id, sender, reply_text[:80])

            # Check first word or full normalized command
            first_word = reply_text.strip().split()[0].lower().rstrip("!.,;:") if reply_text.strip() else ""
            clean_cmd = re.sub(r"[^a-zA-Z\s]", "", reply_text).strip().lower()

            with session() as s:
                draft = s.get(Draft, draft_id)
                if not draft:
                    log.warning("Draft #%d not found in database", draft_id)
                    continue

                action = None
                if first_word in APPROVE_KEYWORDS or clean_cmd in APPROVE_KEYWORDS:
                    draft.status = DraftStatus.APPROVED
                    action = "approved_as_is"
                    log.info("Draft #%d approved via email reply 'YES'!", draft_id)
                elif first_word in REJECT_KEYWORDS or clean_cmd in REJECT_KEYWORDS:
                    draft.status = DraftStatus.REJECTED
                    action = "rejected"
                    log.info("Draft #%d rejected via email reply 'NO'", draft_id)
                elif len(reply_text.split()) >= 100:
                    # User edited the post directly on their phone!
                    draft.text = reply_text
                    draft.word_count = len(reply_text.split())
                    draft.status = DraftStatus.APPROVED
                    action = "edited_from_phone_and_approved"
                    log.info("Draft #%d updated with edits from phone (%d words) and approved!", draft_id, draft.word_count)
                else:
                    # User provided revision instructions (e.g. "make it punchier", "change hook")
                    log.info("Draft #%d received conversational revision feedback: %r", draft_id, reply_text)
                    try:
                        import asyncio
                        from app.writer import revise_post
                        from app.mailer import send_draft_email
                        revised_text = asyncio.run(revise_post(draft.text, reply_text, topic=draft.topic or ""))
                        if revised_text:
                            draft.text = revised_text
                            draft.word_count = len(revised_text.split())
                            action = "revised_via_ai"
                            log.info("Draft #%d successfully revised with AI! Re-sending updated email.", draft_id)
                    except Exception as rev_err:
                        log.exception("Failed to revise Draft #%d with AI: %r", draft_id, rev_err)

                if action:
                    s.add(draft)
                    s.commit()
                    s.refresh(draft)
                    results.append({"draft_id": draft_id, "action": action, "status": draft.status})
                    # Mark email as read
                    mail.store(msg_id, "+FLAGS", "\\Seen")

                    # If revised, send an updated preview email to the user so they can review the new version
                    if action == "revised_via_ai":
                        try:
                            from app.mailer import send_draft_email
                            send_draft_email(draft)
                        except Exception as send_err:
                            log.exception("Failed to send revised email for Draft #%d: %r", draft_id, send_err)

        mail.logout()
    except Exception as e:
        log.exception("Error checking email replies via IMAP: %r", e)

    return results

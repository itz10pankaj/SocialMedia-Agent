import html
import logging
import smtplib
import socket
import ssl
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings
from app.db import Draft

log = logging.getLogger(__name__)


def _get_dashboard_url() -> str:
    try:
        ip = socket.gethostbyname(socket.gethostname())
        return f"http://{ip}:8000"
    except Exception:
        return "http://localhost:8000"


def _generate_html(draft: Draft, to_email: str) -> str:
    """Generate a responsive, beautifully styled HTML email template."""
    topic_escaped = html.escape(draft.topic or "Tech News Discovery")
    angle_escaped = html.escape(draft.angle or "")
    
    # Format post text paragraphs
    paragraphs = [p.strip() for p in (draft.text or "").split("\n\n") if p.strip()]
    paragraphs_html = "".join(f'<p style="margin: 0 0 16px 0; font-size: 15px; line-height: 1.7; color: #e2e8f0;">{html.escape(p)}</p>' for p in paragraphs)

    # Format sources
    sources_html = ""
    if draft.sources:
        items = []
        for s in draft.sources:
            s_title = html.escape(s.get("title", s.get("url", "Link")))
            s_url = s.get("url", "#")
            s_src = html.escape(s.get("source", "web"))
            items.append(
                f'<li style="margin-bottom: 6px;">'
                f'<span style="background: rgba(99, 102, 241, 0.2); color: #a5b4fc; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase;">{s_src}</span> '
                f'<a href="{s_url}" style="color: #38bdf8; text-decoration: none; font-size: 13px;">{s_title}</a>'
                f'</li>'
            )
        sources_html = (
            f'<div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #334155;">'
            f'<div style="font-size: 12px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;">Source Stories</div>'
            f'<ul style="margin: 0; padding-left: 18px; color: #94a3b8;">{"".join(items)}</ul>'
            f'</div>'
        )

    settings = get_settings()
    sender = settings.gmail_address
    subject_raw = f"Re: ⚡ Daily LinkedIn Draft #{draft.id}: {draft.topic}"
    subject_quoted = urllib.parse.quote(subject_raw)
    draft_body_quoted = urllib.parse.quote(draft.text or "")
    approve_mailto = f"mailto:{sender}?subject={subject_quoted}&body=YES"
    edit_mailto = f"mailto:{sender}?subject={subject_quoted}&body={draft_body_quoted}"

    dashboard_url = _get_dashboard_url()
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LinkedIn Draft #{draft.id}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0b0f19; padding: 30px 15px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" width="100%" style="max-width: 620px; background-color: #161f30; border: 1px solid #29354d; border-radius: 14px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);" cellspacing="0" cellpadding="0">
          
          <!-- Top Gradient Accent -->
          <tr>
            <td style="height: 4px; background: linear-gradient(90deg, #6366f1, #06b6d4, #10b981);"></td>
          </tr>

          <!-- Header -->
          <tr>
            <td style="padding: 24px 28px 16px 28px; border-bottom: 1px solid #232e42;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <span style="display: inline-block; background: linear-gradient(135deg, #6366f1, #4f46e5); color: #ffffff; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; letter-spacing: 0.02em;">⚡ SOCIAL AGENT</span>
                    <h1 style="margin: 10px 0 4px 0; font-size: 20px; font-weight: 700; color: #ffffff;">Daily LinkedIn Draft</h1>
                    <p style="margin: 0; font-size: 13px; color: #94a3b8;">Review, edit, and approve your automated post</p>
                  </td>
                  <td align="right" valign="top">
                    <span style="display: inline-block; background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 700;">#{draft.id} {draft.status}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Context Callout Banner -->
          <tr>
            <td style="padding: 20px 28px 10px 28px;">
              <div style="background-color: #0f172a; border-left: 3px solid #6366f1; padding: 12px 16px; border-radius: 0 8px 8px 0;">
                <div style="font-size: 14px; font-weight: 700; color: #ffffff; margin-bottom: 4px;">📌 {topic_escaped}</div>
                <div style="font-size: 12px; color: #94a3b8; font-style: italic;">{angle_escaped}</div>
              </div>
            </td>
          </tr>

          <!-- Post Content -->
          <tr>
            <td style="padding: 16px 28px;">
              <div style="background-color: #1e293b; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 22px; position: relative;">
                <div style="font-size: 11px; font-weight: 700; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 14px;">LinkedIn Post Preview ({draft.word_count} words)</div>
                {paragraphs_html}
                {sources_html}
              </div>
            </td>
          </tr>

          <!-- Mobile Action Box -->
          <tr>
            <td style="padding: 10px 28px 24px 28px;">
              <div style="background-color: #111a2e; border: 1px solid #233554; border-radius: 10px; padding: 18px 20px;">
                <div style="font-size: 14px; font-weight: 700; color: #38bdf8; margin-bottom: 12px;">📱 Review & Edit from your Phone:</div>
                
                <!-- Quick Action Buttons -->
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom: 14px;">
                  <tr>
                    <td width="48%" style="vertical-align: top;">
                      <a href="{approve_mailto}" style="display: block; text-align: center; background: linear-gradient(135deg, #10b981, #059669); color: #ffffff; text-decoration: none; padding: 11px 12px; border-radius: 7px; font-size: 12px; font-weight: 700; box-shadow: 0 4px 10px rgba(16, 185, 129, 0.25);">
                        ✅ Approve as-is (Reply YES)
                      </a>
                    </td>
                    <td width="4%"></td>
                    <td width="48%" style="vertical-align: top;">
                      <a href="{edit_mailto}" style="display: block; text-align: center; background: linear-gradient(135deg, #6366f1, #4f46e5); color: #ffffff; text-decoration: none; padding: 11px 12px; border-radius: 7px; font-size: 12px; font-weight: 700; box-shadow: 0 4px 10px rgba(99, 102, 241, 0.25);">
                        ✏️ Tap to Edit Post on Phone
                      </a>
                    </td>
                  </tr>
                </table>

                <div style="font-size: 12px; color: #94a3b8; line-height: 1.7; border-top: 1px solid #1e293b; padding-top: 12px;">
                  <strong style="color: #cbd5e1;">3 Ways to act from mobile:</strong><br>
                  • <strong>Approve:</strong> Tap the green button above, or reply <code>YES</code> to this email.<br>
                  • <strong>Edit text:</strong> Tap the purple button above — it pre-fills the post text into your reply so you can edit and send.<br>
                  • <strong>Ask AI to revise:</strong> Reply with what you want changed (e.g. <em>"Make it punchier"</em> or <em>"Shorten to 120 words"</em>). The AI will rewrite it and send a new preview!<br>
                  • <strong>Web Dashboard:</strong> <a href="{dashboard_url}" style="color: #38bdf8; text-decoration: underline;">Open Dashboard on local Wi-Fi</a>
                </div>
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 16px 28px; background-color: #101623; border-top: 1px solid #1e2638; text-align: center;">
              <p style="margin: 0; font-size: 11px; color: #64748b;">
                Generated locally by <strong>Personal Social Media Agent</strong> with {draft.model} · <a href="{dashboard_url}" style="color: #6366f1; text-decoration: none;">{dashboard_url}</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _generate_plain_text(draft: Draft) -> str:
    """Generate plain-text email for clients that don't render HTML."""
    dashboard_url = _get_dashboard_url()
    sources_text = "\n".join(f"  - [{s.get('source', 'web')}] {s.get('title', '')} ({s.get('url', '')})" for s in draft.sources)
    return (
        f"⚡ Personal Social Media Agent — Daily LinkedIn Draft #{draft.id}\n"
        f"{'=' * 55}\n"
        f"Topic: {draft.topic}\n"
        f"Angle: {draft.angle}\n"
        f"Word Count: {draft.word_count} | Model: {draft.model}\n"
        f"Status: {draft.status}\n\n"
        f"{'-' * 55}\n"
        f"{draft.text}\n"
        f"{'-' * 55}\n\n"
        f"Sources:\n{sources_text}\n\n"
        f"REVIEW FROM PHONE:\n"
        f"1. Reply 'YES' to approve as-is.\n"
        f"2. Or reply with your edited post text to update the draft from your phone!\n"
        f"3. Dashboard on Wi-Fi: {dashboard_url}\n"
    )


def send_draft_email(draft: Draft, to_email: str | None = None) -> bool:
    """Send draft email via Gmail SMTP (SSL on port 465). Returns True if sent successfully."""
    settings = get_settings()
    sender = settings.gmail_address
    password = settings.gmail_app_password
    recipient = to_email or settings.notify_email or sender

    if not sender or not password:
        log.warning("Gmail credentials (GMAIL_ADDRESS / GMAIL_APP_PASSWORD) not configured in .env. Skipping email.")
        return False

    if not recipient:
        log.warning("No recipient email specified. Skipping email.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚡ Daily LinkedIn Draft #{draft.id}: {draft.topic}"
    msg["From"] = f"Social Agent <{sender}>"
    msg["To"] = recipient

    # Attach plain text and HTML parts
    part1 = MIMEText(_generate_plain_text(draft), "plain", "utf-8")
    part2 = MIMEText(_generate_html(draft, recipient), "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    try:
        log.info("Sending draft #%d email to %s via smtp.gmail.com...", draft.id, recipient)
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=20) as server:
            server.login(sender, password)
            server.sendmail(sender, [recipient], msg.as_string())
        log.info("Draft #%d email successfully sent to %s", draft.id, recipient)
        return True
    except Exception as e:
        log.exception("Failed to send draft #%d email to %s: %r", draft.id, recipient, e)
        return False

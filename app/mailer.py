"""Email notifications (P18.2): Gmail SMTP with an app password, from the standard library only.

What it does: `Mailer` sends one email over `smtplib.SMTP_SSL` on port 465 (implicit TLS) or `smtplib.SMTP` with
STARTTLS on any other port (default 587), then logs in with SMTP_USER and the app password (spaces removed),
when SMTP_USER and SMTP_PASSWORD are set and the app is not OFFLINE; it records every email in the store's
`mail_log` as `sent`, `failed` (with a short error code) or `skipped` (`offline`, `not_configured`,
`no_recipient`). Each event runs in its own daemon thread with a socket timeout, so an API call never waits on
SMTP and a failure never reaches the user. The event functions below build Arabic-first emails (RTL HTML and a
plain-text part, English under the Arabic) for: a new mentor request (to the intern), a comment on a request (the
admin's to the intern, the intern's to ADMIN_EMAIL, with the comment's files attached), a request marked done
(to ADMIN_EMAIL), a question sent to the mentor (to ADMIN_EMAIL), a question answered (to the intern, with the
answer row verbatim and its K-id; P18.5: or the mentor's private reply, said to be personal and not part of the
knowledge base), the admin's test email (to ADMIN_EMAIL) and, P21.1, a deadline reminder (to the intern, sent by
`app/reminders.py` shortly before a request's deadline, with the deadline in Amman time).
What it must never do: log, print, store or return the SMTP password (or any SMTP reply text); raise to an API
route; send while OFFLINE=1 or unconfigured; put a link (localhost included) in an email; reach the assistant
(the agent, answer, LLM and prompt code never import this module).
"""

from __future__ import annotations

import html
import smtplib
import ssl
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any

from app.deadlines import amman_text  # P21.1
from app.logging_setup import log_event

#: Seconds for each SMTP socket operation (connect, TLS, login, send).
MAIL_TIMEOUT_S = 15.0
#: SMTP_PORT=465: implicit TLS (`smtplib.SMTP_SSL`); any other port (default 587): plain SMTP + STARTTLS.
SSL_PORT = 465
SENDER_NAME = "Onboarding Academy"
SUBJECT_MAX = 200
OPEN_AR = "افتح «أكاديمية التهيئة» (مساعد التهيئة) لرؤية التفاصيل والرد."
OPEN_EN = "Open the onboarding assistant (Onboarding Academy) to see the details and reply."
FOOTER_AR = "رسالة آلية من مساعد التهيئة — بيانات تدريبية افتراضية."
FOOTER_EN = "An automatic message from the onboarding assistant — fictional training data."
KIND_AR = {"learn": "تعلّم", "do": "نفّذ", "read": "اقرأ"}
KIND_EN = {"learn": "Learn", "do": "Do", "read": "Read"}
SOURCE_AR = {"check": "من «افحص ما سمعت»", "chat": "من المحادثة", "quiz": "من اختبار تدريبي"}
SOURCE_EN = {"check": "from \"Check a rumour\"", "chat": "from the chat", "quiz": "from a practice quiz"}


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class Mail:
    event: str
    to_addr: str
    subject: str
    text: str
    html: str
    attachments: tuple[Attachment, ...] = ()


def error_code(exc: BaseException) -> str:
    """A short label for the mail log (never the exception text: an SMTP reply may echo account details)."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "auth_failed"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "recipient_refused"
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "sender_refused"
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "tls_failed"
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return "connect_failed"
    if isinstance(exc, smtplib.SMTPException):
        return "smtp_error"
    if isinstance(exc, ssl.SSLError):
        return "tls_failed"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, OSError):
        return "connect_failed"
    return "error"


def _one_line(text: str, limit: int) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _p(text: str, style: str = "") -> str:
    return f'<p style="margin:0 0 12px;{style}">{html.escape(text)}</p>'


def compose(event: str, to_addr: str, subject_ar: str, subject_en: str, ar: list[str], en: list[str],
            quotes: list[tuple[str, str]] | None = None, attachments: Iterable[Attachment] = ()) -> Mail:
    """One Arabic-first email: the Arabic paragraphs, the quoted texts (label, text; shown as written), the
    "open the assistant" line, then the English paragraphs. Plain text and RTL HTML say the same."""
    quotes = [(label, text) for label, text in quotes or [] if text and text.strip()]
    subject = _one_line(f"{subject_ar} | {subject_en}", SUBJECT_MAX)
    text_parts = [*ar]
    for label, body in quotes:
        text_parts.append(f"{label}:\n{body.strip()}")
    text_parts += [OPEN_AR, FOOTER_AR, "—", *en, OPEN_EN, FOOTER_EN]
    quote_html = "".join(
        '<div style="margin:0 0 12px;padding:10px 14px;border-inline-start:4px solid #0f766e;background:#f3f7f6;'
        'border-radius:6px">'
        f'<div style="font-size:13px;color:#4b5563;margin-bottom:4px">{html.escape(label)}</div>'
        f'<div dir="auto" style="white-space:pre-wrap">{html.escape(body.strip())}</div></div>'
        for label, body in quotes
    )
    body_html = (
        '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"></head>'
        '<body style="margin:0;padding:16px;background:#ffffff;color:#111827;'
        'font-family:Tahoma,Arial,sans-serif;font-size:15px;line-height:1.7">'
        '<div dir="rtl" lang="ar" style="text-align:right">'
        + "".join(_p(x) for x in ar) + quote_html + _p(OPEN_AR, "font-weight:bold")
        + _p(FOOTER_AR, "font-size:12px;color:#6b7280")
        + '</div><hr style="border:0;border-top:1px solid #e5e7eb;margin:16px 0">'
        '<div dir="ltr" lang="en" style="text-align:left">'
        + "".join(_p(x) for x in en) + _p(OPEN_EN, "font-weight:bold")
        + _p(FOOTER_EN, "font-size:12px;color:#6b7280")
        + "</div></body></html>"
    )
    return Mail(event=event, to_addr=to_addr, subject=subject, text="\n\n".join(text_parts) + "\n", html=body_html,
                attachments=tuple(attachments))


def build_message(mail: Mail, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = _one_line(mail.subject, SUBJECT_MAX)
    msg["From"] = formataddr((SENDER_NAME, sender))
    msg["To"] = mail.to_addr
    msg["Date"] = formatdate(usegmt=True)
    msg["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    msg.set_content(mail.text)
    msg.add_alternative(mail.html, subtype="html")
    for a in mail.attachments:
        maintype, _, subtype = a.content_type.partition("/")
        msg.add_attachment(a.data, maintype=maintype or "application", subtype=subtype or "octet-stream",
                           filename=a.filename)
    return msg


class Mailer:
    """Sends and records notification emails in background threads. Never raises to the caller."""

    def __init__(self, settings: Any, store: Any) -> None:
        self._settings = settings
        self._store = store
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    def __repr__(self) -> str:
        return f"Mailer(configured={self.configured})"

    # -------------------------------------------------------------------------------- settings
    def problem(self) -> str | None:
        """Why nothing is sent (`offline`, `not_configured`), or None when SMTP is ready."""
        s = self._settings
        if getattr(s, "offline", False):
            return "offline"
        if not getattr(s, "smtp_user", None) or getattr(s, "smtp_password", None) is None:
            return "not_configured"
        return None

    @property
    def configured(self) -> bool:
        return self.problem() is None

    @property
    def admin_email(self) -> str | None:
        return getattr(self._settings, "admin_email", None) or None

    @property
    def sender(self) -> str:
        s = self._settings
        return str(getattr(s, "mail_from", None) or getattr(s, "smtp_user", None) or "")

    def _password(self) -> str:
        secret = self._settings.smtp_password
        raw = secret.get_secret_value() if secret is not None else ""
        # Google shows app passwords in groups of four ("abcd efgh ijkl mnop"); the spaces are not part of it.
        return "".join(raw.split())

    # -------------------------------------------------------------------------------- store lookups
    def intern(self, intern_id: str) -> dict[str, Any]:
        try:
            return dict(self._store.get_intern(intern_id) or {})
        except Exception:  # noqa: BLE001
            return {}

    def intern_email(self, intern_id: str) -> str:
        try:
            return str(self._store.intern_email(intern_id) or "")
        except Exception:  # noqa: BLE001
            return ""

    # -------------------------------------------------------------------------------- sending
    def submit(self, build: Callable[[], Iterable[Mail]]) -> threading.Thread:
        """Build and deliver the emails in a daemon thread (store lookups included): the caller never waits."""
        thread = threading.Thread(target=self._run, args=(build,), name="mailer", daemon=True)
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()]
            thread.start()  # P21.1: started before it is listed, so `wait` (another thread) never joins it unstarted
            self._threads.append(thread)
        return thread

    def wait(self, timeout: float = 5.0) -> bool:
        """Join the running threads (tests and shutdown). True when all finished in time."""
        deadline = time.monotonic() + timeout
        with self._lock:
            threads = list(self._threads)
        for t in threads:
            t.join(max(0.0, deadline - time.monotonic()))
        return not any(t.is_alive() for t in threads)

    def _run(self, build: Callable[[], Iterable[Mail]]) -> None:
        try:
            mails = list(build())
        except Exception as exc:  # noqa: BLE001 - a background job never raises
            log_event("mail_failed", stage="build", error=type(exc).__name__)
            return
        for mail in mails:
            self.deliver(mail)

    def deliver(self, mail: Mail) -> tuple[str, str | None]:
        """Send one email now (in the calling thread) and record it: (status, error code)."""
        problem = self.problem() or (None if mail.to_addr else "no_recipient")
        status: str
        error: str | None
        if problem:
            status, error = "skipped", problem
        else:
            try:
                self._send(mail)
                status, error = "sent", None
            except Exception as exc:  # noqa: BLE001 - recorded, never raised
                status, error = "failed", error_code(exc)
        try:
            self._store.mail_log_add({"event": mail.event, "to_addr": mail.to_addr, "subject": mail.subject,
                                      "status": status, "error": error})
        except Exception as exc:  # noqa: BLE001
            log_event("store_write_failed", op="mail_log", error=type(exc).__name__)
        log_event(f"mail_{status}", mail_event=mail.event, error=error, attachments=len(mail.attachments))
        return status, error

    def _send(self, mail: Mail) -> None:
        s = self._settings
        msg = build_message(mail, self.sender)
        context = ssl.create_default_context()
        if int(s.smtp_port) == SSL_PORT:  # implicit TLS from the first byte (Gmail's 465): no STARTTLS
            with smtplib.SMTP_SSL(s.smtp_host, SSL_PORT, timeout=MAIL_TIMEOUT_S, context=context) as smtp:
                smtp.login(s.smtp_user, self._password())
                smtp.send_message(msg)
            return
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=MAIL_TIMEOUT_S) as smtp:  # 587: STARTTLS
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(s.smtp_user, self._password())
            smtp.send_message(msg)


# ===================================================================================== events
def _name(intern: dict[str, Any]) -> tuple[str, str]:
    """(Arabic display name, English display name) of an intern record."""
    ar = str(intern.get("name_ar") or "متدرب")
    en = str(intern.get("name_en") or intern.get("name_ar") or "An intern")
    return ar, en


def _request_quotes(req: dict[str, Any]) -> list[tuple[str, str]]:
    kind = str(req.get("kind") or "")
    quotes = [(f"الطلب ({KIND_AR.get(kind, kind)} · {KIND_EN.get(kind, kind)})", str(req.get("title") or ""))]
    if req.get("note"):
        quotes.append(("ملاحظة · Note", str(req["note"])))
    return quotes


def request_created_mail(req: dict[str, Any], to_addr: str) -> Mail:
    title = _one_line(str(req.get("title") or ""), 80)
    ar = ["لديك طلب جديد من مشرفك."]
    en = ["You have a new request from your mentor."]
    if req.get("due_at"):  # P21.1: the deadline in Amman time
        ar.append(f"الموعد النهائي: {amman_text(req['due_at'])} بتوقيت عمّان")
        en.append(f"Deadline: {amman_text(req['due_at'])} (Amman time)")
    elif req.get("due_date"):
        ar.append(f"الموعد المقترح: {req['due_date']}")
        en.append(f"Suggested date: {req['due_date']}")
    if req.get("kb_id"):
        ar.append(f"مرتبط بصف المعرفة {req['kb_id']}.")
        en.append(f"Linked to knowledge row {req['kb_id']}.")
    return compose("request_created", to_addr, f"طلب جديد من مشرفك: {title}", "New request from your mentor",
                   ar, en, _request_quotes(req))


def comment_mail(req: dict[str, Any], comment: dict[str, Any], files: list[Attachment], intern: dict[str, Any],
                 to_addr: str) -> Mail:
    title = _one_line(str(req.get("title") or ""), 80)
    n = len(files)
    quotes = [("الطلب · Request", str(req.get("title") or "")), ("الرد · Reply", str(comment.get("body") or ""))]
    if comment.get("author") == "admin":
        ar = ["ردّ مشرفك على طلبك."]
        en = ["Your mentor replied on your request."]
        if n:
            ar.append(f"الملفات المرفقة: {n}")
            en.append(f"Attached files: {n}")
        return compose("admin_comment", to_addr, f"ردّ مشرفك على طلبك: {title}", "Your mentor replied", ar, en,
                       quotes, files)
    name_ar, name_en = _name(intern)
    ar = [f"ردّ {name_ar} على طلب أرسلته."]
    en = [f"{name_en} replied on a request you sent."]
    if n:
        ar.append(f"الملفات المرفقة: {n}")
        en.append(f"Attached files: {n}")
    return compose("intern_comment", to_addr, f"ردّ {name_ar} على طلب: {title}", f"{name_en} replied", ar, en,
                   quotes, files)


def request_done_mail(req: dict[str, Any], intern: dict[str, Any], to_addr: str) -> Mail:
    name_ar, name_en = _name(intern)
    title = _one_line(str(req.get("title") or ""), 80)
    return compose("request_done", to_addr, f"أنهى {name_ar} طلباً: {title}", f"{name_en} marked a request done",
                   [f"علّم {name_ar} هذا الطلب «تم»."], [f"{name_en} marked this request as done."],
                   _request_quotes(req))


def question_submitted_mail(intern: dict[str, Any], text: str, source: str, to_addr: str) -> Mail:
    name_ar, name_en = _name(intern)
    where_ar = f" {SOURCE_AR[source]}" if source in SOURCE_AR else ""
    where_en = f" {SOURCE_EN[source]}" if source in SOURCE_EN else ""
    return compose(
        "question_submitted", to_addr, f"سؤال جديد من {name_ar}", f"New question from {name_en}",
        [f"أرسل {name_ar} سؤالاً {SOURCE_AR['quiz']} ليراجعه معك." if source == "quiz"  # P20
         else f"أرسل {name_ar} سؤالاً لم يجد المساعد إجابته{where_ar}.",
         "أجب عنه من «أسئلة المتدربين» في منطقة المشرف: أضف إجابتك إلى قاعدة المعرفة، أو ردّ على المتدرب وحده."],
        [f"{name_en} sent a question {SOURCE_EN['quiz']} to go over with you." if source == "quiz"  # P20
         else f"{name_en} sent a question the assistant could not answer{where_en}.",
         "Answer it under Interns' questions in the admin area: add your answer to the knowledge base, or reply "
         "to this intern only."],
        [("السؤال · Question", text)],
    )


def question_answered_mail(question: str, row_id: str, answer_ar: str, to_addr: str) -> Mail:
    return compose(
        "question_answered", to_addr, "أجاب مشرفك عن سؤالك", "Your mentor answered your question",
        ["أجاب مشرفك عن سؤالك، وأُضيفت الإجابة إلى قاعدة المعرفة."],
        ["Your mentor answered your question; the answer was added to the knowledge base."],
        [("سؤالك · Your question", question), (f"الإجابة ({row_id}) · Answer ({row_id})", answer_ar)],
    )


def question_answered_private_mail(question: str, answer_text: str, to_addr: str) -> Mail:
    """P18.5: the mentor's reply to this intern only (recorded as `question_answered`, like a K-row answer)."""
    return compose(
        "question_answered", to_addr, "ردّ مشرفك على سؤالك", "Your mentor replied to your question",
        ["ردّ مشرفك على سؤالك ردّاً خاصاً بك. هذا الرد ليس من قاعدة المعرفة ولا يراه غيرك."],
        ["Your mentor sent you a personal reply to your question. It is not part of the knowledge base, and only "
         "you can see it."],
        [("سؤالك · Your question", question), ("ردّ مشرفك · Your mentor's reply", answer_text)],
    )


def _minutes_ar(n: int) -> str:
    if n == 1:
        return "دقيقة واحدة"
    if n == 2:
        return "دقيقتين"
    return f"{n} دقائق" if 3 <= n <= 10 else f"{n} دقيقة"


def request_reminder_mail(req: dict[str, Any], minutes: int, to_addr: str) -> Mail:
    """P21.1: "this request is due in N minutes", with the deadline in Amman time (no link, like every email)."""
    title = _one_line(str(req.get("title") or ""), 80)
    when = amman_text(req.get("due_at"))
    mins_ar, mins_en = _minutes_ar(minutes), f"{minutes} minute{'' if minutes == 1 else 's'}"
    return compose(
        "request_reminder", to_addr, f"تذكير: موعد طلب «{title}» بعد {mins_ar}", f"Reminder: a request is due in {mins_en}",
        [f"تذكير: موعد تسليم هذا الطلب بعد {mins_ar}.", f"الموعد النهائي: {when} بتوقيت عمّان."],
        [f"Reminder: this request is due in {mins_en}.", f"Deadline: {when} (Amman time)."],
        _request_quotes(req),
    )


def admin_test_mail(to_addr: str) -> Mail:
    return compose(
        "test", to_addr, "رسالة تجريبية من مساعد التهيئة", "Test email from the onboarding assistant",
        ["هذه رسالة تجريبية: إعداد البريد يعمل."], ["This is a test email: the email setup works."],
    )


def request_created(mailer: Mailer | None, requests: list[dict[str, Any]]) -> None:
    """A new mentor request (one per intern of the target) → that intern's email."""
    if mailer is None or not requests:
        return
    reqs = [dict(r) for r in requests]
    mailer.submit(lambda: [request_created_mail(r, mailer.intern_email(str(r["intern_id"]))) for r in reqs])


def comment_added(mailer: Mailer | None, req: dict[str, Any], comment: dict[str, Any], blobs: list[bytes]) -> None:
    """A comment on a request: the admin's → the intern; the intern's → ADMIN_EMAIL. Its files are attached."""
    if mailer is None:
        return
    req, comment = dict(req), dict(comment)
    files = [Attachment(str(f["filename"]), str(f["content_type"]), bytes(b))
             for f, b in zip(comment.get("files") or [], blobs, strict=False)]
    iid = str(req.get("intern_id"))

    def build() -> list[Mail]:
        intern = mailer.intern(iid)
        to = mailer.intern_email(iid) if comment.get("author") == "admin" else (mailer.admin_email or "")
        return [comment_mail(req, comment, files, intern, to)]

    mailer.submit(build)


def request_done(mailer: Mailer | None, req: dict[str, Any]) -> None:
    """The intern marked a request done → ADMIN_EMAIL."""
    if mailer is None:
        return
    req = dict(req)
    mailer.submit(lambda: [request_done_mail(req, mailer.intern(str(req.get("intern_id"))), mailer.admin_email or "")])


def question_submitted(mailer: Mailer | None, *, intern_id: str, text: str, source: str) -> None:
    """P18.1 hook (wired by the integrator): an intern sent a question to their mentor → ADMIN_EMAIL.

    `intern_id`: the sender's intern id; `text`: the question exactly as sent (1-600 characters, already checked
    by the route); `source`: "check" (Rumour Check), "chat" or "quiz" (a practice quiz question, P20). Call after the store write succeeds."""
    if mailer is None:
        return
    mailer.submit(lambda: [question_submitted_mail(mailer.intern(intern_id), text, source, mailer.admin_email or "")])


def question_answered(mailer: Mailer | None, *, intern_id: str, question: str, row_id: str, answer_ar: str) -> None:
    """P18.1 hook (wired by the integrator): the admin answered an intern's question → that intern's email.

    `question`: the intern's question as sent; `row_id` / `answer_ar`: the K-row the answer created, its id and
    its `answer_ar` verbatim. Call after the KB row is added and the question is marked answered."""
    if mailer is None:
        return
    mailer.submit(lambda: [question_answered_mail(question, row_id, answer_ar, mailer.intern_email(intern_id))])


def question_answered_private(mailer: Mailer | None, *, intern_id: str, question: str, answer_text: str) -> None:
    """P18.5: the admin replied privately to an intern's question → that intern's email.

    `question`: the intern's question as sent; `answer_text`: the stored private reply verbatim. Call after the
    question is marked answered."""
    if mailer is None:
        return
    mailer.submit(lambda: [question_answered_private_mail(question, answer_text, mailer.intern_email(intern_id))])


def request_reminder(mailer: Mailer | None, req: dict[str, Any], minutes: int) -> None:
    """P21.1: a request's deadline is `minutes` away → that intern's email (the reminder was claimed first)."""
    if mailer is None:
        return
    req = dict(req)
    mailer.submit(lambda: [request_reminder_mail(req, minutes, mailer.intern_email(str(req.get("intern_id"))))])


def send_test(mailer: Mailer) -> tuple[str, str | None]:
    """The admin's "send a test email to me" (ADMIN_EMAIL): ("queued", None) or ("skipped", reason). The result
    of a queued email appears in the mail log."""
    to = mailer.admin_email or ""
    problem = mailer.problem() or (None if to else "no_recipient")
    mailer.submit(lambda: [admin_test_mail(to)])
    return ("skipped", problem) if problem else ("queued", None)


__all__ = [
    "MAIL_TIMEOUT_S",
    "SSL_PORT",
    "Attachment",
    "Mail",
    "Mailer",
    "build_message",
    "comment_added",
    "compose",
    "error_code",
    "question_answered",
    "question_answered_private",
    "question_submitted",
    "request_created",
    "request_done",
    "request_reminder",
    "request_reminder_mail",
    "send_test",
]

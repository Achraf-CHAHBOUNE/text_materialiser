"""Every email the platform sends, in the reader's language, through one outbox.

Nothing is sent from inside a request. A request writes the message to `email_outbox`
and returns; the worker (worker.py) sends what is waiting. So a slow or broken mail
server never slows a page, and a message that fails stays there to be retried or read
by an administrator -- nothing is lost.

With no SMTP_HOST set, messages simply wait in the outbox: a fresh install works, and
the admin page shows what would have gone out.

    SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS (1)
    SITE_URL   the address links in emails point to, e.g. https://jurisprudence.ma
"""
from __future__ import annotations

import datetime as dt
import os
from typing import List, Optional

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

import clock
import db


class EmailOutbox(db.Base):
    __tablename__ = "email_outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    to_addr: Mapped[str] = mapped_column(String, index=True)
    template: Mapped[str] = mapped_column(String, default="")
    lang: Mapped[str] = mapped_column(String, default="ar")
    subject: Mapped[str] = mapped_column(String, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="queued", index=True)  # queued|sent|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String, default="")
    # A reminder must go once, however often the worker looks: the key names it
    # ("renewal:42:15") and is unique, so a second copy is refused by the database.
    dedupe_key: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=clock.utcnow)
    sent_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


def site_url() -> str:
    return (os.getenv("SITE_URL") or "http://localhost:5199").rstrip("/")


SIGN = {"ar": "\n\n—\nمنصة الاجتهاد القضائي", "fr": "\n\n—\nPlateforme de jurisprudence"}

# {name: {lang: (subject, body)}}, filled with str.format(**values)
TEMPLATES = {
    "invitation": {
        "ar": ("دعوة للانضمام إلى {org}",
               "مرحبا،\n\nدعاك {inviter} للانضمام إلى حساب {org} على منصة الاجتهاد القضائي.\n"
               "لإنشاء حسابك، افتح الرابط التالي (صالح لمدة 7 أيام):\n{link}"),
        "fr": ("Invitation à rejoindre {org}",
               "Bonjour,\n\n{inviter} vous invite à rejoindre le compte {org} sur la plateforme "
               "de jurisprudence.\nPour créer votre accès, ouvrez ce lien (valable 7 jours) :\n{link}"),
    },
    "password_reset": {
        "ar": ("إعادة تعيين كلمة المرور",
               "مرحبا،\n\nطُلبت إعادة تعيين كلمة المرور لحسابك. افتح الرابط التالي (صالح لمدة ساعة):\n{link}\n\n"
               "إن لم تطلب ذلك، تجاهل هذه الرسالة."),
        "fr": ("Réinitialisation du mot de passe",
               "Bonjour,\n\nUne réinitialisation du mot de passe a été demandée pour votre compte. "
               "Ouvrez ce lien (valable une heure) :\n{link}\n\nSi vous n'êtes pas à l'origine de "
               "cette demande, ignorez ce message."),
    },
    "demo_received": {
        "ar": ("توصلنا بطلبك",
               "مرحبا {name}،\n\nشكرا على اهتمامك. توصلنا بطلب العرض التجريبي وسيتصل بك أحد أعضاء فريقنا قريبا."),
        "fr": ("Nous avons bien reçu votre demande",
               "Bonjour {name},\n\nMerci de votre intérêt. Votre demande de démonstration est bien "
               "reçue ; un membre de notre équipe vous contactera rapidement."),
    },
    "new_lead": {
        "ar": ("طلب جديد: {company}", "طلب عرض تجريبي جديد من {name} ({company})، {email} {phone}.\n\n{message}\n\n{link}"),
        "fr": ("Nouvelle demande : {company}", "Nouvelle demande de démonstration de {name} ({company}), {email} {phone}.\n\n{message}\n\n{link}"),
    },
    "renewal": {
        "ar": ("ينتهي اشتراك {org} خلال {days} يوما",
               "مرحبا،\n\nينتهي اشتراك {org} في {end}. للتجديد أو لأي سؤال، تواصل معنا من صفحة الدعم:\n{link}"),
        "fr": ("L'abonnement de {org} se termine dans {days} jours",
               "Bonjour,\n\nL'abonnement de {org} prend fin le {end}. Pour le renouveler ou pour "
               "toute question, contactez-nous depuis la page d'assistance :\n{link}"),
    },
    "renewal_staff": {
        "ar": ("تجديد: {org} ينتهي في {end}", "اشتراك {org} ينتهي في {end} ({days} يوما).\n{link}"),
        "fr": ("Renouvellement : {org} se termine le {end}", "L'abonnement de {org} se termine le {end} (dans {days} jours).\n{link}"),
    },
    "alert": {
        "ar": ("{count} قرارات جديدة: {name}",
               "مرحبا،\n\nقرارات جديدة تطابق تنبيهك «{name}»:\n\n{items}\n\nكل النتائج:\n{link}"),
        "fr": ("{count} nouvelles décisions : {name}",
               "Bonjour,\n\nDe nouvelles décisions correspondent à votre alerte « {name} » :\n\n{items}\n\n"
               "Tous les résultats :\n{link}"),
    },
    "ticket_reply": {
        "ar": ("رد على طلبك: {subject}", "مرحبا،\n\nتمت إضافة رد على طلب الدعم «{subject}»:\n\n{body}\n\n{link}"),
        "fr": ("Réponse à votre demande : {subject}", "Bonjour,\n\nUne réponse a été ajoutée à votre demande « {subject} » :\n\n{body}\n\n{link}"),
    },
    "ticket_new": {
        "ar": ("طلب دعم جديد: {subject}", "طلب دعم جديد من {author} ({org}):\n\n{body}\n\n{link}"),
        "fr": ("Nouvelle demande d'assistance : {subject}", "Nouvelle demande de {author} ({org}) :\n\n{body}\n\n{link}"),
    },
    "digest": {
        "ar": ("مهامك اليوم", "{body}\n\n{link}"),
        "fr": ("Votre journée", "{body}\n\n{link}"),
    },
}


def queue(to: str, template: str, lang: str = "ar", *, dedupe: Optional[str] = None,
          **values) -> bool:
    """Put a message in the outbox. False if a message with the same `dedupe` key was
    already queued (a reminder is sent once)."""
    lang = lang if lang in ("ar", "fr") else "ar"
    subject, body = TEMPLATES[template][lang]
    values.setdefault("link", site_url())
    safe = {k: ("" if v is None else v) for k, v in values.items()}
    with db.session() as s:
        s.add(EmailOutbox(to_addr=to, template=template, lang=lang,
                          subject=subject.format(**safe), body=body.format(**safe) + SIGN[lang],
                          dedupe_key=dedupe))
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            return False
    return True


def queue_text(to: str, subject: str, body: str, lang: str = "fr", *,
               dedupe: Optional[str] = None) -> bool:
    """A message written by a person (an email to a contact from the CRM), sent through
    the same outbox as everything else."""
    lang = lang if lang in ("ar", "fr") else "fr"
    with db.session() as s:
        s.add(EmailOutbox(to_addr=to, template="direct", lang=lang, subject=subject[:200],
                          body=body + SIGN[lang], dedupe_key=dedupe))
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            return False
    return True


def staff_addresses(roles=("admin", "sales")) -> List[str]:
    with db.session() as s:
        return list(s.scalars(select(db.User.email).where(db.User.role.in_(roles),
                                                          db.User.status == "active")))


def send_pending(limit: int = 50) -> dict:
    """Send what is waiting. Without SMTP settings, leave it waiting and say so."""
    host = os.getenv("SMTP_HOST", "")
    if not host:
        return {"sent": 0, "failed": 0, "skipped": "SMTP_HOST not set"}
    import smtplib
    from email.message import EmailMessage
    port = int(os.getenv("SMTP_PORT", "587"))
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER", "")
    sent = failed = 0
    with db.session() as s:
        rows = list(s.scalars(select(EmailOutbox).where(EmailOutbox.status == "queued",
                                                        EmailOutbox.attempts < 5)
                              .order_by(EmailOutbox.id).limit(limit)))
        if not rows:
            return {"sent": 0, "failed": 0}
        try:
            server = smtplib.SMTP(host, port, timeout=30)
            if os.getenv("SMTP_TLS", "1") not in ("0", "false"):
                server.starttls()
            if os.getenv("SMTP_USER"):
                server.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
        except Exception as e:
            return {"sent": 0, "failed": 0, "error": f"{type(e).__name__}: {e}"}
        for m in rows:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = sender, m.to_addr, m.subject
            msg.set_content(m.body)
            m.attempts += 1
            try:
                server.send_message(msg)
                m.status, m.sent_at, m.error = "sent", clock.utcnow(), ""
                sent += 1
            except Exception as e:
                m.error = f"{type(e).__name__}: {e}"[:300]
                if m.attempts >= 5:
                    m.status = "failed"
                failed += 1
        s.commit()
        try:
            server.quit()
        except Exception:
            pass
    return {"sent": sent, "failed": failed}


def outbox(limit: int = 100) -> List[dict]:
    with db.session() as s:
        return [{"id": m.id, "to": m.to_addr, "template": m.template, "lang": m.lang,
                 "subject": m.subject, "body": m.body, "status": m.status, "error": m.error,
                 "created_at": m.created_at.isoformat() if m.created_at else "",
                 "sent_at": m.sent_at.isoformat() if m.sent_at else ""}
                for m in s.scalars(select(EmailOutbox).order_by(EmailOutbox.id.desc()).limit(limit))]

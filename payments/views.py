import base64
import json
import logging
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _next_saturday_slot() -> str:
    today = date.today()
    days_until_saturday = (5 - today.weekday()) % 7
    if days_until_saturday == 0:
        days_until_saturday = 7
    next_saturday = today + timedelta(days=days_until_saturday)
    return f"Saturday, {_ordinal(next_saturday.day)} {next_saturday.strftime('%B')} at 10:00 AM"


def _combined_notes(payment: dict, payment_link: dict) -> dict:
    notes: dict = {}
    for source in (payment, payment_link):
        if not isinstance(source, dict):
            continue
        raw = source.get("notes")
        if isinstance(raw, dict):
            notes.update(raw)
        elif isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    notes.update(parsed)
            except json.JSONDecodeError:
                pass
    return notes


def _resolve_payment_entities(payload: dict) -> tuple[dict, dict]:
    raw_payment = ((payload.get("payment") or {}).get("entity")) or {}
    raw_link = ((payload.get("payment_link") or {}).get("entity")) or {}
    payment = dict(raw_payment) if isinstance(raw_payment, dict) else {}
    payment_link = dict(raw_link) if isinstance(raw_link, dict) else {}

    if not payment.get("id"):
        pl_payments = payment_link.get("payments")
        if isinstance(pl_payments, list) and pl_payments:
            tail = pl_payments[-1]
            if isinstance(tail, dict) and tail.get("id"):
                payment = {**tail, **payment}
            elif isinstance(tail, str) and tail.startswith("pay_"):
                payment = {**payment, "id": tail}

    customer = payment_link.get("customer") if isinstance(payment_link.get("customer"), dict) else {}
    for field in ("email", "name", "contact"):
        if not payment.get(field) and customer.get(field):
            payment[field] = customer[field]

    return payment, payment_link


def _razorpay_basic_auth_header() -> str | None:
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "") or ""
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "") or ""
    key_id, key_secret = key_id.strip(), key_secret.strip()
    if not key_id or not key_secret:
        return None
    token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    return f"Basic {token}"


def _merge_payment_from_api(payment: dict, api_entity: dict) -> dict:
    if not api_entity:
        return payment
    out = dict(payment)
    for key, value in api_entity.items():
        if value in (None, "", [], {}):
            continue
        if out.get(key) in (None, "", [], {}):
            out[key] = value
    return out


def _fetch_payment_from_razorpay_api(payment_id: str) -> dict:
    auth = _razorpay_basic_auth_header()
    if not auth or not payment_id:
        return {}
    url = f"https://api.razorpay.com/v1/payments/{payment_id}"
    try:
        r = requests.get(url, headers={"Authorization": auth}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("Razorpay payment fetch failed for %s: %s", payment_id, exc)
        return {}


def _fetch_payment_link_by_id(link_id: str) -> dict:
    auth = _razorpay_basic_auth_header()
    if not auth or not link_id:
        return {}
    url = f"https://api.razorpay.com/v1/payment_links/{link_id}"
    try:
        r = requests.get(url, headers={"Authorization": auth}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("Razorpay payment link fetch failed for %s: %s", link_id, exc)
        return {}


def _payment_stub_from_link_entity(link_entity: dict) -> dict:
    if not link_entity:
        return {}
    payments = link_entity.get("payments")
    if not isinstance(payments, list) or not payments:
        return {}
    tail = payments[-1]
    if isinstance(tail, str):
        return {"id": tail, "amount": link_entity.get("amount")}
    if isinstance(tail, dict):
        pid = tail.get("payment_id") or tail.get("id")
        out: dict = {}
        if pid:
            out["id"] = pid
        if tail.get("amount") is not None:
            out["amount"] = tail["amount"]
        elif link_entity.get("amount") is not None:
            out["amount"] = link_entity.get("amount")
        return out
    return {}


def _enrich_payment_from_razorpay(payment: dict) -> dict:
    pid = payment.get("id")
    if not pid or not _razorpay_basic_auth_header():
        return payment
    api_entity = _fetch_payment_from_razorpay_api(pid)
    return _merge_payment_from_api(payment, api_entity)


def _sheet_row_timestamp(payment: dict) -> str:
    ts = payment.get("created_at")
    if ts is not None:
        try:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (TypeError, ValueError, OSError):
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _extract_candidate_name(payment: dict, payment_link: dict, notes: dict) -> str:
    customer = payment_link.get("customer", {}) if isinstance(payment_link.get("customer"), dict) else {}
    return (
        payment.get("name")
        or customer.get("name")
        or notes.get("name")
        or notes.get("full_name")
        or ""
    )


def _extract_candidate_email(payment: dict, payment_link: dict, notes: dict) -> str:
    customer = payment_link.get("customer", {}) if isinstance(payment_link.get("customer"), dict) else {}
    return payment.get("email") or customer.get("email") or notes.get("email") or ""


def _matches_allowed_payment_page_id(payment: dict, payment_link: dict, notes: dict) -> bool:
    allowed_page_id = getattr(settings, "ALLOWED_PAYMENT_PAGE_ID", "").strip()
    if not allowed_page_id:
        return True

    candidates = {
        payment.get("payment_link_id"),
        payment_link.get("id"),
        payment_link.get("reference_id"),
        notes.get("payment_page_id"),
        notes.get("payment_link_id"),
    }
    normalized = {candidate.strip() for candidate in candidates if isinstance(candidate, str) and candidate.strip()}
    return allowed_page_id in normalized


def _page_id_candidates(payment: dict, payment_link: dict, notes: dict) -> list[str]:
    raw = [
        payment.get("payment_link_id"),
        payment_link.get("id"),
        payment_link.get("reference_id"),
        notes.get("payment_page_id"),
        notes.get("payment_link_id"),
    ]
    return [str(x).strip() for x in raw if isinstance(x, str) and str(x).strip()]


WEBHOOK_HANDLED_EVENTS = frozenset(
    {
        "payment.captured",
        "payment_link.paid",
        "order.paid",
    }
)


def _save_payment_to_google_sheet(payment: dict, payment_link: dict, notes: dict, event: str) -> None:
    webapp_url = (getattr(settings, "GOOGLE_SHEETS_WEBAPP_URL", "") or "").strip().rstrip("/")
    if not webapp_url:
        raise ValueError(
            "GOOGLE_SHEETS_WEBAPP_URL is not set. Add it to environment variables "
            "(Render dashboard or .env) so rows can be appended."
        )

    payment_id = payment.get("id")
    if not payment_id:
        raise ValueError("Payment id missing in webhook payload; cannot sync to Google Sheets.")

    check_url = f"{webapp_url}?{urlencode({'check_payment_id': payment_id})}"
    try:
        r = requests.get(check_url, timeout=15)
        if r.ok:
            try:
                check_payload = r.json()
                if check_payload.get("exists") is True:
                    return
            except ValueError:
                pass
    except requests.RequestException:
        pass

    amount_paise = payment.get("amount", 0)
    try:
        amount_rupees = float(amount_paise) / 100
    except (TypeError, ValueError):
        amount_rupees = 0

    # Column order must match the sheet: Payment ID, Email, Name, Amount, Date, status
    sheet_payload = {
        "payment_id": payment_id,
        "email": _extract_candidate_email(payment, payment_link, notes),
        "name": _extract_candidate_name(payment, payment_link, notes),
        "amount": amount_rupees,
        "date": _sheet_row_timestamp(payment),
        "status": event,
    }
    try:
        r = requests.post(
            webapp_url,
            json=sheet_payload,
            headers={"Content-Type": "application/json"},
            timeout=25,
        )
    except requests.RequestException as exc:
        raise ValueError(f"Google Sheets web app request failed: {exc}") from exc

    if not r.ok:
        snippet = (r.text or "")[:400]
        raise ValueError(f"Google Sheets web app HTTP {r.status_code}: {snippet}")

    try:
        post_payload = r.json()
    except ValueError:
        raise ValueError(
            f"Google Sheets web app returned non-JSON (check deployment URL and Apps Script). Body: {(r.text or '')[:400]}"
        )

    if post_payload.get("success") is not True:
        raise ValueError(f"Google Sheets script did not report success: {post_payload}")


@require_GET
def integration_health(request):
    sheet = (getattr(settings, "GOOGLE_SHEETS_WEBAPP_URL", "") or "").strip()
    allowed = (getattr(settings, "ALLOWED_PAYMENT_PAGE_ID", "") or "").strip()
    return JsonResponse(
        {
            "google_sheets_webapp_configured": bool(sheet),
            "google_sheets_url_host_hint": sheet.split("/")[2] if sheet.startswith("http") and len(sheet.split("/")) > 2 else "",
            "smtp_configured": settings.EMAIL_BACKEND
            == "django.core.mail.backends.smtp.EmailBackend",
            "email_host": getattr(settings, "EMAIL_HOST", ""),
            "email_port": getattr(settings, "EMAIL_PORT", None),
            "email_use_tls": getattr(settings, "EMAIL_USE_TLS", None),
            "email_use_ssl": getattr(settings, "EMAIL_USE_SSL", None),
            "allowed_payment_page_id_configured": bool(allowed),
            "razorpay_api_configured": bool(
                (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
                and (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
            ),
            "webhook_post_path": "/api/razorpay/webhook/",
            "note": "If smtp_configured is false on Render, set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD. "
            "Apps Script web app must be deployed with access: Anyone.",
        }
    )


@csrf_exempt
def razorpay_webhook(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    raw_body = request.body
    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    event = data.get("event")
    if event not in WEBHOOK_HANDLED_EVENTS:
        return JsonResponse({"status": "Ignored event", "event": event}, status=200)

    event_payload = data.get("payload") or {}
    payment, payment_link = _resolve_payment_entities(event_payload)

    if not payment.get("id") and payment_link.get("id"):
        link_json = _fetch_payment_link_by_id(payment_link["id"])
        stub = _payment_stub_from_link_entity(link_json)
        payment = {**stub, **payment}

    payment = _enrich_payment_from_razorpay(payment)
    notes = _combined_notes(payment, payment_link)

    allowed_pid = (getattr(settings, "ALLOWED_PAYMENT_PAGE_ID", "") or "").strip()
    if allowed_pid and not _matches_allowed_payment_page_id(payment, payment_link, notes):
        candidates = _page_id_candidates(payment, payment_link, notes)
        logger.info(
            "Webhook skipped: payment page id did not match. event=%s allowed=%s candidates=%s",
            event,
            allowed_pid,
            candidates,
        )
        return JsonResponse(
            {
                "status": "Email skipped for this payment page",
                "allowed_payment_page_id": allowed_pid,
                "seen_payment_link_ids": candidates,
                "fix": "Set ALLOWED_PAYMENT_PAGE_ID on Render to one of seen_payment_link_ids, or use the same Payment Link id in Razorpay.",
            },
            status=200,
        )

    logger.info(
        "Razorpay webhook accepted: event=%s payment_id=%s",
        event,
        payment.get("id"),
    )

    try:
        _save_payment_to_google_sheet(payment, payment_link, notes, event)
    except Exception as e:
        return JsonResponse({"error": f"Google Sheets sync failed: {str(e)}"}, status=500)

    email = _extract_candidate_email(payment, payment_link, notes)
    if not email:
        return JsonResponse({"status": "No email to send"}, status=200)

    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        return JsonResponse(
            {
                "error": (
                    "SMTP is not configured. Set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD "
                    "in your hosting environment (for example Render environment variables), "
                    "redeploy or restart, and ensure Gmail uses an app password if required."
                )
            },
            status=503,
        )

    subject = "Campus Experience Appointment Confirmation : Incanto Dynamics Private Ltd."
    appointment_slot = _next_saturday_slot()
    text_content = (
        "Campus Experience Appointment Confirmed\n\n"
        "Dear Candidate,\n\n"
        f"Congratulations!! We are pleased to confirm your campus experience appointment on {appointment_slot} at our institute.\n\n"
        "A registration fee of Rs.99 is applicable to confirm your appointment.\n"
        "Attendees will receive a Rs.1000 fee waiver towards program enrollment.\n\n"
        "Warm regards,\n"
        "Team Incanto"
    )
    html_content = """<!DOCTYPE html>
<html lang="en" style="margin:0;padding:0;">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Incanto Dynamics - Appointment Confirmed</title>

<style>
body, table, td, a {
  -webkit-text-size-adjust:100%;
  -ms-text-size-adjust:100%;
}
table, td {
  border-collapse:collapse;
}
img {
  border:0;
  display:block;
}
body {
  margin:0;
  padding:0;
  width:100%!important;
  background:#ffffff;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:#000000;
}

.container {
  width:600px;
  max-width:600px;
}

.shadow {
  box-shadow:0 18px 50px rgba(0,0,0,.18);
  border-radius:20px;
}

.hero-wrap {
  background:radial-gradient(circle at 0 0, #fff3e0 0, #ffffff 55%);
  padding:24px;
  border-bottom:1px solid rgba(0,0,0,.06);
}

.tech-frame {
  border-radius:18px;
  border:1px solid rgba(0,0,0,.12);
  padding:20px;
}

.h1 {
  font-size:24px;
  line-height:1.4;
  margin:0;
  font-weight:900;
  letter-spacing:.12em;
  text-transform:uppercase;
}

.lead {
  font-size:15px;
  line-height:1.7;
  margin:0 0 12px;
}

.small {
  font-size:11px;
  color:#444;
}

.micro-label {
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.26em;
  color:#555;
}

.status-bar {
  border-radius:10px;
  border:1px solid rgba(0,0,0,.18);
  padding:6px 10px;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.18em;
  display:inline-block;
  margin-top:10px;
}

.status-dot {
  width:6px;
  height:6px;
  border-radius:999px;
  background:#22c55e;
  display:inline-block;
  margin-right:6px;
}

.highlight-box {
  background:#fff4e8;
  border-radius:14px;
  padding:16px;
  border:1px solid #ff7a1a;
  margin-top:18px;
}
</style>
</head>

<body>

<table width="100%">
<tr>
<td align="center" style="padding:20px;">

<table class="container shadow">

<!-- HERO -->
<tr>
<td class="hero-wrap">

<span class="micro-label">
INCANTO DYNAMICS • CAREER EXCELLENCE • CAMPUS EXPERIENCE
</span>

<div class="tech-frame">

<img src="https://drive.google.com/thumbnail?id=19dMesjVYsMkkK4RMvuofMpOShaZLLbKO&sz=w600"
width="150"
alt="Incanto Dynamics Logo"
style="margin-bottom:12px;" />

<div class="status-bar">
<span class="status-dot"></span> APPOINTMENT CONFIRMED
</div>

<div style="height:14px;"></div>

<h1 class="h1">
Campus Experience<br>Appointment
</h1>

<p style="font-size:12px; margin-top:8px;">
An exclusive opportunity to explore Industrial Automation & Robotics at Incanto Dynamics.
</p>

</div>
</td>
</tr>

<!-- BODY -->
<tr>
<td style="padding:32px 24px;">

<p class="lead">Dear Candidate,</p>

<p class="lead">
<strong>Congratulations!!</strong> We are pleased to confirm your campus experience appointment on <strong>__APPOINTMENT_SLOT__</strong> at our institute.
</p>

<p class="lead">
This session will give you an overview of our <strong>Industrial Automation & Robotics Module</strong>, including hands-on training, career opportunities, and the unique advantages of our institute such as advanced labs, industry exposure, and expert mentorship.
</p>

<div class="highlight-box">
<p class="lead" style="font-size:13px; margin:0;">
<strong>Appointment Fee & Benefit</strong><br><br>
A <strong>registration fee of ₹99</strong> is applicable to confirm your appointment.<br>
Attendees will receive a <strong>₹1000 fee waiver</strong> towards program enrollment.
</p>
</div>

<p class="lead" style="margin-top:22px;">
Our team will guide you through the module details and help you understand how this program can strengthen your career prospects in the automation industry.
</p>

<p class="lead" style="margin-top:22px;">
We look forward to welcoming you.
</p>

<p class="lead" style="margin-top:28px;">
Warm regards,<br>
<strong>Team Incanto</strong>
</p>

</td>
</tr>

<!-- FOOTER -->
<tr>
<td style="padding:16px 24px; text-align:center;">
<p class="small">
© 2025 Incanto Dynamics Pvt Ltd. All rights reserved.
</p>
</td>
</tr>

</table>

</td>
</tr>
</table>

</body>
</html>
""".replace("__APPOINTMENT_SLOT__", appointment_slot)

    try:
        email_message = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        email_message.attach_alternative(html_content, "text/html")
        sent_count = email_message.send()
        if sent_count < 1:
            return JsonResponse({"error": "SMTP accepted zero recipients"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"Email sending failed: {str(e)}"}, status=500)

    return JsonResponse({"status": "Webhook processed and email sent"}, status=200)
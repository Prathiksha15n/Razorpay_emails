import base64
import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return ""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"***@{domain}"
    return f"{local[:2]}***@{domain}"


def _webhook_response(data: dict, status: int, diagnostics: dict | None = None) -> JsonResponse:
    if diagnostics is not None and getattr(settings, "WEBHOOK_VERBOSE_DIAGNOSTICS", True):
        return JsonResponse({**data, "diagnostics": diagnostics}, status=status)
    return JsonResponse(data, status=status)

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


def _payment_amount_paise(payment: dict) -> int:
    raw = payment.get("amount")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _paid_amount_matches_email_threshold(payment: dict) -> bool:
    """Sheet + email only when captured payment amount is exactly REQUIRED_PAYMENT_RUPEES_FOR_EMAIL (INR paise)."""
    required_rupees = int(getattr(settings, "REQUIRED_PAYMENT_RUPEES_FOR_EMAIL", 99))
    if required_rupees < 0:
        return True
    currency = (payment.get("currency") or "INR").upper()
    if currency != "INR":
        return False
    required_paise = required_rupees * 100
    return _payment_amount_paise(payment) == required_paise


def _build_webhook_diagnostics(
    trace_id: str,
    *,
    step: str,
    event: str | None = None,
    payment: dict | None = None,
    payment_link: dict | None = None,
    recipient_email: str | None = None,
    **extra: object,
) -> dict:
    p = payment if isinstance(payment, dict) else {}
    pl = payment_link if isinstance(payment_link, dict) else {}
    required_inr = int(getattr(settings, "REQUIRED_PAYMENT_RUPEES_FOR_EMAIL", 99))
    paise = _payment_amount_paise(p)
    out: dict = {
        "trace_id": trace_id,
        "pipeline_step": step,
        "event": event,
        "payment_id": p.get("id"),
        "payment_link_entity_id": pl.get("id"),
        "amount_paise": paise,
        "currency_reported": p.get("currency") or "INR",
        "amount_rupees_approx": round(paise / 100, 2) if paise else 0.0,
        "amount_required_paise_inr": max(0, required_inr) * 100,
        "amount_gate_passed": _paid_amount_matches_email_threshold(p) if p else False,
        "google_sheets_url_configured": bool(
            (getattr(settings, "GOOGLE_SHEETS_WEBAPP_URL", "") or "").strip()
        ),
        "smtp_is_active_backend": settings.EMAIL_BACKEND
        == "django.core.mail.backends.smtp.EmailBackend",
        "razorpay_live_api_auth_configured": bool(_razorpay_basic_auth_header()),
    }
    if recipient_email:
        out["recipient_email_masked"] = _mask_email(recipient_email)
    for k, v in extra.items():
        if v is not None:
            out[k] = v
    return out


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
    required_inr = int(getattr(settings, "REQUIRED_PAYMENT_RUPEES_FOR_EMAIL", 99))
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
            "required_payment_rupees_inr_for_sheet_and_email": required_inr,
            "required_amount_paise_inr": required_inr * 100,
            "razorpay_api_configured": bool(
                (getattr(settings, "RAZORPAY_KEY_ID", "") or "").strip()
                and (getattr(settings, "RAZORPAY_KEY_SECRET", "") or "").strip()
            ),
            "webhook_post_path": "/api/razorpay/webhook/",
            "webhook_debug_guide_path": "/api/payments/webhook-debug/",
            "verbose_webhook_diagnostics_enabled": getattr(
                settings, "WEBHOOK_VERBOSE_DIAGNOSTICS", True
            ),
            "how_to_debug": [
                "Open Razorpay Dashboard → Account & Settings → Webhooks → your URL → Webhook Logs → click a delivery. The Response body now includes diagnostics.trace_id and pipeline_step.",
                "Open Render Dashboard → your service → Logs. Search for that trace_id (8 hex chars) or payment_id.",
                "Call GET /api/payments/health/ to verify google_sheets_webapp_configured and smtp_configured.",
                "If pipeline_step is ignored_event_not_in_handled_list, add the event in Razorpay or use a link that emits payment.captured / payment_link.paid / order.paid.",
                "If stopped_amount_gate_failed, payment amount_paise must equal required_amount_paise_inr (9900 for 99 INR).",
                "Set WEBHOOK_VERBOSE_DIAGNOSTICS=false on Render to hide diagnostics in webhook responses.",
            ],
            "note": "Sheet row + email run only when payment amount is exactly REQUIRED_PAYMENT_RUPEES_FOR_EMAIL INR "
            "(default 99, i.e. 9900 paise). Other amounts return HTTP 200 but are skipped. "
            "Configure EMAIL_* on Render and GOOGLE_SHEETS_WEBAPP_URL as before.",
        }
    )


@require_GET
def webhook_debug_guide(request):
    return JsonResponse(
        {
            "where_to_look": {
                "razorpay": "Dashboard → Account & Settings → Webhooks → select endpoint → Logs / Recent deliveries → open one row → Response body.",
                "render": "dashboard.render.com → Your Web Service → Logs (stdout). Every webhook line is prefixed with trace_id in log messages.",
            },
            "response_fields": {
                "diagnostics.trace_id": "Match this in Render logs.",
                "diagnostics.pipeline_step": "Last stage reached; use the how_to_debug list in GET /api/payments/health/ for meanings.",
                "diagnostics.amount_gate_passed": "Must be true for sheet+email (99 INR = 9900 paise).",
                "diagnostics.smtp_is_active_backend": "Must be true on production or email is never sent (503).",
            },
            "env_vars_to_verify_on_render": [
                "GOOGLE_SHEETS_WEBAPP_URL",
                "EMAIL_HOST_USER",
                "EMAIL_HOST_PASSWORD",
                "RAZORPAY_KEY_ID",
                "RAZORPAY_KEY_SECRET",
                "REQUIRED_PAYMENT_RUPEES_FOR_EMAIL",
                "WEBHOOK_VERBOSE_DIAGNOSTICS",
            ],
        }
    )


@csrf_exempt
def razorpay_webhook(request):
    trace_id = secrets.token_hex(4)

    if request.method != "POST":
        logger.warning("[%s] razorpay_webhook rejected: not POST", trace_id)
        return _webhook_response(
            {"error": "Invalid request method"},
            400,
            _build_webhook_diagnostics(trace_id, step="reject_not_post"),
        )

    raw_body = request.body
    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        logger.warning("[%s] razorpay_webhook rejected: invalid JSON", trace_id)
        return _webhook_response(
            {"error": "Invalid JSON"},
            400,
            _build_webhook_diagnostics(trace_id, step="reject_invalid_json"),
        )

    event = data.get("event")
    if event not in WEBHOOK_HANDLED_EVENTS:
        logger.info("[%s] razorpay_webhook ignored event=%s", trace_id, event)
        return _webhook_response(
            {"status": "Ignored event", "event": event},
            200,
            _build_webhook_diagnostics(
                trace_id,
                step="ignored_event_not_in_handled_list",
                event=event,
                handled_events=sorted(WEBHOOK_HANDLED_EVENTS),
            ),
        )

    event_payload = data.get("payload") or {}
    payment, payment_link = _resolve_payment_entities(event_payload)

    if not payment.get("id") and payment_link.get("id"):
        link_json = _fetch_payment_link_by_id(payment_link["id"])
        stub = _payment_stub_from_link_entity(link_json)
        payment = {**stub, **payment}

    payment = _enrich_payment_from_razorpay(payment)
    notes = _combined_notes(payment, payment_link)

    if not _paid_amount_matches_email_threshold(payment):
        paid_paise = _payment_amount_paise(payment)
        required_inr = int(getattr(settings, "REQUIRED_PAYMENT_RUPEES_FOR_EMAIL", 99))
        logger.info(
            "[%s] amount_gate_fail event=%s payment_id=%s paise=%s required_paise=%s currency=%s",
            trace_id,
            event,
            payment.get("id"),
            paid_paise,
            max(0, required_inr) * 100,
            payment.get("currency"),
        )
        return _webhook_response(
            {
                "status": "Skipped: amount does not match required INR for sheet and email",
                "required_rupees": max(0, required_inr),
                "required_paise_inr": max(0, required_inr) * 100,
                "paid_paise": paid_paise,
                "paid_rupees_approx": round(paid_paise / 100, 2) if paid_paise else 0,
                "currency_seen": payment.get("currency") or "INR",
                "gate_disabled_note": "Set REQUIRED_PAYMENT_RUPEES_FOR_EMAIL=-1 to allow any INR amount (not recommended).",
            },
            200,
            _build_webhook_diagnostics(
                trace_id,
                step="stopped_amount_gate_failed",
                event=event,
                payment=payment,
                payment_link=payment_link,
            ),
        )

    logger.info(
        "[%s] amount_gate_ok event=%s payment_id=%s paise=%s",
        trace_id,
        event,
        payment.get("id"),
        _payment_amount_paise(payment),
    )

    try:
        _save_payment_to_google_sheet(payment, payment_link, notes, event)
    except Exception as e:
        logger.exception("[%s] google_sheets_error payment_id=%s", trace_id, payment.get("id"))
        return _webhook_response(
            {"error": f"Google Sheets sync failed: {str(e)}"},
            500,
            _build_webhook_diagnostics(
                trace_id,
                step="failed_google_sheets_after_amount_ok",
                event=event,
                payment=payment,
                payment_link=payment_link,
                sheets_error_short=str(e)[:220],
            ),
        )

    email = _extract_candidate_email(payment, payment_link, notes)
    if not email:
        logger.info("[%s] no_recipient_email payment_id=%s", trace_id, payment.get("id"))
        return _webhook_response(
            {"status": "No email to send"},
            200,
            _build_webhook_diagnostics(
                trace_id,
                step="stopped_no_email_on_payment_or_customer",
                event=event,
                payment=payment,
                payment_link=payment_link,
                note_keys=list(notes.keys()),
            ),
        )

    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        logger.error(
            "[%s] smtp_not_configured backend=%s",
            trace_id,
            settings.EMAIL_BACKEND,
        )
        return _webhook_response(
            {
                "error": (
                    "SMTP is not configured. Set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD "
                    "in your hosting environment (for example Render environment variables), "
                    "redeploy or restart, and ensure Gmail uses an app password if required."
                )
            },
            503,
            _build_webhook_diagnostics(
                trace_id,
                step="failed_smtp_not_configured_sheet_already_saved",
                event=event,
                payment=payment,
                payment_link=payment_link,
                recipient_email=email,
                email_backend=settings.EMAIL_BACKEND,
            ),
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
            logger.error("[%s] smtp_zero_recipients payment_id=%s", trace_id, payment.get("id"))
            return _webhook_response(
                {"error": "SMTP accepted zero recipients"},
                500,
                _build_webhook_diagnostics(
                    trace_id,
                    step="failed_smtp_zero_recipients",
                    event=event,
                    payment=payment,
                    payment_link=payment_link,
                    recipient_email=email,
                ),
            )
    except Exception as e:
        logger.exception("[%s] email_send_exception payment_id=%s", trace_id, payment.get("id"))
        return _webhook_response(
            {"error": f"Email sending failed: {str(e)}"},
            500,
            _build_webhook_diagnostics(
                trace_id,
                step="failed_smtp_exception_after_sheet_ok",
                event=event,
                payment=payment,
                payment_link=payment_link,
                recipient_email=email,
                email_error_short=str(e)[:220],
            ),
        )

    logger.info("[%s] success sheet+email payment_id=%s", trace_id, payment.get("id"))
    return _webhook_response(
        {"status": "Webhook processed and email sent"},
        200,
        _build_webhook_diagnostics(
            trace_id,
            step="complete_sheet_saved_email_sent",
            event=event,
            payment=payment,
            payment_link=payment_link,
            recipient_email=email,
        ),
    )
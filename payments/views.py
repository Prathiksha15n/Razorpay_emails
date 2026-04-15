import json
from datetime import date, timedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

ALLOWED_EMAIL_PAYMENT_PAGE_ID = "pl_SdfIYqzSAAzoB2"


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


@csrf_exempt
def razorpay_webhook(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    payload = request.body
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    event = data.get("event")
    if event not in ["payment.captured", "payment_link.paid"]:
        return JsonResponse({"status": "Ignored event"}, status=200)

    payment = data.get("payload", {}).get("payment", {}).get("entity", {})
    payment_link = data.get("payload", {}).get("payment_link", {}).get("entity", {})
    notes = payment.get("notes", {}) if isinstance(payment.get("notes"), dict) else {}

    payment_page_id = (
        payment.get("payment_link_id")
        or payment_link.get("id")
        or notes.get("payment_page_id")
    )

    if payment_page_id != ALLOWED_EMAIL_PAYMENT_PAGE_ID:
        return JsonResponse({"status": "Email skipped for this payment page"}, status=200)

    email = payment.get("email")
    if not email:
        return JsonResponse({"status": "No email to send"}, status=200)

    if settings.EMAIL_BACKEND != "django.core.mail.backends.smtp.EmailBackend":
        return JsonResponse(
            {
                "error": (
                    "SMTP is not configured. Set EMAIL_HOST_USER and "
                    "EMAIL_HOST_PASSWORD, then restart the server."
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
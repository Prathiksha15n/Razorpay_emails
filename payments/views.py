import json
import hmac
import hashlib
import requests

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import EmailMultiAlternatives
from django.conf import settings


WEBHOOK_SECRET = "razorpay_webhook_secret_987654"

GOOGLE_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbz03oztBueZxLEPOhxjR3z_LMFACKoLyDI_OFbdqwx-g9Lz2X0Wx1gNH2m0lx17FC4f_w/exec"


# @csrf_exempt
# def razorpay_webhook(request):

#     if request.method != "POST":
#         return JsonResponse({"error": "Invalid request method"}, status=400)

#     try:
#         payload = request.body
#         received_signature = request.headers.get("X-Razorpay-Signature")

#         if not received_signature:
#             return JsonResponse({"error": "Signature missing"}, status=400)

#         generated_signature = hmac.new(
#             bytes(WEBHOOK_SECRET, "utf-8"),
#             payload,
#             hashlib.sha256
#         ).hexdigest()

#         if not hmac.compare_digest(generated_signature, received_signature):
#             return JsonResponse({"error": "Invalid signature"}, status=400)

#         data = json.loads(payload.decode("utf-8"))
#         event = data.get("event")

#         print("Webhook Event Received:", event)

#         # ✅ FIXED EVENT HERE
#         if event == "payment.captured":

#             payment = data["payload"]["payment"]["entity"]

#             payment_id = payment.get("id")
#             email = payment.get("email")
#             amount = payment.get("amount", 0) / 100
#             status = payment.get("status")

#             # Safe name handling
#             name = payment.get("name")
#             if not name:
#                 name = payment.get("notes", {}).get("name")

#             print("Payment Captured:", payment_id)

#             if email:

#                 subject = "Campus Experience Appointment Confirmation : Incanto Dynamics Private Ltd."

#                 text_content = f"""
# Dear Candidate,

# Your Campus Experience Appointment has been confirmed.

# Team Incanto
# """

#                 # 🔥 YOUR ORIGINAL HTML — UNTOUCHED
#                 html_content = f"""
# <!DOCTYPE html>
# <html lang="en" style="margin:0;padding:0;">
# <head>
#   <meta charset="UTF-8" />
#   <meta name="viewport" content="width=device-width" />
#   <title>Incanto Dynamics — Campus Experience Appointment Confirmed</title>
#   <style>
#     body,table,td,a {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
#     table,td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; border-collapse:collapse; }}
#     img {{ -ms-interpolation-mode:bicubic; border:0; outline:none; text-decoration:none; display:block; }}
#     body {{
#       margin:0;
#       padding:0;
#       width:100%!important;
#       height:100%!important;
#       background:#ffffff;
#       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
#       color:#000000;
#     }}

#     .w-600{{width:600px;max-width:600px;}}
#     .px-24{{padding-left:24px;padding-right:24px;}}
#     .py-16{{padding-top:16px;padding-bottom:16px;}}
#     .py-32{{padding-top:32px;padding-bottom:32px;}}

#     .btn{{
#       display:inline-block;
#       padding:14px 30px;
#       background:#ff7a1a;
#       color:#000!important;
#       text-decoration:none;
#       border-radius:999px;
#       font-weight:900;
#       font-size:13px;
#       letter-spacing:.16em;
#       text-transform:uppercase;
#       border:2px solid #000;
#       box-shadow:0 0 0 1px rgba(0,0,0,.6),0 0 20px rgba(255,122,26,.6);
#     }}

#     .shadow{{box-shadow:0 18px 50px rgba(0,0,0,.18);border-radius:20px;}}
#     .lead{{font-size:15px;line-height:1.7;margin:0 0 10px;}}
#     .small{{font-size:11px;color:#444;line-height:1.6;}}

#     .h1{{
#       font-size:24px;
#       line-height:1.4;
#       margin:0;
#       font-weight:900;
#       letter-spacing:.12em;
#       text-transform:uppercase;
#     }}

#     .micro-label{{
#       font-family:Consolas,Menlo,Monaco,monospace;
#       font-size:10px;
#       text-transform:uppercase;
#       letter-spacing:.26em;
#       color:#555;
#     }}

#     .tag{{
#       display:inline-block;
#       background:#000;
#       color:#ff7a1a;
#       font-weight:700;
#       font-size:9px;
#       letter-spacing:.22em;
#       padding:7px 14px;
#       border-radius:999px;
#       text-transform:uppercase;
#       border:1px solid #ff7a1a;
#     }}

#     .hero-wrap{{
#       background:radial-gradient(circle at 0 0,#fff3e0 0,#ffffff 55%);
#       padding:20px 24px 26px;
#       border-bottom:1px solid rgba(0,0,0,.06);
#     }}

#     .tech-frame{{
#       border-radius:18px;
#       border:1px solid rgba(0,0,0,.12);
#       padding:18px;
#       position:relative;
#     }}

#     .status-bar{{
#       border-radius:10px;
#       border:1px solid rgba(0,0,0,.18);
#       padding:6px 10px;
#       font-size:10px;
#       text-transform:uppercase;
#       letter-spacing:.18em;
#       display:inline-block;
#       margin-top:8px;
#     }}

#     .status-dot{{
#       width:6px;height:6px;border-radius:999px;
#       background:#22c55e;display:inline-block;margin-right:6px;
#       box-shadow:0 0 8px rgba(34,197,94,.8);
#     }}

#     .hud-line{{
#       height:1px;
#       background:linear-gradient(90deg,transparent,#000,transparent);
#       opacity:.15;
#       margin:12px 0 14px;
#     }}

#     .highlight-box{{
#       background:#fff4e8;
#       border-radius:14px;
#       padding:15px 16px;
#       border:1px solid #ff7a1a;
#     }}

#     @media screen and (max-width:620px){{
#       .w-600{{width:100%!important;}}
#       .px-24{{padding-left:18px!important;padding-right:18px!important;}}
#       .h1{{font-size:20px!important;}}
#       .lead{{font-size:14px!important;}}
#     }}
#   </style>
# </head>

# <body>
# <table width="100%" cellpadding="0" cellspacing="0">
# <tr>
# <td align="center" style="padding:18px;">

# <table class="w-600 shadow" cellpadding="0" cellspacing="0">

# <tr>
# <td class="hero-wrap">
# <span class="micro-label">INCANTO DYNAMICS • CAREER EXCELLENCE • CAMPUS EXPERIENCE</span>

# <div class="tech-frame">

# <img src="https://drive.google.com/thumbnail?id=19dMesjVYsMkkK4RMvuofMpOShaZLLbKO&sz=w600"
#      width="150" alt="Incanto Dynamics">

# <div class="status-bar">
# <span class="status-dot"></span>APPOINTMENT CONFIRMED
# </div>

# <div style="height:6px;"></div>

# <div class="hud-line"></div>

# <h1 class="h1">Campus Experience<br>Appointment</h1>

# <p style="font-size:12px;">
# An exclusive opportunity to explore Industrial Automation & Robotics at Incanto Dynamics.
# </p>

# </div>
# </td>
# </tr>

# <tr>
# <td class="px-24 py-32">

# <p class="lead">Dear Candidate,</p>

# <p class="lead">
# <strong>Congratulations!!</strong> We are pleased to confirm your campus experience appointment on
# <strong>Saturday, 21th February at 10:00 AM</strong> at our institute.
# </p>

# <p class="lead">
# This session will give you an overview of our
# <strong>Industrial Automation & Robotics Module</strong>, including hands-on training,
# career opportunities, and the unique advantages of our institute such as
# advanced labs, industry exposure, and expert mentorship.
# </p>

# <div class="highlight-box">
# <p class="lead" style="font-size:13px;">
# <strong>Appointment Fee & Benefit</strong><br>
# A <strong>registration fee of ₹99</strong> is applicable to confirm your appointment.<br>
# Attendees will receive a <strong>₹1000 fee waiver</strong> towards program enrollment.
# </p>
# </div>

# <p class="lead" style="margin-top:20px;">
# Our team will guide you through the module details and help you understand how this
# program can strengthen your career prospects in the automation industry.
# </p>

# <p class="lead" style="margin-top:20px;">
# We look forward to welcoming you.
# </p>

# <p class="lead" style="margin-top:26px;">
# Warm regards,<br>Team Incanto
# </p>

# </td>
# </tr>

# <tr>
# <td class="px-24 py-16">
# <p class="small" style="text-align:center;">
# © 2025 Incanto Dynamics Pvt Ltd. All rights reserved.
# </p>
# </td>
# </tr>

# </table>
# </td>
# </tr>
# </table>
# </body>
# </html>
# """

#                 email_message = EmailMultiAlternatives(
#                     subject=subject,
#                     body=text_content,
#                     from_email=settings.DEFAULT_FROM_EMAIL,
#                     to=[email],
#                 )

#                 email_message.attach_alternative(html_content, "text/html")
#                 email_message.send()

#                 print("Exact HTML Email sent successfully")

#             sheet_payload = {
#                 "payment_id": payment_id,
#                 "name": name,
#                 "email": email,
#                 "amount": amount,
#                 "status": status
#             }

#             requests.post(GOOGLE_SCRIPT_URL, json=sheet_payload)

#         return JsonResponse({"status": "Webhook received"}, status=200)

#     except Exception as e:
#         print("Webhook Error:", str(e))
#         return JsonResponse({"error": "Server error"}, status=500)


@csrf_exempt
def razorpay_webhook(request):

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=400)

    try:
        payload = request.body
        received_signature = request.headers.get("X-Razorpay-Signature")

        if not received_signature:
            return JsonResponse({"error": "Signature missing"}, status=400)

        generated_signature = hmac.new(
            bytes(WEBHOOK_SECRET, "utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(generated_signature, received_signature):
            return JsonResponse({"error": "Invalid signature"}, status=400)

        data = json.loads(payload.decode("utf-8"))
        event = data.get("event")

        print("Webhook Event Received:", event)

        if event != "payment_link.paid":
            return JsonResponse({"status": "Ignored"}, status=200)

        payment = data["payload"]["payment"]["entity"]

        payment_id = payment.get("id")
        email = payment.get("email")
        amount = payment.get("amount", 0) / 100
        status = payment.get("status")
        name = payment.get("name") or payment.get("notes", {}).get("name")

        print("Processing Payment:", payment_id)

        # =====================================
        # ✅ CHECK IF PAYMENT ALREADY EXISTS
        # =====================================

        check_response = requests.get(
            GOOGLE_SCRIPT_URL,
            params={"check_payment_id": payment_id},
            timeout=5
        )

        check_data = check_response.json()

        if check_data.get("exists"):
            print("Duplicate payment ignored:", payment_id)
            return JsonResponse({"status": "Already processed"}, status=200)

        # =====================================
        # 📊 SAVE TO GOOGLE SHEET
        # =====================================

        sheet_payload = {
            "payment_id": payment_id,
            "name": name,
            "email": email,
            "amount": amount,
            "status": status
        }

        requests.post(GOOGLE_SCRIPT_URL, json=sheet_payload, timeout=5)

        print("Saved to Google Sheet")

        # =====================================
        # 📧 SEND EMAIL (ONLY AFTER SAVE)
        # =====================================

        if email:

            subject = "Campus Experience Appointment Confirmation : Incanto Dynamics Private Ltd."

            text_content = """
Dear Candidate,

Your Campus Experience Appointment has been confirmed.

Team Incanto
"""

            html_content = """
<!DOCTYPE html>
<html lang="en" style="margin:0;padding:0;">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width" />
<title>Incanto Dynamics — Campus Experience Appointment Confirmed</title>

<style>
body,table,td,a { -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }
table,td { mso-table-lspace:0pt; mso-table-rspace:0pt; border-collapse:collapse; }
img { -ms-interpolation-mode:bicubic; border:0; outline:none; text-decoration:none; display:block; }

body {
  margin:0;
  padding:0;
  width:100%!important;
  height:100%!important;
  background:#ffffff;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:#000000;
}

.w-600 { width:600px; max-width:600px; }
.px-24 { padding-left:24px; padding-right:24px; }
.py-16 { padding-top:16px; padding-bottom:16px; }
.py-32 { padding-top:32px; padding-bottom:32px; }

.btn {
  display:inline-block;
  padding:14px 30px;
  background:#ff7a1a;
  color:#000 !important;
  text-decoration:none;
  border-radius:999px;
  font-weight:900;
  font-size:13px;
  letter-spacing:.16em;
  text-transform:uppercase;
  border:2px solid #000;
  box-shadow:0 0 0 1px rgba(0,0,0,.6),0 0 20px rgba(255,122,26,.6);
}

.shadow {
  box-shadow:0 18px 50px rgba(0,0,0,.18);
  border-radius:20px;
}

.lead {
  font-size:15px;
  line-height:1.7;
  margin:0 0 10px;
}

.small {
  font-size:11px;
  color:#444;
  line-height:1.6;
}

.h1 {
  font-size:24px;
  line-height:1.4;
  margin:0;
  font-weight:900;
  letter-spacing:.12em;
  text-transform:uppercase;
}

.micro-label {
  font-family:Consolas,Menlo,Monaco,monospace;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.26em;
  color:#555;
}

.tag {
  display:inline-block;
  background:#000;
  color:#ff7a1a;
  font-weight:700;
  font-size:9px;
  letter-spacing:.22em;
  padding:7px 14px;
  border-radius:999px;
  text-transform:uppercase;
  border:1px solid #ff7a1a;
}

.hero-wrap {
  background:radial-gradient(circle at 0 0, #fff3e0 0, #ffffff 55%);
  padding:20px 24px 26px;
  border-bottom:1px solid rgba(0,0,0,.06);
}

.tech-frame {
  border-radius:18px;
  border:1px solid rgba(0,0,0,.12);
  padding:18px;
  position:relative;
}

.status-bar {
  border-radius:10px;
  border:1px solid rgba(0,0,0,.18);
  padding:6px 10px;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.18em;
  display:inline-block;
  margin-top:8px;
}

.status-dot {
  width:6px;
  height:6px;
  border-radius:999px;
  background:#22c55e;
  display:inline-block;
  margin-right:6px;
  box-shadow:0 0 8px rgba(34,197,94,.8);
}

.hud-line {
  height:1px;
  background:linear-gradient(90deg, transparent, #000, transparent);
  opacity:.15;
  margin:12px 0 14px;
}

.highlight-box {
  background:#fff4e8;
  border-radius:14px;
  padding:15px 16px;
  border:1px solid #ff7a1a;
}

@media screen and (max-width:620px){
  .w-600 { width:100%!important; }
  .px-24 { padding-left:18px!important; padding-right:18px!important; }
  .h1 { font-size:20px!important; }
  .lead { font-size:14px!important; }
}
</style>
</head>

<body>
<table width="100%" cellpadding="0" cellspacing="0">
<tr>
<td align="center" style="padding:18px;">

<table class="w-600 shadow" cellpadding="0" cellspacing="0">

<tr>
<td class="hero-wrap">
<span class="micro-label">INCANTO DYNAMICS • CAREER EXCELLENCE • CAMPUS EXPERIENCE</span>

<div class="tech-frame">

<img src="https://drive.google.com/thumbnail?id=19dMesjVYsMkkK4RMvuofMpOShaZLLbKO&sz=w600"
width="150" alt="Incanto Dynamics">

<div class="status-bar">
<span class="status-dot"></span>APPOINTMENT CONFIRMED
</div>

<div style="height:6px;"></div>

<div class="hud-line"></div>

<h1 class="h1">Campus Experience<br>Appointment</h1>

<p style="font-size:12px;">
An exclusive opportunity to explore Industrial Automation & Robotics at Incanto Dynamics.
</p>

</div>
</td>
</tr>

<tr>
<td class="px-24 py-32">

<p class="lead">Dear Candidate,</p>

<p class="lead">
<strong>Congratulations!!</strong> We are pleased to confirm your campus experience appointment on
<strong>Saturday, 21st February at 10:00 AM</strong> at our institute.
</p>

<p class="lead">
This session will give you an overview of our
<strong>Industrial Automation & Robotics Module</strong>, including hands-on training,
career opportunities, and the unique advantages of our institute such as
advanced labs, industry exposure, and expert mentorship.
</p>

<div class="highlight-box">
<p class="lead" style="font-size:13px;">
<strong>Appointment Fee & Benefit</strong><br>
A <strong>registration fee of ₹99</strong> is applicable to confirm your appointment.<br>
Attendees will receive a <strong>₹1000 fee waiver</strong> towards program enrollment.
</p>
</div>

<p class="lead" style="margin-top:20px;">
Our team will guide you through the module details and help you understand how this
program can strengthen your career prospects in the automation industry.
</p>

<p class="lead" style="margin-top:20px;">
We look forward to welcoming you.
</p>

<p class="lead" style="margin-top:26px;">
Warm regards,<br>Team Incanto
</p>

</td>
</tr>

<tr>
<td class="px-24 py-16">
<p class="small" style="text-align:center;">
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

"""

            email_message = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
            )

            email_message.attach_alternative(html_content, "text/html")
            email_message.send()

            print("Exact HTML Email sent successfully")

        return JsonResponse({"status": "Webhook processed"}, status=200)

    except Exception as e:
        print("Webhook Error:", str(e))
        return JsonResponse({"error": "Server error"}, status=500)

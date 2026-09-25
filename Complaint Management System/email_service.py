import os
import smtplib
import time
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from fpdf import FPDF
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "samsonwork67@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")

EMAIL_HEADER_RE = re.compile(r'[\r\n]')

def sanitize_header(value: str) -> str:
    """Sanitize email header to prevent injection."""
    if not isinstance(value, str):
        value = str(value)
    return EMAIL_HEADER_RE.sub('', value).strip()

def send_email(to_email, subject, body, attachment_path=None):
    start_time = time.perf_counter()
    if not SMTP_USER or not SMTP_PASSWORD:
        raise ValueError("SMTP_USER or SMTP_PASSWORD is not set in the environment.")

    # Sanitize headers to prevent injection
    to_email = sanitize_header(to_email)
    subject = sanitize_header(subject)
    SMTP_USER = sanitize_header(SMTP_USER)

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(attachment_path)}")
        msg.attach(part)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
    print(f"[PERF] send_email to {to_email} took: {time.perf_counter() - start_time:.4f}s")

def generate_complaint_pdf(ref_id, payload):
    start_time = time.perf_counter()
    pdf_dir = os.path.join("static", "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"{ref_id}.pdf")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, f"Complaint Summary - {ref_id}", ln=True, align="C")

    for key, value in payload.items():
        # Encode key and value to latin-1 to avoid fpdf character encoding issues
        k_str = str(key).encode('latin-1', 'replace').decode('latin-1')
        v_str = str(value).encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, f"{k_str}: {v_str}")

    pdf.output(pdf_path)
    print(f"[PERF] generate_complaint_pdf took: {time.perf_counter() - start_time:.4f}s")
    return pdf_path

def send_complaint_notifications(payload, complaint_ref_id):
    """
    Generates the complaint PDF and dispatches notifications to both 
    the Admin (with the PDF attached) and the complainant.
    Does not crash if email transmission or PDF generation fails.
    """
    pdf_path = None
    try:
        pdf_path = generate_complaint_pdf(complaint_ref_id, payload)
        print(f"[EMAIL_SERVICE] Generated PDF at: {pdf_path}")
    except Exception as e:
        print(f"[EMAIL_SERVICE] Failed to generate PDF: {e}")

    # Send admin email
    try:
        admin_body = (
            f"A new complaint has been submitted.\n\n"
            f"Reference ID: {complaint_ref_id}\n"
            f"Name: {payload.get('Your Name')}\n"
            f"Category: {payload.get('Type of Complaint')}\n"
            f"Details: {payload.get('Details of Complaint')}"
        )
        send_email(
            ADMIN_EMAIL,
            f"New Complaint Received - {complaint_ref_id}",
            admin_body,
            attachment_path=pdf_path
        )
        print(f"[EMAIL_SERVICE] Admin email sent successfully.")
    except Exception as e:
        print(f"[EMAIL_SERVICE] Failed to send admin email: {e}")

    # Send complainant email
    try:
        complainant_email = payload.get("Email address")
        if complainant_email and isinstance(complainant_email, str) and "@" in complainant_email and "." in complainant_email:
            complainant_body = (
                f"Thank you for your complaint. We have received your submission (Reference ID: {complaint_ref_id}). "
                f"We will review your complaint and get back to you within a couple of working days."
            )
            send_email(
                complainant_email,
                f"Complaint Received - {complaint_ref_id}",
                complainant_body
            )
            print(f"[EMAIL_SERVICE] Complainant email sent successfully to {complainant_email}.")
    except Exception as e:
        print(f"[EMAIL_SERVICE] Failed to send complainant email: {e}")

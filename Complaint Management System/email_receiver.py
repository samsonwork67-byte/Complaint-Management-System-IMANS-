import os
import imaplib
import email
import socket
from email.header import decode_header
from datetime import datetime
from postgres_client import db_client, _generate_ref_id_atomic
from dotenv import load_dotenv
import uuid
import threading
from email_service import send_complaint_notifications

load_dotenv()

# -----------------------
# CONFIG
# -----------------------
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", 993))
EMAIL_USER = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASS = os.environ.get("EMAIL_PASSWORD")

# -----------------------
# HELPERS
# -----------------------
def clean_text(text):
    if not text:
        return ""
    return str(text).replace("\r", " ").replace("\n", " ").strip()

def decode_mime_words(s):
    if not s:
        return ""
    decoded = decode_header(s)
    return "".join(
        part.decode(enc or "utf-8") if isinstance(part, bytes) else part
        for part, enc in decoded
    )

def extract_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                return part.get_payload(decode=True).decode(errors="ignore")
    else:
        return msg.get_payload(decode=True).decode(errors="ignore")
    return ""

def simple_classify(subject, body):
    text = (subject + " " + body).lower()

    complaint_keywords = [
        "complaint", "complain", "report", "issue", "problem",
        "favouritism", "favoritism", "harassment", "misconduct",
        "unfair", "bully", "abuse", "corruption",
        "aduan", "laporan", "tidak adil", "rasuah"
    ]

    strong_indicators = [
        "i want to complain",
        "i would like to report",
        "this is a complaint",
        "i am reporting",
        "saya ingin membuat aduan",
        "saya nak buat aduan"
    ]

    spam_keywords = [
        "buy now", "discount", "promotion", "click here",
        "subscribe", "free money", "earn money"
    ]

    score = 0

    # strong signals (VERY important)
    for k in strong_indicators:
        if k in text:
            score += 5

    # normal signals
    for k in complaint_keywords:
        if k in text:
            score += 2

    # spam penalty
    for k in spam_keywords:
        if k in text:
            score -= 5

    # extra safety: if email contains emotional complaint language
    emotional_words = ["unfair", "angry", "worst", "terrible", "wrong", "bias"]
    for w in emotional_words:
        if w in text:
            score += 1

    return score >= 2

def is_already_processed(message_id):
    if not message_id:
        return False
    try:
        res = db_client.table("processed_emails").select("id").eq("message_id", message_id).execute()
        return bool(res.data)
    except:
        return False

def mark_as_processed(message_id):
    if not message_id:
        return
    try:
        db_client.table("processed_emails").insert({
            "message_id": message_id,
            "processed_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"[EMAIL RECEIVER] Failed to mark processed: {e}")

# -----------------------
# PROCESS SINGLE EMAIL
# -----------------------
OWN_EMAIL = (os.environ.get("EMAIL_ADDRESS") or "").strip().lower()

def process_email(msg):
    subject = decode_mime_words(msg.get("subject") or "")
    from_email_raw = msg.get("from") or ""
    sender_email = email.utils.parseaddr(from_email_raw)[1].strip().lower()
    message_id = msg.get("Message-ID", "").strip()

    # Hard stop: never process email sent from our own system account
    if sender_email == OWN_EMAIL:
        print(f"[EMAIL RECEIVER] Skipped self-sent email: {subject}")
        mark_as_processed(message_id)
        return

    skip_senders = [
        'noreply', 'no-reply', 'donotreply', 'mailer-daemon',
        'google.com', 'github.com', 'supabase.com', 'canva.com',
        'accounts.google.com', 'googleplay', 'engage.canva.com'
    ]
    if any(skip in sender_email for skip in skip_senders):
        print(f"[EMAIL RECEIVER] Skipped automated email from {sender_email}")
        mark_as_processed(message_id)
        return

    body = clean_text(extract_body(msg))

    if not simple_classify(subject, body):
        print(f"[EMAIL RECEIVER] Ignored non-complaint email from {sender_email}")
        mark_as_processed(message_id)
        return

    # Generate reference ID using atomic sequence
    ref_id = _generate_ref_id_atomic(db_client)

    tracking_id = str(uuid.uuid4())

    complaint_payload = {
        "Timestamp": datetime.now().isoformat(),
        "Tracking ID": tracking_id,
        "Complaint Reference ID": ref_id,
        "Your Name": None,
        "Email address": sender_email,
        "Your Phone Number": None,
        "Name of The Accused": None,
        "Position of The Accused": None,
        "Company of The Accused": None,
        "Type of Complaint": subject or "EMAIL COMPLAINT",
        "Date of Incident": None,
        "Time of Incident (General)": None,
        "Location of Incident": None,
        "Details of Complaint": body,
        "Other involved parties (If applicable)": None,
        "Upload file if there are evidences": None,
        "Status": "ONGOING",
    }

    try:
        insert_res = db_client.table("complaint").insert(complaint_payload).execute()

        if insert_res.data:
            print(f"[EMAIL RECEIVER] Complaint {ref_id} created from {sender_email}")

            mark_as_processed(message_id)

            if sender_email == EMAIL_USER.lower():
                print("[EMAIL RECEIVER] Skipping self-sent email")
                return

        else:
            print("[EMAIL RECEIVER] Insert failed")

    except Exception as e:
        print("[EMAIL RECEIVER ERROR]", e)

# -----------------------
# FETCH AND PROCESS NEW EMAIL BY UID
# -----------------------
def fetch_and_process_uid(mail, uid):
    try:
        res, msg_data = mail.uid('fetch', uid, '(RFC822)')
        if res != "OK":
            return
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        process_email(msg)
    except Exception as e:
        print(f"[EMAIL RECEIVER] Error fetching UID {uid}: {e}")

# -----------------------
# STARTUP EMAIL SCAN
# -----------------------
def startup_scan(mail):
    print("[EMAIL RECEIVER] Running startup scan for missed emails...")

    status, data = mail.uid('search', None, 'UNSEEN')

    if status != "OK":
        print("[EMAIL RECEIVER] Startup scan failed")
        return

    uids = data[0].split() if data[0] else []

    print(f"[EMAIL RECEIVER] Found {len(uids)} unseen emails during downtime")

    for uid in uids:
        try:
            res, msg_data = mail.uid('fetch', uid, '(RFC822)')
            if res != "OK":
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            process_email(msg)

        except Exception as e:
            print(f"[EMAIL RECEIVER] Startup scan error UID {uid}: {e}")

# -----------------------
# IMAP IDLE LISTENER
# -----------------------
def idle_listener():
    while True:
        try:
            print("[EMAIL RECEIVER] Connecting to IMAP...")
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
            mail.login(EMAIL_USER, EMAIL_PASS)
            mail.select("INBOX")
            startup_scan(mail)

            # Get current highest UID so we only process NEW ones
            status, data = mail.uid('search', None, 'ALL')
            existing_uids = data[0].split() if data[0] else []
            last_uid = int(existing_uids[-1]) if existing_uids else 0
            print(f"[EMAIL RECEIVER] Watching for emails after UID {last_uid}...")

            # Send IDLE command
            tag = mail._new_tag().decode()
            mail.send(f"{tag} IDLE\r\n".encode())

            # Wait for server response
            response = mail.readline()
            if b'idling' not in response.lower() and b'+ ' not in response:
                print(f"[EMAIL RECEIVER] IDLE not supported or failed: {response}")
                mail.logout()
                import time; time.sleep(30)
                continue

            print("[EMAIL RECEIVER] IDLE mode active — waiting for new emails...")

            # Set socket timeout to 29 minutes (IMAP IDLE max is 30 min)
            mail.socket().settimeout(29 * 60)

            try:
                while True:
                    # Wait for server to send EXISTS notification
                    line = mail.readline()
                    if not line:
                        break

                    # Server sends "* N EXISTS" when new email arrives
                    if b'EXISTS' in line:
                        print(f"[EMAIL RECEIVER] New email detected: {line.decode().strip()}")

                        # Exit IDLE
                        mail.send(b'DONE\r\n')
                        mail.readline()  # read server response to DONE

                        # Search for emails newer than last_uid
                        status, new_data = mail.uid('search', None, f'UID {last_uid + 1}:*')
                        new_uids = new_data[0].split() if new_data[0] else []

                        for uid in new_uids:
                            uid_int = int(uid)
                            if uid_int > last_uid:
                                fetch_and_process_uid(mail, uid)
                                last_uid = uid_int

                        # Re-enter IDLE
                        tag = mail._new_tag().decode()
                        mail.send(f"{tag} IDLE\r\n".encode())
                        mail.readline()
                        print("[EMAIL RECEIVER] Re-entered IDLE mode...")

            except socket.timeout:
                # Normal — IDLE timed out after 29 min, reconnect
                print("[EMAIL RECEIVER] IDLE timeout, reconnecting...")
                try:
                    mail.send(b'DONE\r\n')
                    mail.readline()
                except:
                    pass

            mail.logout()

        except Exception as e:
            print(f"[EMAIL RECEIVER] Connection error: {e}")
            import time; time.sleep(15)

# -----------------------
# START (called from app.py)
# -----------------------
def fetch_unread_emails():
    """Called by app.py — starts IDLE listener in background thread if not already running."""
    pass  # IDLE thread handles everything

def start_idle_listener():
    thread = threading.Thread(target=idle_listener, daemon=True)
    thread.start()
    print("[EMAIL RECEIVER] IDLE listener started")

if __name__ == "__main__":
    print("[EMAIL RECEIVER] Starting IDLE email listener...")
    idle_listener()
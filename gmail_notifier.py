#!/usr/bin/env python3
"""
gmail_notifier.py
-----------------
Does two things on a loop (checks every minute):

  1. Gmail check  — reads your unread Gmail messages and prints a
                    summary to the terminal (and optionally tells Alexa).

  2. Work reminder — fires a desktop notification and an optional Alexa
                     announcement 10 minutes before your work start time
                     on the days you configure.

100 % FREE — uses:
  • Gmail API        (free, needs a Google Cloud project — see SETUP.md)
  • plyer            (free desktop notifications — pip install plyer)
  • alexapy          (optional Alexa TTS — pip install alexapy)

Quick start:
  1.  pip install --upgrade google-auth-oauthlib google-auth-httplib2
          google-api-python-client plyer requests alexapy
  2.  Follow SETUP.md to get credentials.json from Google Cloud Console.
  3.  python3 gmail_notifier.py
      (First run opens a browser to log in to your Google account.)
"""

import os
import sys
import time
import asyncio
import datetime

# ── USER CONFIGURATION ────────────────────────────────────────────────────────

# Your name — used in the reminder message
USER_NAME = "Kaushal"

# How many unread emails to display at once
MAX_EMAILS_TO_SHOW = 5

# Days when the work reminder fires
# 0 = Monday, 1 = Tuesday, 2 = Wednesday, 3 = Thursday, 4 = Friday,
# 5 = Saturday, 6 = Sunday
WORK_REMINDER_DAYS = {0, 1}   # Monday and Tuesday

# The time your shift actually starts (used in the reminder message)
SHIFT_START_TIME = datetime.time(12, 39)

# Reminder fires this many minutes BEFORE the shift start
REMINDER_LEAD_MINUTES = 10

# ── OPTIONAL ALEXA INTEGRATION ────────────────────────────────────────────────
# Leave blank ("") to skip Alexa — desktop notifications still work.
# Set via environment variables:
#   export AMAZON_EMAIL="your@email.com"
#   export AMAZON_PASSWORD="your_amazon_password"
#   export ALEXA_DEVICE_NAME="Echo"
AMAZON_EMAIL      = os.environ.get("AMAZON_EMAIL", "")
AMAZON_PASSWORD   = os.environ.get("AMAZON_PASSWORD", "")
ALEXA_DEVICE_NAME = os.environ.get("ALEXA_DEVICE_NAME", "Echo")

# ── GMAIL CREDENTIALS ────────────────────────────────────────────────────────
# Path to credentials.json downloaded from Google Cloud Console.
# See SETUP.md for step-by-step instructions.
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")

# ─────────────────────────────────────────────────────────────────────────────

_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Derived reminder time and message — computed from the config above
_reminder_time = (
    datetime.datetime.combine(datetime.date.today(), SHIFT_START_TIME)
    - datetime.timedelta(minutes=REMINDER_LEAD_MINUTES)
).time()

_REMINDER_MESSAGE = (
    f"Heads up, {USER_NAME}! You need to leave for work in "
    f"{REMINDER_LEAD_MINUTES} minutes. "
    f"Your shift starts at {SHIFT_START_TIME.strftime('%H:%M')}. Don't be late!"
)

# Tracks whether the reminder has already fired today
_reminder_fired_date: datetime.date | None = None


# ── GMAIL ─────────────────────────────────────────────────────────────────────

def _get_gmail_service():
    """
    Authenticate with Gmail (opens browser on first run to ask permission)
    and return a Gmail API service object.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print(
            "[ERROR] Google API libraries not installed.\n"
            "        Run:  pip install google-auth-oauthlib "
            "google-auth-httplib2 google-api-python-client"
        )
        sys.exit(1)

    token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(
                    f"[ERROR] credentials.json not found at {CREDENTIALS_FILE}\n"
                    "        Follow the steps in SETUP.md to download it."
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, _SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as fh:
            fh.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def check_gmail() -> list[dict]:
    """
    Return a list of unread messages (up to MAX_EMAILS_TO_SHOW).
    Each dict has 'from', 'subject', and 'snippet'.
    """
    service = _get_gmail_service()
    result  = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["UNREAD", "INBOX"], maxResults=MAX_EMAILS_TO_SHOW)
        .execute()
    )
    messages = result.get("messages", [])
    emails   = []

    for msg in messages:
        detail  = service.users().messages().get(userId="me", id=msg["id"]).execute()
        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        emails.append(
            {
                "from":    headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(no subject)"),
                "snippet": detail.get("snippet", ""),
            }
        )

    return emails


def print_emails(emails: list[dict]) -> None:
    if not emails:
        print("  ✅  No unread emails in your inbox.")
        return

    print(f"  📬  You have {len(emails)} unread email(s):\n")
    for i, email in enumerate(emails, 1):
        print(f"  [{i}] From    : {email['from']}")
        print(f"       Subject : {email['subject']}")
        print(f"       Preview : {email['snippet'][:120]}")
        print()


# ── DESKTOP NOTIFICATION ──────────────────────────────────────────────────────

def send_desktop_notification(title: str, message: str) -> None:
    """Show a desktop notification using plyer (cross-platform, free)."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Gmail Notifier",
            timeout=30,
        )
    except ImportError:
        print("[WARN] plyer not installed — desktop notification skipped.")
        print(f"       Notification: {title} — {message}")
    except Exception as exc:
        print(f"[WARN] Desktop notification failed: {exc}")


# ── ALEXA TTS (optional) ──────────────────────────────────────────────────────

async def _alexa_say_async(text: str) -> None:
    try:
        from alexapy import AlexaLogin, AlexaAPI
    except ImportError:
        return  # Alexa not installed — silently skip

    login = AlexaLogin(
        url="amazon.com",
        email=AMAZON_EMAIL,
        password=AMAZON_PASSWORD,
        outputpath=os.path.dirname(os.path.abspath(__file__)),
        debug=False,
    )
    await login.login_with_cookie()

    if not login.status.get("login_successful"):
        print("[WARN] Alexa login failed — skipping Alexa announcement.")
        await login.close()
        return

    devices = await AlexaAPI.get_devices(login)
    target  = next(
        (
            d for d in devices
            if (d.get("accountName") or d.get("deviceName") or "").lower()
            == ALEXA_DEVICE_NAME.lower()
        ),
        None,
    )

    if target is None:
        print(f"[WARN] Alexa device '{ALEXA_DEVICE_NAME}' not found.")
        await login.close()
        return

    api = AlexaAPI(target, login)
    try:
        await api.send_tts(text)
    finally:
        await login.close()


def alexa_say(text: str) -> None:
    """Speak *text* on Alexa (only if credentials are configured)."""
    if AMAZON_EMAIL and AMAZON_PASSWORD:
        try:
            asyncio.run(_alexa_say_async(text))
        except Exception as exc:
            print(f"[WARN] Alexa TTS error: {exc}")


# ── REMINDER LOGIC ────────────────────────────────────────────────────────────

def _day_names(day_set: set[int]) -> str:
    """Convert a set of weekday numbers to a readable string."""
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return ", ".join(names[d] for d in sorted(day_set))


def check_work_reminder() -> None:
    """Fire the work reminder if it is the right day and time."""
    global _reminder_fired_date

    now   = datetime.datetime.now()
    today = now.date()

    is_work_day      = now.weekday() in WORK_REMINDER_DAYS
    is_reminder_time = (now.hour == _reminder_time.hour and now.minute == _reminder_time.minute)
    already_fired    = (_reminder_fired_date == today)

    if is_work_day and is_reminder_time and not already_fired:
        print(f"\n⏰  [{now:%H:%M}] WORK REMINDER FIRING!")
        send_desktop_notification("⏰ Work reminder!", _REMINDER_MESSAGE)
        alexa_say(_REMINDER_MESSAGE)
        _reminder_fired_date = today
        print(f"    {_REMINDER_MESSAGE}\n")


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  Gmail Notifier + Work Reminder")
    print("=" * 60)
    print(f"  Max emails shown   : {MAX_EMAILS_TO_SHOW}")
    print(f"  Reminder days      : {_day_names(WORK_REMINDER_DAYS)}")
    print(f"  Reminder time      : {_reminder_time.strftime('%H:%M')} "
          f"({REMINDER_LEAD_MINUTES} min before {SHIFT_START_TIME.strftime('%H:%M')})")
    print(f"  Alexa enabled      : {'Yes' if AMAZON_EMAIL else 'No (set AMAZON_EMAIL to enable)'}")
    print("=" * 60)
    print()

    # ── Initial Gmail check on startup ────────────────────────────
    print(f"[{datetime.datetime.now():%H:%M:%S}] Checking Gmail …")
    try:
        emails = check_gmail()
        print_emails(emails)
        if emails:
            send_desktop_notification(
                "📬 Unread Gmail",
                f"You have {len(emails)} unread email(s). Check your terminal.",
            )
    except Exception as exc:
        print(f"[WARN] Gmail check failed: {exc}")

    # ── Continuous loop ───────────────────────────────────────────
    print(f"[{datetime.datetime.now():%H:%M:%S}] Monitoring started. Press Ctrl+C to stop.\n")

    gmail_check_interval = 300   # re-check Gmail every 5 minutes
    last_gmail_check     = time.time()

    while True:
        try:
            # Work reminder check — runs every minute
            check_work_reminder()

            # Gmail — re-check every 5 minutes
            if time.time() - last_gmail_check >= gmail_check_interval:
                print(f"\n[{datetime.datetime.now():%H:%M:%S}] Re-checking Gmail …")
                try:
                    emails = check_gmail()
                    print_emails(emails)
                    if emails:
                        send_desktop_notification(
                            "📬 Unread Gmail",
                            f"You have {len(emails)} unread email(s). Check your terminal.",
                        )
                except Exception as exc:
                    print(f"[WARN] Gmail check failed: {exc}")
                last_gmail_check = time.time()

        except KeyboardInterrupt:
            print("\n👋  Stopped.")
            sys.exit(0)

        time.sleep(60)  # wait one minute before next reminder check


if __name__ == "__main__":
    main()

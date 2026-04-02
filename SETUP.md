# 📖 SETUP GUIDE — gmail_notifier.py

> **Everything here is 100% free.** No paid services, no credit cards.

---

## What this script does

| Feature | Details |
|---|---|
| 📬 Gmail check | Shows your unread emails in the terminal (and a desktop popup) |
| ⏰ Work reminder | At **12:29** on **Monday & Tuesday** you get a desktop notification (and Alexa speaks if set up) saying you need to leave in 10 minutes |

---

## Step 1 — Install Python (free)

If you don't have Python yet:

1. Go to **https://www.python.org/downloads/**
2. Download the latest Python 3 installer
3. Run it — tick **"Add Python to PATH"** before clicking Install

Open a terminal (Command Prompt on Windows, Terminal on Mac/Linux) and check it works:

```
python3 --version
```

---

## Step 2 — Install the required libraries (free)

Copy-paste this one command into your terminal:

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client plyer requests alexapy
```

Wait for it to finish (about 1–2 minutes).

---

## Step 3 — Set up Gmail access (free, takes ~5 minutes)

Google needs you to create a small "project" so the script can read your Gmail.  
**You will never be charged — the Gmail API free tier allows millions of reads per day.**

### 3a — Create a Google Cloud project

1. Open **https://console.cloud.google.com/** in your browser
2. Sign in with your Google / Gmail account
3. Click the project dropdown at the top → **"New Project"**
4. Give it any name (e.g. `gmail-notifier`) → click **Create**

### 3b — Enable the Gmail API

1. In the search bar at the top type **"Gmail API"** and click on it
2. Click **Enable**

### 3c — Create OAuth credentials

1. In the left sidebar go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. If asked, click **Configure consent screen**:
   - Choose **External** → click Create
   - Fill in "App name" (e.g. `My Gmail Notifier`) and your email → Save & Continue
   - Click **Add or remove scopes** → search for `gmail.readonly` → tick it → Update → Save & Continue
   - Under **Test users** click **+ Add users** → add your own Gmail address → Save & Continue
4. Back on Create credentials → **OAuth client ID**:
   - Application type: **Desktop app**
   - Name: anything → click **Create**
5. Click **Download JSON** — save the file as **`credentials.json`**
6. Move `credentials.json` into the same folder as `gmail_notifier.py`

---

## Step 4 — Run the script for the first time

```bash
python3 gmail_notifier.py
```

A browser window will open automatically asking you to log in with your Google account.  
Click **Allow** — this only happens once.

The script will then:
- Show your unread emails in the terminal
- Show a desktop notification
- Keep running and remind you at 12:29 on Monday & Tuesday

Press **Ctrl + C** to stop it.

---

## Step 5 — (Optional) Add Alexa voice reminders

If you want Alexa to *speak* the reminder:

```bash
# On Mac / Linux:
export AMAZON_EMAIL="your@amazon.com"
export AMAZON_PASSWORD="yourpassword"
export ALEXA_DEVICE_NAME="Echo"    # exact name shown in the Alexa app

# On Windows Command Prompt:
set AMAZON_EMAIL=your@amazon.com
set AMAZON_PASSWORD=yourpassword
set ALEXA_DEVICE_NAME=Echo
```

Then run the script in the same terminal window.

---

## Step 6 — Make it run automatically every time your computer starts (optional)

### On Linux / Mac (using cron)

1. Open terminal and type:

```bash
crontab -e
```

2. Add this line at the bottom (replace the path with your actual path):

```
@reboot python3 /full/path/to/gmail_notifier.py >> /tmp/gmail_notifier.log 2>&1
```

### On Windows (Task Scheduler)

1. Press **Win + S** → search "Task Scheduler" → Open it
2. Click **Create Basic Task** on the right
3. Name: `Gmail Notifier` → Next
4. Trigger: **When the computer starts** → Next
5. Action: **Start a program**
   - Program: `python`
   - Arguments: `C:\path\to\gmail_notifier.py`
6. Finish

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `credentials.json not found` | Make sure you downloaded it from Step 3c and put it in the same folder as the script |
| Browser doesn't open | Run `python3 gmail_notifier.py` in a normal terminal (not inside VS Code's integrated terminal) |
| `No module named 'plyer'` | Run `pip install plyer` |
| Desktop notification doesn't show | On Mac, go to System Settings → Notifications → Python → Allow notifications |
| Alexa doesn't speak | Check `AMAZON_EMAIL`/`AMAZON_PASSWORD` env vars are set; make sure the device name matches exactly what's in the Alexa app |

---

## Summary of files

```
your-project-folder/
├── gmail_notifier.py   ← the script
├── credentials.json    ← you download this from Google (Step 3c)
└── token.json          ← auto-created on first run (don't share this!)
```

**Never share `credentials.json` or `token.json` with anyone — they give access to your Gmail.**

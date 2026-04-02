#!/usr/bin/env python3
"""
alexa_good_morning.py
---------------------
Monitors your home Wi-Fi for your phone (by MAC address).
When your phone is detected during the morning window Alexa announces:

  • "Good morning, Kaushal!"
  • Current local time (Australia)
  • Today's weather high / low temperature (Open-Meteo, free — no API key)
  • Today's Nepali (BS) date and day name
  • Any special events / festivals in Nepal today (Nepali Patro API)

Requirements:
    pip install scapy alexapy requests nepali-datetime

How it works:
    1. Every POLL_INTERVAL seconds the script sends an ARP request across
       the local subnet.  If the phone's MAC address replies the phone is
       considered awake / screen-on.
    2. The check only runs inside the MORNING_START … MORNING_END window.
    3. Once Alexa has spoken a flag prevents a second greeting until the
       following day.

Usage (requires root / admin for raw network access):
    sudo python3 alexa_good_morning.py
"""

import os
import time
import datetime
import asyncio
import sys

import requests
import scapy.all as scapy

# ── USER CONFIGURATION ────────────────────────────────────────────────────────

# Your name — used in the greeting
USER_NAME = "Kaushal"

# Your home network subnet in CIDR notation
SUBNET = "192.168.1.0/24"

# MAC address of your phone (lowercase, colon-separated)
PHONE_MAC = "aa:bb:cc:dd:ee:ff"

# Morning window — Alexa will only speak during this time range
MORNING_START = datetime.time(6, 0)   # 06:00 AM
MORNING_END   = datetime.time(10, 0)  # 10:00 AM

# How often (in seconds) to ARP-scan for the phone
POLL_INTERVAL = 30

# ── LOCATION (for weather) ────────────────────────────────────────────────────
# Default: Sydney, Australia.  Change to your city's coordinates.
# Find yours at https://www.latlong.net/
LATITUDE  = -33.8688
LONGITUDE = 151.2093
# IANA timezone name for your location (used by the Open-Meteo weather API)
# Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
TIMEZONE = "Australia/Sydney"

# ── ALEXA ACCOUNT CREDENTIALS ─────────────────────────────────────────────────
# Set these as environment variables — never hard-code credentials:
#
#   export AMAZON_EMAIL="your@email.com"
#   export AMAZON_PASSWORD="your_amazon_password"
#   export ALEXA_DEVICE_NAME="Echo"   # name shown in the Alexa app
#
AMAZON_EMAIL      = os.environ.get("AMAZON_EMAIL", "")
AMAZON_PASSWORD   = os.environ.get("AMAZON_PASSWORD", "")
ALEXA_DEVICE_NAME = os.environ.get("ALEXA_DEVICE_NAME", "Echo")

# ─────────────────────────────────────────────────────────────────────────────

# Nepali month names in English (Bikram Sambat)
_NEPALI_MONTHS = [
    "Baisakh", "Jestha", "Ashadh", "Shrawan",
    "Bhadra",  "Ashwin", "Kartik", "Mangsir",
    "Poush",   "Magh",   "Falgun", "Chaitra",
]


# ── DATA FETCHERS ─────────────────────────────────────────────────────────────

def get_weather() -> tuple[float, float]:
    """
    Fetch today's forecast high and low temperature (°C) from Open-Meteo.
    Open-Meteo is completely free and requires no API key.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude":  LATITUDE,
        "longitude": LONGITUDE,
        "daily":     "temperature_2m_max,temperature_2m_min",
        "timezone":  TIMEZONE,
        "forecast_days": 1,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            raise requests.HTTPError(
                f"Weather API returned HTTP {resp.status_code}. "
                "Check your LATITUDE/LONGITUDE/TIMEZONE settings."
            )
        data = resp.json()
        high = float(data["daily"]["temperature_2m_max"][0])
        low  = float(data["daily"]["temperature_2m_min"][0])
        return high, low
    except requests.ConnectionError as exc:
        raise requests.ConnectionError("Unable to connect to the weather service.") from exc


def get_nepali_events(bs_year: int, bs_month: int, bs_day: int) -> list[str]:
    """
    Fetch special events / festivals for the given BS date from the
    Nepali Calendar public REST API (nepalicalendar.rat32.com).
    Returns an empty list if the API is unreachable or returns no events.
    """
    url = (
        f"https://nepalicalendar.rat32.com/api/v1/calendar"
        f"/{bs_year}/{bs_month}/{bs_day}/"
    )
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data   = resp.json()
            events = data.get("events", [])
            if isinstance(events, list):
                return [
                    e.get("title", str(e)) if isinstance(e, dict) else str(e)
                    for e in events
                ]
    except Exception as exc:
        print(f"[WARN] Nepali events API error: {exc}")
    return []


def get_nepali_date_info() -> tuple[str, str, list[str]]:
    """
    Convert today's date to Bikram Sambat (BS) using the nepali-datetime
    library, then fetch any special events from the Nepali Patro API.

    Returns:
        bs_date_str  – e.g. "19 Baisakh 2081 BS"
        day_name     – English weekday, e.g. "Tuesday"
        events       – list of event/festival names for today
    """
    try:
        import nepali_datetime  # pip install nepali-datetime
    except ImportError:
        print("[ERROR] nepali-datetime is not installed.  Run:  pip install nepali-datetime")
        return "Nepali date unavailable", "", []

    try:
        today_np   = nepali_datetime.date.today()
        bs_year    = today_np.year
        bs_month   = today_np.month
        bs_day     = today_np.day
        month_name = _NEPALI_MONTHS[bs_month - 1]
        # Use the Gregorian weekday name (same calendar day everywhere)
        day_name   = datetime.date.today().strftime("%A")
        bs_date_str = f"{bs_day} {month_name} {bs_year} BS"
        events      = get_nepali_events(bs_year, bs_month, bs_day)
        return bs_date_str, day_name, events
    except Exception as exc:
        print(f"[WARN] Nepali date conversion error: {exc}")
        return "Nepali date unavailable", "", []


# ── MESSAGE BUILDER ───────────────────────────────────────────────────────────

def build_morning_message() -> str:
    """Assemble the full Alexa announcement from all data sources."""
    now      = datetime.datetime.now()
    # Remove the leading zero from the hour for natural speech (e.g. "7:05 AM")
    time_str = now.strftime("%I:%M %p").lstrip("0")

    parts: list[str] = [
        f"Good morning, {USER_NAME}!",
        f"The current time is {time_str}.",
    ]

    # Weather
    try:
        high, low = get_weather()
        parts.append(
            f"Today's weather forecast for your area: "
            f"a high of {high:.0f} degrees and a low of {low:.0f} degrees Celsius."
        )
    except Exception as exc:
        print(f"[WARN] Weather fetch failed: {exc}")
        parts.append("I was unable to fetch today's weather forecast.")

    # Nepali Patro
    bs_date_str, day_name, events = get_nepali_date_info()
    if bs_date_str != "Nepali date unavailable":
        parts.append(
            f"In Nepal, today is {day_name}, {bs_date_str}."
        )
        if events:
            events_text = ", ".join(events)
            parts.append(f"Special events in Nepal today: {events_text}.")
        else:
            parts.append("There are no special events in Nepal today.")
    else:
        parts.append("I was unable to retrieve today's Nepali calendar information.")

    parts.append("Have a wonderful day!")
    return "  ".join(parts)


# ── NETWORK HELPERS ───────────────────────────────────────────────────────────

def scan_for_phone(subnet: str, phone_mac: str) -> bool:
    """
    ARP-broadcast *subnet* and return True if *phone_mac* responds
    (i.e. the phone is awake and connected to the network).
    """
    phone_mac   = phone_mac.lower()
    arp_request = scapy.ARP(pdst=subnet)
    broadcast   = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
    packet      = broadcast / arp_request

    answered, _ = scapy.srp(packet, timeout=3, verbose=False)
    for _, response in answered:
        if response[scapy.Ether].src.lower() == phone_mac:
            return True
    return False


def in_morning_window() -> bool:
    """Return True if the current local time falls within the morning window."""
    now = datetime.datetime.now().time()
    return MORNING_START <= now <= MORNING_END


# ── ALEXA TTS ─────────────────────────────────────────────────────────────────

async def alexa_say(text: str) -> None:
    """
    Log in to Amazon and send *text* as a TTS announcement to the configured
    Alexa device via the alexapy library.
    """
    try:
        from alexapy import AlexaLogin, AlexaAPI
    except ImportError:
        print("[ERROR] alexapy is not installed.  Run:  pip install alexapy")
        sys.exit(1)

    login = AlexaLogin(
        url="amazon.com",
        email=AMAZON_EMAIL,
        password=AMAZON_PASSWORD,
        outputpath=".",
        debug=False,
    )

    await login.login_with_cookie()

    if not login.status.get("login_successful"):
        print("[ERROR] Amazon login failed. Check AMAZON_EMAIL / AMAZON_PASSWORD.")
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
        print(f"[ERROR] Alexa device '{ALEXA_DEVICE_NAME}' not found.")
        print(
            "Available devices:",
            [d.get("accountName") or d.get("deviceName") for d in devices],
        )
        await login.close()
        return

    api = AlexaAPI(target, login)
    try:
        await api.send_tts(text)
        print(f"[{datetime.datetime.now():%H:%M:%S}] Alexa said: {text!r}")
    finally:
        await login.close()


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

def main() -> None:
    # Guard: make sure credentials are configured
    if not AMAZON_EMAIL or not AMAZON_PASSWORD:
        print(
            "[ERROR] Amazon credentials are not set.\n"
            "        Export them before running:\n"
            "          export AMAZON_EMAIL='your@email.com'\n"
            "          export AMAZON_PASSWORD='your_password'"
        )
        sys.exit(1)

    print("=== Alexa Good Morning ===")
    print(f"  User                   : {USER_NAME}")
    print(f"  Watching for phone MAC : {PHONE_MAC}")
    print(f"  Subnet                 : {SUBNET}")
    print(f"  Morning window         : {MORNING_START.strftime('%H:%M')} – {MORNING_END.strftime('%H:%M')}")
    print(f"  Location (timezone)    : {TIMEZONE}")
    print(f"  Alexa device           : {ALEXA_DEVICE_NAME}")
    print(f"  Poll interval          : {POLL_INTERVAL}s")
    print()

    last_greeted_date: datetime.date | None = None

    while True:
        today           = datetime.date.today()
        already_greeted = (last_greeted_date == today)

        if in_morning_window() and not already_greeted:
            print(f"[{datetime.datetime.now():%H:%M:%S}] Morning window active — scanning for phone …")
            if scan_for_phone(SUBNET, PHONE_MAC):
                print(f"[{datetime.datetime.now():%H:%M:%S}] Phone detected — building message …")
                message = build_morning_message()
                print(f"[{datetime.datetime.now():%H:%M:%S}] Triggering Alexa …")
                asyncio.run(alexa_say(message))
                last_greeted_date = today
            else:
                print(f"[{datetime.datetime.now():%H:%M:%S}] Phone not found on network yet.")
        else:
            reason = "already greeted today" if already_greeted else "outside morning window"
            print(f"[{datetime.datetime.now():%H:%M:%S}] Sleeping ({reason}) …")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
alexa_good_morning.py
---------------------
Monitors your home Wi-Fi network for your phone (by MAC address).
When your phone is detected as active during the morning window
(meaning you have woken up and picked up your phone), the script
tells an Alexa device to say "Good morning!"

Requirements:
    pip install scapy alexapy

How it works:
    1. Every POLL_INTERVAL seconds the script sends an ARP request to
       your local subnet.  If your phone's MAC address replies, it is
       considered "awake / screen-on" on the network.
    2. The check only runs inside the MORNING_START … MORNING_END window.
    3. Once Alexa has spoken, a flag prevents a second greeting until
       midnight the following day.

Usage:
    Run as root / with sufficient network privileges (required by scapy):
        sudo python3 alexa_good_morning.py
"""

import os
import time
import datetime
import asyncio
import sys

import scapy.all as scapy

# ── USER CONFIGURATION ────────────────────────────────────────────────────────

# Your home network subnet in CIDR notation, e.g. "192.168.1.0/24"
SUBNET = "192.168.1.0/24"

# MAC address of your phone (lowercase, colon-separated), e.g. "aa:bb:cc:dd:ee:ff"
PHONE_MAC = "aa:bb:cc:dd:ee:ff"

# Morning window: Alexa will only speak during this time range
MORNING_START = datetime.time(6, 0)   # 06:00 AM
MORNING_END   = datetime.time(10, 0)  # 10:00 AM

# How often (in seconds) to ARP-scan for the phone
POLL_INTERVAL = 30

# The message Alexa will say
GREETING_TEXT = "Good morning! Have a great day!"

# ── ALEXA ACCOUNT CREDENTIALS ─────────────────────────────────────────────────
# Store credentials in environment variables to keep them out of source code:
#
#   export AMAZON_EMAIL="your@email.com"
#   export AMAZON_PASSWORD="your_amazon_password"
#   export ALEXA_DEVICE_NAME="Echo"   # optional, defaults to "Echo"
#
AMAZON_EMAIL      = os.environ.get("AMAZON_EMAIL", "")
AMAZON_PASSWORD   = os.environ.get("AMAZON_PASSWORD", "")
ALEXA_DEVICE_NAME = os.environ.get("ALEXA_DEVICE_NAME", "Echo")

# ─────────────────────────────────────────────────────────────────────────────


def scan_for_phone(subnet: str, phone_mac: str) -> bool:
    """
    Send an ARP broadcast across *subnet* and return True if *phone_mac*
    is among the replies (i.e. the phone is actively connected to the network).
    """
    phone_mac = phone_mac.lower()
    arp_request = scapy.ARP(pdst=subnet)
    broadcast   = scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
    packet      = broadcast / arp_request

    answered, _ = scapy.srp(packet, timeout=3, verbose=False)

    for _, response in answered:
        if response[scapy.Ether].src.lower() == phone_mac:
            return True
    return False


def in_morning_window() -> bool:
    """Return True if the current local time is within the morning window."""
    now = datetime.datetime.now().time()
    return MORNING_START <= now <= MORNING_END


async def alexa_say(text: str) -> None:
    """
    Authenticate with Amazon and send a TTS announcement to the configured
    Alexa device using the alexapy library.
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
        print("[ERROR] Amazon login failed. Check your credentials.")
        return

    devices = await AlexaAPI.get_devices(login)
    target  = next(
        (d for d in devices if d.get("accountName", "").lower() == ALEXA_DEVICE_NAME.lower()),
        None,
    )

    if target is None:
        print(f"[ERROR] Alexa device '{ALEXA_DEVICE_NAME}' not found.")
        print("Available devices:", [d.get("accountName") for d in devices])
        return

    api = AlexaAPI(target, login)
    try:
        await api.send_tts(text)
        print(f"[{datetime.datetime.now():%H:%M:%S}] Alexa said: {text!r}")
    finally:
        await login.close()


def main() -> None:
    print("=== Alexa Good Morning ===")
    print(f"  Watching for phone MAC : {PHONE_MAC}")
    print(f"  Subnet                 : {SUBNET}")
    print(f"  Morning window         : {MORNING_START.strftime('%H:%M')} – {MORNING_END.strftime('%H:%M')}")
    print(f"  Poll interval          : {POLL_INTERVAL}s")
    print()

    last_greeted_date: datetime.date | None = None

    while True:
        today = datetime.date.today()
        already_greeted = (last_greeted_date == today)

        if in_morning_window() and not already_greeted:
            print(f"[{datetime.datetime.now():%H:%M:%S}] Morning window active — scanning for phone …")
            phone_detected = scan_for_phone(SUBNET, PHONE_MAC)

            if phone_detected:
                print(f"[{datetime.datetime.now():%H:%M:%S}] Phone detected — triggering Alexa …")
                asyncio.run(alexa_say(GREETING_TEXT))
                last_greeted_date = today
            else:
                print(f"[{datetime.datetime.now():%H:%M:%S}] Phone not found on network yet.")
        else:
            if already_greeted:
                reason = "already greeted today"
            else:
                reason = "outside morning window"
            print(f"[{datetime.datetime.now():%H:%M:%S}] Sleeping ({reason}) …")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()

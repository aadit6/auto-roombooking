#!/usr/bin/env python
"""Interactive setup: asks the same things the booking portal asks, then writes
config.json and .env so nothing has to be edited by hand.

    python setup_wizard.py
"""
import getpass
import json
import os
import re
import sys
from datetime import datetime

from wrb.live import check, next_year_codes, year_url
from wrb.rules import TERM_DATES, WEEKDAY_NAMES, expand, parse_weekdays, summarise

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
ENVFILE = os.path.join(HERE, ".env")


# --------------------------------------------------------------------- input
def ask(prompt, default=None, secret=False):
    suffix = " [%s]" % default if default not in (None, "") else ""
    while True:
        raw = (getpass.getpass if secret else input)("%s%s: " % (prompt, suffix))
        raw = raw.strip()
        if raw:
            return raw
        if default is not None:
            return default
        print("  (required)")


def ask_yes(prompt, default=True):
    d = "Y/n" if default else "y/N"
    raw = input("%s [%s]: " % (prompt, d)).strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


def ask_list(prompt, default=""):
    raw = ask(prompt, default)
    return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]


def ask_time(prompt, default):
    while True:
        v = ask(prompt, default)
        if re.fullmatch(r"\d{1,2}:\d{2}", v):
            h, m = v.split(":")
            return "%02d:%02d" % (int(h), int(m))
        print("  use HH:MM, e.g. 17:00")


def ask_date(prompt, default):
    while True:
        v = ask(prompt, default)
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            print("  use YYYY-MM-DD")


def rule(banner):
    print("\n" + banner)
    name = ask("  A name for this pattern", "Evening study")
    days = ask_list("  Which days? (Mon,Tue,Wed,Thu,Fri,Sat,Sun)", "Wed,Thu")
    parse_weekdays(days)                       # validate now, not at 3am
    start = ask_time("  Start time", "17:00")
    end = ask_time("  End time", "22:00")
    rooms = ask_list("  Rooms in order of preference", "OC1.06,OC1.09,OC1.04,OC1.01")
    strict = ask_yes("  Book ONLY these rooms (never a different room)?", True)
    size = int(ask("  Group size", "6"))
    reason = ask("  Reason for booking (max 35 chars)", "Group study session")[:35]

    print("\n  When? 1) whole terms   2) specific date range")
    if ask("  Choose", "1") == "1":
        year = ask("  Academic year", "2026/27")
        available = ", ".join(TERM_DATES.get(year, {}))
        terms = ask_list("  Which terms? (%s)" % (available or "autumn,spring,summer"),
                         "autumn,spring")
        when = {"terms": terms}
    else:
        lo = ask_date("  First date", "2026-10-05")
        hi = ask_date("  Last date", "2026-12-12")
        when = {"date_ranges": [[lo, hi]]}

    split = ask("  Split into shorter bookings? hours, or blank for one block", "")
    r = {"name": name, "weekdays": days, "start": start, "end": end,
         "rooms": rooms, "strict_rooms": strict, "size": size, "reason": reason}
    r.update(when)
    if split.strip():
        r["split_hours"] = int(split)
    return r


# ---------------------------------------------------------------------- main
def main():
    print("=" * 68)
    print(" Warwick room booking - setup")
    print("=" * 68)
    print("\nThis asks the same things the booking website asks, then saves")
    print("your answers so the robot can book for you automatically.\n")

    # 1. credentials
    print("--- 1. Your Warwick login ---")
    username = ask("ITS username (e.g. u1234567)")
    password = ask("Password (not shown as you type)", secret=True)

    # 2. notifications
    print("\n--- 2. Where should we email you? ---")
    email = ask("Your email address")
    smtp = {}
    if ask_yes("Send real emails via your own mail account? "
               "(no = notify through GitHub instead)", False):
        smtp["SMTP_HOST"] = ask("  SMTP server", "smtp.gmail.com")
        smtp["SMTP_PORT"] = ask("  Port", "587")
        smtp["SMTP_USER"] = ask("  SMTP username (your email)", email)
        smtp["SMTP_PASSWORD"] = ask("  SMTP app password", secret=True)

    # 3. which system
    print("\n--- 3. Which booking system? ---")
    print("Looking for next year's instance...")
    current = ask("Current academic year code (e.g. 2526)", "2526")
    candidates = [year_url(c) for c in next_year_codes(current, 2)]
    chosen = None
    for url in candidates:
        st = check(url)
        print("   %s" % st)
        if chosen is None and st.state in ("holding", "live"):
            chosen = url
    if chosen is None:
        chosen = candidates[0]
        print("   none published yet; defaulting to %s" % chosen)
    instance = ask("Watch which URL?", chosen)

    # 4. what to book
    print("\n--- 4. What do you want booked? ---")
    rules = [rule("Booking pattern 1")]
    while ask_yes("\nAdd another booking pattern?", False):
        rules.append(rule("Booking pattern %d" % (len(rules) + 1)))

    cfg = {
        "instance": {"url": instance},
        "notify": {"email": email},
        "academic_year": ask("\nAcademic year for term dates", "2026/27"),
        "defaults": {"strict_rooms": True},
        "delay_seconds": 2,
        "rules": rules,
    }

    # 5. preview before writing anything
    try:
        slots = expand(cfg)
    except ValueError as e:
        print("\nThat configuration is not valid: %s" % e)
        return 1

    print("\n" + "=" * 68)
    print("This will book %d slots:" % len(slots))
    print(summarise(slots))
    if slots:
        print("\nFirst few:")
        for s in slots[:5]:
            print("   %s" % s)
    print("=" * 68)
    if not ask_yes("\nSave this?", True):
        print("Nothing written.")
        return 1

    with open(CONFIG, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    lines = ["WRB_USERNAME=%s" % username,
             "WRB_PASSWORD=%s" % password,
             "NOTIFY_EMAIL=%s" % email]
    lines += ["%s=%s" % (k, v) for k, v in smtp.items()]
    with open(ENVFILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print("\nSaved:")
    print("   %s   (what to book - safe to share)" % CONFIG)
    print("   %s          (your password - NEVER share or commit)" % ENVFILE)
    print("\nTry it now:      python run.py --check")
    print("Book for real:   python run.py --confirm")
    print("\nTo run it in the cloud, put these in GitHub -> Settings ->")
    print("Secrets and variables -> Actions:")
    for k in ["WRB_USERNAME", "WRB_PASSWORD", "NOTIFY_EMAIL"] + list(smtp):
        print("   %s" % k)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)

#!/usr/bin/env python
"""Command line front end for the Warwick room booker.

    python book.py --date 2026-09-15 --start 14:00 --end 15:00        # dry run
    python book.py --date 2026-09-15 --start 14:00 --end 15:00 --confirm
    python book.py --list
    python book.py --watch --date 2026-09-15 --start 14:00 --confirm

Nothing is ever booked unless --confirm is passed.
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime

from dotenv import load_dotenv

from wrb.booker import Booker, BookingRequest
from wrb.client import WRBClient, WRBError


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Book a room in Warwick WRB.")
    p.add_argument("--date", help="booking date, YYYY-MM-DD")
    p.add_argument("--start", default="14:00", help="start time HH:MM (default 14:00)")
    p.add_argument("--end", help="end time HH:MM (default: start + 1h)")
    p.add_argument("--size", type=int, default=4, help="group size (default 4)")
    p.add_argument("--reason", default="Group study session",
                   help="reason for booking, max 35 chars")
    p.add_argument("--rooms", default="",
                   help="comma separated room preference, e.g. 'A1.25,MS.03'")
    p.add_argument("--zone", help="zone label, e.g. 'Main Site'")
    p.add_argument("--suitability", action="append", default=[],
                   help="facility label; repeatable")
    p.add_argument("--telephone", default="", help="contact number (optional)")
    p.add_argument("--base", default=None,
                   help="override WRB base URL (e.g. next year's system)")
    p.add_argument("--confirm", action="store_true",
                   help="actually place the booking (default is a dry run)")
    p.add_argument("--list", action="store_true", help="list existing bookings and exit")
    p.add_argument("--watch", action="store_true",
                   help="keep retrying until a room is booked")
    p.add_argument("--interval", type=int, default=60,
                   help="seconds between attempts in --watch mode (default 60)")
    p.add_argument("--max-attempts", type=int, default=0,
                   help="stop after N attempts in --watch mode (0 = forever)")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def plus_one_hour(hhmm):
    t = datetime.strptime(hhmm, "%H:%M")
    return "%02d:%02d" % (t.hour + 1, t.minute)


def build_request(a):
    if not a.date:
        raise SystemExit("--date is required (YYYY-MM-DD)")
    return BookingRequest(
        day=datetime.strptime(a.date, "%Y-%m-%d").date(),
        start=a.start,
        end=a.end or plus_one_hour(a.start),
        size=a.size,
        reason=a.reason,
        zone=a.zone,
        suitabilities=a.suitability,
        rooms=[r.strip() for r in a.rooms.split(",") if r.strip()],
        telephone=a.telephone,
    )


def attempt(a, req):
    """One full login -> search -> select -> confirm cycle."""
    client = WRBClient(base=a.base, verbose=not a.quiet)
    b = Booker(client=client)
    b.c.login()

    options = b.search(req)
    if not options:
        print("[search] no rooms available for %s %s-%s" % (req.day, req.start, req.end))
        return None

    print("[search] %d option(s):" % len(options))
    for o in options:
        print("   ", o)

    choice = b.pick(options, prefer=req.rooms)
    print("[pick]", choice)

    b.select(choice)
    res = b.confirm(req, dry_run=not a.confirm)

    if res is None:                      # dry run
        print("\nDRY RUN - nothing booked. Re-run with --confirm to book.")
        return None

    print("\n[result] ok=%s" % res["ok"])
    if res["errors"]:
        print("[result] errors:", res["errors"])
    print("[result]", res["text"][:600])

    if res["ok"]:
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        os.makedirs("bookings", exist_ok=True)
        path = os.path.join("bookings", "booking_%s.html" % stamp)
        b.c.dump(path)
        record = {"when": stamp, "date": str(req.day), "start": req.start,
                  "end": req.end, "room": choice.room, "reason": req.reason,
                  "proof": path}
        with open("bookings/log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        print("[saved]", path)
        return record
    return None


def main(argv=None):
    load_dotenv()
    a = parse_args(argv)

    if a.list:
        c = WRBClient(base=a.base, verbose=not a.quiet)
        c.login()
        for row in Booker(client=c).my_bookings():
            print("  ", " | ".join(row))
        return 0

    req = build_request(a)
    print("Request: %s %s-%s  size=%s  reason=%r  prefer=%s"
          % (req.day, req.start, req.end, req.size, req.reason, req.rooms or "-"))
    print("Mode:", "CONFIRM (will book)" if a.confirm else "dry run")

    if not a.watch:
        return 0 if attempt(a, req) or not a.confirm else 1

    n = 0
    while True:
        n += 1
        print("\n===== attempt %d @ %s =====" % (n, datetime.now().isoformat(timespec="seconds")))
        try:
            if attempt(a, req):
                print("BOOKED - stopping watch.")
                return 0
        except WRBError as e:
            print("[warn]", e)
        except Exception:
            traceback.print_exc()
        if a.max_attempts and n >= a.max_attempts:
            print("giving up after %d attempts" % n)
            return 1
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())

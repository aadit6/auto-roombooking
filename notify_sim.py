#!/usr/bin/env python
"""Throwaway: send the two go-live notifications with simulated data.

Mirrors exactly what run.py sends when the booking system opens, so the
delivery path (GitHub issue -> email, and SMTP if configured) can be
verified before the real thing happens. Books nothing and touches no
state; deleted along with its branch once the emails have arrived.
"""
import json

from wrb.notify import Notifier, live_message, results_message
from wrb.rules import expand

MARK = ("> **SIMULATED TEST - no rooms were actually booked.**\n"
        "> Sent to verify notification delivery. Safe to close.\n\n")

cfg = json.load(open("config.json", encoding="utf-8"))
inst = cfg["instance"]["url"]
pending = expand(cfg)[:12]
print("config expands to %d slots; simulating with %d" % (len(expand(cfg)), len(pending)))

n = Notifier(cfg)
print("backends active:", [b.__name__ for b in n.backends] or "NONE")

ok1 = n.send("Room booking is OPEN - booking %d slot(s) now" % len(pending),
             MARK + "```\n" + live_message(inst, pending) + "\n```")
print("live notification sent:", ok1)

rooms = ["OC1.06", "OC1.09", "OC1.04", "OC1.01"]
booked = [(s, rooms[i % 4], "BK%06d" % (417200 + i)) for i, s in enumerate(pending[:6])]
failed = [(pending[6], "none of OC1.06/OC1.09/OC1.04/OC1.01 free")]
skipped = [(s, "deferred to next run") for s in pending[7:10]]

ok2 = n.send("Room booking: %d booked, %d failed" % (len(booked), len(failed)),
             MARK + "```\n" + results_message(inst, booked, failed, skipped) + "\n```")
print("results notification sent:", ok2)

raise SystemExit(0 if (ok1 and ok2) else 1)

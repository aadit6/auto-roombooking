#!/usr/bin/env python
"""Watch a WRB instance and book every slot the config asks for.

    python run.py --check            # is it open yet? what would be booked?
    python run.py                    # one pass, dry run (books nothing)
    python run.py --confirm          # one pass, books for real
    python run.py --confirm --loop --interval 30   # sprint: poll hard until done

Safe to run repeatedly: state.json records what is already booked, so a slot is
never booked twice.
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime

from dotenv import load_dotenv

from wrb.booker import Booker
from wrb.client import WRBClient, WRBError
from wrb.live import check
from wrb.notify import Notifier, live_message, results_message
from wrb.rules import Slot, expand, summarise
from wrb.state import State

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "config.json")
DEFAULT_STATE = os.path.join(HERE, "state.json")


def log(msg):
    print("%s  %s" % (datetime.now().isoformat(timespec="seconds"), msg), flush=True)


def load_config(path):
    if not os.path.exists(path):
        raise SystemExit(
            "No config at %s.\nRun:  python setup_wizard.py" % path)
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not cfg.get("rules"):
        raise SystemExit("config has no 'rules'")
    return cfg


def slot_request(slot):
    """Adapt a rules.Slot to the BookingRequest the booker expects."""
    from wrb.booker import BookingRequest
    return BookingRequest(
        day=slot.day, start=slot.start, end=slot.end, size=slot.size,
        reason=slot.reason, zone=slot.zone,
        suitabilities=list(slot.suitabilities), rooms=list(slot.rooms))


def book_slot(b, slot, confirm, state, instance, day_rooms):
    """Attempt one slot. Returns (status, room, reference, detail)."""
    req = slot_request(slot)
    options = b.search(req)
    if not options:
        return "none", None, None, "no rooms offered"

    # Never take a second room for a day we already hold one on.
    already = set(r for r in day_rooms if r)
    usable = [o for o in options if o.room not in already]
    choice = b.pick(usable, prefer=list(slot.rooms), strict=slot.strict_rooms)
    if choice is None:
        return ("blocked", None, None,
                "none of %s free (offered: %s)"
                % ("/".join(slot.rooms), ", ".join(o.room for o in usable[:6]) or "-"))

    b.select(choice)
    res = b.confirm(req, dry_run=not confirm)
    if res is None:
        return "dry", choice.room, None, "dry run"
    if res.get("limit_hit"):
        return "limit", choice.room, None, "booking limit reached"
    if res["ok"]:
        return "booked", choice.room, res.get("reference"), res["text"][:200]
    return "failed", choice.room, None, (res["errors"] or [res["text"][:200]])[0]


def run_once(cfg, args, state, notifier):
    instance = cfg["instance"]["url"]
    status = check(instance)
    log("instance %s" % status)

    slots = expand(cfg, horizon_days=cfg.get("horizon_days", 400))
    pending = [s for s in slots if not state.is_booked(instance, s)]

    if args.check:
        print("\nConfigured slots:\n%s" % summarise(slots))
        print("\n%d total, %d already booked, %d pending"
              % (len(slots), len(slots) - len(pending), len(pending)))
        print("State: %s" % state.summary())
        return "checked"

    if not status.live:
        log("not open yet (%s) - %d slot(s) waiting" % (status.state, len(pending)))
        return "waiting"

    if not pending:
        log("open, and everything is already booked")
        return "done"

    # Announce go-live once, before booking, so the user hears about it even if
    # the booking run then goes wrong.
    if not state.flag("announced:" + instance):
        notifier.send("Room booking is OPEN - booking %d slot(s) now" % len(pending),
                      live_message(instance, pending))
        state.set_flag("announced:" + instance, datetime.now().isoformat(timespec="seconds"))
        state.save()

    client = WRBClient(base=instance, verbose=not args.quiet)
    client.login()
    b = Booker(client=client)

    booked, failed, skipped = [], [], []
    limit_hit = False
    cap = int(cfg.get("max_new_bookings_per_run", 0))

    for slot in pending:
        if state.is_booked(instance, slot):
            continue
        if cap and len(booked) >= cap:
            log("  reached max_new_bookings_per_run=%d; the rest run next time" % cap)
            skipped.extend((s, "deferred to next run") for s in pending
                           if not state.is_booked(instance, s))
            break
        day_rooms = state.booked_rooms_on(instance, slot.day)
        try:
            outcome, room, ref, detail = book_slot(
                b, slot, args.confirm, state, instance, day_rooms)
        except WRBError as e:
            outcome, room, ref, detail = "failed", None, None, str(e)
        except Exception:
            outcome, room, ref, detail = "failed", None, None, traceback.format_exc(limit=3)

        if outcome == "booked":
            log("  BOOKED  %s -> %s (%s)" % (slot, room, ref or "no ref"))
            state.record(instance, slot, room, ref, detail)
            state.save()
            booked.append((slot, room, ref))
        elif outcome == "dry":
            log("  dry-run %s -> would book %s" % (slot, room))
            skipped.append((slot, "dry run"))
        elif outcome == "limit":
            log("  LIMIT   %s - stopping" % slot)
            limit_hit = True
            break
        elif outcome in ("blocked", "none"):
            log("  pending %s - %s" % (slot, detail))
            state.record_failure(instance, slot, detail)
            skipped.append((slot, detail))
        else:
            log("  FAILED  %s - %s" % (slot, detail))
            state.record_failure(instance, slot, detail)
            failed.append((slot, detail))

        # Re-enter the wizard cleanly and stay polite to the server.
        try:
            client._absorb(client.s.get(client.base + "book.aspx"))
        except Exception:
            pass
        time.sleep(cfg.get("delay_seconds", 2))

    state.prune()
    state.save()

    if booked or failed or limit_hit:
        subject = "Room booking: %d booked, %d failed" % (len(booked), len(failed))
        if limit_hit:
            subject += " (hit booking limit)"
        body = results_message(instance, booked, failed, skipped)
        if limit_hit:
            body += ("\n\nThe system refused further bookings - you have reached "
                     "the account limit. Remaining slots were not attempted.")
        notifier.send(subject, body)

    remaining = [s for s in expand(cfg) if not state.is_booked(instance, s)]
    log("pass complete: %d booked, %d failed, %d still pending"
        % (len(booked), len(failed), len(remaining)))
    return "done" if not remaining else "partial"


def main(argv=None):
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--state", default=DEFAULT_STATE)
    p.add_argument("--confirm", action="store_true", help="actually book")
    p.add_argument("--check", action="store_true", help="report status and exit")
    p.add_argument("--loop", action="store_true", help="keep polling until finished")
    p.add_argument("--interval", type=int, default=60, help="seconds between polls")
    p.add_argument("--max-minutes", type=int, default=0, help="stop --loop after N minutes")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    state = State(args.state)
    notifier = Notifier(cfg, verbose=not args.quiet)

    if os.environ.get("WRB_URL"):
        cfg.setdefault("instance", {})["url"] = os.environ["WRB_URL"]

    started = time.time()
    while True:
        try:
            outcome = run_once(cfg, args, state, notifier)
        except SystemExit:
            raise
        except Exception:
            log("run failed:\n%s" % traceback.format_exc())
            outcome = "error"

        if not args.loop or outcome in ("done", "checked"):
            return 0 if outcome in ("done", "checked", "waiting", "partial") else 1
        if args.max_minutes and (time.time() - started) / 60 >= args.max_minutes:
            log("time budget reached, stopping")
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())

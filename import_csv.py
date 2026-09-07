#!/usr/bin/env python
"""Bulk-import one-off bookings from a spreadsheet.

Turns a CSV (one row per event) into config.json's "rules" list. Meant for
someone handing you a spreadsheet of what to book instead of clicking
through the web form or the interactive wizard one event at a time.

    python import_csv.py                  # reads bookings.csv, replaces rules
    python import_csv.py --file mine.csv
    python import_csv.py --append         # add to existing rules instead
    python import_csv.py --default-reason "KCSOC social"   # see below

CSV columns (header row required):

    label, rooms, date, start, end, size, reason, strict

    rooms                          - multiple values, separated by ; or ,
    date                           - YYYY-MM-DD, the single day to book
    label, size, reason, strict    - optional, fall back to config.json's
                                      "defaults" if left blank

A row that leaves "reason" blank falls back to config.json's
defaults.reason. --default-reason sets that fallback (and saves it to
config.json), so it only needs to be given once - every future import
(including a plain drag-and-drop CSV upload, which cannot pass CLI
flags) keeps using it until it is set again.

See bookings.example.csv for filled-in examples.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime

from wrb.rules import WEEKDAY_NAMES, expand, summarise

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")

TRUE_WORDS = {"yes", "y", "true", "1"}
FALSE_WORDS = {"no", "n", "false", "0"}
TIME_RE = re.compile(r"\d{1,2}:\d{2}")


def split_list(v):
    return [x.strip() for x in re.split(r"[;,]", v or "") if x.strip()]


def parse_bool(v, default):
    v = (v or "").strip().lower()
    if not v:
        return default
    if v in TRUE_WORDS:
        return True
    if v in FALSE_WORDS:
        return False
    raise ValueError("expected yes/no, got %r" % v)


def row_to_rule(row, rownum, defaults):
    """Validate one spreadsheet row and turn it into a rule dict.

    Raises ValueError with every problem found in the row (not just the
    first) so a person fixing a spreadsheet does not have to re-run this
    once per typo.
    """
    errors = []

    date_str = (row.get("date") or "").strip()
    day_of = None
    if not date_str:
        errors.append("no date given")
    else:
        try:
            day_of = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            errors.append("date %r is not YYYY-MM-DD" % date_str)

    start = (row.get("start") or "").strip()
    end = (row.get("end") or "").strip()
    for field_name, v in (("start", start), ("end", end)):
        if not TIME_RE.fullmatch(v):
            errors.append("%s %r is not HH:MM" % (field_name, v))

    rooms = split_list(row.get("rooms"))
    if not rooms:
        errors.append("no rooms given")

    size_raw = (row.get("size") or "").strip()
    size = defaults.get("size", 4)
    if size_raw:
        try:
            size = int(size_raw)
        except ValueError:
            errors.append("size %r is not a number" % size_raw)

    reason = (row.get("reason") or "").strip() or defaults.get("reason", "Group study session")
    reason = reason[:35]

    try:
        strict = parse_bool(row.get("strict"), defaults.get("strict_rooms", True))
    except ValueError as e:
        errors.append("strict: %s" % e)
        strict = True

    if errors:
        raise ValueError("row %d: %s" % (rownum, "; ".join(errors)))

    label = (row.get("label") or "").strip() or "%s %s" % ("/".join(rooms[:2]), date_str)

    return {"name": label, "weekdays": [WEEKDAY_NAMES[day_of.weekday()]],
            "date_ranges": [[date_str, date_str]], "start": start, "end": end,
            "rooms": rooms, "strict_rooms": strict, "size": size, "reason": reason}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=os.path.join(HERE, "bookings.csv"),
                     help="CSV to import (default: bookings.csv)")
    ap.add_argument("--append", action="store_true",
                     help="add to existing rules instead of replacing them")
    ap.add_argument("--default-reason", default=os.environ.get("DEFAULT_REASON", ""),
                     help="fallback reason for rows that leave 'reason' blank; "
                          "saved to config.json's defaults so it also applies "
                          "next time, without needing to be given again")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print("No such file: %s" % args.file)
        print("Export your spreadsheet as CSV and save it there, "
              "or pass --file to point at it.")
        return 1

    if not os.path.exists(CONFIG):
        print("config.json does not exist yet. Run setup_wizard.py first so "
              "your login, instance URL and notify email are set up - this "
              "script only fills in *which rooms and times* to book.")
        return 1

    with open(CONFIG, encoding="utf-8") as fh:
        cfg = json.load(fh)

    if args.default_reason.strip():
        cfg.setdefault("defaults", {})["reason"] = args.default_reason.strip()[:35]
    defaults = cfg.get("defaults", {})

    with open(args.file, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"rooms", "date", "start", "end"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            print("CSV is missing required column(s): %s" % ", ".join(sorted(missing)))
            print("Columns: label,rooms,date,start,end,size,reason,strict")
            return 1
        rows = [(i, row) for i, row in enumerate(reader, start=2) if any(row.values())]

    if not rows:
        print("No data rows found in %s - nothing to do." % args.file)
        return 1

    new_rules, errors = [], []
    for rownum, row in rows:
        try:
            new_rules.append(row_to_rule(row, rownum, defaults))
        except ValueError as e:
            errors.append(str(e))

    if errors:
        print("Found %d problem(s) in %s - nothing was changed:\n"
              % (len(errors), args.file))
        for e in errors:
            print("  ::error::%s" % e)
        return 1

    cfg["rules"] = (cfg.get("rules", []) + new_rules) if args.append else new_rules

    try:
        slots = expand(cfg)
    except ValueError as e:
        print("::error::Config is not valid after import: %s" % e)
        return 1

    print("Imported %d event(s) from %s%s:\n"
          % (len(new_rules), args.file, " (added to existing)" if args.append else ""))
    for r in new_rules:
        print("  - %s" % r["name"])
    print("\nThis produces %d booking slot(s):" % len(slots))
    print(summarise(slots))
    if slots:
        print("\nFirst few:")
        for s in slots[:5]:
            print("   %s" % s)

    with open(CONFIG, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    print("\nSaved to %s" % CONFIG)
    return 0


if __name__ == "__main__":
    sys.exit(main())

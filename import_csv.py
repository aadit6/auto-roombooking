#!/usr/bin/env python
"""Bulk-import booking patterns from a spreadsheet.

Turns a CSV (one row per room/day/time pattern) into config.json's "rules"
list. Meant for someone handing you a spreadsheet of what to book instead of
clicking through the web form or the interactive wizard one pattern at a
time.

    python import_csv.py                  # reads bookings.csv, replaces rules
    python import_csv.py --file mine.csv
    python import_csv.py --append         # add to existing rules instead

CSV columns (header row required):

    label, rooms, days, start, end, terms, date_from, date_to, size, reason, strict

    rooms / days / terms  - multiple values, separated by ; or ,
    terms  OR  date_from + date_to  - give one, not both
    label, size, reason, strict  - optional, fall back to config.json's
                                    "defaults" if left blank

See bookings.example.csv for a filled-in example.
"""
import argparse
import csv
import json
import os
import re
import sys

from wrb.rules import TERM_DATES, expand, parse_weekdays, summarise

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


def row_to_rule(row, rownum, defaults, year):
    """Validate one spreadsheet row and turn it into a rule dict.

    Raises ValueError with every problem found in the row (not just the
    first) so a person fixing a spreadsheet does not have to re-run this
    once per typo.
    """
    errors = []

    days = split_list(row.get("days"))
    if days:
        try:
            parse_weekdays(days)
        except ValueError as e:
            errors.append(str(e))
    else:
        errors.append("no days given")

    start = (row.get("start") or "").strip()
    end = (row.get("end") or "").strip()
    for field_name, v in (("start", start), ("end", end)):
        if not TIME_RE.fullmatch(v):
            errors.append("%s %r is not HH:MM" % (field_name, v))

    rooms = split_list(row.get("rooms"))
    if not rooms:
        errors.append("no rooms given")

    terms = split_list(row.get("terms"))
    date_from = (row.get("date_from") or "").strip()
    date_to = (row.get("date_to") or "").strip()
    when = {}
    if terms and (date_from or date_to):
        errors.append("give terms OR date_from/date_to, not both")
    elif terms:
        table = TERM_DATES.get(year, {})
        for t in terms:
            if t.lower() not in table:
                errors.append("unknown term %r for academic_year %s" % (t, year))
        when = {"terms": terms}
    elif date_from and date_to:
        when = {"date_ranges": [[date_from, date_to]]}
    else:
        errors.append("need terms, or date_from + date_to")

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

    label = (row.get("label") or "").strip()
    if not label:
        label = "%s %s" % ("/".join(rooms[:2]), "+".join(days))

    r = {"name": label, "weekdays": days, "start": start, "end": end,
         "rooms": rooms, "strict_rooms": strict, "size": size, "reason": reason}
    r.update(when)
    return r


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=os.path.join(HERE, "bookings.csv"),
                     help="CSV to import (default: bookings.csv)")
    ap.add_argument("--append", action="store_true",
                     help="add to existing rules instead of replacing them")
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
    defaults = cfg.get("defaults", {})
    year = cfg.get("academic_year", "2026/27")

    with open(args.file, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"rooms", "days", "start", "end"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            print("CSV is missing required column(s): %s" % ", ".join(sorted(missing)))
            print("Columns: label,rooms,days,start,end,terms,date_from,"
                  "date_to,size,reason,strict")
            return 1
        rows = [(i, row) for i, row in enumerate(reader, start=2) if any(row.values())]

    if not rows:
        print("No data rows found in %s - nothing to do." % args.file)
        return 1

    new_rules, errors = [], []
    for rownum, row in rows:
        try:
            new_rules.append(row_to_rule(row, rownum, defaults, year))
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

    print("Imported %d pattern(s) from %s%s:\n"
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

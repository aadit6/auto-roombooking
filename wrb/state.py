"""Durable record of what has already been booked.

This is the guard against double-booking.  A slot that appears here as booked
is never attempted again, no matter how many times the watcher runs.  In CI the
file is committed back to the repository after each run so it survives the
ephemeral runner.
"""
import json
import os
from datetime import date, datetime


class State:
    def __init__(self, path):
        self.path = path
        self.data = {"booked": {}, "failures": {}, "flags": {}}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except (ValueError, OSError):
                pass                       # corrupt state must not block booking
        for k in ("booked", "failures", "flags"):
            self.data.setdefault(k, {})

    # ------------------------------------------------------------------ io
    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    # -------------------------------------------------------------- lookup
    @staticmethod
    def key(instance, slot):
        return "%s|%s" % (instance.rstrip("/").rsplit("/", 1)[-1], slot.key)

    def is_booked(self, instance, slot):
        return self.key(instance, slot) in self.data["booked"]

    def booked_rooms_on(self, instance, day):
        """Rooms already held on a given date - used to avoid stacking rooms."""
        pre = "%s|%s|" % (instance.rstrip("/").rsplit("/", 1)[-1], day.isoformat())
        return [v.get("room") for k, v in self.data["booked"].items()
                if k.startswith(pre)]

    def record(self, instance, slot, room, reference, text=""):
        self.data["booked"][self.key(instance, slot)] = {
            "room": room,
            "reference": reference,
            "date": slot.day.isoformat(),
            "start": slot.start,
            "end": slot.end,
            "rule": slot.rule,
            "at": datetime.now().isoformat(timespec="seconds"),
            "detail": text[:300],
        }
        self.data["failures"].pop(self.key(instance, slot), None)

    def record_failure(self, instance, slot, why):
        k = self.key(instance, slot)
        entry = self.data["failures"].get(k, {"count": 0})
        entry["count"] += 1
        entry["last"] = why[:300]
        entry["at"] = datetime.now().isoformat(timespec="seconds")
        self.data["failures"][k] = entry

    def failure_count(self, instance, slot):
        return self.data["failures"].get(self.key(instance, slot), {}).get("count", 0)

    # --------------------------------------------------------------- flags
    def flag(self, name):
        return self.data["flags"].get(name)

    def set_flag(self, name, value=True):
        self.data["flags"][name] = value

    # -------------------------------------------------------------- pruning
    def prune(self, before=None):
        """Drop records for dates that have passed; keeps the file small."""
        before = before or date.today()
        for bucket in ("booked", "failures"):
            for k in list(self.data[bucket]):
                parts = k.split("|")
                if len(parts) < 2:
                    continue
                try:
                    d = datetime.strptime(parts[1], "%Y-%m-%d").date()
                except ValueError:
                    continue
                if d < before:
                    del self.data[bucket][k]

    # ------------------------------------------------------------- summary
    def summary(self):
        booked = self.data["booked"]
        return "%d booked, %d slots with failures" % (
            len(booked), len(self.data["failures"]))

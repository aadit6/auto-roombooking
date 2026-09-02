"""Turning recurring booking rules into concrete slots.

A rule says something like "17:00-22:00 every Wednesday and Thursday of the
autumn and spring terms, in one of these four rooms".  expand() flattens that
into individual dated slots that the booker can attempt one at a time.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Convenience presets so a new user does not have to look term dates up.
TERM_DATES = {
    "2026/27": {
        "autumn": ("2026-10-05", "2026-12-12"),
        "spring": ("2027-01-11", "2027-03-20"),
        "summer": ("2027-04-26", "2027-07-03"),
    },
}


@dataclass(frozen=True)
class Slot:
    """One concrete booking attempt."""
    day: date
    start: str
    end: str
    size: int
    reason: str
    rooms: tuple = ()
    strict_rooms: bool = True
    zone: str = None
    suitabilities: tuple = ()
    rule: str = ""

    @property
    def key(self):
        return "%s|%s|%s" % (self.day.isoformat(), self.start, self.end)

    def __str__(self):
        return "%s %s %s-%s (%s)" % (
            WEEKDAY_NAMES[self.day.weekday()], self.day, self.start, self.end,
            "/".join(self.rooms) if self.rooms else "any")


def parse_weekdays(values):
    out = []
    for v in values:
        k = str(v).strip().lower()[:3]
        if k not in WEEKDAYS:
            raise ValueError("unknown weekday %r" % v)
        out.append(WEEKDAYS[k])
    return sorted(set(out))


def _as_date(v):
    if isinstance(v, date):
        return v
    return datetime.strptime(str(v), "%Y-%m-%d").date()


def date_ranges_for(rule, year="2026/27"):
    """Explicit ranges if given, else the named terms, else nothing."""
    if rule.get("date_ranges"):
        return [(_as_date(a), _as_date(b)) for a, b in rule["date_ranges"]]
    terms = rule.get("terms")
    if terms:
        table = TERM_DATES.get(year, {})
        out = []
        for t in terms:
            if t.lower() not in table:
                raise ValueError("no dates known for term %r in %s" % (t, year))
            a, b = table[t.lower()]
            out.append((_as_date(a), _as_date(b)))
        return out
    raise ValueError("rule %r has neither date_ranges nor terms" % rule.get("name"))


def split_slots(start, end, chunk_hours):
    """Break 17:00-22:00 into consecutive chunks, if the rule asks for it."""
    if not chunk_hours:
        return [(start, end)]
    fmt = "%H:%M"
    s = datetime.strptime(start, fmt)
    e = datetime.strptime(end, fmt)
    out = []
    while s < e:
        nxt = min(s + timedelta(hours=chunk_hours), e)
        out.append((s.strftime(fmt), nxt.strftime(fmt)))
        s = nxt
    return out


def expand(config, today=None, horizon_days=400):
    """Expand every rule in a config into dated slots, soonest first."""
    today = today or date.today()
    defaults = config.get("defaults", {})
    year = config.get("academic_year", "2026/27")
    slots = []

    for rule in config.get("rules", []):
        weekdays = parse_weekdays(rule.get("weekdays", []))
        if not weekdays:
            raise ValueError("rule %r lists no weekdays" % rule.get("name"))

        rooms = tuple(rule.get("rooms", defaults.get("rooms", [])))
        strict = rule.get("strict_rooms", defaults.get("strict_rooms", True))
        size = int(rule.get("size", defaults.get("size", 4)))
        reason = rule.get("reason", defaults.get("reason", "Group study session"))
        zone = rule.get("zone", defaults.get("zone"))
        suits = tuple(rule.get("suitabilities", defaults.get("suitabilities", [])))
        chunk = rule.get("split_hours", defaults.get("split_hours"))

        for lo, hi in date_ranges_for(rule, year):
            d = lo
            while d <= hi:
                if d.weekday() in weekdays and d >= today and \
                        (d - today).days <= horizon_days:
                    for s, e in split_slots(rule["start"], rule["end"], chunk):
                        slots.append(Slot(
                            day=d, start=s, end=e, size=size, reason=reason,
                            rooms=rooms, strict_rooms=strict, zone=zone,
                            suitabilities=suits, rule=rule.get("name", "")))
                d += timedelta(days=1)

    slots.sort(key=lambda s: (s.day, s.start))
    return slots


def summarise(slots):
    if not slots:
        return "no slots"
    by_rule = {}
    for s in slots:
        by_rule.setdefault(s.rule or "(unnamed)", []).append(s)
    lines = []
    for name, group in by_rule.items():
        lines.append("  %-18s %3d slots  %s .. %s"
                     % (name, len(group), group[0].day, group[-1].day))
    return "\n".join(lines)

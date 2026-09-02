"""Detecting whether a WRB instance is open for business.

Each academic year gets its own instance, e.g. .../WRB2526/ then .../WRB2627/.
The next year's instance is published long before it opens, and the two states
are cleanly distinguishable without logging in:

    not yet open : HTTP 200 + "Application Unavailable" holding page
    open         : HTTP 302 -> PortalLogin.aspx
    not deployed : HTTP 404
"""
import re
from dataclasses import dataclass

import requests

from .client import UA

UNAVAILABLE = re.compile(r"application unavailable|currently unavailable", re.I)


@dataclass
class Liveness:
    url: str
    state: str            # "live" | "holding" | "missing" | "error"
    status: int = 0
    detail: str = ""

    @property
    def live(self):
        return self.state == "live"

    def __str__(self):
        return "%-45s %-8s (HTTP %s) %s" % (self.url, self.state, self.status, self.detail)


def check(url, timeout=20):
    """Classify a WRB instance URL without authenticating."""
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=False,
                         headers={"User-Agent": UA})
    except requests.RequestException as e:
        return Liveness(url, "error", 0, str(e)[:120])

    if r.status_code == 404:
        return Liveness(url, "missing", 404, "not deployed yet")

    if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
        target = r.headers.get("Location", "")
        if "login" in target.lower() or "portal" in target.lower():
            return Liveness(url, "live", r.status_code, "redirects to %s" % target[:70])
        return Liveness(url, "live", r.status_code, "redirects to %s" % target[:70])

    if r.status_code == 200:
        if UNAVAILABLE.search(r.text):
            return Liveness(url, "holding", 200, "Application Unavailable page")
        # A 200 that is not the holding page means the app rendered something
        # real, which for the root URL means it is serving.
        return Liveness(url, "live", 200, "serving content")

    return Liveness(url, "error", r.status_code, r.reason)


def year_url(year_code, host="https://abs.warwick.ac.uk"):
    return "%s/WRB%s/" % (host.rstrip("/"), year_code)


def next_year_codes(start, count=3):
    """'2526' -> ['2627', '2728', '2829']"""
    a = int(start[:2])
    out = []
    for i in range(1, count + 1):
        out.append("%02d%02d" % ((a + i) % 100, (a + i + 1) % 100))
    return out

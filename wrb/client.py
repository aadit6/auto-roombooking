"""Client for the Scientia Enterprise Web Room Booking system (University of Warwick).

The whole booking wizard is a single ASP.NET WebForms page that posts back to
itself.  Driving it is therefore a matter of round-tripping __VIEWSTATE and
friends while flipping one control at a time, exactly as the browser does.
"""
import os
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# ASP.NET Calendar encodes each day cell as days elapsed since this epoch.
CAL_EPOCH = date(2000, 1, 1)

HIDDEN = ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION",
          "__LASTFOCUS", "__SCROLLPOSITIONX", "__SCROLLPOSITIONY")


class WRBError(RuntimeError):
    pass


def cal_arg(d):
    """Event argument the calendar expects for a given date."""
    return str((d - CAL_EPOCH).days)


class WRBClient:
    def __init__(self, base=None, username=None, password=None, verbose=True):
        self.base = (base or os.environ.get(
            "WRB_BASE", "https://abs.warwick.ac.uk/WRB2526/")).rstrip("/") + "/"
        self.username = username or os.environ["WRB_USERNAME"]
        self.password = password or os.environ["WRB_PASSWORD"]
        self.verbose = verbose
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        self.page = None       # BeautifulSoup of the current page
        self.url = None        # URL the current page came from

    # ---------------------------------------------------------------- utils
    def log(self, *a):
        if self.verbose:
            print(*a, flush=True)

    def _absorb(self, resp):
        self.page = BeautifulSoup(resp.text, "lxml")
        self.url = resp.url
        return resp

    def _form(self):
        f = self.page.find("form")
        if f is None:
            raise WRBError("no form on page %s" % self.url)
        return f

    def state(self):
        """Current values of every submittable control on the page."""
        f = self._form()
        data = {}
        for i in f.find_all("input"):
            n, t = i.get("name"), (i.get("type") or "text").lower()
            if not n:
                continue
            if t in ("checkbox", "radio"):
                if i.has_attr("checked"):
                    data[n] = i.get("value", "on")
            elif t in ("submit", "button", "image", "reset", "file"):
                continue        # only the button actually clicked is submitted
            else:
                data[n] = i.get("value", "")
        for sel in f.find_all("select"):
            n = sel.get("name")
            if not n:
                continue
            chosen = [o.get("value", o.get_text(strip=True))
                      for o in sel.find_all("option") if o.has_attr("selected")]
            if not chosen:
                opts = sel.find_all("option")
                chosen = [opts[0].get("value", "")] if opts else [""]
            data[n] = chosen if sel.has_attr("multiple") else chosen[0]
        for ta in f.find_all("textarea"):
            if ta.get("name"):
                data[ta["name"]] = ta.get_text()
        return data

    def _post(self, data, action=None):
        action = urljoin(self.url, action or self._form().get("action") or "")
        r = self.s.post(action, data=data, headers={"Referer": self.url})
        r.raise_for_status()
        return self._absorb(r)

    def postback(self, target, argument="", extra=None):
        """Emulate javascript:__doPostBack(target, argument)."""
        data = self.state()
        data["__EVENTTARGET"] = target
        data["__EVENTARGUMENT"] = argument
        if extra:
            data.update(extra)
        return self._post(data)

    def click(self, submit_name, extra=None):
        """Submit the form as if `submit_name` (a submit button) was clicked."""
        data = self.state()
        data["__EVENTTARGET"] = ""
        data["__EVENTARGUMENT"] = ""
        btn = self._form().find("input", attrs={"name": submit_name})
        data[submit_name] = btn.get("value", "") if btn else ""
        if extra:
            data.update(extra)
        return self._post(data)

    # ---------------------------------------------------------------- login
    def login(self):
        r = self._absorb(self.s.get(self.base))
        if "Login.aspx" not in r.url:
            self.log("[login] already authenticated ->", r.url)
            return r
        user_ctl = self.control("$user")
        pass_ctl = self.control("$password")
        logon_ctl = None
        for i in self._form().find_all("input", attrs={"type": "submit"}):
            if (i.get("name") or "").endswith("$logon"):
                logon_ctl = i.get("name")
        if not (user_ctl and pass_ctl and logon_ctl):
            raise WRBError("unexpected login form layout")
        r = self.click(logon_ctl, extra={user_ctl: self.username,
                                         pass_ctl: self.password})
        if "Login.aspx" in r.url:
            raise WRBError("login rejected (bad credentials or locked account)")
        self.log("[login] ok ->", r.url)
        return r

    # ------------------------------------------------------------ inspect
    def text(self):
        return self.page.get_text(" ", strip=True)

    def options(self, name_suffix):
        """(value, label) pairs for the select whose name ends with suffix."""
        for sel in self.page.find_all("select"):
            if (sel.get("name") or "").endswith(name_suffix):
                return [(o.get("value", ""), o.get_text(strip=True))
                        for o in sel.find_all("option")]
        return []

    def control(self, suffix):
        """Full control name ending with the given suffix, or None."""
        for tag in self.page.find_all(["input", "select", "textarea"]):
            n = tag.get("name") or ""
            if n.endswith(suffix):
                return n
        return None

    def postback_target(self, suffix):
        """Find a __doPostBack target (link, image button, etc.) by name suffix.

        Not every postback source is an <input>; the calendar, for instance, is
        a <table> driven by javascript hrefs, so control() cannot see it.
        """
        for tag in self.page.find_all(True):
            blob = (tag.get("href") or "") + (tag.get("onclick") or "")
            for m in re.finditer(r"__doPostBack\('([^']+)','([^']*)'\)", blob):
                if m.group(1).endswith(suffix):
                    return m.group(1)
        return None

    def select_date(self, d):
        """Click a day cell in the ASP.NET calendar."""
        target = self.postback_target("CollegeCalendar1$theCalendar")
        if not target:
            raise WRBError("calendar control not found on %s" % self.url)
        self.postback(target, cal_arg(d))
        box = self.control("calendarDateTextBox")
        got = self.page.find("input", attrs={"name": box}).get("value") if box else None
        if not got or not got.startswith(d.strftime("%d/%m/%Y")):
            raise WRBError("date %s did not take (textbox=%r)" % (d, got))
        self.log("[date] selected", got)
        return got

    def errors(self):
        out = []
        for tag in self.page.find_all(attrs={"class": re.compile(
                r"error|warning|validation", re.I)}):
            t = tag.get_text(" ", strip=True)
            if t:
                out.append(t)
        return out

    def dump(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(self.page))
        return path

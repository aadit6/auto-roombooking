"""Telling the user what happened.

Two backends, both optional and independently useful:

  smtp          a real email, needs SMTP_* settings (Gmail app password works)
  github_issue  opens an issue on the repo; GitHub then emails the owner, which
                needs no configuration at all inside GitHub Actions

Notification failures are never allowed to abort a booking run - getting the
room matters more than the announcement.
"""
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage


def _env(*names, default=None):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


class Notifier:
    def __init__(self, config=None, verbose=True):
        cfg = (config or {}).get("notify", {}) if config else {}
        self.to = _env("NOTIFY_EMAIL", default=cfg.get("email"))
        self.verbose = verbose
        self.backends = []

        if _env("SMTP_HOST") and _env("SMTP_USER") and _env("SMTP_PASSWORD") and self.to:
            self.backends.append(self._send_smtp)
        if _env("GITHUB_TOKEN") and _env("GITHUB_REPOSITORY"):
            self.backends.append(self._send_issue)

    def log(self, *a):
        if self.verbose:
            print(*a, flush=True)

    # ---------------------------------------------------------------- public
    def send(self, subject, body):
        if not self.backends:
            self.log("[notify] no backend configured; would have sent: %s" % subject)
            return False
        ok = False
        for backend in self.backends:
            try:
                backend(subject, body)
                ok = True
            except Exception as e:                    # never block the booking
                self.log("[notify] %s failed: %s" % (backend.__name__, e))
        return ok

    # -------------------------------------------------------------- backends
    def _send_smtp(self, subject, body):
        host = _env("SMTP_HOST")
        port = int(_env("SMTP_PORT", default="587"))
        user = _env("SMTP_USER")
        password = _env("SMTP_PASSWORD")
        sender = _env("SMTP_FROM", default=user)

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = self.to
        msg.set_content(body)

        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(),
                                  timeout=30) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, password)
                s.send_message(msg)
        self.log("[notify] emailed %s" % self.to)

    def _send_issue(self, subject, body):
        repo = _env("GITHUB_REPOSITORY")
        token = _env("GITHUB_TOKEN")
        payload = json.dumps({"title": subject, "body": body}).encode()
        req = urllib.request.Request(
            "https://api.github.com/repos/%s/issues" % repo,
            data=payload, method="POST",
            headers={"Authorization": "Bearer %s" % token,
                     "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json",
                     "User-Agent": "auto-roombooking"})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        self.log("[notify] opened GitHub issue on %s" % repo)


def live_message(instance, slots):
    body = [
        "The room booking system has just opened:",
        "",
        "    %s" % instance,
        "",
        "Booking %d slot(s) now. You will get a second message with the results."
        % len(slots),
        "",
    ]
    for s in slots[:40]:
        body.append("  %s" % s)
    if len(slots) > 40:
        body.append("  ... and %d more" % (len(slots) - 40))
    return "\n".join(body)


def results_message(instance, booked, failed, skipped):
    lines = ["Booking run finished on %s" % instance, ""]
    lines.append("Booked : %d" % len(booked))
    lines.append("Failed : %d" % len(failed))
    lines.append("Pending: %d (will retry on the next run)" % len(skipped))
    if booked:
        lines += ["", "BOOKED"]
        for slot, room, ref in booked:
            lines.append("  %s  %-10s ref %s" % (slot, room, ref or "-"))
    if failed:
        lines += ["", "FAILED"]
        for slot, why in failed[:30]:
            lines.append("  %s  %s" % (slot, why))
    return "\n".join(lines)

# Setting this up

Roughly 15 minutes. You need a GitHub account and your Warwick login. You do
**not** need to install anything, understand code, or leave a computer switched
on — it runs on GitHub's servers.

---

## Step 1 — Get your own copy

If someone sent you a link to their repository, click **Use this template →
Create a new repository** (or **Fork**). Otherwise, from the project folder:

```bash
git init
git add .
git commit -m "Room booking robot"
gh repo create auto-roombooking --private --source=. --push
```

> **Make it private.** It will hold your booking schedule, and private repos
> keep your Actions minutes on the free allowance.

---

## Step 2 — Tell it your login

In your repository: **Settings → Secrets and variables → Actions → New
repository secret**. Add these three, one at a time:

| Name | Value |
|---|---|
| `WRB_USERNAME` | your ITS username, e.g. `u1234567` |
| `WRB_PASSWORD` | your ITS password |
| `NOTIFY_EMAIL` | where you want to be emailed |

Secrets are encrypted. They are not visible in logs, and nobody who reads the
repository can see them.

### Optional: real emails instead of GitHub notifications

By default you get notified through a GitHub issue, and GitHub emails that to
you — zero setup. If you would rather have a plain email, add four more
secrets. For Gmail you must generate an **app password** first
(Google Account → Security → 2-Step Verification → App passwords):

| Name | Value |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASSWORD` | the 16-character app password (**not** your Gmail password) |

---

## Step 3 — Check it works

Go to the **Actions** tab. If you see a banner offering to enable workflows,
click it. Then pick **“1. Test my setup”** on the left and press
**Run workflow**.

It takes about a minute and proves three things: GitHub can reach the Warwick
site, your login works, and your notifications arrive. A green tick means you
are set. If it fails, see Troubleshooting below.

---

## Step 4 — Say what you want booked

Two ways, both fine.

**In the browser:** Actions → **“2. Change what gets booked”** → Run workflow.
Fill the form in and it saves for you:

| Field | Example |
|---|---|
| Days | `Wed,Thu` |
| Start / End | `17:00` / `22:00` |
| Rooms | `OC1.06,OC1.09,OC1.04,OC1.01` (best first) |
| Book ONLY these rooms | ticked |
| Terms | `autumn,spring,summer` |
| Group size | `6` |
| Reason | `Group study session` |
| Booking system URL | `https://abs.warwick.ac.uk/WRB2627/` |

**Or on your own computer**, which asks the same questions in a friendlier way:

```bash
python setup_wizard.py
python run.py --check      # shows exactly which dates it will book
```

> **“Book ONLY these rooms”** is the important one. Ticked, it will *never*
> book a room you did not ask for — if all four Oculus rooms are taken it books
> nothing and tries again on the next run. Unticked, it falls back to the
> smallest room that fits.

**Got a whole spreadsheet of individual bookings instead of just one
pattern?** Skip the form above — this is the smoothest option if you're
setting this up for someone else who doesn't want to touch code at all:

1. In your spreadsheet app, add columns `label, rooms, date, start, end,
   size, reason, strict` — one row per event (see
   [`bookings.example.csv`](bookings.example.csv) for filled-in examples —
   `label`, `size`, `reason`, `strict` are optional). `date` is the single
   day to book (`YYYY-MM-DD`); the weekday is worked out automatically.
2. **File → Download / Save As → CSV.**
3. On the repo's GitHub page: **Add file → Upload files**, drag the CSV in,
   rename it to `bookings.csv` if it isn't already, then **Commit changes**.
4. That's it — the upload itself triggers **“3. Import from spreadsheet”**,
   which turns every row into a booking and saves it. Check the
   **Actions** tab; a red ✗ means a row had a problem (it'll say exactly
   which row and why — nothing is saved until every row is valid).

---

## Step 5 — Turn the watcher on

Nothing more to do: **“Watch and book”** runs automatically every 10 minutes
from the moment the code is in your repository. While the system is closed each
run takes a few seconds and does nothing.

When it opens you get an email saying so, then a second email listing every
room it booked.

To watch it work: Actions → **Watch and book** → most recent run.

---

## Step 6 — On opening day, sprint

Rooms are first come, first served, so even a 10-minute gap can lose you OC1.06. If
you know the system opens today:

Actions → **Sprint (fast polling)** → Run workflow → leave the defaults.

That polls every 30 seconds for 5 hours and books the instant it opens. Start
it in the morning and forget about it.

---

## Troubleshooting

**“1. Test my setup” fails at the login step**
Your username or password secret is wrong. Re-enter them — a trailing space is
the usual culprit. Note it can only test the login while *some* instance is
open; if all are closed it says so and that is not a failure.

**It cannot reach the Warwick site from GitHub**
Unlikely but possible if Warwick blocks cloud IP ranges. Fall back to running
it on your own machine (see below).

**It booked nothing and said “none of OC1.06/... free”**
Working as intended — someone else had those rooms. It retries every 10
minutes; leave it running.

**Scheduled runs stopped after a couple of months**
GitHub disables schedules on repositories with no activity for 60 days. The
watcher writes a heartbeat on every run to prevent this, but if it does happen
GitHub emails you a link to re-enable it.

**“hit booking limit”**
Warwick refused further bookings on your account. Nothing to fix in the tool —
you are at your allowance. Reduce how many weeks you ask for.

---

## Running it on your own computer instead

Only needed if you would rather not use GitHub, or GitHub cannot reach Warwick.
The machine must be switched on for it to work.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
python setup_wizard.py

python run.py --check      # what would happen
python run.py --confirm    # do it once
```

To have Windows run it automatically every 15 minutes:

```powershell
.\schedule.ps1 -Register -Confirm
.\schedule.ps1 -Status
.\schedule.ps1 -Unregister
```

---

## Things worth knowing

- Every booking is **provisional** (`P`). Central Timetabling can cancel it.
- The tool **never books the same slot twice** — `state.json` records what it
  has done, and that file is saved back to your repository after every run.
- It books **one room per slot**, never several.
- Bookings do not carry over to the next academic year; they are deleted at the
  rollover, which is why a new instance appears each year.
- Asking for a whole year of 5-hour slots is ~300 room-hours. That is a lot,
  and Central Timetabling may cancel bookings they consider excessive. The
  config books at most 20 new slots per run to spread the load; consider doing
  one term at a time.
- Automating a university system is a grey area in the IT regulations. Keep
  the poll interval gentle — do not lower it much below 10 minutes.

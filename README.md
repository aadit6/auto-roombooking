# auto-roombooking

Automates the University of Warwick **Web Room Booking** system
(`https://abs.warwick.ac.uk/WRB2526/`) — searching, selecting and confirming a
room without a browser, plus a watcher that fires as soon as next year's
instance opens. Every booking it makes is submitted **as a society/club
booking** — see [Things worth knowing](#things-worth-knowing).

---

## Setup

Roughly 15 minutes. You need a GitHub account and the Warwick login of the
account that should do the booking. You do **not** need to install anything,
understand code, or leave a computer switched on — it runs on GitHub's
servers, following instructions alone.

This guide assumes the common case: you already have **a spreadsheet of what
to book** — a list of rooms, dates and times, e.g. exported from wherever
your society already tracks its bookings. If you only ever want one
recurring weekly pattern instead of a list of one-off events, see
[Alternative: one recurring pattern](#alternative-one-recurring-pattern-instead-of-a-spreadsheet)
further down.

### Step 1 — Get your own copy

If someone sent you a link to their repository, click **Use this template →
Create a new repository** (or **Fork**). Otherwise, from the project folder:

```bash
git init
git add .
git commit -m "Room booking robot"
gh repo create auto-roombooking --private --source=. --push
```

> **Private vs public.** Private keeps your Actions minutes on the free
> 2000-minutes/month allowance and keeps `config.json` (your booking
> schedule) out of public view — the safer default. A public repo gets
> unmetered Actions minutes (so you can poll more often) at the cost of
> `config.json`'s contents — including anything you put in `notify.email` —
> being visible to anyone.

### Step 2 — Tell it your login

In your repository: **Settings → Secrets and variables → Actions → New
repository secret**. Add these three, one at a time:

| Name | Value |
|---|---|
| `WRB_USERNAME` | your ITS username, e.g. `u1234567` |
| `WRB_PASSWORD` | your ITS password |
| `NOTIFY_EMAIL` | where you want to be emailed |

Secrets are encrypted and are not visible in logs.

### Step 3 — Check it works

Go to the **Actions** tab. If you see a banner offering to enable workflows,
click it. Then pick **"1. Test my setup"** on the left and press
**Run workflow**.

It takes about a minute and proves three things: GitHub can reach the Warwick
site, your login works, and your notifications arrive. A green tick means you
are set. If it fails, see [Troubleshooting](#troubleshooting).

### Step 4 — Upload your spreadsheet

This is the main path for setting this up for someone else who doesn't want
to touch code or JSON at all.

**1. Set up your spreadsheet with these columns** (header row required):

| Column | Required? | Format | Example |
|---|---|---|---|
| `rooms` | **yes** | room code(s), best first, separated by `;` or `,` | `OC1.06;OC1.09;OC1.04` |
| `date` | **yes** | `YYYY-MM-DD` — the single day to book | `2026-11-04` |
| `start` | **yes** | `HH:MM`, 24-hour | `17:00` |
| `end` | **yes** | `HH:MM`, 24-hour | `22:00` |
| `size` | optional | how many people; snapped up to the nearest room capacity | `10` |
| `reason` | optional | shown to Warwick, **max 35 characters**. Leave blank to use the default reason (see below) | `KCSOC Gita Circle` |
| `strict` | optional | `yes`/`no` — `yes` means *never* book a different room than listed | `yes` |

A filled-in example lives at
[`bookings.example.csv`](bookings.example.csv):

```csv
label,rooms,date,start,end,size,reason,strict
Oculus evening,OC1.06;OC1.09;OC1.04;OC1.01,2026-11-04,17:00,22:00,5,Group study session,yes
Library Friday morning,L1.02;L1.03,2026-11-06,09:00,11:00,6,Project meeting,yes
```

**2. Download and upload it.**

1. In your spreadsheet app: **File → Download / Save As → CSV.**
2. On the repo's GitHub page: **Add file → Upload files**, drag the CSV in,
   rename it to `bookings.csv` if it isn't already, then **Commit changes**.
3. That's it — the upload itself triggers **"3. Import from spreadsheet"**,
   which turns every row into a booking and saves it. Check the **Actions**
   tab; a red ✗ means a row had a problem (it'll say exactly which row and
   why — nothing is saved until every row is valid).

**Where does the data actually live?** `bookings.csv` is only ever read
*once*, at the moment you upload it — that's when `import_csv.py` turns each
row into an entry in `config.json`'s `rules` list. From then on, **only
`config.json` matters**: the watcher (`run.py`, running every 10 minutes)
reads `config.json` at booking time and never looks at `bookings.csv` again.
Uploading a new `bookings.csv` re-runs the import and rewrites `config.json`
(add `append` if you want to add to the existing list instead of replacing
it) — but changing `bookings.csv` after the fact does nothing on its own; you
have to re-upload it (or re-run the import workflow) for a change to take
effect.

> Every booking this tool makes has the "society/club booking" option
> switched on — see [Things worth knowing](#things-worth-knowing). There is
> no per-row or per-config way to turn this off; if you need personal (not
> society) bookings, remove `ctl("SocietyClub"): "Yes"` in `wrb/booker.py`.

### Alternative: one recurring pattern instead of a spreadsheet

If all you want is a single "same time every week" pattern, skip the
spreadsheet:

**In the browser:** Actions → **"2. Change what gets booked"** → Run
workflow. Fill the form in and it saves for you:

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

> **"Book ONLY these rooms"** is the important one. Ticked, it will *never*
> book a room you did not ask for — if all four Oculus rooms are taken it
> books nothing and tries again on the next run. Unticked, it falls back to
> the smallest room that fits.

**Note:** this form *replaces* the whole booking list with this one pattern —
don't run it after uploading a spreadsheet unless you mean to discard those
rows.

**Or on your own computer**, which asks the same questions in a friendlier
way:

```bash
python setup_wizard.py
python run.py --check      # shows exactly which dates it will book
```

### Step 5 — Turn the watcher on

Nothing more to do: **"Watch and book"** runs automatically every 10 minutes
from the moment the code is in your repository. While the system is closed
each run takes a few seconds and does nothing.

When it opens you get an email saying so, then a second email listing every
room it booked.

To watch it work: Actions → **Watch and book** → most recent run.

### Step 6 — On opening day, sprint

Rooms are first come, first served. If you know the system opens today:

Actions → **Sprint (fast polling)** → Run workflow → leave the defaults.

That polls every 30 seconds for 5 hours and books the instant it opens. Start
it in the morning and forget about it.

### Troubleshooting

**"1. Test my setup" fails at the login step**
Your username or password secret is wrong. Re-enter them — a trailing space
is the usual culprit. Note it can only test the login while *some* instance
is open; if all are closed it says so and that is not a failure.

**It cannot reach the Warwick site from GitHub**
Unlikely but possible if Warwick blocks cloud IP ranges. Fall back to running
it on your own machine (see below).

**It booked nothing and said "none of OC1.06/... free"**
Working as intended — someone else had those rooms. It retries every 10
minutes; leave it running.

**Scheduled runs stopped after a couple of months**
GitHub disables schedules on repositories with no activity for 60 days. The
watcher writes a heartbeat to prevent this, but if it does happen GitHub
emails you a link to re-enable it.

**"hit booking limit"**
Warwick refused further bookings on your account. Nothing to fix in the
tool — you are at your allowance. Reduce how many weeks/rows you ask for.

### Running it on your own computer instead

Only needed if you would rather not use GitHub, or GitHub cannot reach
Warwick. The machine must be switched on for it to work.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
python setup_wizard.py
# or: python import_csv.py --file bookings.csv --default-reason "KCSOC Gita Circle"

python run.py --check      # what would happen
python run.py --confirm    # do it once
```

To have Windows run it automatically every 15 minutes:

```powershell
.\schedule.ps1 -Register -Confirm
.\schedule.ps1 -Status
.\schedule.ps1 -Unregister
```
## Reference

### config.json

Normally you never hand-edit this — the setup steps above generate it for
you — but it's plain JSON if you ever need to:

```json
{
  "instance": { "url": "https://abs.warwick.ac.uk/WRB2627/" },
  "notify":   { "email": "you@example.com" },
  "academic_year": "2026/27",
  "max_new_bookings_per_run": 20,
  "defaults": { "strict_rooms": true, "size": 6, "reason": "Group study session" },
  "rules": [
    {
      "name": "Wed+Thu evenings",
      "weekdays": ["Wed", "Thu"],
      "start": "17:00",
      "end": "22:00",
      "terms": ["autumn", "spring", "summer"],
      "rooms": ["OC1.06", "OC1.09", "OC1.04", "OC1.01"],
      "strict_rooms": true
    }
  ]
}
```

| Key | Meaning |
|---|---|
| `weekdays` | any of `Mon`…`Sun` |
| `terms` | `autumn` / `spring` / `summer`, resolved from `academic_year` |
| `date_ranges` | `[["2026-10-05","2026-12-12"]]` — use instead of `terms`; a CSV-imported one-off row is stored as a single-day range here |
| `rooms` | preference order; matched as a substring, so `OC1.06` matches `OC1.06 (Oculus)` |
| `strict_rooms` | `true` = whitelist. Never books a room you did not list |
| `split_hours` | e.g. `1` turns 17:00–22:00 into five 1-hour bookings |
| `max_new_bookings_per_run` | staging limit, so a year is not requested in one burst |

Sizes are snapped to the values the dropdown actually offers (1–5, 10, 15,
20, 30, …), so `"size": 6` searches for a room seating 10.

### GitHub Actions workflows

| Workflow | What it does |
|---|---|
| **1. Test my setup** | proves reachability, login and notifications |
| **2. Change what gets booked** | a web form that rewrites `config.json` (one recurring pattern) |
| **3. Import from spreadsheet** | uploading `bookings.csv` rewrites `config.json` (many one-off events); optional `default_reason` input |
| **Watch and book** | every 10 min: poll, and book when it opens |
| **Sprint (fast polling)** | manual: poll every 30 s for 5 h on opening day |

10 minutes is fine on a public repo — Actions minutes are unmetered there.
On a private repo, budget minutes against the 2000 free/month allowance
before lowering the interval. The sprint workflow is how you get sub-minute
reaction on the day regardless.

### One-off bookings from the command line

`book.py` books a single slot without touching `config.json`:

```bash
python book.py --date 2026-09-15 --start 14:00 --end 15:00 --size 4
python book.py --date 2026-09-15 --start 14:00 --rooms "A1.25,MS.03" --confirm
```

### Layout

```
run.py                main entry: watch -> notify -> book everything in config
book.py               one-off single booking from the command line
setup_wizard.py       interactive config builder
import_csv.py         bulk config builder from a spreadsheet (bookings.csv)
config.json           what to book
state.json            what has already been booked (the anti-double-book guard)
schedule.ps1          local Windows Task Scheduler registration
.github/workflows/    the five cloud workflows
wrb/client.py         session, login, VIEWSTATE round-tripping, postbacks
wrb/booker.py         the five wizard steps
wrb/rules.py          recurring rules -> dated slots
wrb/state.py          durable booking record
wrb/notify.py         email / GitHub issue notification
wrb/live.py           instance liveness detection
recon/                investigation scripts and captured HTML
```

---

# auto-roombooking

Automates the University of Warwick **Web Room Booking** system
(`https://abs.warwick.ac.uk/WRB2526/`) — searching, selecting and confirming a
room without a browser, plus a watcher that fires as soon as next year's
instance opens.

**Status: working.** Two real bookings were placed by this code:
`A1.25 (Millburn)` Tue 15/09/2026 14:00–15:00 (ref **BKB97EF7**) and
`A1.27 (Millburn)` Thu 17/09/2026 17:00–18:00 (ref **BKB98077**).

---

## 1. What the site actually is

Not a Warwick-SSO app. It is **Scientia Enterprise Foundation / Syllabus Plus
Web Room Booking v2.2.3.12** — a classic ASP.NET WebForms application. That
matters a lot: there is no JavaScript SPA and no API, but every interaction is
a plain form POST that round-trips `__VIEWSTATE`, `__VIEWSTATEGENERATOR` and
`__EVENTVALIDATION`. So a bare `requests.Session` can drive it. **No browser,
no Selenium/Playwright, no AI agent needed** — which is why this is fast
(a booking takes ~4 seconds) and reliable enough to schedule.

### Authentication flow

```
GET  https://abs.warwick.ac.uk/WRB2526/
 302 /wrb2526/PortalLogin.aspx?ReturnUrl=%2fWRB2526%2f
 302 https://timetablingmanagement.warwick.ac.uk/scientia/portal/Forward.aspx?SdbName=2526&ApplicationName=WRB
 302 /Scientia/Portal/Login.aspx?ReturnUrl=...&SdbName=2526&ApplicationName=WRB
 200 login form
POST .../Login.aspx   ctl00$ContentPlaceHolder1$user / $password / $logon
 302 Forward.aspx -> portallogin.aspx?Token=<guid>&Sdb=2526&Application=WRB
 302 /wrb2526/default.aspx      (logged in)
```

Cookies issued: `ASP.NET_SessionId`, `ScientiaPortal` (on
`timetablingmanagement`), `wrb2526`, `KeepPortalHidden` (on `abs`).

**Gotcha:** ASP.NET only runs a button's server handler if that button's
`name=value` is in the POST body. Submitting the form without
`...$logon=Login` silently re-renders the login page.

### The booking wizard

One page (`default.aspx`, posting to `Book.aspx`) with five server-side steps:

| Step | What | Control that advances it |
|---|---|---|
| 1 | Room filters (size / zone / facilities) | — |
| 2 | Date (ASP.NET Calendar) | `__doPostBack` on the calendar |
| 3 | Time (start / end / duration) | — |
| 4 | Grid of available rooms | `ctl00$Main$ShowOptionsBtn` (`Next >`) |
| 5 | Booking details form | `ctl00$Main$SelectOptionButton` (`Next >`) |
| 6 | Confirmation + reference | `ctl00$Main$MakeBookingBtn` (**postback, not a submit**) |

---

## 2. Parameters

### Step 1–3 — search

| Control name | Meaning | Values |
|---|---|---|
| `ctl00$Main$Room1$ReqSize` | group size | `1,2,3,4,5,10,15,20,25,30,40,50,60,70,80,90,100,150,200,250,300,325,370,400,450,500` |
| `ctl00$Main$Room1$ZoneList` | campus zone | `*` = any; GUIDs for *Gibbet Hill Site*, *Main Site*, *Westwood Site* |
| `ctl00$Main$Room1$SuitabilityList` | facilities (multi-select) | GUIDs for Blackboard, DataVideo Projector/LCD/Plasma, Film Projector (35mm), Flat Room, Lecture Capture, Rehearsal Room, Rehearsal Room (Music), TEAMS Audio only / Enhanced / Tutor Camera, Tiered Room, Visualizer, Whiteboard |
| `ctl00$Main$Date1$CollegeCalendar1$theCalendar` | date | postback **argument = days since 2000-01-01** (e.g. `9754` = 2026-09-15) |
| `ctl00$Main$Time1$StartTimeList` | start | `1`=09:00 … `13`=21:00 |
| `ctl00$Main$Time1$EndTimeList` | end | `1`=10:00 … `13`=22:00 |
| `ctl00$Main$Time1$DurList` | duration | `1`=1:00 … `13` |

The zone/suitability GUIDs are **not** hardcoded here — the code resolves them
from the option labels at runtime, so they survive a system rollover.

### Step 4 — choosing a room

Each grid row carries a checkbox
`ctl00$Main$OptionSelector$OptionsGrid$ctlNN$rdoMultiple` whose `value` is the
option id (a signed 32-bit int, e.g. `487425335`). `Client/OptionSelection.js`
also maintains three hidden fields that **the server reads instead of the
checkboxes** — miss them and the app throws an unhandled `Error.aspx`:

| Hidden field | Set to |
|---|---|
| `ctl00$Main$OptionSelector$SelectedItem` | comma-separated option id(s) |
| `ctl00$Main$OptionSelector$ItemsCount` | how many are selected |
| `ctl00$Main$OptionSelector$AllowedItems` | server-set max — **3 rooms per booking** |

Grid also offers `PrevDayBtn` / `NextDayBtn` / `PrevPeriod` / `NextPeriod` /
`ExtendSearchLink` postbacks to widen the search.

### Step 5 — the booking form

Prefilled from your account: `email`, `firstName`, `lastName`, `department`
(*School of Engineering*), `departmentCode` (*ES*), `userType` (*UG*).

Must be supplied — the booking fails validation without them:

| Field | Value |
|---|---|
| `...$BookingForm1$meaningfulName` | reason, **max 35 chars** |
| `...$BookingForm1$FoodDrink` | `Yes` ("food and drink will not be taken into the room") |
| `...$BookingForm1$Layout` | `Yes` ("furniture cannot be moved") |
| `...$BookingForm1$acceptConditions` | `Yes` |

Optional: `tel`, `SocietyClub`, `Disturbance`, `AttendanceFee`,
`External-Speaker` (all default `No`).

Confirm with a postback to `ctl00$Main$MakeBookingBtn` — it is
`<input type="button">`, so sending it as a submit value does nothing.

All bookings come back marked **`P` = "Provisional only — booking may be
cancelled"**. That is normal for student ad-hoc bookings, not an error.

---

## 3. Usage

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
python setup_wizard.py          # asks what the booking portal asks
```

Credentials live in `.env` (gitignored) or, in CI, in GitHub Secrets:

```
WRB_USERNAME=u5618364
WRB_PASSWORD=...
NOTIFY_EMAIL=you@example.com
```

### The watcher

`run.py` is the main entry point. It checks whether the instance is open,
emails you when it opens, then books every slot in `config.json`.

```bash
python run.py --check                        # status + exactly what it would book
python run.py                                # one pass, dry run
python run.py --confirm                      # one pass, books for real
python run.py --confirm --loop --interval 30 # sprint: poll hard until done
```

**Nothing is booked without `--confirm`.**

### One-off bookings

`book.py` books a single slot without touching the config:

```bash
python book.py --date 2026-09-15 --start 14:00 --end 15:00 --size 4
python book.py --date 2026-09-15 --start 14:00 --rooms "A1.25,MS.03" --confirm
```

### config.json

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
| `date_ranges` | `[["2026-10-05","2026-12-12"]]` — use instead of `terms` |
| `rooms` | preference order; matched as a substring, so `OC1.06` matches `OC1.06 (Oculus)` |
| `strict_rooms` | `true` = whitelist. Never books a room you did not list |
| `split_hours` | e.g. `1` turns 17:00–22:00 into five 1-hour bookings |
| `max_new_bookings_per_run` | staging limit, so a year is not requested in one burst |

Sizes are snapped to the values the dropdown actually offers (1–5, 10, 15, 20,
30, …), so `"size": 6` searches for a room seating 10.

### Bulk import from a spreadsheet

If what to book comes as a spreadsheet (many rooms/days/times at once) rather
than one pattern, save it as CSV and let `import_csv.py` build the `rules`
list for you instead of typing it in by hand:

```bash
python import_csv.py --file bookings.csv     # replaces the rules list
python import_csv.py --file bookings.csv --append   # adds to it instead
```

See `bookings.example.csv` for the columns it expects (`rooms`, `days`,
`start`, `end`, `terms` or `date_from`/`date_to`, plus optional `label`,
`size`, `reason`, `strict`). It validates every row before writing anything —
one bad row and `config.json` is left untouched, with every problem listed at
once. In the cloud, this runs automatically via **"3. Import from
spreadsheet"** the moment `bookings.csv` is uploaded through GitHub's web UI
(Add file → Upload files) — no git or editing required.

### Running it in the cloud

Five GitHub Actions workflows, described fully in **[SETUP.md](SETUP.md)**:

| Workflow | What it does |
|---|---|
| **1. Test my setup** | proves reachability, login and notifications |
| **2. Change what gets booked** | a web form that rewrites `config.json` (one pattern) |
| **3. Import from spreadsheet** | uploading `bookings.csv` rewrites `config.json` (many patterns) |
| **Watch and book** | every 30 min: poll, and book when it opens |
| **Sprint (fast polling)** | manual: poll every 30 s for 5 h on opening day |

30 minutes is chosen so a private repo stays inside the 2000 free
Actions-minutes/month. The sprint workflow is how you get sub-minute reaction
on the day without burning that budget.

To run locally on Windows instead: `.\schedule.ps1 -Register -Confirm`.

---

## 4. Layout

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

## 5. Notes and limits

- **Term-time rooms are not bookable yet.** The 25/26 instance's horizon ends
  ~2 Oct 2026 and its room pool is only the 15 rooms flagged *"Centrally
  Timetabled all year - including vacations"* (Millburn, Zeeman, Maths,
  Westwood). **No Oculus room appears in it at all**, so `OC1.06` and friends
  cannot be verified until WRB2627 opens. They do exist — the timetable service
  resolves `oc106`, `oc109`, `oc104`, `oc101` — but whether they are ad-hoc
  bookable by a student is unconfirmed.
- Max **3 rooms per booking transaction** (`AllowedItems`), server-enforced.
- Bookings are **provisional** (`P`) and may be cancelled by Central Timetabling.
- 5-hour blocks (17:00–22:00) are accepted; no need to split.
- Bookings are **deleted at the year rollover**, which is why each year is a
  separate instance.
- `myBookings.aspx` shows an empty grid for dates beyond the instance's own
  academic year even when the booking is real. Verify by re-running the search:
  a booked room disappears from the options.
- Confirmation emails go to your **@warwick.ac.uk** address, not to a personal
  one.
- Ad-hoc bookings are *"first come, first served"* and need *"one clear working
  day's notice"*.
- Automating a university system is a grey area under IT regulations, and a
  year of 5-hour slots (~300 room-hours) is conspicuous. Stage it.

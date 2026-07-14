---
name: siggraph-calendar
description: Build a filtered, triaged .ics calendar from the SIGGRAPH conference schedule. Use when the user wants to scrape SIGGRAPH sessions, triage which to attend, or generate a calendar file for SIGGRAPH. Handles yearly reconfiguration, re-scraping with triage preservation, and Apple/Google Calendar export.
---

# SIGGRAPH Conference Calendar Builder

This skill scrapes the SIGGRAPH conference schedule website, guides you through choosing which sessions to attend, and produces a `.ics` file importable into Apple Calendar or Google Calendar.

The two scripts that do the work live alongside this file in `scripts/`. Bootstrap them into your working directory in Step 1.

---

## Step 0 — Install dependencies

```bash
python3 -c "import bs4, lxml" 2>&1
```

If that fails:

```bash
python3 -m pip install beautifulsoup4 lxml --break-system-packages
```

---

## Step 1 — Bootstrap scripts

Check whether `scrape.py` and `generate_ics.py` exist in the current working directory. If either is missing, read it from this skill's `scripts/` directory (use the path relative to this SKILL.md file) and write it to the current directory.

---

## Step 2 — Configure for this year

Ask the user: **"Which year's SIGGRAPH are you building a calendar for?"**

The schedule URL pattern is `https://s{YEAR}.conference-schedule.org/`. Confirm the site is live.

Set **`YEAR`** at the top of `scrape.py` (e.g. `"2026"`) — `BASE_URL` is derived from it automatically.

Extract two more values from the page source and update them in `scrape.py`:

**`DATES`** — conference dates. Find in `<select name="date_sel">` option values.

**`VERSION_PARAM`** — cache-buster on the day files. Search the page source for `wp_program_view_all_` and copy the `?v=XXXXXXXXXX` suffix.

Also set **`YEAR`** at the top of `generate_ics.py` to match — `ICS_PATH`, the calendar name, and event UIDs are all derived from it.

---

## Step 3 — Choose session types

Fetch the schedule page and find the session type options in `<select name="etype_filt">`. Show the user the full list and ask which types they want.

Update `WANTED_TYPES` in `scrape.py`. Standard abbreviations:

| Session type | Abbreviation |
|---|---|
| Technical Papers | `Pap:` |
| Talks | `Talk:` |
| Production Sessions | `ProdSess:` |
| Panels | `Pan:` |
| Courses | `Crs:` |
| ACM SIGGRAPH 365 | `365` |

---

## Step 4 — Scrape

```bash
python3 scrape.py
```

Takes 30–90 seconds. Show the session counts. Re-runs are safe — existing triage and notes are preserved; new sessions get blank triage; removed sessions are warned about.

---

## Step 5 — Triage

Tell the user to open `sessions.csv` and fill in the `triage` column:

| Value | Meaning |
|---|---|
| blank | Skip |
| `y` | Include |
| `y*` | Include, mark important (starred title) |

The `notes` column accepts personal reminders; they appear at the top of the calendar event description and survive re-scrapes.

Offer to make bulk edits via chat. Wait for the user to finish before proceeding.

---

## Step 6 — Generate

```bash
python3 generate_ics.py
```

Report included vs. skipped counts.

**Apple Calendar:** Double-click the `.ics`. Import into a dedicated "SIGGRAPH {YEAR}" calendar, not your main one.

**Google Calendar:** Settings → Import.

**Re-importing after re-scrape:** Delete events from the SIGGRAPH calendar first (or delete and recreate it), then re-import. Triage and notes live in `sessions.csv`, not the calendar app.

---

## Step 7 — Iterate and archive

Re-run `scrape.py` any time as the schedule updates. Triage is preserved.

After the conference: right-click "SIGGRAPH {YEAR}" in Apple Calendar → Export → import into your permanent SIGGRAPH calendar → delete the year calendar.

---

## Technical reference (load only if needed for debugging)

The site uses WordPress + the Linklings conference management plugin. Schedule data is in static per-day HTML files:

```
/wp-content/linklings_snippets/wp_program_view_all_YYYY-MM-DD.txt?v=XXXXXXXX
```

Two session structures in the HTML:

1. **Standard sessions** (365, Panels, Production Sessions): `tr.agenda-item[ssid!="none"]` — detail page at `/?post_type=page&p=15&id={ssid}&sess={psid}`. Description in `div.abstract-sect`; contributors in `div.presenter-details`.

2. **Container sessions** (Tech Papers, Talks, Courses): `tr.agenda-item[ssid="none"]` — room inline in `span.presentation-location`; sub-presentations in `tr.slots-slidedown.{psid}`. Sessions with no slidedown (Town Hall, Fast Forward, Closing) are emitted as-is.

The `etypes` attribute can be space-separated (e.g. `"sstype132 evtt102"`); match any wanted type in the list.

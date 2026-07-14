#!/usr/bin/env python3
"""
SIGGRAPH schedule scraper.
Fetches sessions of the desired types and saves sessions.csv + sessions_details.json.

Two kinds of sessions in the site HTML:
  1. Standard sessions (ACM SIGGRAPH 365, Panels, Production Sessions):
     tr.agenda-item with ssid != "none"; detail page at /presentation/?id={ssid}&sess={psid}
  2. Container sessions (Technical Papers, Talks, Courses):
     tr.agenda-item with ssid="none"; room inline; individual presentations in
     tr.slots-slidedown.{psid} rows, each with their own ssid and detail page.
"""

import csv
import json
import time
import urllib.request
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from pathlib import Path

YEAR = "YYYY"  # Set during Step 2, e.g. "2026"
BASE_URL = f"https://s{YEAR}.conference-schedule.org"
DATES = []  # Set during Step 2, e.g. ["2026-07-19", "2026-07-20", ...]
VERSION_PARAM = ""  # Set during Step 2, e.g. "v=1778950960"

# Session types the user wants to attend, set during Step 3 based on their answer.
# Format: etype_code -> abbreviated label for calendar title.
# Example (codes vary by year — re-check the site's etype_filt options):
#   "sstype102": "365",       # ACM SIGGRAPH 365
#   "evtt108":   "Pan:",      # Panels
#   "sstype124": "ProdSess:", # Production Sessions
#   "evtt111":   "Talk:",     # Talks
#   "sstype132": "Pap:",      # Technical Papers
#   "evtt103":   "Crs:",      # Courses
WANTED_TYPES = {
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

LA_TZ = timezone(timedelta(hours=-7))  # PDT in July


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req).read().decode("utf-8")


def parse_day_file(date):
    url = f"{BASE_URL}/wp-content/linklings_snippets/wp_program_view_all_{date}.txt?{VERSION_PARAM}"
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    sessions = []

    # First pass: collect parent session rows.
    # Standard sessions go directly to sessions[]; container sessions go to parent_info.
    parent_info = {}  # psid -> {etype, type_abbr, room, date, s_utc, e_utc}

    for row in soup.find_all("tr", class_="agenda-item"):
        etypes_raw = row.get("etypes", "").strip()
        # etypes can be space-separated (e.g. "sstype132 evtt102"); match any wanted type
        matched_etype = next((t for t in etypes_raw.split() if t in WANTED_TYPES), None)
        if not matched_etype:
            continue
        ssid = row.get("ssid", "").strip()
        psid = row.get("psid", "").strip()
        s_utc = row.get("s_utc", "")
        e_utc = row.get("e_utc", "")

        if ssid and ssid != "none":
            # Standard session — detail page linked directly
            title_td = row.find("td", class_="combo-sess-pres")
            if not title_td:
                continue
            link = title_td.find("a", href=lambda h: h and "post_type=page&p=15" in h)
            if not link:
                continue
            title = link.get_text(strip=True)
            detail_url = BASE_URL + link["href"]
            sessions.append({
                "date": date,
                "s_utc": s_utc,
                "e_utc": e_utc,
                "etype": matched_etype,
                "type_abbr": WANTED_TYPES[matched_etype],
                "title": title,
                "room": "",  # filled from detail page
                "ssid": ssid,
                "psid": psid,
                "detail_url": detail_url,
            })
        else:
            # Container session — may have individual presentations in a slidedown row,
            # or may have none (e.g. Town Hall, Fast Forward, Closing Session)
            room_span = row.find("span", class_="presentation-location")
            room = room_span.get_text(strip=True) if room_span else ""
            # Title: in <a> for sessions with a slidedown, or in <span.presentation-title> otherwise
            title_td = row.find("td", class_="combo-sess-pres")
            title = ""
            if title_td:
                a = title_td.find("a")
                if a:
                    title = a.get_text(strip=True).replace("\xa0", " ").strip()
                if not title:
                    span = title_td.find("span", class_="presentation-title")
                    if span:
                        title = span.get_text(strip=True)
            parent_info[psid] = {
                "etype": matched_etype,
                "type_abbr": WANTED_TYPES[matched_etype],
                "room": room,
                "date": date,
                "s_utc": s_utc,
                "e_utc": e_utc,
                "title": title,
            }

    # Second pass: collect container session entries (TechPapers, Talks).
    # The session itself is the calendar entry; individual presentations become notes.
    emitted_psids = set()
    for slidedown in soup.find_all("tr", class_="slots-slidedown"):
        classes = [c for c in slidedown.get("class", []) if c != "slots-slidedown"]
        if not classes:
            continue
        psid = classes[0]
        if psid not in parent_info:
            continue
        parent = parent_info[psid]
        emitted_psids.add(psid)

        # Collect sub-presentations for the notes field
        sub_presentations = []
        for sub_row in slidedown.find_all("tr", class_="agenda-item"):
            ssid = sub_row.get("ssid", "").strip()
            if not ssid:
                continue
            title_td = sub_row.find("td", class_="title-speakers-td")
            if not title_td:
                continue
            title_link = title_td.find("a", href=True)
            if not title_link:
                continue
            paper_title = title_link.get_text(strip=True)
            if not paper_title:
                continue

            # Authors inline in the sub-row
            authors = []
            seen = set()
            for pd in sub_row.find_all("div", class_="presenter-details"):
                name_tag = pd.find("div", class_="presenter-name")
                if not name_tag:
                    continue
                name = name_tag.get_text(strip=True)
                if name in seen:
                    continue
                seen.add(name)
                institutions = [
                    inst.get_text(strip=True)
                    for inst in pd.find_all("div", class_="presenter-institution")
                ]
                authors.append({"name": name, "institutions": institutions})

            sub_presentations.append({"title": paper_title, "authors": authors})

        sessions.append({
            "date": parent["date"],
            "s_utc": parent["s_utc"],
            "e_utc": parent["e_utc"],
            "etype": parent["etype"],
            "type_abbr": parent["type_abbr"],
            "title": parent["title"],
            "room": parent["room"],
            "ssid": psid,
            "psid": psid,
            "detail_url": None,
            "inline_contributors": sub_presentations,
        })

    # Emit container sessions that had no slidedown (Town Hall, Fast Forward, Closing, etc.)
    for psid, parent in parent_info.items():
        if psid not in emitted_psids:
            sessions.append({
                "date": parent["date"],
                "s_utc": parent["s_utc"],
                "e_utc": parent["e_utc"],
                "etype": parent["etype"],
                "type_abbr": parent["type_abbr"],
                "title": parent["title"],
                "room": parent["room"],
                "ssid": psid,
                "psid": psid,
                "detail_url": None,
                "inline_contributors": [],
            })

    return sessions


def parse_detail_page(url):
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    pres = soup.find("div", class_="presentation-display")
    if not pres:
        return {"room": "", "description": "", "contributors": []}

    # Room name (may be absent for sub-presentations whose room comes from the parent)
    room_sect = pres.find("div", class_="room-sect")
    room = ""
    if room_sect:
        room = room_sect.get_text(strip=True).replace("Location", "", 1).strip()

    # Description (class is "abstract-sect info-section")
    desc_div = pres.find("div", class_="abstract-sect")
    description = ""
    if desc_div:
        # Strip the "Description" label prefix
        description = desc_div.get_text(separator=" ", strip=True)
        if description.startswith("Description"):
            description = description[len("Description"):].strip()

    # Contributors: deduplicated list of {name, institutions}
    contributors = []
    seen = set()
    for pd in pres.find_all("div", class_="presenter-details"):
        name_tag = pd.find("div", class_="presenter-name")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        if name in seen:
            continue
        seen.add(name)
        institutions = [
            inst.get_text(strip=True)
            for inst in pd.find_all("div", class_="presenter-institution")
        ]
        contributors.append({"name": name, "institutions": institutions})

    return {"room": room, "description": description, "contributors": contributors}


def format_local_time(utc_str):
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    return dt.astimezone(LA_TZ).strftime("%Y-%m-%d %H:%M")


def main():
    print("Fetching schedule data...")
    all_sessions = []
    for date in DATES:
        print(f"  {date}...", end=" ", flush=True)
        day_sessions = parse_day_file(date)
        print(f"{len(day_sessions)} sessions")
        all_sessions.extend(day_sessions)

    print(f"\nTotal: {len(all_sessions)} sessions. Fetching detail pages...")

    details = {}
    fetch_sessions = [s for s in all_sessions if s["detail_url"]]
    inline_sessions = [s for s in all_sessions if not s["detail_url"]]
    print(f"  ({len(fetch_sessions)} need detail page fetch, {len(inline_sessions)} have inline data)")

    for i, sess in enumerate(fetch_sessions):
        print(f"  [{i+1}/{len(fetch_sessions)}] {sess['type_abbr']} {sess['title'][:60]}")
        try:
            detail = parse_detail_page(sess["detail_url"])
        except Exception as e:
            print(f"    WARNING: {e}")
            detail = {"room": "", "description": "", "contributors": []}
        details[sess["ssid"]] = detail
        if i < len(fetch_sessions) - 1:
            time.sleep(0.3)

    for sess in inline_sessions:
        details[sess["ssid"]] = {
            "room": sess["room"],
            "description": "",
            "sub_presentations": sess.get("inline_contributors", []),  # list of {title, authors}
            "contributors": [],
        }

    # Load existing triage and notes so re-runs don't wipe them out
    csv_path = "sessions.csv"
    existing_triage = {}  # session_id -> triage string
    existing_notes = {}   # session_id -> notes string
    if Path(csv_path).exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sid = row.get("session_id", "").strip()
                if not sid:
                    continue
                triage = row.get("triage", "").strip()
                notes = row.get("notes", "").strip()
                if triage:
                    existing_triage[sid] = triage
                if notes:
                    existing_notes[sid] = notes

    new_ids = {s["ssid"] for s in all_sessions}
    dropped = [sid for sid in existing_triage if sid not in new_ids]
    added = [s["ssid"] for s in all_sessions if s["ssid"] not in existing_triage]
    if dropped:
        print(f"\nNOTE: {len(dropped)} previously triaged session(s) no longer in schedule:")
        for sid in dropped:
            print(f"  removed: {sid}")
    if added:
        print(f"NOTE: {len(added)} new session(s) added (triage blank).")

    # Write sessions.csv — the triage file
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["triage", "notes", "type", "title", "date", "start", "end", "room", "session_id"])
        for sess in all_sessions:
            detail = details.get(sess["ssid"], {})
            room = detail.get("room") or sess["room"]
            start = format_local_time(sess["s_utc"])
            end = format_local_time(sess["e_utc"])
            writer.writerow([
                existing_triage.get(sess["ssid"], ""),
                existing_notes.get(sess["ssid"], ""),
                sess["type_abbr"],
                sess["title"],
                sess["date"],
                start,
                end,
                room,
                sess["ssid"],
            ])

    # Write sessions_details.json — descriptions and contributors for ics generation
    json_path = "sessions_details.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(details, f, indent=2, ensure_ascii=False)

    print(f"\nDone!")
    print(f"  {csv_path} — {len(all_sessions)} sessions, fill in the 'triage' column")
    print(f"  {json_path} — descriptions and contributors")
    print(f"\nTriage values: blank=skip, y=include, y*=important (starred in calendar title)")


if __name__ == "__main__":
    main()

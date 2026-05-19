#!/usr/bin/env python3
"""
Generate a .ics calendar file from triaged sessions.csv + sessions_details.json.

Triage values in sessions.csv:
  (blank) = skip
  y       = include
  y*      = include, mark as important (starred title)
"""

import csv
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

LA_TZ = timezone(timedelta(hours=-7))  # PDT in July

CSV_PATH = "sessions.csv"
JSON_PATH = "sessions_details.json"
ICS_PATH = "siggraph2026.ics"


def escape_ics(text):
    """Escape text for ICS format."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_line(line):
    """Fold long lines per RFC 5545 (max 75 octets)."""
    result = []
    line = line.encode("utf-8")
    while len(line) > 75:
        result.append(line[:75].decode("utf-8", errors="replace"))
        line = b" " + line[75:]
    result.append(line.decode("utf-8", errors="replace"))
    return "\r\n".join(result)


def parse_local_dt(date_str, time_str):
    """Parse 'YYYY-MM-DD HH:MM' as LA time and return UTC datetime."""
    dt_str = f"{date_str} {time_str}" if time_str else date_str
    local_dt = datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M")
    return local_dt.replace(tzinfo=LA_TZ)


def format_dt(dt):
    """Format datetime as ICS UTC timestamp."""
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def stable_uid(session_id):
    """Deterministic UID based on session_id — same session always gets the same UID."""
    h = hashlib.sha1(f"siggraph2026-{session_id}".encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}@siggraph2026"


def build_notes(detail, user_notes=""):
    """Build the calendar description from session detail and optional user notes."""
    parts = []

    if user_notes:
        parts.append(f"Notes: {user_notes}")

    description = detail.get("description", "")
    if description:
        parts.append(description)

    # Standard sessions: list contributors
    contributors = detail.get("contributors", [])
    if contributors:
        lines = []
        for c in contributors:
            insts = ", ".join(c["institutions"]) if c["institutions"] else ""
            lines.append(c["name"] + (f" ({insts})" if insts else ""))
        parts.append("Contributors: " + "; ".join(lines))

    # Container sessions (TechPapers/Talks): list sub-presentations
    sub_presentations = detail.get("sub_presentations", [])
    if sub_presentations:
        lines = []
        for p in sub_presentations:
            author_names = ", ".join(a["name"] for a in p.get("authors", []))
            line = p["title"]
            if author_names:
                line += f" — {author_names}"
            lines.append(line)
        parts.append("Papers/Talks:\n" + "\n".join(f"• {l}" for l in lines))

    return "\n\n".join(parts)


def main():
    details = json.loads(Path(JSON_PATH).read_text(encoding="utf-8"))

    events = []
    skipped = 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            triage = row["triage"].strip().lower()
            if triage not in ("y", "y*"):
                skipped += 1
                continue

            starred = triage == "y*"
            type_abbr = row["type"].strip()
            title = row["title"].strip()
            session_id = row["session_id"].strip()

            # Build calendar title
            star_prefix = "* " if starred else ""
            cal_title = f"{star_prefix}{type_abbr} {title}"

            # Parse times
            try:
                start_dt = parse_local_dt(row["date"], row["start"].split(" ")[-1])
                end_dt = parse_local_dt(row["date"], row["end"].split(" ")[-1])
            except Exception as e:
                print(f"WARNING: bad time for '{title}': {e}")
                continue

            room = row["room"].strip()
            user_notes = row.get("notes", "").strip()
            detail = details.get(session_id, {})
            detail_room = detail.get("room", "")
            if detail_room and not room:
                room = detail_room
            description = build_notes(detail, user_notes)

            events.append({
                "uid": stable_uid(session_id),
                "title": cal_title,
                "start": format_dt(start_dt),
                "end": format_dt(end_dt),
                "location": room,
                "description": description,
            })

    print(f"Including {len(events)} sessions, skipping {skipped}.")

    # Write ICS file
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SIGGRAPH 2026 Schedule//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:SIGGRAPH 2026",
        "X-WR-TIMEZONE:America/Los_Angeles",
    ]

    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            fold_line(f"UID:{ev['uid']}"),
            fold_line(f"SUMMARY:{escape_ics(ev['title'])}"),
            fold_line(f"DTSTART:{ev['start']}"),
            fold_line(f"DTEND:{ev['end']}"),
            fold_line(f"LOCATION:{escape_ics(ev['location'])}"),
            fold_line(f"DESCRIPTION:{escape_ics(ev['description'])}"),
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")

    Path(ICS_PATH).write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    print(f"Written to {ICS_PATH}")
    print(f"Import into Apple Calendar: double-click {ICS_PATH}")
    print(f"Import into Google Calendar: go to Settings > Import > choose {ICS_PATH}")


if __name__ == "__main__":
    main()

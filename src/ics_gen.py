"""Parse schedule HTML and generate ICS calendar file."""

import re
from datetime import datetime, date, time, timedelta
from bs4 import BeautifulSoup
import icalendar
from icalendar import Calendar, Event, vRecur

DAY_MAP = {
    "M": "MO",
    "T": "TU",
    "W": "WE",
    "H": "TH",
    "TH": "TH",
    "F": "FR",
    "S": "SA",
    "SN": "SU",
    "SU": "SU",
}

# Map S/Y year ranges to semester start/end dates
# We use the second year of the S/Y for the calendar year calculation


def parse_date_with_year(date_str: str, default_year: int) -> date | None:
    # Try common formats: "Jul 20", "July 20", "Jul 20, 2026", "July 20, 2026", "20 July", "20 Jul", etc.
    # Clean up multiple spaces
    date_str = re.sub(r'\s+', ' ', date_str.strip())
    
    # Try parsing with year first if it has a 4-digit number
    year_match = re.search(r'\b(20\d{2})\b', date_str)
    if year_match:
        year = int(year_match.group(1))
        # Remove the year from string to parse the rest
        date_str_no_yr = date_str.replace(year_match.group(1), "").strip()
        # Clean up any leftover punctuation at the end/middle like commas
        date_str_no_yr = re.sub(r'[\s,]+', ' ', date_str_no_yr).strip()
    else:
        year = default_year
        date_str_no_yr = date_str
        
    # Standard month names to numbers mapping
    months_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    # Look for month and day
    # Pattern 1: "Month Day" e.g., "Jul 20" or "July 20"
    m1 = re.search(r'\b([A-Za-z]+)\s+(\d{1,2})\b', date_str_no_yr)
    if m1:
        mon_str = m1.group(1).lower()
        if mon_str in months_map:
            return date(year, months_map[mon_str], int(m1.group(2)))
            
    # Pattern 2: "Day Month" e.g., "20 Jul" or "20 July"
    m2 = re.search(r'\b(\d{1,2})\s+([A-Za-z]+)\b', date_str_no_yr)
    if m2:
        mon_str = m2.group(2).lower()
        if mon_str in months_map:
            return date(year, months_map[mon_str], int(m2.group(1)))
            
    return None


def parse_start_date_from_announcement(text: str, default_year: int) -> date | None:
    """Parse start date from OES announcement text.
    Only returns a date if it's found under the '1st Sem' / '1st Semester' / 'First Semester' section.
    """
    # 1. Normalize line endings and whitespace
    text = re.sub(r'\r\n', '\n', text)
    
    # 2. Find the 1st semester section
    # Match "1st Semester" or "First Semester" or "1st Sem" or "First Sem"
    matches = list(re.finditer(r'(?:1st|First)\s*(?:Sem(?:ester)?)\b', text, re.IGNORECASE))
    if not matches:
        return None
        
    for match in matches:
        start_idx = match.start()
        # Look ahead up to 1000 characters
        window = text[start_idx:start_idx + 1000]
        
        # We also want to make sure we don't bleed into the next major semester section like "2nd Sem" or "Summer"
        # If there is a next semester section in the window, we truncate the window there
        next_sem_match = re.search(r'(?:2nd|Second|Summer)\s*(?:Sem(?:ester)?|20\d{2})\b', window[20:], re.IGNORECASE)
        if next_sem_match:
            # Truncate window at the start of next sem section (offset by 20 to ignore the match at start)
            window = window[:20 + next_sem_match.start()]
            
        # In this window, find "1st Day of Classes" (case-insensitive)
        match_classes = re.search(
            r'(?:1st\s+Day\s+of\s+Classes|Start\s+of\s+Classes|Classes\s+Begin)\s*[:\-–]\s*([^\n\r]+)',
            window,
            re.IGNORECASE
        )
        if match_classes:
            date_str = match_classes.group(1).strip()
            # Clean up date_str (remove HTML tags, extra whitespace, etc.)
            date_str = re.sub(r'<[^>]+>', '', date_str).strip()
            
            # Now parse the date string (e.g. "Jul 20" or "July 20")
            parsed = parse_date_with_year(date_str, default_year)
            if parsed:
                return parsed
                
    return None


def get_semester_dates(year: int, semester: str, check_oes: bool = False) -> tuple[date, date]:
    """Return (start, end) dates for a given school year and semester.

    S/Y 2025-2026, 1st Sem -> Aug 2025 - Dec 2025
    S/Y 2025-2026, 2nd Sem -> Jan 2026 - May 2026
    """
    is_first_sem = "1st" in semester or "First" in semester
    
    if is_first_sem:
        start_date = date(year, 8, 1)
        end_date = date(year, 12, 25)
        
        if check_oes:
            print("Checking OES announcement tab for 1st Day of Classes...")
            try:
                try:
                    from .oes_scraper import fetch_oes_announcement_text
                except (ImportError, ValueError):
                    from oes_scraper import fetch_oes_announcement_text
                
                annc_text = fetch_oes_announcement_text()
                parsed_date = parse_start_date_from_announcement(annc_text, year)
                if parsed_date:
                    print(f"Found 1st Day of Classes in OES announcement: {parsed_date}")
                    start_date = parsed_date
                else:
                    print("Could not find/parse '1st Day of Classes' for 1st Sem in OES announcements. Falling back to July 20.")
                    start_date = date(year, 7, 20)
            except Exception as e:
                print(f"Error checking OES announcements: {e}. Falling back to July 20.")
                start_date = date(year, 7, 20)
                
        return (start_date, end_date)
        
    elif "2nd" in semester or "Second" in semester:
        return (date(year + 1, 1, 1), date(year + 1, 5, 29))
    else:
        # Summer - short term, 2 months
        return (date(year + 1, 6, 1), date(year + 1, 7, 31))


def detect_period(html: str) -> tuple[str, int]:
    """Detect the selected semester period from the schedule page.

    Returns (semester_str, school_year_start)
    e.g. ("2nd Sem", 2025) for "2nd Sem. S/Y 2025-2026"
    """
    soup = BeautifulSoup(html, "html.parser")
    select = soup.find("select")
    if select:
        for opt in select.find_all("option"):
            if opt.get("selected") is not None:
                text = opt.get_text(strip=True)
                # Parse "2nd Sem. S/Y 2025-2026" or "1st Sem. S/Y 2025-2026"
                match = re.search(
                    r"(\d(?:st|nd|rd|th)\s*Sem)\.?\s*S/Y\s*(\d{4})-(\d{4})", text
                )
                if match:
                    sem = match.group(1).strip()
                    year = int(match.group(2))
                    return (sem, year)
                # Parse "Summer 2025"
                match = re.search(r"Summer\s+(\d{4})", text)
                if match:
                    return ("Summer", int(match.group(1)))
                return (text, datetime.now().year)
    # Fallback
    text = html.lower()
    if "2nd sem" in text:
        return ("2nd Sem", datetime.now().year)
    return ("1st Sem", datetime.now().year)


def parse_days(day_str: str) -> list[str]:
    """Parse combined day abbreviations like 'MWF', 'TTH', 'S' into RRULE BYDAY codes."""
    day_str = day_str.upper().strip()
    days = []
    i = 0
    while i < len(day_str):
        # Try two-char match first (TH, SN, SU, etc.)
        if i + 1 < len(day_str):
            two = day_str[i : i + 2]
            if two in DAY_MAP:
                days.append(DAY_MAP[two])
                i += 2
                continue
        # Single char match
        char = day_str[i]
        if char in DAY_MAP:
            days.append(DAY_MAP[char])
            i += 1
        else:
            i += 1
    # Remove duplicates while preserving order
    seen = set()
    unique_days = []
    for d in days:
        if d not in seen:
            seen.add(d)
            unique_days.append(d)
    return unique_days


def normalize_time(t: str) -> str:
    """Convert '08:30AM' or '8:30 AM' to '08:30 AM'."""
    t = t.strip().upper()
    # Insert space before AM/PM if missing
    t = re.sub(r"([AP]M)$", r" \1", t)
    return t


def parse_time(time_str: str) -> tuple[time, time] | None:
    """Parse time range like '08:30AM-10:00AM' into (start, end) time objects."""
    time_str = time_str.strip()
    match = re.match(
        r"(\d{1,2}:\d{2}\s*[AP]M)\s*[-–]\s*(\d{1,2}:\d{2}\s*[AP]M)",
        time_str,
        re.IGNORECASE,
    )
    if not match:
        return None
    fmt = "%I:%M %p"
    start = datetime.strptime(normalize_time(match.group(1)), fmt).time()
    end = datetime.strptime(normalize_time(match.group(2)), fmt).time()
    return start, end


def parse_schedule_column(schedule_text: str) -> tuple[str, str] | None:
    """Split '08:30AM-10:00AM TTH' into ('08:30AM-10:00AM', 'TTH')."""
    schedule_text = schedule_text.strip()
    match = re.match(
        r"(\d{1,2}:\d{2}\s*[AP]M\s*[-–]\s*\d{1,2}:\d{2}\s*[AP]M)\s+([A-Za-z]+)",
        schedule_text,
        re.IGNORECASE,
    )
    if match:
        return (match.group(1), match.group(2))
    return None


def cleanup_1enrl(val: str) -> str:
    if not val:
        return ""
    val = val.replace("1ENRL", "")
    val = val.replace("ENRL", "")
    return val.strip(" -")


def parse_schedule_table(html: str) -> tuple[list[dict], str, int]:

    """Parse schedule HTML.

    Returns (entries, semester_str, school_year_start).
    Each entry: {code, course_no, subject, days, time, room, teacher}
    """
    soup = BeautifulSoup(html, "html.parser")
    sem_str, year = detect_period(html)

    entries = []

    # Find table with headers: Code, Course No, Description, Unit, Schedule, Room, Teacher
    # Prioritize table with id="cart" (OES Enrolled cart)
    target_table = soup.find("table", id="cart")
    if not target_table:
        tables = soup.find_all("table")
        for table in tables:
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if "schedule" in headers and "room" in headers:
                target_table = table
                break

    if target_table is None:
        print("Warning: No schedule table found")
        return entries, sem_str, year

    # Map header names to column indices
    header_cells = target_table.find("tr").find_all(["th", "td"])
    col_map = {}
    for idx, cell in enumerate(header_cells):
        text = cell.get_text(strip=True).lower()
        if text == "code":
            col_map["code"] = idx
        elif text in ["course no", "course no."]:
            col_map["course_no"] = idx
        elif "desc" in text or "subject" in text or "title" in text:
            col_map["subject"] = idx
        elif text == "schedule":
            col_map["schedule"] = idx
        elif text == "room":
            col_map["room"] = idx
        elif "teacher" in text:
            col_map["teacher"] = idx

    def get_cell(cells, key):
        if key in col_map and col_map[key] < len(cells):
            return cells[col_map[key]].get_text(strip=True)
        return ""

    data_rows = target_table.find_all("tr")[1:]
    last_code = ""
    last_course_no = ""
    last_subject = ""
    for row in data_rows:
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        schedule_text = get_cell(cells, "schedule")
        if not schedule_text:
            continue

        parsed = parse_schedule_column(schedule_text)
        if parsed is None:
            continue

        time_str, days_str = parsed

        code = cleanup_1enrl(get_cell(cells, "code"))
        course_no = cleanup_1enrl(get_cell(cells, "course_no"))
        subject = cleanup_1enrl(get_cell(cells, "subject"))

        if not code:
            code = last_code
        else:
            last_code = code

        if not course_no:
            course_no = last_course_no
        else:
            last_course_no = course_no

        if not subject:
            subject = last_subject
        else:
            last_subject = subject

        entries.append(
            {
                "code": code,
                "course_no": course_no,
                "subject": subject,
                "days": days_str,
                "time": time_str,
                "room": cleanup_1enrl(get_cell(cells, "room")),
                "teacher": cleanup_1enrl(get_cell(cells, "teacher")),
            }
        )


    return entries, sem_str, year


def find_next_weekday(start_date: date, weekday_code: str) -> date:
    """Find the first occurrence of a weekday on or after start_date."""
    day_num_map = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
    target = day_num_map.get(weekday_code, 0)
    current = start_date.weekday()
    days_ahead = (target - current) % 7
    return start_date + timedelta(days=days_ahead)

def generate_ics(html: str, output_path: str = "data/schedule.ics") -> str:
    """Generate an ICS file from schedule HTML. Returns path to generated file."""
    import os
    if os.path.dirname(output_path):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    entries, sem_str, year = parse_schedule_table(html)
    if not entries:
        print("No schedule entries found, skipping ICS generation.")
        return ""

    start_date, end_date = get_semester_dates(year, sem_str, check_oes=True)
    print(f"Period: {sem_str} S/Y {year}-{year + 1}")
    print(f"Events: {start_date} to {end_date}")

    cal = Calendar()
    cal.add("prodid", "-//myUNC Scraper//EN")
    cal.add("version", "2.0")
    cal.add("calname", f"UNC Schedule - {sem_str} S/Y {year}-{year + 1}")

    for entry in entries:
        title = (
            f"{entry['subject']} - {entry['code']}"
            if entry["subject"]
            else (entry["code"] or "Class")
        )

        description_parts = []
        if entry["course_no"]:
            description_parts.append(entry["course_no"])
        if entry["teacher"]:
            description_parts.append(entry["teacher"])
        description = "\n".join(description_parts) if description_parts else ""

        parsed_time = parse_time(entry["time"])
        if parsed_time is None:
            print(f"  Skipping (unparseable time): {entry['code']} - {entry['time']}")
            continue

        start_t, end_t = parsed_time
        day_codes = parse_days(entry["days"])
        if not day_codes:
            print(f"  Skipping (no days): {entry['code']} - {entry['days']}")
            continue

        # Find the very first class date to use as the start of the repeating event
        first_event_date = min(find_next_weekday(start_date, day_code) for day_code in day_codes)

        event = Event()
        event.add("summary", title)
        event.add("location", entry["room"])
        event.add("description", description)
        event.add("dtstart", datetime.combine(first_event_date, start_t))
        event.add("dtend", datetime.combine(first_event_date, end_t))
        event.add("dtstamp", datetime.now())

        # Use UNTIL instead of COUNT to cleanly handle multiple days until the semester ends
        # We combine end_date with 23:59:59 to ensure the last day is fully included
        event.add(
            "rrule",
            vRecur(
                freq="WEEKLY",
                until=datetime.combine(end_date, time(23, 59, 59)),
                byday=day_codes
            )
        )

        cal.add_component(event)

    with open(output_path, "wb") as f:
        f.write(cal.to_ical())

    print(f"ICS file generated: {output_path} ({len(entries)} entries)")
    return output_path

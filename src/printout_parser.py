"""Parse schedule from PDF/Text printout and generate PNG and ICS schedules."""

import os
import re
import sys
import datetime
import subprocess
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Ensure local imports work
sys.path.insert(0, str(Path(__file__).parent))

from ics_gen import get_semester_dates, parse_time, find_next_weekday
from block_sched_gen import split_days, time_to_hours
from icalendar import Calendar, Event, vRecur

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file using the pdftotext CLI utility with layout preservation."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except Exception as e:
        print(f"Error extracting text from PDF using pdftotext: {e}")
        # Try a basic fallback or raise
        raise RuntimeError(
            f"Failed to run pdftotext. Make sure 'pdftotext' is installed and in your PATH. Error: {e}"
        )

def parse_printout(file_path: str) -> dict:
    """Parse UNC Certificate of Matriculation printout (PDF or TXT).
    
    Returns a dictionary:
    {
        "metadata": {
            "name": str,
            "course": str,
            "level": str,
            "semester": str,
            "sy": str,
            "sy_start": int
        },
        "subjects": [
            {
                "code": str,
                "course_no": str,
                "subject": str,
                "units": str,
                "schedules": [
                    {
                        "schedule": str,
                        "room": str
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """
    file_path = str(file_path)
    if file_path.lower().endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
    else:
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        
    lines = text.splitlines()
    
    name = ""
    course = ""
    level = ""
    semester = ""
    sy = ""
    
    for line in lines:
        if "Name:" in line:
            match = re.search(r"Name:\s*(.*)", line)
            if match:
                name = match.group(1).strip()
        elif "Course:" in line:
            match = re.search(r"Course:\s*(.*)", line)
            if match:
                course = match.group(1).strip()
        elif "Level:" in line:
            match = re.search(r"Level:\s*([^B\n]+)", line)
            if match:
                lvl = match.group(1).strip()
                # Clean up any trailing BN (Billing Number) info
                lvl = re.sub(r"\s+BN:.*", "", lvl).strip()
                level = lvl
        
        sem_sy_match = re.search(r"(\d(?:st|nd|rd|th)\s*Sem|Summer)\s*S/Y\s*(\d{4}-\d{4})", line, re.IGNORECASE)
        if sem_sy_match:
            semester = sem_sy_match.group(1).strip()
            sy = sem_sy_match.group(2).strip()
            
        # Fallback for Summer with just a year
        if not semester:
            summer_match = re.search(r"Summer\s+(\d{4})", line, re.IGNORECASE)
            if summer_match:
                semester = "Summer"
                year = summer_match.group(1)
                sy = f"{year}-{int(year)+1}"

    # Extract sy_start year
    sy_start = datetime.datetime.now().year
    if sy:
        match = re.match(r"(\d{4})", sy)
        if match:
            sy_start = int(match.group(1))

    header_found = False
    subject_entries = []
    current_subject = None

    for line in lines:
        # Detect table headers
        if "Code" in line and "Course No/Title" in line and "Schedule" in line:
            header_found = True
            continue
        
        if not header_found:
            continue
            
        # End of schedule section
        if "Total Units:" in line or "TUITION AND OTHER FEES" in line or "MISC FEE CHARGES:" in line:
            break
            
        if len(line.strip()) == 0:
            continue
            
        # Pad lines to ensure horizontal slicing works safely
        if len(line) < 120:
            line = line.ljust(120)
            
        code_part = line[0:10].strip()
        course_part = line[10:60].strip()
        unit_part = line[60:71].strip()
        sched_part = line[71:96].strip()
        room_part = line[96:107].strip()
        
        # A new subject line starts with a numeric code of at least 4 digits
        if code_part.isdigit() and len(code_part) >= 4:
            if current_subject:
                subject_entries.append(current_subject)
                
            current_subject = {
                "code": code_part,
                "course_no": course_part,
                "subject": "",
                "units": unit_part,
                "schedules": []
            }
            if sched_part:
                current_subject["schedules"].append({
                    "schedule": sched_part,
                    "room": room_part
                })
        elif current_subject:
            # Continuation line
            if course_part:
                if current_subject["subject"]:
                    current_subject["subject"] += " " + course_part
                else:
                    current_subject["subject"] = course_part
            if sched_part:
                current_subject["schedules"].append({
                    "schedule": sched_part,
                    "room": room_part
                })

    if current_subject:
        subject_entries.append(current_subject)
        
    # Clean up subject names (e.g. merge multiple spaces)
    for sub in subject_entries:
        sub["subject"] = re.sub(r"\s+", " ", sub["subject"]).strip()

    return {
        "metadata": {
            "name": name,
            "course": course,
            "level": level,
            "semester": semester,
            "sy": sy,
            "sy_start": sy_start
        },
        "subjects": subject_entries
    }

def generate_png_schedule(parsed_data: dict, output_path: str = "data/schedule.png") -> str:
    """Generate a weekly grid PNG schedule from parsed data using matplotlib."""
    metadata = parsed_data["metadata"]
    subjects = parsed_data["subjects"]
    
    if not subjects:
        print("No subjects to generate PNG for.")
        return ""
        
    # Flatten subject schedules
    schedule_slots = []
    time_regex = r'(\d{1,2}:\d{2}\s*[AP]M)\s*[-–]\s*(\d{1,2}:\d{2}\s*[AP]M)'
    
    for sub in subjects:
        for s in sub["schedules"]:
            sched_text = s["schedule"].strip()
            time_match = re.search(time_regex, sched_text, re.IGNORECASE)
            if not time_match:
                continue
            start_t, end_t = time_match.groups()
            
            time_str = sched_text[time_match.start():time_match.end()]
            time_idx = sched_text.find(time_str)
            day_str = sched_text[time_idx + len(time_str):].strip()
            
            days = split_days(day_str)
            for day in days:
                schedule_slots.append({
                    'code': sub['code'],
                    'course_no': sub['course_no'],
                    'title': sub['subject'] or sub['course_no'],
                    'day': day.upper(),
                    'start': start_t,
                    'end': end_t,
                    'room': s['room'],
                    'start_hours': time_to_hours(start_t),
                    'end_hours': time_to_hours(end_t)
                })
                
    if not schedule_slots:
        print("No valid schedule slots parsed for PNG generation.")
        return ""
        
    df = pd.DataFrame(schedule_slots)
    
    # Determine the days layout
    has_sunday = any(df['day'] in ['SU', 'SN'] for df in schedule_slots)
    if has_sunday:
        day_map = {'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4, 'S': 5, 'SU': 6, 'SN': 6}
        day_labels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        num_days = 7
    else:
        day_map = {'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4, 'S': 5}
        day_labels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        num_days = 6
        
    # Determine dynamic time range
    min_hour = min(row['start_hours'] for row in schedule_slots) - 1.0
    max_hour = max(row['end_hours'] for row in schedule_slots) + 1.0
    # Keep it within reasonable grid bounds
    min_hour = max(7.0, min(8.0, min_hour))
    max_hour = min(22.0, max(18.0, max_hour))
    
    # Setup color palette
    unique_titles = df['title'].unique()
    colors_palette = ['#FFADAD', '#CAFFBF', '#9BF6FF', '#FFD6A5', '#BDB2FF', '#FFC6FF', '#E2F0CB', '#FFDAC1']
    course_colors = {title: colors_palette[i % len(colors_palette)] for i, title in enumerate(unique_titles)}
    
    # Create the figure
    fig, ax = plt.subplots(figsize=(12, 9))
    
    # Title and subtitle formatting
    title_text = f"WEEKLY SCHEDULE — {metadata['name']}"
    subtitle_text = f"{metadata['course']} | {metadata['level']}\n{metadata['semester']} S/Y {metadata['sy']}"
    
    ax.set_title(title_text, fontsize=14, fontweight='bold', pad=25, color='#1D3557')
    # Add subtitle using plt.figtext or text
    plt.text(0.5, 0.94, subtitle_text, fontsize=10.5, color='#457B9D', ha='center', transform=fig.transFigure)
    
    # Set axis limits
    ax.set_xlim(-0.5, num_days - 0.5)
    ax.set_ylim(max_hour, min_hour)  # Inverted Y-axis so time goes down
    
    # X Axis
    ax.set_xticks(range(num_days))
    ax.set_xticklabels(day_labels, fontsize=11, fontweight='bold', color='#1D3557')
    
    # Y Axis
    hours_ticks = np.arange(int(np.floor(min_hour)), int(np.ceil(max_hour)) + 1, 1)
    ax.set_yticks(hours_ticks)
    ax.set_yticklabels([datetime.time(int(h)).strftime("%I:%M %p") for h in hours_ticks], fontsize=10, color='#1D3557')
    
    # Draw vertical day dividers
    for x in range(num_days - 1):
        ax.axvline(x + 0.5, color='#E5E5E5', linestyle='-', linewidth=1.2)
        
    # Draw horizontal grid lines
    ax.grid(axis='y', linestyle=':', color='#CCCCCC', alpha=0.7)
    
    # Draw events
    for _, row in df.iterrows():
        if row['day'] not in day_map:
            continue
        day_idx = day_map[row['day']]
        start = row['start_hours']
        end = row['end_hours']
        
        # Draw class rectangle
        rect = plt.Rectangle(
            (day_idx - 0.43, start), 0.86, end - start,
            facecolor=course_colors[row['title']], edgecolor='#457B9D', linewidth=1.2, alpha=0.9
        )
        ax.add_patch(rect)
        
        # Word wrap the title
        words = row['title'].split()
        lines_list, curr_line = [], ""
        for w in words:
            if len(curr_line + " " + w) > 16:
                lines_list.append(curr_line.strip())
                curr_line = w
            else:
                curr_line += " " + w
        if curr_line:
            lines_list.append(curr_line.strip())
        formatted_title = "\n".join(lines_list)
        
        # Label content
        room_str = f"Room: {row['room']}" if row['room'] else "No Room"
        label = f"{row['course_no'].split('-')[0]}\n{formatted_title}\n{room_str}\n{row['start']} - {row['end']}"
        
        duration = end - start
        if duration <= 1.0:
            font_size = 7.0
        elif duration <= 1.5:
            font_size = 7.5
        else:
            font_size = 8.5
            
        ax.text(
            day_idx, (start + end) / 2, label,
            ha='center', va='center', fontsize=font_size, color='#1D3557', weight='bold'
        )
        
    plt.tight_layout()
    # Adjust layout to make room for subtitle
    plt.subplots_adjust(top=0.88)
    
    # Save the plot
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Schedule PNG generated successfully at: {output_path}")
    return output_path

def generate_ics_schedule(parsed_data: dict, output_path: str = "data/schedule.ics") -> str:
    """Generate an ICS file from parsed data."""
    metadata = parsed_data["metadata"]
    subjects = parsed_data["subjects"]
    
    if not subjects:
        print("No subjects to generate ICS for.")
        return ""
        
    sy_start = metadata["sy_start"]
    semester = metadata["semester"]
    
    start_date, end_date = get_semester_dates(sy_start, semester, check_oes=True)
    
    day_rrule_map = {
        'M': 'MO',
        'T': 'TU',
        'W': 'WE',
        'TH': 'TH',
        'F': 'FR',
        'S': 'SA',
        'SU': 'SU',
        'SN': 'SU'
    }
    
    cal = Calendar()
    cal.add("prodid", "-//myUNC Scraper//EN")
    cal.add("version", "2.0")
    cal.add("calname", f"UNC Schedule - {metadata['name']}")
    
    event_count = 0
    time_regex = r'(\d{1,2}:\d{2}\s*[AP]M)\s*[-–]\s*(\d{1,2}:\d{2}\s*[AP]M)'
    
    for sub in subjects:
        for s in sub["schedules"]:
            sched_text = s["schedule"].strip()
            time_match = re.search(time_regex, sched_text, re.IGNORECASE)
            if not time_match:
                continue
            start_t_str, end_t_str = time_match.groups()
            
            time_str = sched_text[time_match.start():time_match.end()]
            time_idx = sched_text.find(time_str)
            day_str = sched_text[time_idx + len(time_str):].strip()
            
            parsed_time = parse_time(f"{start_t_str}-{end_t_str}")
            if not parsed_time:
                continue
            start_t, end_t = parsed_time
            
            days = split_days(day_str)
            day_codes = [day_rrule_map[d.upper()] for d in days if d.upper() in day_rrule_map]
            if not day_codes:
                continue
                
            # Find the first class date to start the repeating event
            first_event_date = min(find_next_weekday(start_date, day_code) for day_code in day_codes)
            
            event_title = f"{sub['subject']} - {sub['code']}" if sub['subject'] else f"{sub['course_no']} - {sub['code']}"
            description = f"Course No: {sub['course_no']}\nUnits: {sub['units']}"
            
            event = Event()
            event.add("summary", event_title)
            event.add("location", s["room"])
            event.add("description", description)
            event.add("dtstart", datetime.datetime.combine(first_event_date, start_t))
            event.add("dtend", datetime.datetime.combine(first_event_date, end_t))
            event.add("dtstamp", datetime.datetime.now())
            
            event.add(
                "rrule",
                vRecur(
                    freq="WEEKLY",
                    until=datetime.datetime.combine(end_date, datetime.time(23, 59, 59)),
                    byday=day_codes
                )
            )
            cal.add_component(event)
            event_count += 1
            
    if event_count == 0:
        print("No valid events generated, skipping ICS output.")
        return ""
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(cal.to_ical())
        
    print(f"Schedule ICS generated successfully at: {output_path} ({event_count} events)")
    return output_path

import os
import re
import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Hardcoded alias map to resolve curriculum/OES naming differences
ALIASES = {
    'computer programming 1': ['fundamentals of programming', 'computer programming 1'],
    'computer programming 2': ['intermediate programming', 'computer programming 2'],
    'information management (database systems 1)': ['database management (info mgt) 1', 'database management 1'],
    'networking 1': ['networking and communications 1', 'networking 1', 'networking and communications'],
    'web systems and technologies 1': ['web development 1', 'web systems 1'],
    'advanced database systems': ['database management (info mgt) 2', 'advanced database'],
    'networking 2': ['networking and communications 2', 'networking 2'],
    'web systems and technologies 2': ['web development 2', 'web systems 2'],
    'human-computer interaction': ['human computer interaction'],
    'application development and emerging technologies': ['applications development and emerging technologies', 'integrative programming and technologies'],
    'social and professional issues in it': ['social issues and professional practice'],
    'internship / practicum': ['practicum (incl. cpso)', 'practicum', 'internship'],
    'physical education 1 (physical fitness)': ['movement competency training', 'physical education 1', 'pe 1', 'pathfit 1', 'movement competency'],
    'physical education 2 (rhythmic activities)': ['exercise based fitness activities', 'physical education 2', 'pe 2', 'pathfit 2'],
    'physical education 3 (individual/dual sports)': ['outdoor and simulation sports', 'physical education 3', 'pe 3', 'pathfit 3'],
    'physical education 4 (team sports)': ['dance', 'physical education 4', 'pe 4', 'pathfit 4'],
    'team sports': ['dance', 'team sports'],
    'national service training program 1': ['national service training program 1', 'nstp 1', 'nstp1k'],
    'national service training program 2': ['national service training program 2', 'nstp 2', 'nstp2k'],
    'understanding the self': ['understanding the self', 'uts'],
    'purposive communication': ['purposive communication', 'pc'],
    'mathematics in the modern world': ['mathematics in the modern world', 'mmw'],
    'readings in philippine history': ['readings in philippine history', 'rph'],
    'contemporary world': ['the contemporary world', 'tcw'],
    'ethics': ['ethics', 'eth'],
    'science, technology, and society': ['science, technology, and society', 'sts'],
    'arts appreciation': ['art appreciation', 'aa'],
}

def titles_match(prop_title, oes_title):
    p_norm = prop_title.strip().lower()
    o_norm = oes_title.strip().lower()
    if p_norm == o_norm:
        return True
    if p_norm in ALIASES:
        for alias in ALIASES[p_norm]:
            if alias in o_norm or o_norm in alias:
                return True
    for k, aliases in ALIASES.items():
        if p_norm == k or p_norm in aliases:
            if o_norm in aliases or o_norm == k:
                return True
    def clean(t):
        return t.replace(' ', '').replace('-', '').replace('and', '&').replace(',', '')
    if clean(p_norm) == clean(o_norm):
        return True
    if len(p_norm) > 5 and len(o_norm) > 5:
        if p_norm in o_norm or o_norm in p_norm:
            return True
    return False

def normalize_year(y):
    if pd.isna(y): return -1
    y = str(y).lower().strip()
    if '1' in y or 'first' in y: return 1
    if '2' in y or 'second' in y: return 2
    if '3' in y or 'third' in y: return 3
    if '4' in y or 'fourth' in y: return 4
    if '5' in y or 'fifth' in y: return 5
    return -1

def normalize_semester(s):
    if pd.isna(s): return -1
    s = str(s).lower().strip()
    if '3' in s or 'summer' in s: return 3
    if '1' in s or 'first' in s: return 1
    if '2' in s or 'second' in s: return 2
    return -1

def time_to_hours(t_str):
    """Converts a time string like '06:30PM' into a float number of hours (18.5)."""
    t = datetime.datetime.strptime(t_str.replace(" ", ""), "%I:%M%p")
    return t.hour + t.minute / 60.0

def split_days(day_str):
    day_str = day_str.strip()
    days = []
    i = 0
    while i < len(day_str):
        if i + 1 < len(day_str) and day_str[i:i+2].upper() == 'TH':
            days.append('TH')
            i += 2
        elif day_str[i].upper() in ['M', 'T', 'W', 'F', 'S']:
            days.append(day_str[i].upper())
            i += 1
        else:
            i += 1
    return days

def get_block_name(course_no):
    parts = course_no.split('-')
    if len(parts) < 2:
        return "UNKNOWN"
    section_code = parts[-1].strip()
    
    # Strip trailing 'L' if it represents a Lab section (e.g. OQaL, PYaL)
    if len(section_code) >= 4 and section_code[-1].upper() == 'L':
        section_code = section_code[:-1]
        
    if len(section_code) < 3:
        return f"UNKNOWN {section_code.upper()}"
        
    prog_char = section_code[1].upper()
    block_letter = section_code[-1].upper()
    
    prog_map = {
        'B': 'BIT',
        'C': 'BCS',
        'A': 'ACT',
        # Online / OES codes
        'Q': 'EE',
        'P': 'CpE',
        'O': 'CE',
        'S': 'ME',
        # F2F / Professional codes
        'U': 'EE',
        'V': 'CE',
        'W': 'CpE',
        'Y': 'CpE',
        'X': 'ME',
        # Architecture & Interior Design
        'N': 'ARCH',
        'D': 'BSID',
    }
    prog = prog_map.get(prog_char, "UNKNOWN")
    return f"{prog} {block_letter}"

def get_prospectus_periods(prospectus_path="prospectus/it_prospectus.csv"):
    if not os.path.exists(prospectus_path):
        return []
    df = pd.read_csv(prospectus_path)
    pairs = df[['year level', 'semester']].drop_duplicates().values.tolist()
    def sort_key(pair):
        yr, sem = pair[0].lower(), pair[1].lower()
        
        # Year mapping
        if "1st" in yr or "first" in yr:
            yr_val = 1
        elif "2nd" in yr or "second" in yr:
            yr_val = 2
        elif "3rd" in yr or "third" in yr:
            yr_val = 3
        elif "4th" in yr or "fourth" in yr:
            yr_val = 4
        else:
            yr_val = 5
            
        # Semester mapping
        if "1st" in sem or "first" in sem:
            sem_val = 1
        elif "2nd" in sem or "second" in sem:
            sem_val = 2
        else:
            sem_val = 3
            
        return (yr_val, sem_val)
    return sorted(pairs, key=sort_key)

def generate_schedules_for_period(year_level, semester, prospectus_path="prospectus/it_prospectus.csv", avail_path="data/available_subjects.csv", output_dir="data/BlockSchedules"):
    if not os.path.exists(avail_path):
        print(f"Error: {avail_path} does not exist. Please export OES available subjects to CSV first.")
        return False
        
    prop_df = pd.read_csv(prospectus_path)
    avail_df = pd.read_csv(avail_path)
    
    period_prop = prop_df[
        (prop_df['year level'].apply(normalize_year) == normalize_year(year_level)) & 
        (prop_df['semester'].apply(normalize_semester) == normalize_semester(semester))
    ]
    prop_descriptions = period_prop['subject description'].tolist()
    
    print(f"\nMatching available subjects for {year_level} - {semester}...")
    
    matched_rows = []
    for idx, row in avail_df.iterrows():
        title = row['title']
        for desc in prop_descriptions:
            if titles_match(desc, title):
                matched_rows.append(row)
                break
                
    if not matched_rows:
        print("No matching subjects found in available subjects for the selected period.")
        return False
        
    matched_df = pd.DataFrame(matched_rows)
    schedule = []
    time_regex = r'(\d{1,2}:\d{2}\s*[AP]M)\s*[-–]\s*(\d{1,2}:\d{2}\s*[AP]M)'
    
    for idx, row in matched_df.iterrows():
        sched_text = str(row['schedule']).strip()
        time_match = re.search(time_regex, sched_text, re.IGNORECASE)
        if not time_match:
            continue
        start_t, end_t = time_match.groups()
        
        time_str = sched_text[time_match.start():time_match.end()]
        time_idx = sched_text.find(time_str)
        day_str = sched_text[time_idx + len(time_str):].strip()
        
        days = split_days(day_str)
        block = get_block_name(row['course_no'])
        
        for day in days:
            schedule.append({
                'code': row['course_no'],
                'block': block,
                'title': row['title'],
                'day': day,
                'start': start_t,
                'end': end_t,
                'room': row['room'] if pd.notna(row['room']) else "",
                'start_hours': time_to_hours(start_t),
                'end_hours': time_to_hours(end_t)
            })
            
    if not schedule:
        print("No valid schedule slots parsed from matching subjects.")
        return False
        
    df = pd.DataFrame(schedule)
    df = df[~df['block'].str.upper().str.contains("UNKNOWN")]
    
    # Filter by prospectus program prefix to sort out unrelated blocks/courses
    filename = os.path.basename(prospectus_path).lower()
    allowed_prefixes = []
    if "ee_" in filename or "ee." in filename:
        allowed_prefixes = ["EE"]
    elif "it_" in filename or "it." in filename:
        allowed_prefixes = ["BIT", "BCS", "ACT"]
    elif "ce_" in filename or "ce." in filename:
        allowed_prefixes = ["CE"]
    elif "cpe_" in filename or "cpe." in filename:
        allowed_prefixes = ["CpE"]
    elif "me_" in filename or "me." in filename:
        allowed_prefixes = ["ME"]
    elif "arch_" in filename or "arch." in filename:
        allowed_prefixes = ["ARCH"]
    elif "bsid_" in filename or "bsid." in filename:
        allowed_prefixes = ["BSID"]
    else:
        name_part = filename.split('_')[0].split('.')[0].upper()
        if name_part == "IT":
            allowed_prefixes = ["BIT", "BCS", "ACT"]
        elif name_part == "CPE":
            allowed_prefixes = ["CpE"]
        else:
            allowed_prefixes = [name_part]

    if allowed_prefixes:
        df = df[df['block'].apply(lambda b: any(b.upper().startswith(prefix.upper()) for prefix in allowed_prefixes))]
        
    if df.empty:
        print("No valid non-UNKNOWN schedule slots parsed from matching subjects.")
        return False
    
    courses = df['title'].unique()
    colors_palette = ['#FFADAD', '#CAFFBF', '#9BF6FF', '#FFD6A5', '#BDB2FF', '#FFC6FF']
    course_colors = {course: colors_palette[i % len(colors_palette)] for i, course in enumerate(courses)}
    
    day_map = {'M': 0, 'T': 1, 'W': 2, 'TH': 3, 'F': 4, 'S': 5}
    day_labels = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    blocks = sorted(df['block'].unique())
    
    os.makedirs(output_dir, exist_ok=True)
    
    def plot_schedule_on_axis(ax, block_name, block_df):
        ax.set_title(f"WEEKLY SCHEDULE — {block_name} ({year_level} — {semester})", fontsize=14, fontweight='bold', pad=15, color='#1D3557')
        ax.set_xlim(-0.5, 5.5)
        ax.set_ylim(21.5, 7.5)
        ax.set_xticks(range(6))
        ax.set_xticklabels(day_labels, fontsize=11, fontweight='bold')
        
        hours = np.arange(8, 22, 1)
        ax.set_yticks(hours)
        ax.set_yticklabels([datetime.time(int(h)).strftime("%I:%M %p") for h in hours], fontsize=10)
        
        for x in range(5):
            ax.axvline(x + 0.5, color='#E5E5E5', linestyle='-', linewidth=1)
        ax.grid(axis='y', linestyle=':', color='#CCCCCC', alpha=0.7)
        
        for _, row in block_df.iterrows():
            if row['day'] not in day_map:
                continue
            day_idx = day_map[row['day']]
            start = row['start_hours']
            end = row['end_hours']
            
            rect = plt.Rectangle((day_idx - 0.42, start), 0.84, end - start,
                                 facecolor=course_colors[row['title']], edgecolor='#4A4A4A', linewidth=1.2, alpha=0.95)
            ax.add_patch(rect)
            
            words = row['title'].split()
            lines_list, curr_line = [], ""
            for w in words:
                if len(curr_line + " " + w) > 15:
                    lines_list.append(curr_line.strip())
                    curr_line = w
                else:
                    curr_line += " " + w
            if curr_line:
                lines_list.append(curr_line.strip())
            formatted_title = "\n".join(lines_list)
            
            label = f"{row['code'].split('-')[0]}\n{formatted_title}\nRoom: {row['room']}\n({row['start']}-{row['end']})"
            duration = end - start
            font_size = 7.0 if duration <= 1.5 else 8.5
            
            ax.text(day_idx, (start + end)/2, label, ha='center', va='center', fontsize=font_size, color='#1D3557', weight='bold')

    for block in blocks:
        fig, ax = plt.subplots(figsize=(11, 8.5))
        plot_schedule_on_axis(ax, block, df[df['block'] == block])
        plt.tight_layout()
        
        safe_filename = f"schedule_block_{block.replace(' ', '_')}.png"
        full_path = os.path.join(output_dir, safe_filename)
        plt.savefig(full_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"Saved independent block layout to '{full_path}'")
        
    num_blocks = len(blocks)
    fig, axes = plt.subplots(num_blocks, 1, figsize=(12, 8 * num_blocks))
    if num_blocks == 1:
        axes = [axes]
    for idx, block in enumerate(blocks):
        plot_schedule_on_axis(axes[idx], block, df[df['block'] == block])
    plt.tight_layout()
    master_path = os.path.join(output_dir, 'weekly_schedule_blocks.png')
    plt.savefig(master_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved complete master schedule canvas to '{master_path}'")
    return True


def generate_ics_schedules_for_period(year_level, semester, prospectus_path="prospectus/it_prospectus.csv", avail_path="data/available_subjects.csv", output_dir="data/BlockSchedules"):
    if not os.path.exists(avail_path):
        print(f"Error: {avail_path} does not exist. Please export OES available subjects to CSV first.")
        return False
        
    prop_df = pd.read_csv(prospectus_path)
    avail_df = pd.read_csv(avail_path)
    
    period_prop = prop_df[
        (prop_df['year level'].apply(normalize_year) == normalize_year(year_level)) & 
        (prop_df['semester'].apply(normalize_semester) == normalize_semester(semester))
    ]
    prop_descriptions = period_prop['subject description'].tolist()
    
    print(f"\nMatching available subjects for {year_level} - {semester}...")
    
    matched_rows = []
    for idx, row in avail_df.iterrows():
        title = row['title']
        for desc in prop_descriptions:
            if titles_match(desc, title):
                matched_rows.append(row)
                break
                
    if not matched_rows:
        print("No matching subjects found in available subjects for the selected period.")
        return False
        
    matched_df = pd.DataFrame(matched_rows)
    schedule = []
    time_regex = r'(\d{1,2}:\d{2}\s*[AP]M)\s*[-–]\s*(\d{1,2}:\d{2}\s*[AP]M)'
    
    for idx, row in matched_df.iterrows():
        sched_text = str(row['schedule']).strip()
        time_match = re.search(time_regex, sched_text, re.IGNORECASE)
        if not time_match:
            continue
        start_t, end_t = time_match.groups()
        
        time_str = sched_text[time_match.start():time_match.end()]
        time_idx = sched_text.find(time_str)
        day_str = sched_text[time_idx + len(time_str):].strip()
        
        days = split_days(day_str)
        block = get_block_name(row['course_no'])
        
        for day in days:
            schedule.append({
                'code': row['code'],
                'course_no': row['course_no'],
                'block': block,
                'title': row['title'],
                'day': day,
                'start': start_t,
                'end': end_t,
                'room': row['room'] if pd.notna(row['room']) else "",
                'teacher': row['teacher'] if pd.notna(row['teacher']) else "",
                'start_hours': time_to_hours(start_t),
                'end_hours': time_to_hours(end_t)
            })
            
    if not schedule:
        print("No valid schedule slots parsed from matching subjects.")
        return False
        
    df = pd.DataFrame(schedule)
    df = df[~df['block'].str.upper().str.contains("UNKNOWN")]
    
    # Filter by prospectus program prefix to sort out unrelated blocks/courses
    filename = os.path.basename(prospectus_path).lower()
    allowed_prefixes = []
    if "ee_" in filename or "ee." in filename:
        allowed_prefixes = ["EE"]
    elif "it_" in filename or "it." in filename:
        allowed_prefixes = ["BIT", "BCS", "ACT"]
    elif "ce_" in filename or "ce." in filename:
        allowed_prefixes = ["CE"]
    elif "cpe_" in filename or "cpe." in filename:
        allowed_prefixes = ["CpE"]
    elif "me_" in filename or "me." in filename:
        allowed_prefixes = ["ME"]
    elif "arch_" in filename or "arch." in filename:
        allowed_prefixes = ["ARCH"]
    elif "bsid_" in filename or "bsid." in filename:
        allowed_prefixes = ["BSID"]
    else:
        name_part = filename.split('_')[0].split('.')[0].upper()
        if name_part == "IT":
            allowed_prefixes = ["BIT", "BCS", "ACT"]
        elif name_part == "CPE":
            allowed_prefixes = ["CpE"]
        else:
            allowed_prefixes = [name_part]

    if allowed_prefixes:
        df = df[df['block'].apply(lambda b: any(b.upper().startswith(prefix.upper()) for prefix in allowed_prefixes))]
        
    if df.empty:
        print("No valid non-UNKNOWN schedule slots parsed from matching subjects.")
        return False
    blocks = sorted(df['block'].unique())
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Import necessary modules from ics_gen or define locally
    from ics_gen import get_semester_dates, parse_time, find_next_weekday
    from icalendar import Calendar, Event, vRecur
    
    # Use current year for dates (matching the default logic of ics_gen.py)
    sy_start = datetime.datetime.now().year
            
    start_date, end_date = get_semester_dates(sy_start, semester)
    
    day_rrule_map = {
        'M': 'MO',
        'T': 'TU',
        'W': 'WE',
        'TH': 'TH',
        'F': 'FR',
        'S': 'SA'
    }
    
    for block in blocks:
        block_df = df[df['block'] == block]
        cal = Calendar()
        cal.add("prodid", "-//myUNC Scraper//EN")
        cal.add("version", "2.0")
        cal.add("calname", f"OES Block Schedule - {block}")
        
        grouped = block_df.groupby(['code', 'course_no', 'title', 'room', 'teacher', 'start', 'end'])
        
        for (code, course_no, title, room, teacher, start_t_str, end_t_str), group in grouped:
            event_title = f"{title} - {code}"
            description = f"Course: {course_no}\nTeacher: {teacher}"
            
            parsed_time = parse_time(f"{start_t_str}-{end_t_str}")
            if not parsed_time:
                continue
            start_t, end_t = parsed_time
            
            day_codes = [day_rrule_map[d] for d in group['day'].tolist() if d in day_rrule_map]
            if not day_codes:
                continue
                
            first_event_date = min(find_next_weekday(start_date, day_code) for day_code in day_codes)
            
            event = Event()
            event.add("summary", event_title)
            event.add("location", room)
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
            
        safe_filename = f"schedule_block_{block.replace(' ', '_')}.ics"
        full_path = os.path.join(output_dir, safe_filename)
        with open(full_path, "wb") as f:
            f.write(cal.to_ical())
        print(f"Saved block ICS file to '{full_path}'")
        
    return True


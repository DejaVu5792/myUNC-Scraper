import os
import pandas as pd
import json
from block_sched_gen import titles_match, normalize_period_string
from notify import send_notification
from change_detect import get_stored_content, store_content

def track_subjects_for_period(year_level, semester, prospectus_path, avail_path="data/available_subjects.csv"):
    if not os.path.exists(avail_path):
        print(f"Error: {avail_path} does not exist. Please export OES available subjects to CSV first.")
        return False
        
    prop_df = pd.read_csv(prospectus_path)
    avail_df = pd.read_csv(avail_path)
    
    # Filter prospectus for the specified period (normalized to avoid mismatch)
    period_prop = prop_df[
        (prop_df['year level'].apply(normalize_period_string) == normalize_period_string(year_level)) & 
        (prop_df['semester'].apply(normalize_period_string) == normalize_period_string(semester))
    ]
    
    if period_prop.empty:
        print(f"No subjects found in prospectus for {year_level} - {semester}.")
        return False

    required_subjects = period_prop[['subject id', 'subject description']].to_dict('records')
    
    tracker_key = f"tracker_{os.path.basename(prospectus_path)}_{year_level}_{semester}".replace(' ', '_').replace('.csv', '')
    old_available_str = get_stored_content(tracker_key)
    old_available = json.loads(old_available_str) if old_available_str else []
    
    unavailable = []
    available_reqs = []
    available_subjects = []
    newly_available = []
    available_count = 0
    
    print(f"\nTracking subjects for {year_level} - {semester}...")
    
    for req in required_subjects:
        desc = req['subject description']
        subj_id = req['subject id']
        
        # Check if this description matches any title in available subjects
        # Or if the subject id matches the course_no (prefix)
        found = False
        for idx, row in avail_df.iterrows():
            title = row['title']
            course_no = str(row['course_no'])
            if titles_match(desc, title) or course_no.startswith(subj_id):
                found = True
                break
                
        if found:
            available_reqs.append(req)
            available_subjects.append(subj_id)
            if old_available_str is not None and subj_id not in old_available:
                newly_available.append(req)
        else:
            unavailable.append(req)
            
    # Save the new baseline
    store_content(tracker_key, json.dumps(available_subjects))
    
    total_required = len(required_subjects)
    unavailable_count = len(unavailable)
    
    print("\n=== Subject Tracker Report ===")
    print(f"Total required subjects: {total_required}")
    print(f"Available: {len(available_reqs)}")
    print(f"Not yet available: {unavailable_count}")
    
    msg_lines = [
        f"Subject Tracker Report for {os.path.basename(prospectus_path)}",
        f"Period: {year_level} - {semester}",
        f"Total required: {total_required}",
        f"Available: {len(available_reqs)}",
        f"Not yet available: {unavailable_count}"
    ]
    
    if available_reqs:
        print("\nAvailable subjects:")
        msg_lines.append("\nAvailable subjects:")
        for a in available_reqs:
            line = f"~ {a['subject id']}: {a['subject description']}"
            print(line)
            msg_lines.append(line)
    
    if newly_available:
        print("\nNewly available subjects!")
        msg_lines.append("\nNewly available subjects!")
        for u in newly_available:
            line = f"+ {u['subject id']}: {u['subject description']}"
            print(line)
            msg_lines.append(line)

    if unavailable_count > 0:
        print("\nSubjects not yet available:")
        msg_lines.append("\nSubjects not yet available:")
        for u in unavailable:
            line = f"- {u['subject id']}: {u['subject description']}"
            print(line)
            msg_lines.append(line)
            
    report_message = "\n".join(msg_lines)
    
    priority = 3
    if newly_available:
        priority = 5
        title_prefix = "Newly Available Subjects!"
    else:
        title_prefix = "Subject Tracker"
    
    send_notification(
        title=f"{title_prefix}: {unavailable_count} subjects missing",
        message=report_message,
        priority=priority,
        markdown=False
    )
    
    return True

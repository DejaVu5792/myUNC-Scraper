import re
import os
from pathlib import Path
from collections import defaultdict
import pandas as pd
import inquirer
from inquirer.themes import BlueComposure
import block_sched_gen

AVAIL_PATH = "data/available_subjects.csv"
DAY_ORDER = {"M": 0, "T": 1, "W": 2, "TH": 3, "F": 4, "S": 5}
TIME_RE = re.compile(r'(\d{1,2}:\d{2}\s*[AP]M)\s*[-–]\s*(\d{1,2}:\d{2}\s*[AP]M)', re.IGNORECASE)


def safe_str(val):
    if pd.isna(val):
        return ""
    return str(val)


def time_to_minutes(t_str):
    t = pd.to_datetime(t_str.strip(), format="%I:%M%p")
    return t.hour * 60 + t.minute


def parse_schedule_cell(sched_str, entry_row=None):
    m = TIME_RE.search(sched_str)
    if not m:
        return None
    start_str, end_str = m.groups()
    start_min = time_to_minutes(start_str)
    end_min = time_to_minutes(end_str)

    remainder = sched_str[m.end():].strip()
    parts = [p.strip() for p in remainder.split(",")]
    day_str = parts[0] if parts else ""
    days = block_sched_gen.split_days(day_str)

    if entry_row is not None:
        sched_type = safe_str(entry_row.get("type"))
        room = safe_str(entry_row.get("room"))
    else:
        sched_type = parts[1] if len(parts) > 1 else ""
        room = parts[2] if len(parts) > 2 else ""

    return {
        "start_min": start_min,
        "end_min": end_min,
        "start_str": start_str,
        "end_str": end_str,
        "days": days,
        "type": sched_type,
        "room": room,
    }


def select_prospectus_and_period():
    prospectus_dir = Path("prospectus")
    if not prospectus_dir.exists():
        print(f"Directory '{prospectus_dir}' does not exist.")
        return None, None

    csv_files = sorted(list(prospectus_dir.glob("*.csv")))
    if not csv_files:
        print(f"No prospectus CSV files found in '{prospectus_dir}'.")
        return None, None

    choices = [(f"{f.stem.replace('_', ' ').title()} ({f.name})", str(f)) for f in csv_files]
    choices.append(("Back to main menu", None))

    questions = [inquirer.List("prospectus", message="Select prospectus", choices=choices, carousel=True)]
    answers = inquirer.prompt(questions, theme=BlueComposure())
    if not answers or answers.get("prospectus") is None:
        return None, None

    selected_prospectus = answers["prospectus"]
    periods = block_sched_gen.get_prospectus_periods(selected_prospectus)
    if not periods:
        print("Could not read prospectus periods.")
        return None, None

    period_choices = [(f"{yr} - {sem}", (yr, sem)) for yr, sem in periods]
    period_choices.append(("Back to main menu", None))

    questions_period = [inquirer.List("period", message=f"Select period from {Path(selected_prospectus).name}", choices=period_choices, carousel=True)]
    answers_period = inquirer.prompt(questions_period, theme=BlueComposure())
    if not answers_period or answers_period.get("period") is None:
        return None, None

    return selected_prospectus, answers_period["period"]


def load_available_subjects(path=None):
    path = path or AVAIL_PATH
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def get_matching_subjects(prospectus_path, year_level, semester):
    prop_df = pd.read_csv(prospectus_path)
    avail_df = load_available_subjects()

    period_prop = prop_df[
        (prop_df["year level"].apply(block_sched_gen.normalize_year) == block_sched_gen.normalize_year(year_level))
        & (prop_df["semester"].apply(block_sched_gen.normalize_semester) == block_sched_gen.normalize_semester(semester))
    ]
    prop_descriptions = period_prop["subject description"].tolist()

    matched_rows = []
    for _, row in avail_df.iterrows():
        title = row["title"]
        for desc in prop_descriptions:
            if block_sched_gen.titles_match(desc, title):
                matched_rows.append(row)
                break

    if not matched_rows:
        return []

    matched_df = pd.DataFrame(matched_rows)
    summaries = []
    grouped = matched_df.groupby("course_no")
    for course_no, group in grouped:
        row = group.iloc[0]

        time_groups = defaultdict(list)
        for _, e in group.iterrows():
            sched_str = str(e["schedule"]).strip()
            parsed = parse_schedule_cell(sched_str, e)
            if parsed:
                key = (parsed["start_str"], parsed["end_str"])
                if key not in time_groups:
                    time_groups[key] = {"start": parsed["start_str"], "end": parsed["end_str"], "days": []}
                time_groups[key]["days"].extend(parsed["days"])

        sched_rows = []
        for v in time_groups.values():
            sorted_days = sorted(set(v["days"]), key=lambda d: DAY_ORDER.get(d, 99))
            day_str = "".join(sorted_days)
            sched_rows.append({"time": f"{v['start']}-{v['end']}", "days": day_str})

        sched_rows.sort(key=lambda x: time_to_minutes(x["time"].split("-")[0]))

        summaries.append({
            "course_no": course_no,
            "code": str(row["code"]),
            "title": row["title"],
            "unit": row["unit"],
            "tally": row["tally"],
            "entries": group,
            "sched_rows": sched_rows,
        })
    summaries.sort(key=lambda s: (s["title"], s["course_no"]))
    return summaries


def get_entry_details(entry):
    sched_str = str(entry["schedule"]).strip()
    parsed = parse_schedule_cell(sched_str, entry)
    teacher = entry["teacher"] if pd.notna(entry["teacher"]) else "(No teacher assigned)"
    return parsed, teacher


def display_subject_detail(summary):
    entries = summary["entries"]
    print("\n" + "━" * 70)
    print(f" {summary['course_no']} - {summary['title']}")
    print("━" * 70)

    for _, entry in entries.iterrows():
        parsed, teacher = get_entry_details(entry)
        if parsed:
            day_str = "".join(parsed["days"])
            line = f"  {teacher} - {day_str} {parsed['start_str']}-{parsed['end_str']}"
            if parsed["type"]:
                line += f" [{parsed['type']}]"
            if parsed["room"]:
                line += f" {parsed['room']}"
            print(line)

    print()
    print(f"  Course No: {summary['course_no']}  |  Code: {summary['code']}")
    print(f"  Tally: {summary['tally']}")
    print("\n" + "━" * 70)
    input("\nPress Enter to go back...")


def render_subject_table(summaries):
    col_defs = [
        ("num", " #", ">"),
        ("course_no", " Course No", "<"),
        ("code", " Code", "<"),
        ("title", " Title", "<"),
        ("tally", " Tally", ">"),
        ("schedule", " Schedule", "<"),
    ]
    rows_data = []
    for idx, s in enumerate(summaries, 1):
        max_rows = max(len(s["sched_rows"]), 1)
        for ri in range(max_rows):
            vals = {}
            if ri == 0:
                vals["num"] = str(idx)
                vals["course_no"] = s["course_no"]
                vals["code"] = s["code"]
                vals["title"] = s["title"]
                vals["tally"] = s["tally"]
            else:
                vals["num"] = ""
                vals["course_no"] = ""
                vals["code"] = ""
                vals["title"] = ""
                vals["tally"] = ""

            if ri < len(s["sched_rows"]):
                sr = s["sched_rows"][ri]
                vals["schedule"] = f"{sr['time']} {sr['days']}"
            else:
                vals["schedule"] = ""
            rows_data.append(vals)

    widths = []
    for key, header, _ in col_defs:
        max_len = len(header)
        for rd in rows_data:
            max_len = max(max_len, len(rd[key]))
        widths.append(max_len + 2)

    term_width = 120
    fixed = sum(widths[:-1]) + len(col_defs) + 1
    sched_max = term_width - fixed
    if widths[-1] > sched_max:
        widths[-1] = sched_max
    if widths[-1] < 12:
        widths[-1] = 12

    def sep_line(left, mid, right, hor="─"):
        parts = []
        for w in widths:
            parts.append(hor * w)
        return left + mid.join(parts) + right

    lines = []
    lines.append(sep_line("┌", "┬", "┐"))
    hdr = ""
    for i, (key, header, align) in enumerate(col_defs):
        w = widths[i]
        if align == "<":
            hdr += f"│ {header:<{w-1}}"
        else:
            hdr += f"│{header:>{w-1}} "
    lines.append(hdr + "│")
    lines.append(sep_line("├", "┼", "┤"))

    prev_title = summaries[0]["title"]
    si = 0
    for ri, vals in enumerate(rows_data):
        row = ""
        for i, (key, _, align) in enumerate(col_defs):
            w = widths[i]
            val = vals[key]
            if len(val) > w - 2:
                val = val[: w - 5] + "..."
            if align == "<":
                row += f"│ {val:<{w-1}}"
            else:
                row += f"│{val:>{w-1}} "
        lines.append(row + "│")
        if ri < len(rows_data) - 1:
            next_vals = rows_data[ri + 1]
            if next_vals["num"] != "":
                nxt_title = summaries[si + 1]["title"]
                if nxt_title != prev_title:
                    lines.append(sep_line("╠", "╬", "╣", "═"))
                else:
                    lines.append(sep_line("├", "┼", "┤"))
                prev_title = nxt_title
                si += 1

    lines.append(sep_line("└", "┴", "┘"))
    return "\n".join(lines)


def interactive_viewer():
    prospectus_path, period = select_prospectus_and_period()
    if not prospectus_path or not period:
        return

    year_level, semester = period
    summaries = get_matching_subjects(prospectus_path, year_level, semester)
    if not summaries:
        print(f"No matching subjects found in available subjects for {year_level} - {semester}.")
        input("\nPress Enter to continue...")
        return

    while True:
        print()
        print(f"  {Path(prospectus_path).stem} — {year_level} — {semester}")
        table = render_subject_table(summaries)
        print(table)
        print()

        try:
            inp = input("  Enter number to view subject (0 = back): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not inp or inp == "0":
            break

        try:
            idx = int(inp) - 1
            if 0 <= idx < len(summaries):
                display_subject_detail(summaries[idx])
            else:
                print("  Invalid number.")
        except ValueError:
            print("  Enter a number.")

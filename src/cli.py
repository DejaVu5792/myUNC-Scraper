#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""CLI entry point for myUNC Scraper."""

import argparse
import argcomplete
from argcomplete.completers import ChoicesCompleter
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper import (
    scrape_schedule,
    scrape_transcript,
    scrape_evaluation,
)
from oes_scraper import (
    scrape_oes_enrolled_schedule,
    scrape_oes_available_subjects,
    export_available_subjects_to_csv,
)
from ics_gen import generate_ics
from change_detect import (
    is_first_run,
    has_changed,
    commit_update,
    generate_diff,
    generate_diff_grades,
)
from notify import send_notification
import block_sched_gen
from subject_tracker import track_subjects_for_period
import inquirer
from inquirer.themes import BlueComposure


def check_transcript(force: bool = False):
    print("Scraping Transcript of Grades...")
    html = scrape_transcript()
    if is_first_run("transcript_grades"):
        print("First run - storing baseline for Transcript of Grades.")
        generate_diff_grades("transcript_grades", html)  # stores baseline
        return
    changed, diff = generate_diff_grades("transcript_grades", html)
    if changed or force:
        print(
            "Change detected in Transcript of Grades!"
            if changed
            else "Force: simulating change."
        )
        print(f"Diff preview: {diff[:200]}...")
        send_notification(
            title="Transcript of Grades Updated",
            message=diff[:2000],
            markdown=True,
        )
        if not force:
            generate_diff_grades("transcript_grades", html)  # update baseline
    else:
        print("No changes detected in Transcript of Grades.")


def check_evaluation(force: bool = False):
    print("Scraping Student Evaluation (all year levels)...")
    results = scrape_evaluation()
    for level, html in results.items():
        key = f"evaluation_{level.lower().replace(' ', '_')}"
        label = f"Student Evaluation - {level}"
        print(f"\n  [{level}]")
        if is_first_run(key):
            print(f"    First run - storing baseline.")
            commit_update(key, html)
            continue
        if has_changed(key, html) or force:
            print(
                f"    Change detected!"
                if has_changed(key, html)
                else "    Force: simulating change."
            )
            diff = generate_diff(key, html)
            print(f"    Diff length: {len(diff)} chars")
            send_notification(
                title=f"{label} Updated",
                message=f"A change was detected in {label}.\n\nDiff preview:\n{diff[:1000]}",
            )
            if not force:
                commit_update(key, html)
        else:
            print(f"    No changes detected.")


def generate_schedule():
    print("Scraping Schedule...")
    html = scrape_schedule()
    path = generate_ics(html)
    if path:
        print(f"Done. Schedule saved to: {path}")
    else:
        print("Could not generate schedule ICS.")


def generate_oes_schedule():
    print("Scraping OES Enrolled Subjects...")
    html = scrape_oes_enrolled_schedule()
    path = generate_ics(html, "data/oes_schedule.ics")
    if path:
        print(f"Done. OES Schedule saved to: {path}")
    else:
        print("Could not generate OES schedule ICS.")


def generate_oes_available_subjects(departments: list[str] = None):
    print("Scraping OES Available Subjects (A-Z)...")
    subjects = scrape_oes_available_subjects(departments=departments)
    path = export_available_subjects_to_csv(subjects)
    if path:
        print(f"Done. Saved to: {path}")
    else:
        print("Could not export available subjects.")


def select_printout_file() -> str:
    """Helper to select a printout PDF or TXT file from data/ or enter a path."""
    import os
    data_dir = Path("data")
    files = []
    if data_dir.exists():
        files = sorted(list(data_dir.glob("*.pdf")) + list(data_dir.glob("*.txt")))
        
    choices = [(f"{f.name}", str(f)) for f in files]
    choices.append(("Enter custom path...", "custom"))
    choices.append(("Back to main menu", None))
    
    questions = [
        inquirer.List(
            "file",
            message="Select printout file",
            choices=choices,
            carousel=True,
        )
    ]
    try:
        answers = inquirer.prompt(questions, theme=BlueComposure())
        if not answers or answers.get("file") is None:
            return None
            
        selected = answers["file"]
        if selected == "custom":
            questions_custom = [
                inquirer.Text(
                    "path",
                    message="Enter path to printout file (PDF or TXT)",
                    validate=lambda _, x: os.path.exists(x) or "File does not exist!"
                )
            ]
            answers_custom = inquirer.prompt(questions_custom, theme=BlueComposure())
            if answers_custom:
                return answers_custom["path"]
            return None
        return selected
    except Exception as e:
        print(f"Error selecting printout file: {e}")
        return None


def generate_schedule_from_printout(file_path: str = None):
    print("Generating Schedule from Printout...")
    import re
    if not file_path:
        file_path = select_printout_file()
        if not file_path:
            return
            
    try:
        from printout_parser import parse_printout, generate_png_schedule, generate_ics_schedule
        parsed = parse_printout(file_path)
        
        name_clean = "schedule"
        if parsed.get("metadata") and parsed["metadata"].get("name"):
            raw_name = parsed["metadata"]["name"]
            raw_name = re.sub(r"\[.*?\]", "", raw_name)
            name_clean = "".join(c if c.isalnum() or c in " _-" else "" for c in raw_name).strip().replace(" ", "_")
            if not name_clean:
                name_clean = "schedule"
        
        png_path = f"data/{name_clean}.png"
        ics_path = f"data/{name_clean}.ics"
        
        png_res = generate_png_schedule(parsed, png_path)
        ics_res = generate_ics_schedule(parsed, ics_path)
        
        if png_res:
            print(f"Done. Schedule PNG saved to: {png_res}")
        else:
            print("Could not generate PNG schedule.")
            
        if ics_res:
            print(f"Done. Schedule ICS saved to: {ics_res}")
        else:
            print("Could not generate ICS schedule.")
            
    except Exception as e:
        print(f"Error generating schedule from printout: {e}")
        raise e


def select_prospectus_and_period() -> tuple[str, tuple[str, str]]:
    """Helper to select a prospectus file and a period.
    Returns (prospectus_path, (year_level, semester)) or (None, None).
    """
    prospectus_dir = Path("prospectus")
    if not prospectus_dir.exists():
        print(f"Error: Directory '{prospectus_dir}' does not exist.")
        return None, None
        
    csv_files = sorted(list(prospectus_dir.glob("*.csv")))
    if not csv_files:
        print(f"Error: No prospectus CSV files found in '{prospectus_dir}'.")
        return None, None
        
    choices = [(f"{f.stem.replace('_', ' ').title()} ({f.name})", str(f)) for f in csv_files]
    choices.append(("Back to main menu", None))
    
    questions = [
        inquirer.List(
            "prospectus",
            message="Select prospectus",
            choices=choices,
            carousel=True,
        )
    ]
    try:
        answers = inquirer.prompt(questions, theme=BlueComposure())
        if not answers or answers.get("prospectus") is None:
            return None, None
            
        selected_prospectus = answers["prospectus"]
        periods = block_sched_gen.get_prospectus_periods(selected_prospectus)
        if not periods:
            print(f"Error: Could not read prospectus periods from '{selected_prospectus}'.")
            return None, None
            
        period_choices = [(f"{yr} - {sem}", (yr, sem)) for yr, sem in periods]
        period_choices.append(("Back to main menu", None))
        
        questions_period = [
            inquirer.List(
                "period",
                message=f"Select period from {Path(selected_prospectus).name}",
                choices=period_choices,
                carousel=True,
            )
        ]
        answers_period = inquirer.prompt(questions_period, theme=BlueComposure())
        if not answers_period or answers_period.get("period") is None:
            return None, None
            
        return selected_prospectus, answers_period["period"]
    except Exception as e:
        print(f"Error selecting prospectus/period: {e}")
        return None, None


def generate_oes_block_schedules(prospectus_path: str = None, year_level: str = None, semester: str = None):
    print("Generating OES Block Schedules...")
    if not prospectus_path or not year_level or not semester:
        prospectus_path, period = select_prospectus_and_period()
        if not prospectus_path or not period:
            return
        year_level, semester = period
        
    try:
        success = block_sched_gen.generate_schedules_for_period(year_level, semester, prospectus_path, "data/available_subjects.csv")
        if success:
            print(f"Done. Schedules generated in 'data/BlockSchedules/' folder.")
        else:
            print("Could not generate block schedules.")
    except Exception as e:
        print(f"Error: {e}")


def generate_oes_block_schedules_ics(prospectus_path: str = None, year_level: str = None, semester: str = None):
    print("Generating OES Block Schedules (ICS)...")
    if not prospectus_path or not year_level or not semester:
        prospectus_path, period = select_prospectus_and_period()
        if not prospectus_path or not period:
            return
        year_level, semester = period
        
    try:
        success = block_sched_gen.generate_ics_schedules_for_period(year_level, semester, prospectus_path, "data/available_subjects.csv")
        if success:
            print(f"Done. ICS schedules generated in 'data/BlockSchedules/' folder.")
        else:
            print("Could not generate block schedules ICS.")
    except Exception as e:
        print(f"Error: {e}")

def run_subject_tracker(prospectus_path: str = None, year_level: str = None, semester: str = None):
    print("Running Subject Tracker...")
    if not prospectus_path or not year_level or not semester:
        prospectus_path, period = select_prospectus_and_period()
        if not prospectus_path or not period:
            return
        year_level, semester = period
        
    try:
        success = track_subjects_for_period(year_level, semester, prospectus_path, "data/available_subjects.csv")
        if success:
            print(f"Done. Subject tracking report generated.")
        else:
            print("Could not run subject tracker.")
    except Exception as e:
        print(f"Error: {e}")


def scrape_all(force: bool = False, departments: list[str] = None):

    generate_schedule()
    check_transcript(force=force)
    check_evaluation(force=force)
    generate_oes_schedule()
    generate_oes_available_subjects(departments=departments)


def notify_error(task_name: str, error: Exception) -> None:
    """Send error notification."""
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    error_msg = "".join(tb)
    send_notification(
        title=f"UNC Scraper Error - {task_name}",
        message=f"Error in {task_name}:\n{type(error).__name__}: {error}\n\n{error_msg[:1500]}",
    )
# The user wants to scrape multiple tasks selectively using a checkbox prompt.
def scrape_multiple():
    questions = [
        inquirer.Checkbox(
            "tasks",
            message="Select scrapers to run (Space to toggle, Enter to run, Esc/Empty to go back)",
            choices=[
                ("Check myUNC Transcript of Grades", "2"),
                ("Check myUNC Student Evaluation", "3"),
                ("Export OES Available Subjects (CSV)", "6"),
            ],
            carousel=True,
        )
    ]
    try:
        answers = inquirer.prompt(questions, theme=BlueComposure())
        if not answers:
            return  # Escape key pressed
            
        selected = answers.get("tasks", [])
        if not selected:
            return  # Nothing selected, go back cleanly
        actions = {
            "1": (generate_schedule, "Generate myUNC Schedule (ICS)"),
            "2": (check_transcript, "Check myUNC Transcript of Grades"),
            "3": (check_evaluation, "Check myUNC Student Evaluation"),
            "5": (generate_oes_schedule, "Generate OES Enrolled Premat Schedule (ICS)"),
            "6": (generate_oes_available_subjects, "Export OES Available Subjects (CSV)"),
            "7": (generate_oes_block_schedules, "Generate OES Block Schedules (PNG)"),
            "10": (run_subject_tracker, "Run Subject Tracker"),
        }
        
        for task_id in selected:
            action, title = actions[task_id]
            print("\n" + "═" * 50)
            print(f" ▶ Running: {title}")
            print("═" * 50)
            try:
                action()
            except Exception as sub_err:
                print(f" ✘ Sub-task '{title}' failed: {sub_err}")
    except Exception as e:
        print(f"Error: {e}")


# The user wants log outputs encased in a styled box.

def execute_with_ui(action, title):
    import os
    print("\n" + "┏" + "━" * 68 + "┓")
    print(f"┃ {title.ljust(66)} ┃")
    print("┗" + "━" * 68 + "┛\n")
    
    try:
        action()
        print("\n" + "━" * 70)
        print(" ✔ Task finished successfully.")
    except Exception as e:
        print("\n" + "━" * 70)
        print(f" ✘ Task failed with error: {e}")
        raise e
    finally:
        print("━" * 70)
        input("\nPress Enter to return to main menu...")
        print("\n" * 2) # Spacer instead of screen clear



def prospectus_completer(prefix, **kwargs):
    prospectus_dir = Path("prospectus")
    if prospectus_dir.exists():
        return [str(p) for p in prospectus_dir.glob("*.csv") if str(p).startswith(prefix)]
    return []

def depts_completer(prefix, **kwargs):
    depts = ["SCIS", "CAS", "CEA", "CBA", "COED", "CON", "CCJE", "NSTP"]
    if not prefix:
        return depts
    parts = prefix.split(",")
    base = ",".join(parts[:-1])
    if base:
        base += ","
    current_word = parts[-1]
    
    matches = [base + d for d in depts if d.lower().startswith(current_word.lower())]
    return matches

LAST_CHOICE_FILE = Path(__file__).parent.parent / "data" / "update_checks" / "last_choice.txt"

def get_last_choice() -> str:
    try:
        if LAST_CHOICE_FILE.exists():
            return LAST_CHOICE_FILE.read_text().strip()
    except Exception:
        pass
    return "2"

def save_last_choice(choice: str) -> None:
    try:
        LAST_CHOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_CHOICE_FILE.write_text(choice)
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(description="myUNC Scraper")
    parser.add_argument(
        "-s", "--schedule", action="store_true", help="Generate Schedule ICS"
    )
    parser.add_argument(
        "-t",
        "--transcript",
        action="store_true",
        help="Check Transcript of Grades (notify on change)",
    )
    parser.add_argument(
        "-e",
        "--evaluation",
        action="store_true",
        help="Check Student Evaluation (notify on change)",
    )
    parser.add_argument("-a", "--all", action="store_true", help="Run all scrapers")
    parser.add_argument("--oes-schedule", action="store_true", help="Generate OES Enrolled Schedule ICS")
    parser.add_argument("--oes-available", action="store_true", help="Export OES Available Subjects to CSV")
    parser.add_argument(
        "--depts",
        type=str,
        help="Comma-separated list of departments to scan (e.g., SCIS,CAS) when using --oes-available"
    ).completer = depts_completer
    parser.add_argument("--oes-block-sched", action="store_true", help="Generate OES Block Schedules (from CSV & Prospectus)")
    parser.add_argument("--oes-block-sched-ics", action="store_true", help="Generate OES Block Schedules as ICS (from CSV & Prospectus)")
    parser.add_argument("--track-subjects", action="store_true", help="Run Subject Tracker")
    parser.add_argument(
        "--printout",
        type=str,
        help="Path to Certificate of Matriculation printout (PDF or TXT) to generate PNG/ICS schedule"
    )
    parser.add_argument(
        "--prospectus",
        type=str,
        help="Path to prospectus CSV file (e.g., prospectus/it_prospectus.csv) to use with block schedule generation"
    ).completer = prospectus_completer
    parser.add_argument(
        "--year-level",
        type=str,
        help="Year level for block schedule generation (e.g., 'First Year' or '1st Year')"
    ).completer = ChoicesCompleter(["First Year", "Second Year", "Third Year", "Fourth Year", "Fifth Year", "1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"])
    parser.add_argument(
        "--semester",
        type=str,
        help="Semester for block schedule generation (e.g., 'First Semester' or '1st Semester')"
    ).completer = ChoicesCompleter(["First Semester", "Second Semester", "Summer", "1st Semester", "2nd Semester"])

    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run browser in headful (headed) mode"
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force notification (simulate change detected)",
    )
    parser.add_argument(
        "-mu",
        "--myunc-username",
        type=str,
        help="myUNC Username override"
    )
    parser.add_argument(
        "-mp",
        "--myunc-password",
        type=str,
        help="myUNC Password override"
    )
    parser.add_argument(
        "-ou",
        "--oes-username",
        type=str,
        help="OES Email/Username override"
    )
    parser.add_argument(
        "-op",
        "--oes-password",
        type=str,
        help="OES Password override"
    )
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if args.headful:
        os.environ["HEADLESS"] = "false"

    if args.myunc_username:
        os.environ["UNC_USERNAME"] = args.myunc_username
    if args.myunc_password:
        os.environ["UNC_PASSWORD"] = args.myunc_password
    if args.oes_username:
        os.environ["UNC_OES_EMAIL"] = args.oes_username
    if args.oes_password:
        os.environ["UNC_OES_PASSWORD"] = args.oes_password

    # If no flags provided, run interactive menu
    if not any([args.schedule, args.transcript, args.evaluation, args.all, args.oes_schedule, args.oes_available, args.oes_block_sched, args.oes_block_sched_ics, args.track_subjects, args.printout]):
        if "HEADLESS" not in os.environ:
            os.environ["HEADLESS"] = "false"  # Default to headful in TUI

        default_choice = get_last_choice()
        valid_choices = ["1", "2", "3", "4", "5", "6", "7", "9", "10", "11", "8", "toggle_headful"]
        if default_choice not in valid_choices:
            default_choice = "2"

        while True:
            questions = [
                inquirer.List(
                    "choice",
                    message="=== myUNC Scraper ===",
                    choices=[
                        ("[X] Headful Mode" if os.environ.get("HEADLESS") == "false" else "[ ] Headful Mode", "toggle_headful"),
                        ("Check myUNC Transcript of Grades (notify on change)", "2"),
                        ("Check myUNC Student Evaluation (notify on change)", "3"),
                        ("Export OES Available Subjects (CSV)", "6"),
                        ("Generate myUNC Schedule (ICS)", "1"),
                        ("Generate OES Enrolled Premat Schedule (ICS)", "5"),
                        ("Generate OES Block Schedules (PNG)", "7"),
                        ("Generate OES Block Schedules (ICS)", "9"),
                        ("Generate PNG/ICS Schedule from Printout", "11"),
                        ("Run Subject Tracker", "10"),
                        ("Scrape Multiple", "4"),
                        ("Exit", "8"),
                    ],
                    default=default_choice,
                    carousel=True,
                )
            ]
            try:
                answers = inquirer.prompt(questions, theme=BlueComposure())
                if not answers:
                    break
                choice = answers.get("choice")
                if choice == "8":
                    print("Bye.")
                    break
                if choice == "toggle_headful":
                    current_headless = os.environ.get("HEADLESS", "false")
                    os.environ["HEADLESS"] = "true" if current_headless == "false" else "false"
                    default_choice = "toggle_headful"
                    continue

                default_choice = choice
                save_last_choice(choice)

                actions = {
                    "1": (generate_schedule, "Generate myUNC Schedule (ICS)"),
                    "2": (check_transcript, "Check myUNC Transcript of Grades"),
                    "3": (check_evaluation, "Check myUNC Student Evaluation"),
                    "4": (scrape_multiple, "Scrape Multiple"),
                    "5": (generate_oes_schedule, "Generate OES Enrolled Premat Schedule (ICS)"),
                    "6": (generate_oes_available_subjects, "Export OES Available Subjects (CSV)"),
                    "7": (generate_oes_block_schedules, "Generate OES Block Schedules (PNG)"),
                    "9": (generate_oes_block_schedules_ics, "Generate OES Block Schedules (ICS)"),
                    "10": (run_subject_tracker, "Run Subject Tracker"),
                    "11": (generate_schedule_from_printout, "Generate PNG/ICS Schedule from Printout"),
                }

                action_info = actions.get(choice)

                if action_info is None:
                    print("Invalid option.")
                    continue

                action, title = action_info
                execute_with_ui(action, title)
            except KeyboardInterrupt:
                print("\nBye.")
                break
            except Exception as e:
                notify_error(choice, e)
                print(f"Error: {e}")
        return

    # Run selected options
    depts_list = None
    if args.depts:
        depts_list = [d.strip() for d in args.depts.split(",") if d.strip()]

    if args.all:
        try:
            scrape_all(force=args.force, departments=depts_list)
        except Exception as e:
            notify_error("scrape_all", e)
            raise
    else:
        if args.schedule:
            try:
                generate_schedule()
            except Exception as e:
                notify_error("schedule", e)
                raise
        if args.transcript:
            try:
                check_transcript(force=args.force)
            except Exception as e:
                notify_error("transcript", e)
                raise
        if args.evaluation:
            try:
                check_evaluation(force=args.force)
            except Exception as e:
                notify_error("evaluation", e)
                raise
        if args.oes_schedule:
            try:
                generate_oes_schedule()
            except Exception as e:
                notify_error("oes_schedule", e)
                raise
        if args.oes_available:
            try:
                generate_oes_available_subjects(departments=depts_list)
            except Exception as e:
                notify_error("oes_available", e)
                raise
        if args.oes_block_sched:
            try:
                generate_oes_block_schedules(
                    prospectus_path=args.prospectus,
                    year_level=args.year_level,
                    semester=args.semester
                )
            except Exception as e:
                notify_error("oes_block_sched", e)
                raise
        if args.oes_block_sched_ics:
            try:
                generate_oes_block_schedules_ics(
                    prospectus_path=args.prospectus,
                    year_level=args.year_level,
                    semester=args.semester
                )
            except Exception as e:
                notify_error("oes_block_sched-ics", e)
                raise
        if args.track_subjects:
            try:
                run_subject_tracker(
                    prospectus_path=args.prospectus,
                    year_level=args.year_level,
                    semester=args.semester
                )
            except Exception as e:
                notify_error("track_subjects", e)
                raise
        if args.printout:
            try:
                generate_schedule_from_printout(
                    file_path=args.printout
                )
            except Exception as e:
                notify_error("printout_schedule", e)
                raise



if __name__ == "__main__":
    main()

"""CLI entry point for myUNC Scraper."""

import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

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
    path = generate_ics(html, "oes_schedule.ics")
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
    )
    parser.add_argument("--oes-block-sched", action="store_true", help="Generate OES Block Schedules (from CSV & Prospectus)")
    parser.add_argument("--oes-block-sched-ics", action="store_true", help="Generate OES Block Schedules as ICS (from CSV & Prospectus)")
    parser.add_argument(
        "--prospectus",
        type=str,
        help="Path to prospectus CSV file (e.g., prospectus/it_prospectus.csv) to use with block schedule generation"
    )
    parser.add_argument(
        "--year-level",
        type=str,
        help="Year level for block schedule generation (e.g., 'First Year')"
    )
    parser.add_argument(
        "--semester",
        type=str,
        help="Semester for block schedule generation (e.g., 'First Semester')"
    )

    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force notification (simulate change detected)",
    )
    args = parser.parse_args()

    # If no flags provided, run interactive menu
    if not any([args.schedule, args.transcript, args.evaluation, args.all, args.oes_schedule, args.oes_available, args.oes_block_sched, args.oes_block_sched_ics]):

        while True:
            questions = [
                inquirer.List(
                    "choice",
                    message="=== myUNC Scraper ===",
                    choices=[
                        ("Check myUNC Transcript of Grades (notify on change)", "2"),
                        ("Check myUNC Student Evaluation (notify on change)", "3"),
                        ("Export OES Available Subjects (CSV)", "6"),
                        ("Generate myUNC Schedule (ICS)", "1"),
                        ("Generate OES Enrolled Premat Schedule (ICS)", "5"),
                        ("Generate OES Block Schedules (PNG)", "7"),
                        ("Generate OES Block Schedules (ICS)", "9"),
                        ("Scrape Multiple", "4"),
                        ("Exit", "8"),
                    ],
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

                actions = {
                    "1": (generate_schedule, "Generate myUNC Schedule (ICS)"),
                    "2": (check_transcript, "Check myUNC Transcript of Grades"),
                    "3": (check_evaluation, "Check myUNC Student Evaluation"),
                    "4": (scrape_multiple, "Scrape Multiple"),
                    "5": (generate_oes_schedule, "Generate OES Enrolled Premat Schedule (ICS)"),
                    "6": (generate_oes_available_subjects, "Export OES Available Subjects (CSV)"),
                    "7": (generate_oes_block_schedules, "Generate OES Block Schedules (PNG)"),
                    "9": (generate_oes_block_schedules_ics, "Generate OES Block Schedules (ICS)"),
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



if __name__ == "__main__":
    main()

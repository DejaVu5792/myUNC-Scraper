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


def generate_oes_available_subjects():
    print("Scraping OES Available Subjects (A-Z)...")
    subjects = scrape_oes_available_subjects()
    path = export_available_subjects_to_csv(subjects)
    if path:
        print(f"Done. Saved to: {path}")
    else:
        print("Could not export available subjects.")


def generate_oes_block_schedules():
    print("Generating OES Block Schedules...")
    periods = block_sched_gen.get_prospectus_periods("it_prospectus.csv")
    if not periods:
        print("Error: Could not read prospectus periods. Make sure it_prospectus.csv is available.")
        return
        
    choices = [(f"{yr} - {sem}", (yr, sem)) for yr, sem in periods]
    choices.append(("Back to main menu", None))
    
    questions = [
        inquirer.List(
            "period",
            message="Select prospectus period",
            choices=choices,
        )
    ]
    try:
        answers = inquirer.prompt(questions, theme=BlueComposure())
        if not answers or answers.get("period") is None:
            return
            
        yr, sem = answers["period"]
        success = block_sched_gen.generate_schedules_for_period(yr, sem, "it_prospectus.csv", "available_subjects.csv")
        if success:
            print(f"Done. Schedules generated in 'output/' folder.")
        else:
            print("Could not generate block schedules.")
    except Exception as e:
        print(f"Error: {e}")


def scrape_all(force: bool = False):
    generate_schedule()
    check_transcript(force=force)
    check_evaluation(force=force)
    generate_oes_schedule()
    generate_oes_available_subjects()


def notify_error(task_name: str, error: Exception) -> None:
    """Send error notification."""
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    error_msg = "".join(tb)
    send_notification(
        title=f"UNC Scraper Error - {task_name}",
        message=f"Error in {task_name}:\n{type(error).__name__}: {error}\n\n{error_msg[:1500]}",
    )


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
    parser.add_argument("--oes-block-sched", action="store_true", help="Generate OES Block Schedules (from CSV & Prospectus)")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force notification (simulate change detected)",
    )
    args = parser.parse_args()

    # If no flags provided, run interactive menu
    if not any([args.schedule, args.transcript, args.evaluation, args.all, args.oes_schedule, args.oes_available, args.oes_block_sched]):
        while True:
            questions = [
                inquirer.List(
                    "choice",
                    message="=== myUNC Scraper ===",
                    choices=[
                        ("Check myUNC Transcript of Grades (notify on change)", "2"),
                        ("Check myUNC Student Evaluation (notify on change)", "3"),
                        ("Export OES Available SCIS Subjects (CSV)", "6"),
                        ("Generate myUNC Schedule (ICS)", "1"),
                        ("Generate OES Enrolled Premat Schedule (ICS)", "5"),
                        ("Generate OES Block Schedules (PNG)", "7"),
                        ("Scrape All", "4"),
                        ("Exit", "8"),
                    ],
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
                    "1": generate_schedule,
                    "2": check_transcript,
                    "3": check_evaluation,
                    "4": scrape_all,
                    "5": generate_oes_schedule,
                    "6": generate_oes_available_subjects,
                    "7": generate_oes_block_schedules,
                }
                action = actions.get(choice)
                if action is None:
                    print("Invalid option.")
                    continue

                action()
            except KeyboardInterrupt:
                print("\nBye.")
                break
            except Exception as e:
                notify_error(choice, e)
                print(f"Error: {e}")
        return

    # Run selected options
    if args.all:
        try:
            scrape_all(force=args.force)
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
                generate_oes_available_subjects()
            except Exception as e:
                notify_error("oes_available", e)
                raise
        if args.oes_block_sched:
            try:
                generate_oes_block_schedules()
            except Exception as e:
                notify_error("oes_block_sched", e)
                raise


if __name__ == "__main__":
    main()

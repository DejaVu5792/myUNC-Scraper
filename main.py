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


def scrape_all(force: bool = False):
    generate_schedule()
    check_transcript(force=force)
    check_evaluation(force=force)


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
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force notification (simulate change detected)",
    )
    args = parser.parse_args()

    # If no flags provided, run interactive menu
    if not any([args.schedule, args.transcript, args.evaluation, args.all, args.oes_schedule, args.oes_available]):
        while True:
            print("\n=== myUNC Scraper ===")
            print("  1) Generate Schedule ICS")
            print("  2) Check Transcript of Grades (notify on change)")
            print("  3) Check Student Evaluation (notify on change)")
            print("  4) Scrape All")
            print("  5) Generate OES Enrolled Schedule ICS")
            print("  6) Export OES Available Subjects to CSV")
            print("  7) Exit")
            choice = input("\nSelect option: ").strip()

            if choice == "7":
                print("Bye.")
                break

            actions = {
                "1": generate_schedule,
                "2": check_transcript,
                "3": check_evaluation,
                "4": scrape_all,
                "5": generate_oes_schedule,
                "6": generate_oes_available_subjects,
            }
            action = actions.get(choice)
            if action is None:
                print("Invalid option.")
                continue

            try:
                action()
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


if __name__ == "__main__":
    main()

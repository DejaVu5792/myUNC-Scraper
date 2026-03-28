"""CLI entry point for myUNC Scraper."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from scraper import scrape_schedule, scrape_transcript, scrape_evaluation
from ics_gen import generate_ics
from change_detect import has_changed, generate_diff, commit_update, is_first_run
from ntfy_notify import send_notification


def check_transcript():
    print("Scraping Transcript of Grades...")
    html = scrape_transcript()
    if is_first_run("transcript"):
        print("First run - storing baseline for Transcript of Grades.")
        commit_update("transcript", html)
        return
    if has_changed("transcript", html):
        print("Change detected in Transcript of Grades!")
        diff = generate_diff("transcript", html)
        print(f"Diff length: {len(diff)} chars")
        send_notification(
            title="Transcript of Grades Updated",
            message=f"A change was detected in your Transcript of Grades.\n\nDiff preview:\n{diff[:1000]}",
            priority="high",
        )
        commit_update("transcript", html)
    else:
        print("No changes detected in Transcript of Grades.")


def check_evaluation():
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
        if has_changed(key, html):
            print(f"    Change detected!")
            diff = generate_diff(key, html)
            print(f"    Diff length: {len(diff)} chars")
            send_notification(
                title=f"{label} Updated",
                message=f"A change was detected in {label}.\n\nDiff preview:\n{diff[:1000]}",
                priority="high",
            )
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


def scrape_all():
    generate_schedule()
    check_transcript()
    check_evaluation()


MENU = {
    "1": ("Generate Schedule ICS", generate_schedule),
    "2": ("Check Transcript of Grades (notify on change)", check_transcript),
    "3": ("Check Student Evaluation (notify on change)", check_evaluation),
    "4": ("Scrape All", scrape_all),
    "5": ("Exit", None),
}


def main():
    while True:
        print("\n=== myUNC Scraper ===")
        for key, (label, _) in MENU.items():
            print(f"  {key}) {label}")
        choice = input("\nSelect option: ").strip()

        if choice == "5":
            print("Bye.")
            break

        action = MENU.get(choice)
        if action is None:
            print("Invalid option.")
            continue

        try:
            action[1]()
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()

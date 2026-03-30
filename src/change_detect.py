"""Hash-based change detection for scraped pages."""

import hashlib
import re
import difflib
from pathlib import Path
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent.parent / "data"


def extract_grades_table(html: str) -> str:
    """Extract only the grades tables from transcript HTML."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    grade_tables = []
    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if "mg" in headers and "fg" in headers:
            grade_tables.append(table)

    if not grade_tables:
        return ""

    return "\n".join(str(t) for t in grade_tables)


def parse_grades(grades_html: str) -> dict:
    """Parse grades HTML into a dict keyed by subject (code + title)."""
    soup = BeautifulSoup(grades_html, "html.parser")
    tables = soup.find_all("table")

    grades = {}
    for table in tables:
        rows = table.find_all("tr")[1:]  # Skip header
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 6:
                continue
            code = cells[1].get_text(strip=True)  # Subject column (e.g., BIT121L)
            title = cells[2].get_text(strip=True)  # Descriptive Title
            if not code:
                continue
            mg = cells[3].get_text(strip=True)
            fg = cells[4].get_text(strip=True)
            credits = cells[5].get_text(strip=True)
            key = f"{code} - {title}"
            grades[key] = {
                "mg": mg,
                "fg": fg,
                "credits": credits,
                "code": code,
                "title": title,
            }

    return grades


def format_grade_changes(old_grades: dict, new_grades: dict) -> str:
    """Format changed grades into Markdown notification message."""
    new_lines = []
    changed_lines = []

    for key, new in new_grades.items():
        old = old_grades.get(key)
        if old is None:
            fg = new["fg"] if new["fg"] else "-"
            new_lines.append(
                f"- {new['title']}: **{new['mg']}** **{fg}** {new['credits']}"
            )
        elif old["mg"] != new["mg"] or old["fg"] != new["fg"]:
            mg_old = old["mg"] if old["mg"] else "-"
            mg_new = new["mg"] if new["mg"] else "-"
            mg = f"{mg_old} → **{mg_new}**"
            fg_old = old["fg"] if old["fg"] else "-"
            fg_new = new["fg"] if new["fg"] else "-"
            fg = f"{fg_old} → **{fg_new}**"
            changed_lines.append(f"- {new['title']}: {mg} {fg} {new['credits']}")

    parts = []
    if new_lines:
        parts.append("**New Grades**\n" + "\n".join(new_lines))
    if changed_lines:
        parts.append("**Changed**\n" + "\n".join(changed_lines))

    return "\n\n".join(parts) if parts else "No grade changes"


def normalize_content(text: str) -> str:
    """Remove dynamic content before hashing."""
    text = re.sub(r"\?uid=[a-f0-9]+", "", text)
    text = re.sub(r"\?t=\d+", "", text)
    text = re.sub(r"__EVENTVALIDATION[^<]*", "", text)
    text = re.sub(r"__VIEWSTATE[^<]*", "", text)
    text = re.sub(r"__EVENTTARGET[^<]*", "", text)
    text = re.sub(r"__LASTFOCUS[^<]*", "", text)
    return text


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(exist_ok=True)


def content_hash(text: str) -> str:
    normalized = normalize_content(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_stored_hash(name: str) -> str | None:
    hash_file = DATA_DIR / f"{name}.hash"
    if hash_file.exists():
        return hash_file.read_text().strip()
    return None


def store_hash(name: str, h: str) -> None:
    ensure_data_dir()
    hash_file = DATA_DIR / f"{name}.hash"
    hash_file.write_text(h)


def get_stored_content(name: str) -> str | None:
    content_file = DATA_DIR / f"{name}.content"
    if content_file.exists():
        return content_file.read_text()
    return None


def store_content(name: str, content: str) -> None:
    ensure_data_dir()
    content_file = DATA_DIR / f"{name}.content"
    content_file.write_text(content)


def has_changed(name: str, new_content: str) -> bool:
    """Check if content changed from last stored version. Does NOT update storage."""
    new_hash = content_hash(new_content)
    old_hash = get_stored_hash(name)
    if old_hash is None:
        return False
    return new_hash != old_hash


def commit_update(name: str, new_content: str) -> None:
    """Store the new content hash and content after processing."""
    new_hash = content_hash(new_content)
    store_hash(name, new_hash)
    store_content(name, new_content)


def is_first_run(name: str) -> bool:
    """Check if this is the first time scraping this page."""
    return get_stored_hash(name) is None


def generate_diff(name: str, new_content: str) -> str:
    old_content = get_stored_content(name)
    if old_content is None:
        return "No previous content to compare."
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines, fromfile="previous", tofile="current", lineterm=""
    )
    return "".join(diff)


def generate_diff_grades(name: str, new_html: str) -> tuple[bool, str]:
    """Check grades table changes and generate diff. Returns (changed, formatted_diff)."""
    new_grades = extract_grades_table(new_html)
    old_hash = get_stored_hash(name)

    # First run - store baseline
    if old_hash is None:
        store_hash(name, content_hash(new_grades))
        store_content(name, new_grades)
        return False, ""

    new_hash = content_hash(new_grades)

    if new_hash == old_hash:
        return False, ""

    old_grades = get_stored_content(name)
    if old_grades is None:
        return True, "No previous grades to compare."

    old_grades_parsed = parse_grades(old_grades)
    new_grades_parsed = parse_grades(new_grades)

    formatted = format_grade_changes(old_grades_parsed, new_grades_parsed)
    return True, formatted


def commit_update_grades(name: str, html: str) -> None:
    """Store grades table hash and content."""
    grades = extract_grades_table(html)
    h = content_hash(grades)
    store_hash(name, h)
    store_content(name, grades)

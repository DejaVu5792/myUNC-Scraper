"""Hash-based change detection for scraped pages."""

import hashlib
import re
import difflib
from pathlib import Path
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent.parent / "data" / "update_checks"


def extract_grades_by_semester(html: str) -> dict:
    """Extract grades tables grouped by semester."""
    soup = BeautifulSoup(html, "html.parser")
    semesters = {}

    spans = soup.find_all("span")
    for span in spans:
        text = span.get_text(strip=True)
        if "Sem." in text:
            semester_name = text
            table = span.find_next("table")
            if table:
                semesters[semester_name] = str(table)

    return semesters


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

    tables_html = "\n".join(str(t) for t in grade_tables)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Transcript of Grades</title>
    <style>
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4a4a4a; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        td.td-center {{ text-align: center; }}
    </style>
</head>
<body>
{tables_html}
</body>
</html>"""


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


def parse_semester_grades(html: str) -> dict:
    """Parse grades grouped by semester."""
    semesters = extract_grades_by_semester(html)
    result = {}
    for sem, table_html in semesters.items():
        result[sem] = parse_grades(table_html)
    return result


def find_newest_semester(semesters: dict) -> str | None:
    """Find the newest semester based on year and sem number."""
    import re

    newest = None
    newest_year = -1
    newest_sem = 0

    for sem in semesters.keys():
        # Parse "1st Sem. S/Y 2025-2026" or "2nd Sem. S/Y 2025-2026"
        match = re.search(r"(\d)(?:st|nd|rd|th)\s*Sem.*S/Y\s*(\d{4})-(\d{4})", sem)
        if match:
            sem_num = int(match.group(1))
            year = int(match.group(3))  # Use end year
            if year > newest_year or (year == newest_year and sem_num > newest_sem):
                newest_year = year
                newest_sem = sem_num
                newest = sem
    return newest


def format_semester_grades(semester_name: str, grades: dict) -> str:
    """Format a semester's grades nicely for notification."""
    if not grades:
        return f"**{semester_name}**\nNo grades"

    lines = [f"**{semester_name}**"]
    lines.append("```")
    lines.append(f"{'Subject':<35} {'MG':>5} {'FG':>5} {'Cred':>5}")
    lines.append("-" * 55)

    for key, g in grades.items():
        title = g["title"][:30] + "..." if len(g["title"]) > 30 else g["title"]
        mg = g["mg"] if g["mg"] else "-"
        fg = g["fg"] if g["fg"] else "-"
        cred = g["credits"] if g["credits"] else "-"
        lines.append(f"{title:<35} {mg:>5} {fg:>5} {cred:>5}")

    lines.append("```")
    return "\n".join(lines)


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
    DATA_DIR.mkdir(parents=True, exist_ok=True)


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
    """Check grades by semester. Returns (changed, formatted_message)."""
    # Get semester tables from HTML
    soup = BeautifulSoup(new_html, "html.parser")
    semesters_raw = {}

    spans = soup.find_all("span")
    for span in spans:
        text = span.get_text(strip=True)
        if "Sem." in text:
            semester_name = text
            table = span.find_next("table")
            if table:
                semesters_raw[semester_name] = str(table)

    # Get old semesters from stored content
    old_html = get_stored_content(name)
    if old_html is None:
        # First run - store everything
        clean_html = extract_grades_table(new_html)
        store_content(name, clean_html)
        for sem, table_html in semesters_raw.items():
            store_hash(f"{name}_{sanitize_filename(sem)}", content_hash(table_html))
        return False, ""

    # Parse old semesters
    old_soup = BeautifulSoup(old_html, "html.parser")
    old_spans = old_soup.find_all("span")
    old_semesters_raw = {}
    for span in old_spans:
        text = span.get_text(strip=True)
        if "Sem." in text:
            semester_name = text
            table = span.find_next("table")
            if table:
                old_semesters_raw[semester_name] = str(table)

    # Check each semester for changes
    changed_semesters = []
    for sem, table_html in semesters_raw.items():
        old_table = old_semesters_raw.get(sem, "")
        if content_hash(table_html) != content_hash(old_table):
            changed_semesters.append(sem)

    if not changed_semesters:
        # Update hashes anyway
        for sem, table_html in semesters_raw.items():
            store_hash(f"{name}_{sanitize_filename(sem)}", content_hash(table_html))
        return False, ""

    # Find newest semester from changed ones
    newest = find_newest_semester({s: True for s in changed_semesters})

    if not newest:
        newest = changed_semesters[0]

    # Get old and new grades for newest semester
    new_grades = parse_grades(semesters_raw.get(newest, ""))
    old_grades = parse_grades(old_semesters_raw.get(newest, ""))

    # Use the old format (new + changed grades)
    formatted = format_grade_changes(old_grades, new_grades)

    # Add semester header
    final_message = f"**{newest}**\n\n{formatted}"

    # Update hashes and store clean grades-only content
    for sem, table_html in semesters_raw.items():
        store_hash(f"{name}_{sanitize_filename(sem)}", content_hash(table_html))

    # Store clean HTML with only grades tables for browser viewing
    clean_html = extract_grades_table(new_html)
    store_content(name, clean_html)

    return True, final_message


def sanitize_filename(s: str) -> str:
    """Sanitize string for use in filename."""
    return re.sub(r"[^\w\s-]", "", s).replace(" ", "_")

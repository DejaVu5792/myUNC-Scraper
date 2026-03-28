"""Hash-based change detection for scraped pages."""

import hashlib
import difflib
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(exist_ok=True)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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

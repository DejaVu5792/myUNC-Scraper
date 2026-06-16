# myUNC Scraper
Quick tools for UNC's web portal and OES using CLI or TUI interface.

## Features
- Export schedule from myUNC as ICS
- OES support
    - Export Block Schedules as ICS/PNG for subjects
    - Export currently enrolled subjects in premat as ICS
- Check for changes in Grades
    - Notifies through ntfy
    
# How to use
## Setup
- Setup dependencies
```bash
uv sync
uv run playwright install
cp .env.example .env
```
- Enter credentials in .env or load through using CLI arguments
## Running
- For TUI
```bash
uv run main.py
```
- For args, see help for info
```bash
uv run main.py -h
```
- For OES Available Subjects scan (specific departments)
```bash
uv run main.py --oes-available --depts scis,cas
```

# Disclaimer
Pure AI Slop, vibe coded, made for personal use.

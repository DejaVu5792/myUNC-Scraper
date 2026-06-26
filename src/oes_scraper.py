"""Playwright-based scraper for oes.unc.edu.ph"""

import os
import csv
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, Browser
from playwright_stealth import Stealth
from bs4 import BeautifulSoup

load_dotenv()

OES_BASE_URL = "https://oes.unc.edu.ph/OES/Enrollment/Register.aspx"
def get_flaresolverr_session_info(url: str) -> tuple[list[dict] | None, str | None]:
    flaresolverr_url = os.getenv("FLARESOLVERR_URL")
    if not flaresolverr_url:
        return None, None
    
    # Normalize URL: make sure it has /v1 at the end
    flaresolverr_url = flaresolverr_url.rstrip("/")
    if not flaresolverr_url.endswith("/v1"):
        flaresolverr_url = f"{flaresolverr_url}/v1"
        
    print(f"Querying FlareSolverr (session) at {flaresolverr_url} for {url}...")
    session_id = None
    try:
        res_create = requests.post(flaresolverr_url, json={"cmd": "sessions.create"}, timeout=20)
        res_create.raise_for_status()
        session_id = res_create.json().get("session")
        if not session_id:
            print(f"Warning: Failed to create FlareSolverr session: {res_create.text}")
            return None, None
            
        payload = {
            "cmd": "request.get",
            "url": url,
            "session": session_id,
            "maxTimeout": 60000
        }
        response = requests.post(flaresolverr_url, json=payload, timeout=70)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "ok":
            solution = data.get("solution", {})
            cookies = solution.get("cookies", [])
            ua = solution.get("userAgent")
            print(f"Successfully obtained {len(cookies)} cookies and user-agent from FlareSolverr session.")
            return cookies, ua
        else:
            print(f"FlareSolverr returned status: {data.get('status')} - {data.get('message')}")
    except Exception as e:
        print(f"Warning: Failed to use FlareSolverr session: {e}")
    finally:
        if session_id:
            try:
                requests.post(flaresolverr_url, json={"cmd": "sessions.destroy", "session": session_id}, timeout=10)
            except Exception as destroy_err:
                print(f"Warning: Failed to destroy FlareSolverr session {session_id}: {destroy_err}")
    return None, None

import subprocess
import tempfile
import socket
import time

def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

class StealthBrowserSession:
    def __init__(self, playwright, headless=True, target_url=None):
        self.playwright = playwright
        self.headless = headless
        self.target_url = target_url
        self.proc = None
        self.browser = None
        # Set a persistent user data directory in the workspace
        self.user_data_dir = os.path.join(os.getcwd(), "data/chrome-profile")
        
    def __enter__(self):
        os.makedirs(self.user_data_dir, exist_ok=True)
        
        # 1. Query FlareSolverr first to get cookies and User-Agent if configured (only in headless mode)
        cookies, ua = None, None
        if self.target_url and self.headless:
            cookies, ua = get_flaresolverr_session_info(self.target_url)
        
        port = 9222
        for p in range(9222, 9250):
            if not is_port_open(p):
                port = p
                break
                
        cmd = [
            "chromium",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.user_data_dir}",
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage"
        ]
        if self.headless:
            cmd.append("--headless=new")
        if ua:
            cmd.append(f"--user-agent={ua}")
            
        print(f"Spawning standalone Chromium on port {port} (headless={self.headless}, profile={self.user_data_dir})...")
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait for the debugging port to become active
        for _ in range(40):
            if is_port_open(port):
                break
            time.sleep(0.5)
        else:
            print("Warning: Standalone Chromium did not start in time. Falling back to default Playwright launch.")
            try:
                self.proc.terminate()
            except:
                pass
            self.browser = self.playwright.chromium.launch(headless=self.headless)
            cookies, ua = None, None
            if self.target_url and self.headless:
                cookies, ua = get_flaresolverr_session_info(self.target_url)
            if ua:
                context = self.browser.new_context(user_agent=ua)
            else:
                context = self.browser.new_context()
            if cookies:
                playwright_cookies = []
                for c in cookies:
                    playwright_cookies.append({
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c["domain"],
                        "path": c["path"],
                        "expires": c.get("expiry", -1),
                        "httpOnly": c.get("httpOnly", False),
                        "secure": c.get("secure", False),
                        "sameSite": c.get("sameSite", "Lax")
                    })
                context.add_cookies(playwright_cookies)
            return self.browser, context
            
        self.browser = self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        
        if cookies:
            playwright_cookies = []
            for c in cookies:
                playwright_cookies.append({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c["path"],
                    "expires": c.get("expiry", -1),
                    "httpOnly": c.get("httpOnly", False),
                    "secure": c.get("secure", False),
                    "sameSite": c.get("sameSite", "Lax")
                })
            context.add_cookies(playwright_cookies)
            
        return self.browser, context

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except:
                pass

def solve_turnstile_if_present(page: Page, timeout_sec: int = 20) -> bool:
    # Give it a moment to render
    page.wait_for_timeout(2000)
    
    # Check if we are on a "Just a moment..." page
    if "Just a moment" not in page.title():
        return True
        
    print("Cloudflare Turnstile challenge detected. Attempting bypass...")
    turnstile_frame = None
    for _ in range(timeout_sec):
        for frame in page.frames:
            if "challenges.cloudflare.com" in frame.url:
                turnstile_frame = frame
                break
        if turnstile_frame:
            break
        page.wait_for_timeout(1000)
        
    if not turnstile_frame:
        print("Turnstile frame not found. Waiting for automatic solve...")
        if "Just a moment" not in page.title():
            return True
        return False
        
    print(f"Found Turnstile frame: {turnstile_frame.url[:80]}...")
    
    # Get iframe element bounding box on main page
    iframe_box = None
    try:
        iframe_element = turnstile_frame.frame_element()
        if iframe_element:
            iframe_box = iframe_element.bounding_box()
    except Exception as e:
        print(f"Error getting Turnstile frame bounding box: {e}")
        
    if not iframe_box:
        print("Could not find Turnstile iframe element bounding box. Waiting for automatic solve...")
    else:
        # Get checkbox relative coordinates inside iframe
        js_find_cb = """
        () => {
            function findCheckbox(root) {
                if (!root) return null;
                const el = root.querySelector('input[type="checkbox"]');
                if (el) return el;
                const all = root.querySelectorAll('*');
                for (let i = 0; i < all.length; i++) {
                    const el = all[i];
                    if (el.shadowRoot) {
                        const found = findCheckbox(el.shadowRoot);
                        if (found) return found;
                    }
                }
                return null;
            }
            const cb = findCheckbox(document);
            if (cb) {
                const rect = cb.getBoundingClientRect();
                return {
                    x: rect.left,
                    y: rect.top,
                    width: rect.width,
                    height: rect.height
                };
            }
            return null;
        }
        """
        
        cb_rect = None
        for _ in range(10):
            try:
                cb_rect = turnstile_frame.evaluate(js_find_cb)
                if cb_rect:
                    break
            except Exception as e:
                pass
            page.wait_for_timeout(1000)
            
        if cb_rect:
            # Calculate absolute coordinates
            click_x = iframe_box['x'] + cb_rect['x'] + cb_rect['width'] / 2
            click_y = iframe_box['y'] + cb_rect['y'] + cb_rect['height'] / 2
            
            print(f"Clicking Turnstile checkbox at page coordinates: ({click_x}, {click_y})")
            try:
                page.mouse.move(click_x, click_y)
                page.wait_for_timeout(300)
                page.mouse.down()
                page.wait_for_timeout(100)
                page.mouse.up()
            except Exception as e:
                print(f"Failed coordinate click: {e}")
        else:
            print("Could not find checkbox inside Turnstile frame. Waiting for automatic solve...")

    # Wait for solve (title change or success element)
    for _ in range(15):
        title = page.title()
        if "Just a moment" not in title:
            print("Solve confirmed: page title changed.")
            return True
            
        try:
            success_visible = turnstile_frame.evaluate("""() => {
                const div = document.querySelector('div[id="success"]');
                return div ? div.offsetParent !== null : false;
            }""")
            if success_visible:
                print("Solve confirmed: success element visible.")
                return True
        except:
            pass
            
        page.wait_for_timeout(1000)
        
    return "Just a moment" not in page.title()

def launch_browser(playwright, target_url=None):
    # Backward compatibility fallback
    browser = playwright.chromium.launch(headless=True)
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    context = browser.new_context(user_agent=user_agent)
    return browser, context

def create_page(context) -> Page:
    page = context.new_page()
    
    def on_console(msg):
        if msg.type in ("warning", "verbose"):
            return
        text_lower = msg.text.lower()
        if "[dom]" in text_lower or "autocomplete" in text_lower:
            return
        if "failed to load resource" in text_lower or "status of 404" in text_lower:
            return
        print(f"Browser Console {msg.type}: {msg.text}")
        
    def on_response(res):
        if res.status >= 400:
            if res.status == 404:
                return
            print(f"Network Error: {res.status} {res.url}")

    page.on("console", on_console)
    page.on("pageerror", lambda err: print(f"Browser Page Error: {err}"))
    page.on("response", on_response)
    return page

def login_oes(page: Page) -> None:
    username = os.getenv("UNC_OES_EMAIL")
    password = os.getenv("UNC_OES_PASSWORD")
    if not username or not password:
        raise ValueError("UNC_OES_EMAIL and UNC_OES_PASSWORD must be set in .env")

    # Use load instead of networkidle to prevent Turnstile challenges from blocking page.goto completion
    page.goto(OES_BASE_URL, wait_until="load")
    
    # Solve Turnstile if present
    solve_turnstile_if_present(page)

    # Click to continue with enrollment tab
    page.locator('//*[@id="nav-login-tab2"]').click()
    page.wait_for_timeout(500) # Give the tab a moment to become visible
    
    # Use XPaths provided
    page.locator('//*[@id="enrollmentHolder_txtEmailLogin"]').fill(username)
    page.locator('//*[@id="enrollmentHolder_txtPasswordLogin"]').fill(password)
    page.locator('//*[@id="enrollmentHolder_btnLogin"]').click()
    page.wait_for_load_state("networkidle")

def get_enrolled_subjects(page: Page) -> str:
    # Prematriculation tab
    page.locator('//*[@id="fco"]').click()
    page.wait_for_load_state("networkidle")
    
    # Wait for the table container link and click it to load the enrolled subjects table
    cart_counter = page.locator('//*[@id="enrollmentHolder_imgCartCounter"]')
    cart_counter.wait_for(state="attached", timeout=10000)
    cart_counter.click()
    
    # Wait for the cart table to load and become visible
    page.locator('#cart').wait_for(state="visible", timeout=15000)
    
    return page.content()

def scrape_oes_enrolled_schedule() -> str:
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    with sync_playwright() as p:
        session = StealthBrowserSession(p, headless=headless, target_url=OES_BASE_URL)
        with session as (browser, context):
            page = create_page(context)
            login_oes(page)
            html = get_enrolled_subjects(page)
            return html

def parse_available_subjects(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="offerings")
    subjects = []
    if not table:
        return subjects
    
    rows = table.find_all("tr")[1:] # skip header
    last_code = ""
    last_course_no = ""
    last_unit = ""
    last_title = ""
    last_type = ""
    last_tally = ""
    
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 9:
            continue
        
        # Format based on OEShtml/subjectselection.txt
        # Code  Course No       Unit    Title   Schedule        Type    Room    Teacher Tally
        code_input = cells[0].find("input")
        code = code_input.get("value", "").strip() if code_input else cells[0].get_text(strip=True)
        course_no = cells[1].get_text(strip=True)
        unit = cells[2].get_text(strip=True)
        title = cells[3].get_text(strip=True)
        schedule = cells[4].get_text(strip=True)
        type_str = cells[5].get_text(strip=True)
        room = cells[6].get_text(strip=True)
        teacher = cells[7].get_text(strip=True)
        tally = cells[8].get_text(strip=True)
        
        if not code:
            code = last_code
        else:
            last_code = code
            
        if not course_no:
            course_no = last_course_no
        else:
            last_course_no = course_no
            
        if not unit:
            unit = last_unit
        else:
            last_unit = unit
            
        if not title:
            title = last_title
        else:
            last_title = title
            
        if not type_str:
            type_str = last_type
        else:
            last_type = type_str
            
        if not tally:
            tally = last_tally
        else:
            last_tally = tally
            
        if course_no or title:
            subjects.append({
                "code": code,
                "course_no": course_no,
                "unit": unit,
                "title": title,
                "schedule": schedule,
                "type": type_str,
                "room": room,
                "teacher": teacher,
                "tally": tally
            })
    return subjects

def get_available_subjects(page: Page, departments: list[str] = None) -> list[dict]:
    # Request tab
    page.locator('a[href*="Request.aspx"]').first.click()
    page.wait_for_load_state("networkidle")
    print(f"Request Tab Loaded URL: {page.url}")
    
    # Check if we are on intermediate wizard pages (like Registration-Application.aspx or Registration-PersonalInformation.aspx)
    for step in range(5):
        if "Request.aspx" in page.url:
            break
            
        current_url = page.url
        print(f"Intermediate step page detected: {current_url}")
        
        # If we are on Registration-Application.aspx, select the "Take Subject" option if visible
        if "Registration-Application.aspx" in current_url:
            try:
                page.locator('label[for="enrollmentHolder_rbtListReqType_3"]').click(timeout=3000)
            except:
                pass
                
        # Try to click any "Next", "Confirm", or "Save" button to proceed
        clicked_next = False
        for selector in ['#enrollmentHolder_btnNext2', '#enrollmentHolder_btnNext', '#enrollmentHolder_btnSave', '#enrollmentHolder_btnConfirm', 'input[value*="Next"]', 'input[value*="NEXT"]', 'button:has-text("Next")', 'button:has-text("NEXT")', 'input[value*="Confirm"]', 'button:has-text("Confirm")']:
            try:
                loc = page.locator(selector)
                if loc.count() > 0 and loc.is_visible():
                    print(f"Found step proceed button '{selector}', clicking...")
                    loc.click(timeout=5000)
                    page.wait_for_load_state("networkidle")
                    clicked_next = True
                    break
            except:
                pass
                
        if not clicked_next or page.url == current_url:
            print("No new step proceed action found or url didn't change.")
            break

    # Now we are on Request.aspx (or as close as we can get)
    if "Request.aspx" in page.url:
        # Select the "Take Subject" radio button on Request.aspx if needed
        try:
            page.locator('label[for="enrollmentHolder_rbtListReqType_3"]').click(timeout=5000)
        except Exception as e:
            print(f"Failed selecting request subject on Request page: {e}")
            
        print("Type of SelectRequestType before click:", page.evaluate("typeof SelectRequestType"))
        
        # Click NEXT button on Request.aspx (this has onclick="SelectRequestType();")
        try:
            page.locator('button[onclick="SelectRequestType();"]').click(timeout=5000)
        except Exception as e:
            print(f"Failed clicking NEXT on Request page: {e}")
            
        page.wait_for_load_state("networkidle")
        print(f"After Request page NEXT Click URL: {page.url}")
    
    # View course offerings
    page.get_by_role("button", name="View course offerings").click(timeout=5000)
    page.wait_for_load_state("networkidle")
    
    # Wait for the iframe element to be attached/visible
    page.wait_for_selector("#enrollmentHolder_ifrOfferings", timeout=10000)
    
    # Get the frame using content_frame()
    iframe_handle = page.query_selector("#enrollmentHolder_ifrOfferings")
    frame = iframe_handle.content_frame()
    if not frame:
        raise ValueError("Could not find the Offerings iframe")
        
    # Wait for the iframe's content to load (cboDept)
    frame.wait_for_selector("#enrollmentHolder_cboDept", timeout=15000)
    
    import sys
    import inquirer
    from inquirer.themes import BlueComposure

    # Fetch options
    options_elements = frame.query_selector_all("#enrollmentHolder_cboDept option")
    options = []
    for opt in options_elements:
        val = opt.get_attribute("value")
        text = opt.inner_text().strip()
        if val and val != "-" and val != "0" and text:
            text = " ".join(text.split())
            options.append((text, val))

    print("Available department options in dropdown:")
    for text, val in options:
        print(f"  - {text} (Value: {val})")

    selected_depts = []
    if departments:
        # Resolve departments list
        import re
        for d in departments:
            d_upper = d.upper()
            matched_val = None
            
            # 1. Exact value match
            for text, val in options:
                if val.upper() == d_upper:
                    matched_val = val
                    break
            if matched_val:
                selected_depts.append(matched_val)
                continue
                
            # 2. Exact text match
            for text, val in options:
                if text.upper() == d_upper:
                    matched_val = val
                    break
            if matched_val:
                selected_depts.append(matched_val)
                continue
                
            # 3. Known mappings
            mapped = False
            for text, val in options:
                t_up = text.upper()
                if d_upper == "SCIS" and "COMPUTER" in t_up:
                    matched_val = val
                    mapped = True
                    break
                elif d_upper == "CAS" and "SOCIAL" in t_up:
                    matched_val = val
                    mapped = True
                    break
                elif d_upper in ["CEA", "EN", "ENG", "ENGINEERING"] and "ENGINEERING" in t_up:
                    matched_val = val
                    mapped = True
                    break
                elif d_upper == "CBA" and "BUSINESS" in t_up:
                    matched_val = val
                    mapped = True
                    break
                elif d_upper == "COED" and "TEACHER" in t_up:
                    matched_val = val
                    mapped = True
                    break
                elif d_upper == "CON" and "NURSING" in t_up:
                    matched_val = val
                    mapped = True
                    break
                elif d_upper == "CCJE" and "CRIMINAL" in t_up:
                    matched_val = val
                    mapped = True
                    break
                elif d_upper == "NSTP" and "NSTP" in t_up:
                    matched_val = val
                    mapped = True
                    break
            if mapped:
                selected_depts.append(matched_val)
                continue
                
            # 4. Word-level substring match (to avoid short codes matching inside other words)
            for text, val in options:
                words = [w.strip() for w in re.split(r'\W+', text.upper()) if w.strip()]
                if d_upper in words:
                    matched_val = val
                    break
            if matched_val:
                selected_depts.append(matched_val)
                continue
                
            # 5. Fallback substring match for queries of length >= 3
            if len(d_upper) >= 3:
                for text, val in options:
                    if d_upper in text.upper():
                        matched_val = val
                        break
            if matched_val:
                selected_depts.append(matched_val)
                continue
                
            print(f"Warning: Could not match department input '{d}' to any dropdown option.")

    # If not provided, or resolved to empty, try to prompt/default
    if not selected_depts:
        if sys.stdin.isatty():
            questions = [
                inquirer.Checkbox(
                    "depts",
                    message="Select departments to scan (Space to toggle, Enter to confirm)",
                    choices=options,
                    carousel=True,
                )
            ]
            try:
                answers = inquirer.prompt(questions, theme=BlueComposure())
                if answers and answers.get("depts"):
                    selected_depts = answers["depts"]
            except Exception as pe:
                print(f"Prompt error: {pe}")
        
        # If still empty (e.g. non-interactive or prompt skipped/cancelled)
        if not selected_depts:
            if options:
                selected_depts = [options[0][1]]
                print(f"Defaulting to scan first department: {options[0][0]} (Value: {options[0][1]}).")

    all_subjects = []
    
    # Process each selected department
    for dept_val in selected_depts:
        # Find the text of the department
        dept_text = next((text for text, val in options if val == dept_val), dept_val)
        print(f"\nScanning department: {dept_text} (Value: {dept_val})...")
        
        try:
            frame.select_option("#enrollmentHolder_cboDept", value=dept_val)
            frame.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000) # Wait for AJAX postback to complete
        except Exception as e:
            print(f"Error selecting dept {dept_text}: {e}")
            continue

        # Wait for the first letter link to ensure the list is loaded inside the iframe
        try:
            frame.locator('#enrollmentHolder_rptLinks_lnkLetter_0').wait_for(state="attached", timeout=10000)
        except Exception as e:
            print(f"Could not find the letter links for subject filtering inside the iframe for {dept_text}.")
            
        # Iterate through A-Z (0-25) inside the iframe
        for i in range(26):
            letter = chr(ord('A') + i)
            try:
                letter_locator = frame.locator(f'#enrollmentHolder_rptLinks_lnkLetter_{i}')
                # Check if it exists and wait for it
                if letter_locator.count() > 0:
                    letter_locator.click()
                    frame.wait_for_load_state("networkidle")
                    page.wait_for_timeout(1000) # Give it a moment to load
                    
                    html = frame.content()
                    subjects = parse_available_subjects(html)
                    # Add department info to each subject
                    for subject in subjects:
                        subject["dept"] = dept_text
                    print(f"[{dept_text}] Scraped {len(subjects)} subjects for letter {letter}")
                    all_subjects.extend(subjects)
            except Exception as e:
                print(f"Error scraping letter {letter} for {dept_text}: {e}")
                
    return all_subjects

def scrape_oes_available_subjects(departments: list[str] = None) -> list[dict]:
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    with sync_playwright() as p:
        session = StealthBrowserSession(p, headless=headless, target_url=OES_BASE_URL)
        with session as (browser, context):
            page = create_page(context)
            login_oes(page)
            return get_available_subjects(page, departments=departments)

def export_available_subjects_to_csv(subjects: list[dict], output_path: str = "data/available_subjects.csv") -> str:
    if not subjects:
        print("No available subjects to export.")
        return ""
        
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
    # Ensure every subject has a 'dept' key (fallback to empty string)
    for subject in subjects:
        if "dept" not in subject:
            subject["dept"] = ""
            
    keys = ["dept", "code", "course_no", "unit", "title", "schedule", "type", "room", "teacher", "tally"]
    
    # Load existing subjects if the file exists
    existing_subjects = []
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Filter only fields we care about to match key list
                    cleaned_row = {k: row.get(k, "") for k in keys}
                    existing_subjects.append(cleaned_row)
        except Exception as e:
            print(f"Warning: Could not read existing available subjects from {output_path}: {e}")

    # Use a dictionary to merge and deduplicate
    # Unique key: (code, schedule, type, room)
    # New subjects should overwrite existing ones to have updated tally, teacher, etc.
    merged = {}
    
    # First populate with existing subjects
    for sub in existing_subjects:
        key = (
            str(sub.get("code", "")).strip(),
            str(sub.get("schedule", "")).strip(),
            str(sub.get("type", "")).strip(),
            str(sub.get("room", "")).strip()
        )
        merged[key] = sub
        
    added_list = []
    updated_list = []

    # Overwrite with newly scraped subjects (preserves updated fields and adds new rows)
    for sub in subjects:
        key = (
            str(sub.get("code", "")).strip(),
            str(sub.get("schedule", "")).strip(),
            str(sub.get("type", "")).strip(),
            str(sub.get("room", "")).strip()
        )
        if key not in merged:
            added_list.append(sub)
        else:
            old_sub = merged[key]
            field_changes = {}
            for field in ["dept", "course_no", "unit", "title", "teacher", "tally"]:
                old_val = str(old_sub.get(field, "")).strip()
                new_val = str(sub.get(field, "")).strip()
                if old_val != new_val:
                    field_changes[field] = (old_val, new_val)
            if field_changes:
                updated_list.append((sub, field_changes))
        
        merged[key] = sub
        
    # Convert back to list, preserving order or sorting by dept, title, code, schedule
    def sort_key(s):
        return (
            s.get("dept", ""),
            s.get("title", ""),
            s.get("code", ""),
            s.get("schedule", "")
        )
        
    deduped_subjects = sorted(merged.values(), key=sort_key)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(deduped_subjects)
        
    print(f"Exported {len(deduped_subjects)} available subjects to {output_path} (merged new scrape, was {len(existing_subjects)} existing)")
    
    if added_list or updated_list:
        print("\n--- Changes to Available Subjects CSV ---")
        if added_list:
            print(f"Added {len(added_list)} new subjects:")
            for sub in added_list:
                print(f"  + [{sub.get('dept', '')}] {sub.get('code', '')} - {sub.get('course_no', '')} ({sub.get('title', '')}) | Schedule: {sub.get('schedule', '')} | Room: {sub.get('room', '')} | Teacher: {sub.get('teacher', '')} | Tally: {sub.get('tally', '')}")
        if updated_list:
            print(f"Updated {len(updated_list)} subjects:")
            for sub, field_changes in updated_list:
                changes_str = ", ".join(f"{field}: '{old}' -> '{new}'" for field, (old, new) in field_changes.items())
                print(f"  ~ {sub.get('code', '')} - {sub.get('course_no', '')} ({sub.get('title', '')}) | Schedule: {sub.get('schedule', '')} | Room: {sub.get('room', '')} | Changes: {changes_str}")
        print("-----------------------------------------\n")
    else:
        print("\n--- Changes to Available Subjects CSV ---")
        print("No changes detected.")
        print("-----------------------------------------\n")

    return output_path

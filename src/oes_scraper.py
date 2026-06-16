"""Playwright-based scraper for oes.unc.edu.ph"""

import os
import csv
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, Browser
from bs4 import BeautifulSoup

load_dotenv()

OES_BASE_URL = "https://oes.unc.edu.ph/OES/Enrollment/Register.aspx"

def launch_browser(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    )
    return browser, context

def create_page(context) -> Page:
    page = context.new_page()
    page.on("console", lambda msg: print(f"Browser Console {msg.type}: {msg.text}"))
    page.on("pageerror", lambda err: print(f"Browser Page Error: {err}"))
    page.on("response", lambda res: print(f"Network Error: {res.status} {res.url}") if res.status >= 400 else None)
    return page

def login_oes(page: Page) -> None:
    username = os.getenv("UNC_OES_EMAIL")
    password = os.getenv("UNC_OES_PASSWORD")
    if not username or not password:
        raise ValueError("UNC_OES_EMAIL and UNC_OES_PASSWORD must be set in .env")

    page.goto(OES_BASE_URL, wait_until="networkidle")

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
    page.screenshot(path="debug_enrolled_live.png")
    
    return page.content()

def scrape_oes_enrolled_schedule() -> str:
    with sync_playwright() as p:
        browser, context = launch_browser(p)
        page = create_page(context)
        try:
            login_oes(page)
            html = get_enrolled_subjects(page)
            return html
        finally:
            browser.close()

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
    
    # Check if we are on Registration-Application.aspx or Request.aspx
    if "Registration-Application.aspx" in page.url:
        # We need to click Next to proceed to Request.aspx
        # Select "Take Subject" radio button
        try:
            page.locator('label[for="enrollmentHolder_rbtListReqType_3"]').click(timeout=5000)
        except Exception as e:
            print(f"Failed selecting request subject on Registration-Application: {e}")
        # Click the NEXT button on Registration-Application page (id: enrollmentHolder_btnNext2)
        try:
            page.locator('#enrollmentHolder_btnNext2').click(timeout=5000)
        except Exception as e:
            print(f"Failed clicking next on Registration-Application: {e}")
        page.wait_for_load_state("networkidle")
        print(f"Navigated to: {page.url}")

    # Now we are on Request.aspx
    # Select the "Take Subject" radio button on Request.aspx if needed
    try:
        page.locator('label[for="enrollmentHolder_rbtListReqType_3"]').click(timeout=5000)
    except Exception as e:
        print(f"Failed selecting request subject on Request page: {e}")
        
    print("Type of SelectRequestType before click:", page.evaluate("typeof SelectRequestType"))
    
    # Click NEXT button on Request.aspx (this has onclick="SelectRequestType();")
    # Let's find it specifically by its onclick attribute or selector to avoid ambiguity
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

    selected_depts = []
    if departments:
        # Resolve departments list
        for d in departments:
            d_upper = d.upper()
            matched_val = None
            for text, val in options:
                if (val.upper() == d_upper or 
                    text.upper() == d_upper or 
                    d_upper in text.upper() or 
                    (d_upper == "SCIS" and "COMPUTER" in text.upper()) or
                    (d_upper == "CAS" and "SOCIAL" in text.upper()) or
                    (d_upper == "CBA" and "BUSINESS" in text.upper()) or
                    (d_upper == "COED" and "TEACHER" in text.upper()) or
                    (d_upper == "CEA" and "ENGINEERING" in text.upper()) or
                    (d_upper == "CON" and "NURSING" in text.upper()) or
                    (d_upper == "CCJE" and "CRIMINAL" in text.upper()) or
                    (d_upper == "NSTP" and "NSTP" in text.upper())):
                    matched_val = val
                    break
            if matched_val:
                selected_depts.append(matched_val)
            else:
                print(f"Warning: Could not match department input '{d}' to any dropdown option.")

    # If not provided, or resolved to empty, try to prompt/default
    if not selected_depts:
        if sys.stdin.isatty():
            # Find the default to pre-select (SCIS/CS)
            scis_val = next((val for text, val in options if "COMPUTER" in text.upper() or val == "CS"), None)
            default_selections = [scis_val] if scis_val else []
            
            questions = [
                inquirer.Checkbox(
                    "depts",
                    message="Select departments to scan (Space to toggle, Enter to confirm)",
                    choices=options,
                    default=default_selections,
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
            scis_val = next((val for text, val in options if "COMPUTER" in text.upper() or val == "CS"), None)
            if scis_val:
                selected_depts = [scis_val]
                print(f"Defaulting to scan SCIS department (Value: {scis_val}).")
            elif options:
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
    with sync_playwright() as p:
        browser, context = launch_browser(p)
        page = create_page(context)
        try:
            login_oes(page)
            return get_available_subjects(page, departments=departments)
        finally:
            browser.close()

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
    with open(output_path, 'w', newline='', encoding='utf-8') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(subjects)
        
    print(f"Exported {len(subjects)} available subjects to {output_path}")
    return output_path

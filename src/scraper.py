"""Playwright-based scraper for my.unc.edu.ph"""

import os
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, Browser
from playwright_stealth import Stealth

load_dotenv()

BASE_URL = "https://my.unc.edu.ph/"
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


def login(page: Page) -> None:
    username = os.getenv("UNC_USERNAME")
    password = os.getenv("UNC_PASSWORD")
    if not username or not password:
        raise ValueError("UNC_USERNAME and UNC_PASSWORD must be set in .env")

    # Use load instead of networkidle to prevent Turnstile challenges from blocking page.goto completion
    page.goto(BASE_URL, wait_until="load")
    
    # Solve Turnstile if present
    solve_turnstile_if_present(page)

    page.fill('input[name="ctl00$loginContent$txtUsername"]', username)
    page.fill('input[name="ctl00$loginContent$txtPassword"]', password)
    page.select_option("#ddlLoginAs", label="Student")
    page.click('input[name="ctl00$loginContent$btnSignIn"]')
    page.wait_for_load_state("networkidle")


XPATH_MY_ACCOUNT = "xpath=/html/body/form/div[3]/div/div[4]/ul/li[2]/a"
XPATH_SCHEDULE = "xpath=/html/body/form/div[3]/div/div[4]/ul/li[2]/ul/li[2]/a"
XPATH_TRANSCRIPT = "xpath=/html/body/form/div[3]/div/div[4]/ul/li[2]/ul/li[4]/a"
XPATH_EVALUATION = "xpath=/html/body/form/div[3]/div/div[4]/ul/li[2]/ul/li[5]/a"


def navigate_to_my_account(page: Page) -> None:
    page.locator(XPATH_MY_ACCOUNT).click()
    page.wait_for_load_state("networkidle")


def get_schedule(page: Page) -> str:
    navigate_to_my_account(page)
    page.locator(XPATH_SCHEDULE).click()
    page.wait_for_load_state("networkidle")
    return page.content()


def get_transcript(page: Page) -> str:
    navigate_to_my_account(page)
    page.locator(XPATH_TRANSCRIPT).click()
    page.wait_for_load_state("networkidle")
    return page.content()


YEAR_LEVELS = ["First Year", "Second Year", "Third Year", "Fourth Year"]


def get_evaluation(page: Page) -> str:
    navigate_to_my_account(page)
    page.locator(XPATH_EVALUATION).click()
    page.wait_for_load_state("networkidle")
    return page.content()


def get_evaluation_all_years(page: Page) -> dict[str, str]:
    """Navigate to evaluation and scrape all year levels.

    Returns {year_level: html_content} for each level.
    """
    navigate_to_my_account(page)
    page.locator(XPATH_EVALUATION).click()
    page.wait_for_load_state("networkidle")

    results = {}

    for i, level in enumerate(YEAR_LEVELS):
        if i == 0:
            # First year is the default, capture current content
            results[level] = page.content()
        else:
            page.select_option("#ddlYearLevel", label=level)
            page.wait_for_load_state("load")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(500)
            results[level] = page.content()

    return results


def scrape_schedule() -> str:
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    with sync_playwright() as p:
        session = StealthBrowserSession(p, headless=headless, target_url=BASE_URL)
        with session as (browser, context):
            page = context.new_page()
            login(page)
            html = get_schedule(page)
            return html


def scrape_transcript() -> str:
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    with sync_playwright() as p:
        session = StealthBrowserSession(p, headless=headless, target_url=BASE_URL)
        with session as (browser, context):
            page = context.new_page()
            login(page)
            html = get_transcript(page)
            return html


def scrape_evaluation() -> dict[str, str]:
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    with sync_playwright() as p:
        session = StealthBrowserSession(p, headless=headless, target_url=BASE_URL)
        with session as (browser, context):
            page = context.new_page()
            login(page)
            return get_evaluation_all_years(page)

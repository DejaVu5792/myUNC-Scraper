"""Playwright-based scraper for my.unc.edu.ph"""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, Browser
from playwright_stealth import Stealth

load_dotenv()

BASE_URL = "https://my.unc.edu.ph/"


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


def login(page: Page) -> None:
    username = os.getenv("UNC_USERNAME")
    password = os.getenv("UNC_PASSWORD")
    if not username or not password:
        raise ValueError("UNC_USERNAME and UNC_PASSWORD must be set in .env")

    page.goto(BASE_URL, wait_until="networkidle")

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
    with Stealth().use_sync(sync_playwright()) as p:
        browser, context = launch_browser(p)
        page = context.new_page()
        try:
            login(page)
            html = get_schedule(page)
            return html
        finally:
            browser.close()


def scrape_transcript() -> str:
    with Stealth().use_sync(sync_playwright()) as p:
        browser, context = launch_browser(p)
        page = context.new_page()
        try:
            login(page)
            html = get_transcript(page)
            return html
        finally:
            browser.close()


def scrape_evaluation() -> dict[str, str]:
    with Stealth().use_sync(sync_playwright()) as p:
        browser, context = launch_browser(p)
        page = context.new_page()
        try:
            login(page)
            return get_evaluation_all_years(page)
        finally:
            browser.close()

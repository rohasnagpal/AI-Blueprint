import os
import sys

from playwright.sync_api import Page, expect, sync_playwright


def assert_no_csp_errors(messages: list[str]) -> None:
    violations = [
        message
        for message in messages
        if "content security policy" in message.lower()
        or "violates the following content security policy" in message.lower()
        or "refused to apply inline style" in message.lower()
        or "refused to execute inline" in message.lower()
    ]
    if violations:
        raise AssertionError("CSP violations detected:\n" + "\n".join(violations))


def click_more(page: Page) -> None:
    page.locator("#nav-more").click()
    expect(page.locator("#sidebar-more-menu")).to_be_visible()


def expect_active(page: Page, selector: str) -> None:
    if not page.locator(selector).evaluate("element => element.classList.contains('active')"):
        raise AssertionError(f"Expected {selector} to be active")


def main() -> None:
    base_url = os.environ.get("AI_BLUEPRINT_BASE_URL", "http://127.0.0.1:8000")
    console_messages: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda msg: console_messages.append(f"{msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        response = page.goto(f"{base_url}/index.html", wait_until="networkidle")
        if not response or response.status >= 400:
            raise AssertionError(f"Failed to load index.html: {response.status if response else 'no response'}")

        csp = response.headers.get("content-security-policy", "")
        if "'unsafe-inline'" in csp:
            raise AssertionError(f"CSP still allows unsafe-inline: {csp}")
        for directive in ["script-src-attr 'none'", "style-src-attr 'none'", "object-src 'none'"]:
            if directive not in csp:
                raise AssertionError(f"Missing CSP directive {directive!r}: {csp}")

        local_mode = page.locator("button", has_text="Continue in local mode")
        if local_mode.is_visible():
            local_mode.click()
            expect(page.locator("#v2-auth-modal")).not_to_be_visible()

        expect(page.locator("#nav-more")).to_be_visible()
        click_more(page)
        page.locator("#more-settings").click()
        expect_active(page, "#view-settings")

        click_more(page)
        page.locator("#more-add-doc").click()
        expect_active(page, "#view-add-doc")
        expect(page.locator("#upload-zone")).to_be_visible()
        with page.expect_file_chooser() as chooser:
            page.locator("#upload-zone").click()
        chooser.value

        page.locator("#nav-personas").click()
        expect_active(page, "#view-personas")
        page.locator("button", has_text="Create Persona").click()
        expect(page.locator("#persona-editor-modal")).to_be_visible()
        page.locator("#persona-editor-modal button", has_text="Close").click()

        page.locator("#theme-icon-btn").click()
        page.wait_for_timeout(250)
        theme = page.locator("html").get_attribute("data-theme")
        if theme not in {"light", "dark"}:
            raise AssertionError(f"Unexpected theme after toggle: {theme}")

        assert_no_csp_errors(console_messages)
        if page_errors:
            raise AssertionError("Page errors detected:\n" + "\n".join(page_errors))
        browser.close()

    print("CSP UI smoke passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

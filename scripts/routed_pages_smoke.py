import os
import sys

from playwright.sync_api import Page, expect, sync_playwright


ROUTES = [
    ("/chat", "#view-chat", "Chat"),
    ("/personas", "#view-personas", "Personas"),
    ("/settings", "#view-settings", "Settings"),
    ("/settings/workspaces", "#view-settings", "Workspaces"),
    ("/settings/users", "#view-settings", "Admin Users"),
    ("/documents", "#view-view-docs", "View Documents"),
    ("/documents/add", "#view-add-doc", "Add Document"),
    ("/email", "#view-email", "Email"),
    ("/translate", "#view-translate", "Translate"),
    ("/draft", "#view-draft", "Draft"),
    ("/contract-review", "#view-contract-review", "Contract Review"),
]


def active_view_id(page: Page) -> str | None:
    return page.locator(".view.active").evaluate("element => element.id") if page.locator(".view.active").count() else None


def assert_active(page: Page, selector: str, path: str) -> None:
    expect(page.locator(selector)).to_have_count(1)
    if not page.locator(selector).evaluate("element => element.classList.contains('active')"):
        raise AssertionError(f"{path} did not activate {selector}; active view is {active_view_id(page)}")


def assert_no_errors(console_messages: list[str], page_errors: list[str]) -> None:
    blocked = [
        message
        for message in console_messages
        if "content security policy" in message.lower()
        or "refused to execute" in message.lower()
        or "refused to apply" in message.lower()
    ]
    if blocked:
        raise AssertionError("Console errors detected:\n" + "\n".join(blocked))
    if page_errors:
        raise AssertionError("Page errors detected:\n" + "\n".join(page_errors))


def route_has_no_store(page: Page, base_url: str, path: str) -> None:
    response = page.goto(f"{base_url}{path}", wait_until="networkidle")
    if not response or response.status >= 400:
        raise AssertionError(f"{path} failed to load: {response.status if response else 'no response'}")
    cache_control = response.headers.get("cache-control", "")
    if "no-store" not in cache_control:
        raise AssertionError(f"{path} should be served no-store, got {cache_control!r}")


def main() -> None:
    base_url = os.environ.get("AI_BLUEPRINT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    console_messages: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda msg: console_messages.append(f"{msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        for path, selector, title in ROUTES:
            route_has_no_store(page, base_url, path)
            assert_active(page, selector, path)
            expect(page.locator("#nav-settings")).to_be_visible()
            if page.locator("#more-workspaces").count():
                raise AssertionError("Workspaces should not appear in the More menu")
            if page.locator("#view-title").count():
                expect(page.locator("#view-title")).to_have_text(title)

        assert_no_errors(console_messages, page_errors)
        browser.close()

    print("Routed page smoke passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

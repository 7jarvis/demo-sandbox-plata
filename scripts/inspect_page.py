"""Look at a real page before writing locators.

Prints the accessibility tree of a page (what role/name locators see) and,
for each --check selector, how many elements it matches. Use it when the
Playwright MCP server is not available to the agent.

    python scripts/inspect_page.py /register
    python scripts/inspect_page.py /cards --sign-in +525512345678 \\
        --check 'role=button[name="Freeze card"]' --check '[data-testid=card-balance]'

Exact role-name match: role=button[name="Freeze card"s] (the trailing s).
"""

from __future__ import annotations

import argparse
import os

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="page path, e.g. /cards")
    parser.add_argument("--sign-in", metavar="PHONE", help="sign in as this registered customer first")
    parser.add_argument("--check", action="append", default=[], help="selector to count (repeatable)")
    parser.add_argument("--width", type=int, default=1280)
    args = parser.parse_args()

    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    code = os.getenv("SANDBOX_OTP_CODE", "111111")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(base_url=base_url, viewport={"width": args.width, "height": 900})
        if args.sign_in:
            context.request.post("/login", form={"phone": args.sign_in})
            context.request.post("/login/code", form={"code": code})
        page = context.new_page()
        page.goto(args.path)
        print(f"# {page.url}\n")
        print(page.locator("body").aria_snapshot())
        if args.check:
            print("\n# selector counts (a locator for an action must match exactly 1)")
            for selector in args.check:
                print(f"{page.locator(selector).count():>3}  {selector}")
        browser.close()


if __name__ == "__main__":
    main()

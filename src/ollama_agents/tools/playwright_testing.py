"""Playwright Browser Automated UI Testing Tool for Ollama Agents.

Provides end-to-end user acceptance testing (UAT), visual verification,
form submission, and screenshot capture for web applications.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

WORKSPACE_TESTS_DIR = Path.home() / "ollama_workspace" / "test_screenshots"


def test_ui_playwright(
    url: str = "http://localhost:8100",
    actions: Optional[list] = None,
    viewport_width: int = 1280,
    viewport_height: int = 720,
    headless: bool = True
) -> str:
    """Run automated Playwright User Acceptance Testing (UAT) on a Web UI URL.

    Args:
        url: Target web page URL to navigate and test (default 'http://localhost:8100').
        actions: Optional list of interaction dictionaries to execute in order.
                 Supported action dicts:
                 - {"type": "click", "selector": "#my-btn"}
                 - {"type": "fill", "selector": "#input-id", "value": "text"}
                 - {"type": "wait", "timeout": 2000}
                 - {"type": "screenshot", "name": "step1.png"}
        viewport_width: Browser viewport width (default 1280).
        viewport_height: Browser viewport height (default 720).
        headless: Run browser in headless mode (default True).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Error: playwright library is required. Run `pip install playwright && playwright install chromium`."

    try:
        WORKSPACE_TESTS_DIR.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        
        logs = []
        captured_screenshots = []

        with sync_playwright() as p:
            logger.info("Launching Playwright Chromium browser for UAT on %s...", url)
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height}
            )
            page = context.new_page()

            logs.append(f"[*] Navigating to {url}...")
            response = page.goto(url, wait_until="networkidle", timeout=30000)
            status_code = response.status if response else 0
            page_title = page.title()
            logs.append(f"[+] Page loaded with HTTP status {status_code}. Title: '{page_title}'")

            # Default initial page screenshot
            init_shot_name = f"uat_init_{timestamp}.png"
            init_shot_path = WORKSPACE_TESTS_DIR / init_shot_name
            page.screenshot(path=str(init_shot_path), full_page=True)
            captured_screenshots.append((init_shot_name, f"/workspace/test_screenshots/{init_shot_name}"))

            if actions:
                for idx, act in enumerate(actions, 1):
                    act_type = act.get("type", "").lower()
                    if act_type == "click":
                        sel = act.get("selector", "")
                        page.wait_for_selector(sel, timeout=10000)
                        page.click(sel)
                        logs.append(f"[{idx}] Clicked element '{sel}'")
                    elif act_type == "fill":
                        sel = act.get("selector", "")
                        val = act.get("value", "")
                        page.wait_for_selector(sel, timeout=10000)
                        page.fill(sel, val)
                        logs.append(f"[{idx}] Filled element '{sel}' with value '{val}'")
                    elif act_type == "wait":
                        t_ms = act.get("timeout", 1000)
                        page.wait_for_timeout(t_ms)
                        logs.append(f"[{idx}] Waited {t_ms}ms")
                    elif act_type == "screenshot":
                        custom_name = act.get("name", f"step_{idx}_{timestamp}.png")
                        shot_path = WORKSPACE_TESTS_DIR / custom_name
                        page.screenshot(path=str(shot_path))
                        captured_screenshots.append((custom_name, f"/workspace/test_screenshots/{custom_name}"))
                        logs.append(f"[{idx}] Captured screenshot '{custom_name}'")

            browser.close()

        # Format output message
        result_msg = [
            "=== Playwright Automated User Acceptance Test (UAT) Result ===",
            "\n".join(logs),
            "\nVisual Verification Screenshots:"
        ]
        for sname, surl in captured_screenshots:
            result_msg.append(f"- Saved: ~/ollama_workspace/test_screenshots/{sname}\n  ![UAT Screenshot]({surl})")

        return "\n\n".join(result_msg)

    except Exception as e:
        return f"[Playwright UAT Error]: {type(e).__name__}: {e}"

"""Capture real screenshots of the Streamlit UI (needs: pip install playwright; uses installed Edge)."""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
PORT = 8611
URL = f"http://localhost:{PORT}"

server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(PORT),
                           "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                          cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(URL, timeout=2)
            break
        except Exception:
            time.sleep(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(URL)
        page.get_by_role("button", name="Run negotiation").wait_for(timeout=60000)
        page.screenshot(path=str(OUT / "ui_00_start.png"))
        page.get_by_role("button", name="Run negotiation").click()
        page.get_by_text("Constraint violations").first.wait_for(timeout=60000)
        time.sleep(2)
        page.screenshot(path=str(OUT / "ui_01_negotiation.png"), full_page=True)
        for i, (tab, name) in enumerate([("Protocol evolution", "ui_02_protocol"),
                                         ("Single vs multi-agent", "ui_03_comparison"),
                                         ("Constraint audit", "ui_04_audit")]):
            page.get_by_role("tab", name=tab).click()
            time.sleep(4)
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
        browser.close()
finally:
    server.terminate()
print("done")

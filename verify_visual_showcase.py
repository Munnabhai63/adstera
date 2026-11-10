# verify_visual_showcase.py
import asyncio
from playwright.async_api import async_playwright
import os

ARTIFACT_DIR = r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88"

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # 1. Desktop RechargeTak Home
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("https://rechargetak.com", wait_until="networkidle", timeout=30000)
        await page.screenshot(path=os.path.join(ARTIFACT_DIR, "rechargetak_home.png"), full_page=False)
        print("Captured rechargetak_home.png")
        
        # 2. Desktop TazaLoan Article
        await page.goto("https://tazaloan.com/low-interest-personal-loans-2026", wait_until="networkidle", timeout=30000)
        await page.screenshot(path=os.path.join(ARTIFACT_DIR, "tazaloan_post.png"), full_page=False)
        print("Captured tazaloan_post.png")

        # 3. Desktop TazaBhav Home
        await page.goto("https://tazabhav.com", wait_until="networkidle", timeout=30000)
        await page.screenshot(path=os.path.join(ARTIFACT_DIR, "tazabhav_home.png"), full_page=False)
        print("Captured tazabhav_home.png")

        # 4. Mobile LoanKiSeva
        mobile_page = await browser.new_page(viewport={"width": 390, "height": 844})
        await mobile_page.goto("https://loankiseva.com/pmmy-mudra-loan-apply-online", wait_until="networkidle", timeout=30000)
        await mobile_page.screenshot(path=os.path.join(ARTIFACT_DIR, "loankiseva_mobile.png"), full_page=False)
        print("Captured loankiseva_mobile.png")
        
        await browser.close()

asyncio.run(capture())

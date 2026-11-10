import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        
        # 1. Category Insurance Page
        resp = await page.goto("https://660fbd95.loanraaj.pages.dev/category/insurance", wait_until="networkidle")
        print("Category Insurance status:", resp.status)
        await page.screenshot(path=r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88\category_insurance.png")

        # 2. Privacy Policy Page
        resp = await page.goto("https://660fbd95.loanraaj.pages.dev/privacy-policy", wait_until="networkidle")
        print("Privacy Policy status:", resp.status)
        await page.screenshot(path=r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88\privacy_policy.png")

        await browser.close()

asyncio.run(run())

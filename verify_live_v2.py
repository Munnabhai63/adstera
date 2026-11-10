import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # 1. Desktop Homepage
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("https://4384e357.loanraaj.pages.dev", wait_until="networkidle")
        await page.screenshot(path=r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88\loanraaj_v2_home.png", full_page=False)
        print("Captured loanraaj_v2_home.png")
        
        # 2. Desktop Single Article with Full Content
        await page.goto("https://4384e357.loanraaj.pages.dev/how-to-get-an-instant-loan", wait_until="networkidle")
        await page.screenshot(path=r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88\loanraaj_v2_post.png", full_page=False)
        print("Captured loanraaj_v2_post.png")

        # 3. Mobile View
        mobile_page = await browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
        await mobile_page.goto("https://4384e357.loanraaj.pages.dev/21-machines-to-start-a-profitable-home-business", wait_until="networkidle")
        await mobile_page.screenshot(path=r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88\loanraaj_v2_mobile.png", full_page=False)
        print("Captured loanraaj_v2_mobile.png")

        await browser.close()

asyncio.run(run())

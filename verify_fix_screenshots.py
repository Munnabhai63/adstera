import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # 1. Desktop Post (the exact post user screenshotted)
        page = await browser.new_page(viewport={"width": 1440, "height": 950})
        await page.goto("https://28ff4881.loanraaj.pages.dev/how-i-went-from-broke-to-80000-a-year-by-trucking", wait_until="networkidle")
        await page.screenshot(path=r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88\fixed_post_desktop.png", full_page=False)
        print("Captured fixed_post_desktop.png")

        # Scroll down and capture middle section showing typography and sidebar aligned
        await page.evaluate("window.scrollBy(0, 750)")
        await asyncio.sleep(0.5)
        await page.screenshot(path=r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88\fixed_post_reading.png", full_page=False)
        print("Captured fixed_post_reading.png")

        # 2. Desktop Instant Loan Post
        await page.goto("https://28ff4881.loanraaj.pages.dev/how-to-get-an-instant-loan", wait_until="networkidle")
        await page.screenshot(path=r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88\fixed_instant_loan.png", full_page=False)
        print("Captured fixed_instant_loan.png")

        # 3. Mobile View
        mobile_page = await browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
        await mobile_page.goto("https://28ff4881.loanraaj.pages.dev/how-i-went-from-broke-to-80000-a-year-by-trucking", wait_until="networkidle")
        await mobile_page.screenshot(path=r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88\fixed_post_mobile.png", full_page=False)
        print("Captured fixed_post_mobile.png")

        await browser.close()

asyncio.run(run())

import asyncio
from playwright.async_api import async_playwright
import os

async def capture_english_showcase():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Desktop
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("https://loanraaj.com", wait_until="networkidle", timeout=20000)
        
        artifact_dir = r"C:\Users\munaf\.gemini\antigravity\brain\39572c19-1aa0-4fef-bf2c-bb3cae2f0f88"
        desktop_shot = os.path.join(artifact_dir, "loanraaj_english_desktop.png")
        await page.screenshot(path=desktop_shot, full_page=False)
        print(f"Captured: {desktop_shot}")
        
        # Single Post
        await page.goto("https://loanraaj.com/hotshot-trucking-insurance", wait_until="networkidle", timeout=20000)
        post_shot = os.path.join(artifact_dir, "loanraaj_english_post.png")
        await page.screenshot(path=post_shot, full_page=False)
        print(f"Captured: {post_shot}")

        # Mobile
        mobile_page = await browser.new_page(viewport={"width": 390, "height": 844})
        await mobile_page.goto("https://loanraaj.com", wait_until="networkidle", timeout=20000)
        mobile_shot = os.path.join(artifact_dir, "loanraaj_english_mobile.png")
        await mobile_page.screenshot(path=mobile_shot, full_page=False)
        print(f"Captured: {mobile_shot}")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(capture_english_showcase())

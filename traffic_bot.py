"""
traffic_bot.py — Standalone traffic automation & metrics tracker script from automation.md.
Uses Selenium WebDriver, proxy rotation, human-like behavior, and CSV metrics tracking.
"""
from __future__ import annotations

import os
import random
import time
from pathlib import Path

import pandas as pd
import requests
import yaml
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from a YAML file with sensible defaults."""
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        return {
            "website_url": "https://example.com/article",
            "proxy_api_url": "",
            "num_visitors_per_minute": 5,
            "target_impressions": 1000,
            "target_clicks": 50,
            "target_revenue": 10.0,
            "user_agents": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
                "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
            ],
        }
    with open(cfg_file, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    # Support nested target dict from our existing config.yaml if present
    if "target" in data and "website_url" not in data:
        data["website_url"] = data["target"].get("url", "https://example.com/article")
    if "proxy" in data and "proxy_api_url" not in data:
        data["proxy_api_url"] = data["proxy"].get("api_url", "")
    data.setdefault("num_visitors_per_minute", 5)
    data.setdefault("target_impressions", 1000)
    data.setdefault("target_clicks", 50)
    data.setdefault("target_revenue", 10.0)
    return data


def setup_driver(proxy: str = "", user_agent: str = "") -> webdriver.Chrome:
    """Set up Selenium with proxy, realistic user-agent and disabled automation flags."""
    chrome_options = Options()
    # Check headless mode setting
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    if proxy:
        chrome_options.add_argument(f"--proxy-server={proxy}")
    if user_agent:
        chrome_options.add_argument(f"user-agent={user_agent}")

    # Disable automation flags
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=chrome_options)
    return driver


def get_proxies(api_url: str) -> list[str]:
    """Get a list of proxies from an API or fallback to local proxies.txt."""
    if api_url:
        try:
            response = requests.get(api_url, timeout=10)
            data = response.json()
            if isinstance(data, list):
                return [p if isinstance(p, str) else f"{p.get('host')}:{p.get('port')}" for p in data]
            if isinstance(data, dict) and "data" in data:
                return data["data"]
        except Exception as exc:
            print(f"Warning: Could not fetch proxies from API ({exc}). Checking proxies.txt...")

    # Fallback to local proxies.txt
    p_file = Path("proxies.txt")
    if p_file.exists():
        lines = [ln.strip() for ln in p_file.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
        if lines:
            return lines
    return ["direct"]


def simulate_human_behavior(driver: webdriver.Chrome) -> None:
    """Simulate human-like behavior: mouse movement, random link click, eased scroll."""
    try:
        # Move mouse to random positions
        win_size = driver.get_window_size()
        width = win_size.get("width", 1280)
        height = win_size.get("height", 800)
        x = random.randint(100, max(100, width - 100))
        y = random.randint(100, max(100, height - 100))
        ActionChains(driver).move_by_offset(x, y).perform()

        # Randomly click on elements if present
        elements = driver.find_elements(By.TAG_NAME, "a")
        if elements and random.random() < 0.25:
            try:
                random.choice(elements[:5]).click()
            except Exception:
                pass
        time.sleep(random.uniform(1.0, 2.5))

        # Randomly scroll
        scroll_height = driver.execute_script("return document.body.scrollHeight") or 1000
        for _ in range(3):
            scroll_pos = random.randint(200, max(200, int(scroll_height * 0.8)))
            driver.execute_script(f"window.scrollTo({{top: {scroll_pos}, behavior: 'smooth'}});")
            time.sleep(random.uniform(1.2, 2.2))
    except Exception as exc:
        print(f"Behavior simulation warning: {exc}")


def visit_website(driver: webdriver.Chrome, url: str) -> bool:
    """Visit the target website and simulate realistic dwell and interaction."""
    try:
        driver.get(url)
        time.sleep(random.uniform(5.0, 10.0))
        simulate_human_behavior(driver)
        driver.quit()
        return True
    except Exception as exc:
        print(f"Error visiting {url}: {exc}")
        try:
            driver.quit()
        except Exception:
            pass
        return False


def load_stats(stats_file: str = "stats.csv") -> pd.DataFrame:
    """Load stats from CSV file, creating it if not present."""
    p = Path(stats_file)
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame(columns=["Date", "Impressions", "Clicks", "CTR", "CPM", "Revenue"])
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame(columns=["Date", "Impressions", "Clicks", "CTR", "CPM", "Revenue"])


def update_stats(stats_file: str, impressions: int, clicks: int, revenue: float) -> None:
    """Update stats file with impressions, clicks, CTR, CPM, and revenue."""
    stats = load_stats(stats_file)
    date = pd.Timestamp.now().strftime("%Y/%m/%d %H:%M")
    cpm = (revenue / impressions) * 1000 if impressions > 0 else 0.0
    ctr = (clicks / impressions) * 100 if impressions > 0 else 0.0
    new_row = pd.DataFrame({
        "Date": [date],
        "Impressions": [impressions],
        "Clicks": [clicks],
        "CTR": [f"{ctr:.2f}%"],
        "CPM": [f"${cpm:.2f}"],
        "Revenue": [f"${revenue:.2f}"],
    })
    stats = pd.concat([stats, new_row], ignore_index=True)
    stats.to_csv(stats_file, index=False)


def main() -> None:
    """Main orchestration loop."""
    config = load_config("config.yaml")
    url = config.get("website_url") or "https://example.com/article"
    proxy_api_url = config.get("proxy_api_url", "")
    num_visitors = config.get("num_visitors_per_minute", 5)
    target_impressions = config.get("target_impressions", 1000)
    target_clicks = config.get("target_clicks", 50)
    target_revenue = config.get("target_revenue", 10.0)
    stats_file = "stats.csv"

    # User agents from useragent.in or config
    user_agents = config.get("user_agents", [])
    try:
        import ua_provider
        cached_uas = ua_provider.get_desktop_uas() + ua_provider.get_mobile_uas()
        if cached_uas:
            user_agents = cached_uas
    except Exception:
        pass

    if not user_agents:
        user_agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"]

    proxies = get_proxies(proxy_api_url)
    proxy_count = len(proxies)
    ua_count = len(user_agents)

    impressions = 0
    clicks = 0
    revenue = 0.0

    print("=" * 60)
    print(">> Starting Traffic Bot (automation.md spec)")
    print(f">> Target URL: {url}")
    print(f">> Proxy Pool: {proxy_count} | UA Pool: {ua_count} (useragent.in)")
    print(f">> Targets: {target_impressions} imps | {target_clicks} clicks | ${target_revenue:.2f} revenue")
    print("=" * 60)

    start_time = time.time()
    while impressions < target_impressions and revenue < target_revenue:
        for i in range(num_visitors):
            proxy = proxies[i % proxy_count] if proxies[0] != "direct" else ""
            ua = user_agents[random.randint(0, ua_count - 1)]
            try:
                driver = setup_driver(proxy=proxy, user_agent=ua)
                ok = visit_website(driver, url)
                if ok:
                    impressions += 1
                    click_prob = random.uniform(0.04, 0.08)
                    if random.random() < click_prob:
                        clicks += 1
                        revenue += random.uniform(0.02, 0.06)
            except Exception as loop_err:
                print(f"Session error: {loop_err}")

            time.sleep(random.uniform(0.5, 1.5))

        update_stats(stats_file, impressions, clicks, revenue)
        print(f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] Impressions: {impressions} | Clicks: {clicks} | Revenue: ${revenue:.2f}")

        elapsed = time.time() - start_time
        if elapsed < 60:
            time.sleep(60 - elapsed)
        start_time = time.time()


if __name__ == "__main__":
    main()


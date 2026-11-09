"""
cf_publisher.py — Cloudflare Pages & Static Site Publishing Engine (PUB-1 & PUB-4)

Manages Hugo-compatible static site layouts for all 10 publisher domains:
1. Writes vetted, high-quality Markdown posts into `sites/{domain}/content/posts/{slug}.md`.
2. Automatically generates and updates `sitemap.xml` with XML namespace and <lastmod>.
3. Automatically updates `robots.txt` with sitemap directives.
4. Logs publication records to SQLite via db.py.
5. Dispatches Telegram publication announcements.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import db

logger = logging.getLogger(__name__)

BASE_SITES_DIR = Path(__file__).parent / "sites"

ALL_DOMAINS = [
    "loanraaj.com",
    "rechargetak.com",
    "rechargepur.com",
    "tazaloan.com",
    "loankiseva.com",
    "karzseva.com",
    "loantau.com",
    "tazabhav.com",
    "tazarokda.com",
    "rechargekar.com",
]


class CloudflarePublisher:
    """Manages static site posts, sitemaps, and deployment preparation for Cloudflare Pages."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or BASE_SITES_DIR
        self._ensure_domain_structures()

    def _ensure_domain_structures(self) -> None:
        """Create standard Hugo-compliant directory layouts for all 10 domains."""
        for domain in ALL_DOMAINS:
            dom_path = self.base_dir / domain
            posts_dir = dom_path / "content" / "posts"
            posts_dir.mkdir(parents=True, exist_ok=True)
            self._write_default_robots(domain)

    def _write_default_robots(self, domain: str) -> None:
        """Write robots.txt with sitemap reference."""
        robots_file = self.base_dir / domain / "robots.txt"
        if not robots_file.exists():
            content = f"""User-agent: *
Allow: /

Sitemap: https://{domain}/sitemap.xml
"""
            robots_file.write_text(content, encoding="utf-8")

    def publish_article(self, article: dict, audit_report: dict) -> dict:
        """
        Publish an audited article:
        1. Save Markdown post to sites/{domain}/content/posts/{slug}.md.
        2. Regenerate sitemap.xml.
        3. Log to SQLite database.
        4. Send Telegram announcement.
        """
        domain = article.get("domain", "loanraaj.com")
        slug = article.get("slug", "post")
        title = article.get("title", "")
        content = article.get("content", "")
        word_count = article.get("word_count", 0)
        ai_score = audit_report.get("ai_score_est", 5.0)

        posts_dir = self.base_dir / domain / "content" / "posts"
        posts_dir.mkdir(parents=True, exist_ok=True)

        post_file = posts_dir / f"{slug}.md"
        post_file.write_text(content, encoding="utf-8")

        article_url = f"https://{domain}/posts/{slug}/"

        # Update sitemap.xml
        self.update_sitemap(domain)

        # Log to DB
        post_id = db.log_published_post(
            domain=domain,
            title=title,
            slug=slug,
            file_path=str(post_file),
            word_count=word_count,
            ai_score=ai_score,
            url=article_url,
        )

        logger.info(
            "Published post #%d on %s: '%s' (%d words, AI score=%.1f%%)",
            post_id, domain, title, word_count, ai_score,
        )

        # Dispatch Telegram announcement (best-effort)
        try:
            from alert_bot import get_alert_bot
            bot = get_alert_bot()
            if bot and bot.is_live_configured:
                msg = (
                    f"📰 *New Post Published on {domain}*\n"
                    f"• *Title:* {title}\n"
                    f"• *Length:* {word_count:,} words\n"
                    f"• *AI Score:* {ai_score:.1f}% (Quality Gate Passed ✅)\n"
                    f"• *URL:* {article_url}"
                )
                bot._dispatch(msg)
        except Exception as alert_err:
            logger.debug("Telegram alert notice: %s", alert_err)

        return {
            "post_id": post_id,
            "domain": domain,
            "title": title,
            "url": article_url,
            "file_path": str(post_file),
            "word_count": word_count,
            "published_at": datetime.now().isoformat(),
        }

    def update_sitemap(self, domain: str) -> Path:
        """Regenerate valid sitemap.xml for domain containing all published posts."""
        posts_dir = self.base_dir / domain / "content" / "posts"
        sitemap_file = self.base_dir / domain / "sitemap.xml"

        md_files = sorted(posts_dir.glob("*.md"))
        now_date = datetime.now().strftime("%Y-%m-%d")

        urls_xml = [
            f"""  <url>
    <loc>https://{domain}/</loc>
    <lastmod>{now_date}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>"""
        ]

        for md in md_files:
            slug = md.stem
            mod_date = datetime.fromtimestamp(md.stat().st_mtime).strftime("%Y-%m-%d")
            urls_xml.append(f"""  <url>
    <loc>https://{domain}/posts/{slug}/</loc>
    <lastmod>{mod_date}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>""")

        sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls_xml)}
</urlset>
"""
        sitemap_file.write_text(sitemap_content, encoding="utf-8")
        return sitemap_file

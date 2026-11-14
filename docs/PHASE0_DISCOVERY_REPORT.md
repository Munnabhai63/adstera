# PHASE 0 — DISCOVERY AUDIT REPORT

| Item | Measured Value | Command / Script Used |
|---|---|---|
| **0.1 Current Branch** | `step2-content-and-guards` | `git rev-parse --abbrev-ref HEAD` |
| **0.1 Head SHA** | `fba21676adf840cc4950548a1ae477b4a8b3e89b` | `git rev-parse HEAD` |
| **0.1 Working Tree Status** | Clean (0 uncommitted files) | `git status --porcelain` |
| **0.1 Recent Commits** | 12 commits listed (5 on step2, 3 on step1, 4 on docs) | `git log --oneline -12` |
| **0.1 Remote Heads** | `master (e7a054c)`, `step1-seo-unblock (8564fee)`, `step2-content-and-guards (fba2167)` | `git ls-remote --heads origin` |
| **0.2 .env Exists** | `True` | `Path('.env').is_file()` |
| **0.2 FREELLMAPI Token Set** | `True` (found in `.env`) | `os.getenv('FREELLMAPI_TOKEN')` |
| **0.2 Cloudflare Tunnel Token** | `True` (found in `.env`) | `os.getenv('CLOUDFLARE_TUNNEL_TOKEN')` |
| **0.2 GSC Service Account** | `True` (`mahi-assistant@prosports-467807.iam.gserviceaccount.com`) | `gsc_auth.GSCAuthManager().is_configured()` |
| **0.2 proxies.txt Status** | Exists, 0 valid lines (clean placeholder) | `pool.validate_proxy_lines()` |
| **0.2 vendor/claude_seo/** | `False` (not yet created) | `Path('vendor/claude_seo').is_dir()` |
| **0.2 Claude-SEO Modules** | Present at `F:\UserData\Downloads\ai-power-tools\claude-seo\scripts` | `python -c "import seo_pipeline as s; ..."` |
| **0.3 Total HTML Files** | 474 | `len(list(Path('sites').rglob('*.html')))` |
| **0.3 Sites Directory Size** | 139.4 MB (146,173,281 bytes) | Sum of file stat sizes |
| **0.3 Total Real Articles** | 279 articles across 10 domains | `scripts/preflight_seo.py` |
| **0.3 Total Images in img/** | 1,240 webp images (124 per domain) | `len(list(Path('sites/*/img').glob('*')))` |
| **0.3 Total Sitemap Locs** | 404 URLs across 10 sitemaps | `sitemap.xml <loc>` regex count |
| **0.4 Prose Words >= 1200** | 25 articles | `scratch/measure_all_articles.py` |
| **0.4 Prose Words >= 2000** | 14 articles | `scratch/measure_all_articles.py` |
| **0.4 Prose Words >= 3000** | 3 articles | `scratch/measure_all_articles.py` |
| **0.5 Duplicate Paragraphs (>=12w)** | 47 unique paragraphs across >1 page | `scratch/phase0_duplication.py` |
| **0.5 Corpus Duplicate Words** | 80,068 words (21.27% of 376,350 total body words) | `scratch/phase0_duplication.py` |
| **0.5 Top Duplicate Occurrence** | 8 paragraphs appearing on 163 pages each | `scratch/phase0_duplication.py` |
| **0.6 Fallback String Match** | `autopublish_engine.py:319` | `git grep -n "Comprehensive Market Comparison"` |
| **0.6 Pages With Fallback** | 163 live pages | Regex search across `sites/**/*.html` |
| **0.7 Title Length 45-60** | 27 / 279 pass (252 outside range) | `scratch/phase0_onpage.py` |
| **0.7 Dangling Titles** | 6 / 279 fail | `scratch/phase0_onpage.py` |
| **0.7 Meta Desc Length 120-160** | 260 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 Meta Desc Has Focus KW** | 198 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 Exactly One H1** | 279 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 KW in First 100 Words** | 274 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 In-body Internal Links >= 3**| 185 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 In-content Images >= 5** | 279 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 Alt Text Not Copy of Title** | 106 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 OG Tags Present** | 39 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 Twitter Cards Present** | 33 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 FAQPage Schema** | 92 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 BreadcrumbList Schema** | 92 / 279 pass | `scratch/phase0_onpage.py` |
| **0.7 Article Schema Compliant** | 194 / 279 pass (standalone nodes) | `scratch/phase0_onpage.py` |
| **0.7 Meta Keywords Present** | 0 / 279 (cleanly omitted) | `scratch/phase0_onpage.py` |
| **0.8 Claude-SEO Score Avg/Med** | Mean: 79.22, Median: 88.90, Min: 33.30, 100s: 32 | `scratch/phase0_claude_seo_audit.py` |
| **0.9 Article Nodes Count** | 286 nodes across corpus (7 pages have 2 nodes) | `scratch/phase0_schema.py` |
| **0.9 Stale .html mainEntityOfPage**| 7 pages have conflicting .html entity URLs | `scratch/phase0_schema.py` |
| **0.10 Dry-Run URLs Discovered** | 379 URLs across fleet (31 to 73 per domain) | `python instant_indexer.py --dry-run` |
| **0.10 Stale Flat Conflicts** | 40 URLs point to flat .html when dir/index exists | `scratch/phase0_indexer.py` |
| **0.11 Test Suite Status** | 29/29 Step 1 & 2 tests pass; 0 non-browser failures | `python -m pytest -q` |
| **0.12 Article Internal Links** | 768 total internal links | `scratch/phase0_link_graph.py` |
| **0.12 Broken Links if Keep 2** | 724 would break (56 from surviving 20 articles) | `scratch/phase0_link_graph.py` |
| **0.13 Image Blindness Example** | `sites/loanraaj.com/21-machines-business/index.html` (5 sidebar thumbnails, 0 in body) | `scratch/find_sidebar_only.py` |

### Discrepancy Disclosures
1. **Title Length & Dangling Count**: Measured 252 titles outside 45-60 characters (prompt estimated ~253) and 6 ending in prepositions/colons (prompt estimated 13).
2. **Fallback Pages**: Measured 163 pages containing `Comprehensive Market Comparison` (162 expanded in S2-D + 1 pre-existing).
3. **Environmental Browser Tests**: In environments without Playwright Chromium installed, exactly 13 tests fail with `BrowserType.launch: Executable doesn't exist`. On workstations with Chromium installed, browser tests launch.

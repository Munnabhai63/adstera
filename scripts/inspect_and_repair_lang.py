"""
scripts/inspect_and_repair_lang.py — Detect Devanagari ratio and repair <html lang="..."> and hugo.toml.
"""
import glob
import re
from pathlib import Path

DEV_RE = re.compile(r'[\u0900-\u097F]')

def process_file(path: Path) -> tuple[str, str, bool]:
    content = path.read_text(encoding='utf-8', errors='ignore')
    text_sample = re.sub(r'<[^>]+>', ' ', content)
    total_chars = len(re.sub(r'\s+', '', text_sample))
    dev_chars = len(DEV_RE.findall(text_sample))
    dev_ratio = (dev_chars / total_chars) if total_chars > 0 else 0.0

    expected_lang = 'hi' if dev_ratio >= 0.10 else 'en'
    match = re.search(r'(<html[^>]*\s+lang=["\'])([^"\']+)(["\'])', content, re.IGNORECASE)
    if not match:
        # If no lang tag on <html>, insert it
        new_content = re.sub(r'<html(\s*>)', rf'<html lang="{expected_lang}"\1', content, count=1, flags=re.IGNORECASE)
        path.write_text(new_content, encoding='utf-8')
        return ('missing', expected_lang, True)

    curr_lang = match.group(2)
    if curr_lang != expected_lang:
        new_content = content[:match.start(2)] + expected_lang + content[match.end(2):]
        path.write_text(new_content, encoding='utf-8')
        return (curr_lang, expected_lang, True)

    return (curr_lang, expected_lang, False)

def main():
    fixed_count = 0
    total_count = 0
    en_count = 0
    hi_count = 0

    all_html = list(Path('sites').glob('*/*.html')) + list(Path('sites').glob('*/*/*.html'))
    for p in all_html:
        if not p.is_file() or p.name == '404.html':
            continue
        total_count += 1
        curr, exp, changed = process_file(p)
        if changed:
            fixed_count += 1
        if exp == 'hi':
            hi_count += 1
        else:
            en_count += 1

    print(f"Processed {total_count} pages: {en_count} EN, {hi_count} HI. Fixed {fixed_count} language tag mismatches.")

    # Also check hugo.toml files
    hugo_fixed = 0
    for h in Path('sites').glob('*/hugo.toml'):
        txt = h.read_text(encoding='utf-8', errors='ignore')
        if 'languageCode = "hi"' in txt or 'defaultContentLanguage = "hi"' in txt:
            # Check predominant articles in this domain
            dom = h.parent.name
            dom_articles = list(h.parent.glob('*.html'))
            hi_arts = 0
            for a in dom_articles:
                if 'lang="hi"' in a.read_text(encoding='utf-8', errors='ignore'):
                    hi_arts += 1
            if hi_arts < len(dom_articles) / 2:
                # Mostly english
                txt = txt.replace('languageCode = "hi"', 'languageCode = "en"')
                txt = txt.replace('defaultContentLanguage = "hi"', 'defaultContentLanguage = "en"')
                h.write_text(txt, encoding='utf-8')
                hugo_fixed += 1
    print(f"Checked hugo.toml configs. Updated {hugo_fixed} configs.")

if __name__ == '__main__':
    main()

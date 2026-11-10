from bs4 import BeautifulSoup, Tag
import json
import re

def clean_to_semantic_blocks(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Strip scripts, styles, forms, inputs, buttons, iframes
    for tag in soup(['script', 'style', 'iframe', 'form', 'input', 'button', 'textarea', 'select', 'noscript']):
        tag.decompose()
        
    # 2. Decompose known junk IDs/classes
    junk_markers = ['mvp-content-bot', 'mvp-post-tags', 'mvp-post-soc', 'posts-nav-link', 'comments', 'code-block', 'author-box']
    for tag in list(soup.find_all(True)):
        if not isinstance(tag, Tag) or tag.attrs is None:
            continue
        tag_id = tag.attrs.get('id', '')
        tag_classes = ' '.join(tag.attrs.get('class', []))
        if any(m in str(tag_id).lower() or m in str(tag_classes).lower() for m in junk_markers):
            tag.decompose()
            continue
        # Also remove if text has RIDE ALONG
        if 'RIDE ALONG' in tag.get_text():
            tag.decompose()

    # 3. Now collect only clean content blocks
    blocks = []
    # Find all paragraph, heading, list, table, blockquote, and img tags
    for el in soup.find_all(['h2', 'h3', 'h4', 'p', 'ul', 'ol', 'table', 'blockquote']):
        if not isinstance(el, Tag):
            continue
        # If inside another block (like p inside blockquote or li inside ul), skip parent handling
        if el.parent and el.parent.name in ['ul', 'ol', 'blockquote', 'table']:
            continue
            
        text = el.get_text().strip()
        
        # Check if element only contains junk or empty
        if not text and not el.find('img'):
            continue
            
        # Clean specific phrases
        if any(junk in text for junk in ['window.googletag', 'googletag.cmd', 'Related Posts', 'Advertisement']):
            continue

        if el.name in ['h2', 'h3', 'h4']:
            clean_head = re.sub(r'\s+', ' ', text)
            blocks.append(f'<{el.name}>{clean_head}</{el.name}>')
        elif el.name == 'p':
            # Check if this paragraph contains an image
            imgs = el.find_all('img')
            if imgs:
                for img in imgs:
                    src = img.attrs.get('src', '') if img.attrs else ''
                    alt = img.attrs.get('alt', '') if img.attrs else ''
                    if src and not src.startswith('data:'):
                        blocks.append(f'<div class="article-inner-img"><img src="{src}" alt="{alt}" loading="lazy"></div>')
            # Sanitize inline links
            for a in el.find_all('a'):
                if a.attrs:
                    href = a.attrs.get('href', '')
                    if 'bazartak.net/' in href or 'kamtak.in/' in href:
                        slug = href.strip('/').split('/')[-1]
                        a['href'] = f'/{slug}'
                    a.attrs = {'href': a.attrs.get('href', '#')}
            # Remove inline styles from inner tags
            for child in el.find_all(True):
                if child.name not in ['a', 'strong', 'b', 'em', 'i']:
                    child.unwrap()
                else:
                    child.attrs = {k: v for k, v in child.attrs.items() if k in ['href', 'target']}
            p_html = ''.join(str(c) for c in el.contents).strip()
            if p_html and p_html != '&nbsp;':
                blocks.append(f'<p>{p_html}</p>')
        elif el.name in ['ul', 'ol']:
            items = []
            for li in el.find_all('li', recursive=False):
                li_text = li.get_text().strip()
                if li_text:
                    items.append(f'<li>{li_text}</li>')
            if items:
                blocks.append(f'<{el.name}>' + ''.join(items) + f'</{el.name}>')
        elif el.name == 'blockquote':
            bq_text = el.get_text().strip()
            if bq_text:
                blocks.append(f'<blockquote><p>{bq_text}</p></blockquote>')
        elif el.name == 'table':
            rows = []
            for tr in el.find_all('tr'):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    tag_name = td.name
                    cells.append(f'<{tag_name}>{td.get_text().strip()}</{tag_name}>')
                if cells:
                    rows.append('<tr>' + ''.join(cells) + '</tr>')
            if rows:
                blocks.append('<div class="table-responsive"><table class="article-table">' + ''.join(rows) + '</table></div>')

    return '\n'.join(blocks)

with open('full_scraped_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

for slug in ['how-i-went-from-broke-to-80000-a-year-by-trucking', 'how-to-get-an-instant-loan', '21-machines-to-start-a-profitable-home-business']:
    art = next(a for a in articles if slug in a['slug'])
    res = clean_to_semantic_blocks(art['content'])
    print(f"\n[{slug}] Total semantic blocks generated: {len(res.splitlines())} lines | {len(res)} chars")
    print("Opening divs in content:", res.count('<div'), "Closing divs:", res.count('</div'))
    print("First 3 blocks:")
    for b in res.splitlines()[:3]:
        print(" ", b[:100])

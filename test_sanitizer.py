from bs4 import BeautifulSoup, Comment
import json
import re

with open('full_scraped_articles.json', 'r', encoding='utf-8') as f:
    articles = json.load(f)

# Find the broke-to-80000 article
target = next(a for a in articles if 'broke-to-80000' in a['slug'])

def sanitize_article_html(raw_html):
    soup = BeautifulSoup(raw_html, 'html.parser')
    
    # 1. Remove dangerous or unwanted tags
    for tag in soup(['script', 'style', 'iframe', 'form', 'input', 'button', 'textarea', 'select', 'noscript']):
        tag.decompose()
        
    # 2. Remove comments
    for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
        comment.extract()
        
    # 3. Remove unwanted widget divs
    unwanted_classes = ['code-block', 'ad', 'banner', 'share', 'social', 'relpost', 'newsletter', 'signup', 'author-box', 'wp-block-embed']
    for div in soup.find_all(['div', 'section', 'aside']):
        classes = div.get('class', [])
        if any(any(uc in c.lower() for uc in unwanted_classes) for c in classes):
            div.decompose()
            continue
        div_id = div.get('id', '')
        if any(uc in div_id.lower() for uc in unwanted_classes):
            div.decompose()
            continue
            
    # 4. Clean attributes from content elements
    for el in soup.find_all(True):
        # Keep href on a, src/alt on img
        if el.name == 'a':
            href = el.get('href', '')
            el.attrs = {'href': href}
            # Rewrite bazartak/kamtak to local
            if 'bazartak.net/' in href or 'kamtak.in/' in href:
                slug = href.strip('/').split('/')[-1]
                el['href'] = f'/{slug}'
        elif el.name == 'img':
            src = el.get('src', '')
            alt = el.get('alt', '')
            el.attrs = {
                'src': src,
                'alt': alt,
                'loading': 'lazy',
                'class': 'content-img'
            }
        elif el.name == 'table':
            el.attrs = {'class': 'content-table'}
        else:
            el.attrs = {}
            
    # 5. Remove empty tags
    for el in soup.find_all(['p', 'div', 'span', 'h2', 'h3', 'h4', 'ul', 'ol', 'li']):
        if not el.text.strip() and not el.find('img'):
            el.decompose()
            
    # Get clean inner HTML
    clean_html = ""
    for child in soup.contents:
        if hasattr(child, 'name') and child.name:
            clean_html += str(child) + "\n"
        elif isinstance(child, str) and child.strip():
            clean_html += f"<p>{child.strip()}</p>\n"
            
    return clean_html

cleaned = sanitize_article_html(target['content'])
print("Original length:", len(target['content']))
print("Cleaned length:", len(cleaned))
print("Opening divs in cleaned:", cleaned.count('<div'), "Closing divs:", cleaned.count('</div'))
print("\nFirst 800 chars of cleaned:")
print(cleaned[:800])
print("\nHas form or 'RIDE ALONG'?:", 'RIDE ALONG' in cleaned, 'form' in cleaned.lower())

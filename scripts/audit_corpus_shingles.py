import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bs4 import BeautifulSoup
from shingle_guard import (
    extract_prose_paragraphs,
    get_12_word_shingles,
    validate_text_quality,
    validate_domain_vocabulary,
    QualityPatternError,
    JargonViolationError
)
from scripts.seo_onpage_audit import get_all_article_paths, PROJECT_ROOT

sites_dir = PROJECT_ROOT / "sites"
articles = get_all_article_paths(sites_dir)

total_paragraphs = 0
jargon_rejections = 0
quality_rejections = 0
duplicate_shingle_rejections = 0

seen_shingles = {}
rejected_paras = []

for path in articles:
    domain = path.relative_to(sites_dir).parts[0]
    slug = path.parent.name if path.name == "index.html" else path.stem
    page_id = f"{domain}/{slug}"
    
    text = path.read_text(encoding="utf-8", errors="ignore")
    paras = extract_prose_paragraphs(text)
    total_paragraphs += len(paras)
    
    for p_idx, para in enumerate(paras):
        # 1. Quality check
        try:
            validate_text_quality(para)
        except QualityPatternError as e:
            quality_rejections += 1
            rejected_paras.append((page_id, p_idx, "QualityPatternError", str(e), para[:80]))
            continue
            
        # 2. Vocabulary check
        try:
            validate_domain_vocabulary(domain, para)
        except JargonViolationError as e:
            jargon_rejections += 1
            rejected_paras.append((page_id, p_idx, "JargonViolationError", str(e), para[:80]))
            continue
            
        # 3. Duplicate shingle check
        shingles = get_12_word_shingles(para)
        dup_found = False
        for s in shingles:
            if s in seen_shingles and seen_shingles[s] != page_id:
                dup_found = True
                duplicate_shingle_rejections += 1
                rejected_paras.append((page_id, p_idx, "DuplicateContentError", f"Collides with {seen_shingles[s]}", para[:80]))
                break
            seen_shingles[s] = page_id

total_rejected = len(rejected_paras)

print("========================================================================")
print(" SHINGLE GUARD AUDIT: FULL 279-ARTICLE CURRENT CORPUS")
print("========================================================================")
print(f"Total articles audited:             {len(articles)}")
print(f"Total paragraphs scanned:           {total_paragraphs}")
print(f"Total paragraphs rejected:          {total_rejected} ({total_rejected / total_paragraphs * 100:.2f}%)")
print(f"  - Quality violations:             {quality_rejections}")
print(f"  - Vocabulary jargon violations:   {jargon_rejections}")
print(f"  - Duplicate 12-word shingles:     {duplicate_shingle_rejections}")
print("========================================================================")
if rejected_paras:
    print(f"\nSample rejected paragraphs (first 5 of {total_rejected}):")
    for pid, p_idx, err_type, reason, snippet in rejected_paras[:5]:
        print(f"  [{pid} #p{p_idx}] {err_type}: {reason}")
        print(f"    Snippet: \"{snippet}...\"")

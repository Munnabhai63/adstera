# patch_loanraaj_meta.py
import os

META = '<meta name="google-site-verification" content="google31976c4df01121b2">'
count = 0
for r, _, files in os.walk('sites/loanraaj'):
    for f in files:
        if f.endswith('.html') and not f.startswith('google'):
            path = os.path.join(r, f)
            with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                txt = fp.read()
            if 'google-site-verification' not in txt and '<head>' in txt:
                txt = txt.replace('<head>', f'<head>\n    {META}')
                with open(path, 'w', encoding='utf-8') as fp:
                    fp.write(txt)
                count += 1

print(f"Patched {count} files in loanraaj with google verification meta tag.")

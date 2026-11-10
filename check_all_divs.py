import os
import glob

files = glob.glob(r'sites\loanraaj\*.html')
print(f"Total HTML files: {len(files)}")

broken_files = []
for f in files:
    with open(f, 'r', encoding='utf-8') as fp:
        content = fp.read()
    o = content.count('<div')
    c = content.count('</div')
    if o != c:
        broken_files.append((os.path.basename(f), o, c, o - c))

print(f"Files with unbalanced divs: {len(broken_files)} / {len(files)}")
for name, o, c, diff in broken_files[:10]:
    print(f"  {name}: <div={o}, </div={c} (diff: {diff})")

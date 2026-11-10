with open(r'sites\loanraaj\how-i-went-from-broke-to-80000-a-year-by-trucking.html', 'r', encoding='utf-8') as f:
    html = f.read()

print("Total length:", len(html))

# Count opening and closing divs
open_divs = html.count('<div')
close_divs = html.count('</div')
print(f"Opening divs: {open_divs}, Closing divs: {close_divs}")

# Check where main-layout is
main_idx = html.find('class="main-layout"')
print("main-layout at:", main_idx)

# Check where aside starts
aside_idx = html.find('<aside')
print("aside starts at:", aside_idx)

# Let's see what is immediately before <aside
print("200 chars before <aside:")
print(html[aside_idx-200:aside_idx])

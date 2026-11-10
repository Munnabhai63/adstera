with open(r'woblo_extracted\home-bazartak\index.html', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

idx = text.find('21 Machines')
if idx != -1:
    print("Found '21 Machines' at index:", idx)
    print(text[max(0, idx-200):idx+500])
else:
    print("'21 Machines' NOT found in woblo index.html")

with open(r'woblo_extracted\home-bazartak\index.html', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

idx = text.find('21 Machines')
print(text[max(0, idx-400):idx])

with open(r'woblo_extracted\home-bazartak\index.html', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

idx = text.find('21 Machines')
a_idx = text.rfind('<a ', 0, idx)
print("a_idx:", a_idx)
print(text[a_idx:a_idx+300])

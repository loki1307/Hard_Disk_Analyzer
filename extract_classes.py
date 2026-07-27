import re
import os

# Get the absolute path to the directory this script is in
script_dir = os.path.dirname(os.path.abspath(__file__))
index_path = os.path.join(script_dir, 'index.html')

with open(index_path, 'r', encoding='utf-8') as f:
    html = f.read()

classes = set(re.findall(r'class=\"([^\"]+)\"', html))
print('\n'.join(sorted(classes)))

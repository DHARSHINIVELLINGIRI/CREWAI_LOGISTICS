import os

def rename_in_files():
    base_dir = r"c:\projects\shipment"
    for root, dirs, files in os.walk(base_dir):
        if '.venv' in root or '.git' in root or '__pycache__' in root:
            continue
        for f in files:
            if f.endswith(('.py', '.md', '.yaml', '.css', '.html', '.txt')):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', encoding='utf-8') as file:
                        content = file.read()
                    if 'eShipz' in content:
                        content = content.replace('eShipz', 'eShipz')
                        with open(path, 'w', encoding='utf-8') as file:
                            file.write(content)
                        print(f"Updated {path}")
                except Exception as e:
                    pass

if __name__ == '__main__':
    rename_in_files()

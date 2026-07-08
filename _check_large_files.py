import subprocess, os

os.chdir(r'c:\Work')
result = subprocess.run(
    ['git', 'rev-list', '--objects', 'dev'],
    capture_output=True, text=True, encoding='utf-8', errors='replace'
)

for line in result.stdout.splitlines():
    obj_hash = line.split()[0]
    size_result = subprocess.run(
        ['git', 'cat-file', '-s', obj_hash],
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    try:
        size = int(size_result.stdout.strip())
    except ValueError:
        continue
    if size > 104_857_600:  # > 100 MB
        print(f'{size:>15} {line}')
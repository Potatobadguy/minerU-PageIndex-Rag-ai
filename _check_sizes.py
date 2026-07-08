import subprocess, os

# Get all tracked files
result = subprocess.run(['git', 'ls-tree', '-r', 'HEAD', '--name-only'], capture_output=True, text=True)
files = [l.strip().strip('"') for l in result.stdout.splitlines() if l.strip() and 'CLIXML' not in l]

# Get sizes
sizes = []
for f in files:
    try:
        size = os.path.getsize(f)
        sizes.append((size, f))
    except:
        pass

sizes.sort(key=lambda x: -x[0])
for s, f in sizes[:20]:
    print(f'{s/1024/1024:.1f} MB {f}')
print(f'\nTotal files: {len(files)}')
print(f'Total size: {sum(s[0] for s in sizes)/1024/1024:.1f} MB')

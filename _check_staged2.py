import subprocess
from collections import Counter

result = subprocess.run(['git', 'diff', '--cached', '--name-only'], capture_output=True, text=True)
files = [f.strip().strip('"') for f in result.stdout.splitlines() if f.strip() and 'CLIXML' not in f]

prefixes = Counter()
for f in files:
    if f.startswith('day2_pageindex/'):
        parts = f.split('/')
        if len(parts) >= 2:
            prefix = parts[0] + '/' + parts[1]
            prefixes[prefix] += 1

for p, c in prefixes.most_common(15):
    print(f'{c:>6} files in {p}')
print(f'\nTotal day2_pageindex files: {sum(prefixes.values())}')
print(f'\nTotal files: {len(files)}')

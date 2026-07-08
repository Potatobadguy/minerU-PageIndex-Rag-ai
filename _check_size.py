import subprocess, os

r = subprocess.run(['git', 'diff', '--cached', '--name-only'], capture_output=True, text=True)
files = [f.strip().strip('"') for f in r.stdout.splitlines() if f.strip() and 'CLIXML' not in f]
total = sum(os.path.getsize(f) for f in files if os.path.exists(f))
print(f'Total: {len(files)} files, {total/1024/1024:.1f} MB')

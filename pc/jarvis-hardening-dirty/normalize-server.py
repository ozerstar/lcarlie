from pathlib import Path
import subprocess

root = Path('/opt/lcarlie/source/lcarlie-jarvis-v1')
names = subprocess.check_output(['git', 'diff-tree', '--no-commit-id', '--name-only',
                                 '-r', 'HEAD'], cwd=root, text=True).splitlines()
for name in names:
    path = root / name
    data = path.read_bytes()
    if b'\r\n' in data:
        path.write_bytes(data.replace(b'\r\n', b'\n'))
        print(name)

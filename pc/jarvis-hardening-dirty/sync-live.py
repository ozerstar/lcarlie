from pathlib import Path
from datetime import datetime
import shutil
import subprocess

root = Path('/opt/lcarlie/source/lcarlie-jarvis-v1')
live = Path('/opt/lcarlie/jarvis-phase2')
backup = Path('/opt/lcarlie/backups') / ('jarvis-web-direct-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
names = subprocess.check_output(['git', 'diff-tree', '--no-commit-id', '--name-only',
                                 '-r', 'HEAD'], cwd=root, text=True).splitlines()
for name in names:
    if not name.startswith(('jarvis-phase2/jarvis/', 'jarvis-phase2/webconsole/')):
        continue
    relative = Path(name).relative_to('jarvis-phase2')
    target = live / relative
    if target.exists():
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / name, target)
print(backup)

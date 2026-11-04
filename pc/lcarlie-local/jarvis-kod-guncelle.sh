#!/bin/bash
# Jarvis kod kopyasını sunucudan yeniler ve Graphify haritasını yeniden kurar (modelsiz, dışarı veri gitmez).
# Kullanım (Git Bash):  bash C:/Users/ozery/lcarlie-local/jarvis-kod-guncelle.sh
# Kişisel/gizli veri içerebilecek klasörler (state, evidence, knowledge, yedekler, .env, *.db) ALINMAZ;
# gerçek anahtar değeri (sk-, AIza, ghp_, özel anahtar) içeren dosya da alınmaz.
set -euo pipefail
K=/c/Users/ozery/lcarlie-local
SSH="ssh -o ConnectTimeout=20 -i $HOME/.ssh/lcarlie_vds_ed25519 lcarlie"
$SSH 'cd /opt/lcarlie/jarvis-phase2 && find . \( -path "./.*" -o -path "./venv*" -o -path ./state -o -path "./backup*" -o -path ./backups \
  -o -path "./ui-backup*" -o -path ./nltk_data -o -path ./evidence -o -path ./knowledge -o -path ./varliklar -o -name node_modules \
  -o -name __pycache__ -o -name ".env*" -o -name "*.db" -o -name "*.sqlite*" -o -name "*.bak*" -o -name "*yedek*" \) -prune -o -type f \
  \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" -o -name "*.sh" -o -name "*.sql" -o -name "*.md" -o -name "*.service" \
  -o -name "*.timer" -o -name "*.html" -o -name "*.css" -o -name "requirements*.txt" \) -size -800k -print | sort > /tmp/gk.txt
  xargs -d "\n" grep -lE "sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY" < /tmp/gk.txt > /tmp/gk-gizli.txt || true
  grep -vxFf /tmp/gk-gizli.txt /tmp/gk.txt > /tmp/gk-son.txt || true
  tar -czf /tmp/gk.tgz -T /tmp/gk-son.txt; echo "dosya: $(wc -l < /tmp/gk-son.txt), atlanan(gizli): $(wc -l < /tmp/gk-gizli.txt)"'
scp -q -i "$HOME/.ssh/lcarlie_vds_ed25519" lcarlie:/tmp/gk.tgz "$K/gk.tgz"
$SSH 'rm -f /tmp/gk.txt /tmp/gk-gizli.txt /tmp/gk-son.txt /tmp/gk.tgz'
mkdir -p "$K/jarvis-kod"
cd "$K/jarvis-kod"
# Sunucuda silinen dosyalar kopyada kalmasın: yalnız kod dosyalarını sil (harita, yönergeler, kanca kalır).
find . -type f \( -path ./graphify-out -o -path ./.claude -o -path ./.codex -o -name CLAUDE.md -o -name AGENTS.md -o -name .graphifyignore \) -prune -o -type f -print | grep -v -E '^\./(graphify-out|\.claude|\.codex)/|^\./(CLAUDE|AGENTS)\.md$|^\./\.graphifyignore$' | xargs -r -d '\n' rm -f
tar -xzf "$K/gk.tgz" && rm -f "$K/gk.tgz"
GRAPHIFY_BACKEND=none GRAPHIFY_QUERY_LOG_DISABLE=1 PYTHONIOENCODING=utf-8 "$K/graphify-venv/Scripts/graphify" update . --force | tail -3
date '+%F %T' > .kopya-tarihi
echo "Tamam: $K/jarvis-kod (kopya tarihi $(cat .kopya-tarihi))"

#!/bin/sh
# TEST KAPISI -- kod bu makineden CIKMADAN once suit kosar.
#
# NEDEN VAR (25.10.2026): o gune kadar isleme kapisi yalniz `ruff`
# calistiriyordu. Ayni gun suitin yakaladigi bir PII ihlali -- musteri
# adinin (`musteri_ad`) ajana acik bir sorguya girmesi -- commit'lenip
# itilebildi, cunku kapi testi HIC kosturmuyordu. ruff sozdizimine bakar,
# DAVRANISA bakmaz; PII, bozulan sozlesme ve olu koruma ancak suitte gorunur.
#
# NEDEN pre-push, pre-commit DEGIL: suit ~20 sn. Her commit'te bunu odemek
# insani `--no-verify`a iter -- ve o an ruff da atlanir. Yarim kapi,
# kapisizliktan kotudur. Push, kodun makineden ciktigi tek andir.
#
# NEDEN mutlak venv yolu: kanca kabugunda PATH yok. .pre-commit-config.yaml
# icindeki ruff girdisi de ayni sebeple mutlak yol kullaniyor.
set -u
KOK=$(git rev-parse --show-toplevel 2>/dev/null || echo .)
# 04.11.2026: git kancasi GIT_DIR/GIT_INDEX_FILE'i ortama koyar. Bir
# worktree'den push edilince (GIT_DIR=.git/worktrees/<ad>, mutlak yol) gecici
# depolarda `git commit` calistiran testler (test_coding_executor 13 test,
# test_completion_20261014) o degiskeni miras alip yanlis depoya bakiyor ve
# dusuyordu; ayni testler kancasiz 0 kirmizi. Kok bulunduktan sonra temizlenir.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_PREFIX
PY=/opt/lcarlie/jarvis-phase2/venv/bin/python
[ -x "$PY" ] || { echo "TEST KAPISI: python bulunamadi: $PY"; exit 1; }

cd "$KOK/jarvis-phase2" || { echo "TEST KAPISI: jarvis-phase2 yok"; exit 1; }
OZET=$("$PY" -m unittest discover -s tests -p 'test_*.py' 2>&1)
DURUM=$?
echo "$OZET" | grep -E '^Ran [0-9]+ tests'
if [ "$DURUM" -ne 0 ]; then
  echo "--- DUSEN TESTLER ---"
  echo "$OZET" | grep -E '^(FAIL|ERROR): ' | head -20
  echo "$OZET" | grep -E '^FAILED \('
  echo
  echo "Push durduruldu. Testi duzelt; gercekten gerekiyorsa --no-verify."
fi
exit "$DURUM"

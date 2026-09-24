#!/bin/sh
# Commit oncesi sir kontrolu.
#
# NEDEN VAR: GitHub'in kendi secret scanning'i private depoda ucretli plan
# ister (dogrulandi 24.09.2026). Bedava karsiligi budur. 164 commit'in
# tamami taranip temiz cikti; bu kanca BUNDAN SONRASI icin.
#
# Yalniz SAHNELENEN degisikligin EKLENEN satirlarina bakar: mevcut gecmisi
# her seferinde taramak yavas olurdu ve zaten temiz oldugu olculdu.
#
# Atlamak gerekirse: git commit --no-verify  (gerekcesini bilerek yap)

set -e
BULGU=0

# Anahtar bicimleri. Deger YAZDIRILMAZ -- yalniz dosya ve satir bildirilir,
# yoksa sirri gunluge/terminale tasimis oluruz.
DESEN='(sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|EAA[A-Za-z0-9]{60,}|-----BEGIN [A-Z ]*PRIVATE KEY)'

if git diff --cached --unified=0 | grep -nE "^\+" | grep -qE "$DESEN"; then
  echo "ENGELLENDI: sahnelenen degisiklikte anahtar bicimi var." >&2
  echo "Etkilenen dosyalar:" >&2
  git diff --cached --name-only | while read -r f; do
    if git diff --cached --unified=0 -- "$f" | grep -E "^\+" | grep -qE "$DESEN"; then
      echo "  - $f" >&2
    fi
  done
  BULGU=1
fi

# Sir dosyasi adlari. .env.example bilerek haric: icinde <DEGER> yer tutucular var.
if git diff --cached --name-only --diff-filter=A \
   | grep -iE '(^|/)\.env$|\.env\.[^/]*$|[^/]*\.env$|secret|credential|\.pem$|\.key$' \
   | grep -v '\.env\.example$' | grep -q .; then
  echo "ENGELLENDI: sir dosyasi eklenmeye calisiliyor:" >&2
  git diff --cached --name-only --diff-filter=A \
    | grep -iE '(^|/)\.env$|\.env\.[^/]*$|[^/]*\.env$|secret|credential|\.pem$|\.key$' \
    | grep -v '\.env\.example$' | sed 's/^/  - /' >&2
  BULGU=1
fi

if [ "$BULGU" -ne 0 ]; then
  echo "" >&2
  echo "Commit yapilmadi. Sirri koddan cikar, .env dosyasina koy," >&2
  echo "ornegini .env.example olarak ekle." >&2
  exit 1
fi
exit 0
# temiz yorum

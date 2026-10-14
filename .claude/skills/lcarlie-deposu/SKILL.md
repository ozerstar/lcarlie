---
name: lcarlie-deposu
description: L'CARLIE Jarvis deposunda calisan her ajan icin zorunlu kurallar - dal secimi, test tabani, dokunulmayacak alanlar. Kod okumadan veya degistirmeden ONCE yukle.
---

# L'CARLIE Jarvis deposunda calisma kurallari

Bu dosya olculmus hatalardan dogdu. Her maddenin arkasinda en az bir
gercek vaka var.

## 1. Once dogru dala gec

Calisma dali **`is-sinifi-kapisi`**. Deponun varsayilan dali `main`
**65+ commit geride** ve orada bilerek birakilmis bayat testler var.

    git fetch origin && git checkout is-sinifi-kapisi

`main` uzerinde bulunan test hatalarini duzeltmeye calisma: cogu bu dalda
zaten duzeltilmis. Ornek: `test_valid_task_produces_a_real_proposal`
main'de FAILED, calisma dalinda OK.

## 2. Test tabani 1149 / OK

    python3 -m unittest discover -s tests -p "test_*.py"

- **pytest KURULU DEGIL.** Testler `unittest` ile yazilir ve kosulur.
- Tam ve veri iceren agacta beklenen: **`Ran 1149 tests` / `OK (skipped=25)`**.
- Bu sayiyi dusuren ya da hata ekleyen degisiklik kabul edilmez.
- Bir kez kosup rakami taban kabul etme; sapma olabiliyor.

## 3. Yesil olmamasi her zaman kusur degil

Bu iki durumu kusur sanma -- ikisi de olculdu:

- **Taze checkout/worktree'de `test_gorsel_kompozit` 8 hata verir.**
  Sebep: `varliklar/` altindaki uretilmis veri `.gitignore`'da.
  Yamanin kirdigi bir sey yok.
- **Python 3.11 altinda 40+ test yuklenemez.** Kod 3.12 ile kosuyor.
  Eski surumde cikan `enterContext` hatalari ORTAM farkidir.

Kural: bir seyin yoklugunu, sebebini olcmeden cumleye cevirme.

## 4. Dokunulmayacak alanlar

- `jarvis/` ve `scripts/` altina acik izin olmadan yazma.
- Hicbir `assert` degerini "test gecsin" diye degistirme. Kod-test
  uyusmazligi bulursan RAPOR ET, duzeltme.
- `/opt/lcarlie/...` uretim agacinda duzeltme yapma. Kaynak agac esastir;
  deploy uretimdeki yamayi sessizce geri alir.
- `.env` dosyalarini okuma, anahtar degerlerini ciktiya yazma.

## 5. Rapor bicimi

- Her rakamin yaninda hangi komuttan geldigi yazsin.
- "Veri yok" ile "bakamadim" ayri seylerdir, ayir.
- Kapsamin disina ciktiysan bunu acikca yaz.

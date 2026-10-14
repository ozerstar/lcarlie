"""Cevap üslubunu SONUÇTAN öğrenir: kohortu okur, yeni sürüm ÖNERİR.

SAHİBİN TARİFİ (20.09.2026), birebir
*"atıyorum 10 kişiye cevaplamış ve 2. mesaj gelmemiş, cevaplama tarzını
değiştirecek, kreatif ekiple konuşup daha iyi cevap düşünecek ve onu
yazacak bir sonraki müşteriye."*

Bu modül o döngünün KARAR yarısıdır. Üretme yarısı `satis_dialog`.

🔴 ÖNERİR, UYGULAMAZ
Yeni sürüm `TASLAK` doğar; `ONAYLI`ya insan taşır. Tek satır bile
kendiliğinden yayına girmez. Sebep sadece ihtiyat değil ölçüm: 10 kişilik
örneklem küçüktür ve bu projede küçük örneklemden sonuç çıkarıp yanıldık
(GROWTH-004/005). Eşik bir DEĞİŞİKLİK ÖNERİSİ tetikler, bir HÜKÜM değil.

🔴 NE ÖLÇÜLÜYOR, NE ÖLÇÜLMÜYOR
Ölçülen: cevaptan sonra müşteri tekrar yazdı mı (`DONUS_VAR`/`DONUS_YOK`).
Ölçülmeyen: satış. Ödemelerin %43'ünde otorite çevrim dışı ve
`konusma.sonuc` 274 kaydın 269'unda "bilinmiyor".
**`DONUS_YOK` satılmadı DEMEK DEĞİLDİR** -- müşteri siteden sessizce sipariş
vermiş olabilir. Bu modül hiçbir yerde "satış düştü/arttı" demez.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from . import compliance

# Ölçülen tarihsel taban (20.09.2026, `lcarlie.mesaj`): 1.067 işletme
# mesajının 637'sine müşteri geri yazmış = %59,7. Bu bizim yaklaşımımızın
# değil, o güne kadarki insan/Meta-AI karışımının tabanı -- kıyas noktası
# olarak kullanılıyor, hedef olarak değil.
TABAN_DONUS_YUZDE = 59.7

# Bu sayının altında hüküm verilmez. Sahibin örneği 10; aynen alındı ama
# "karar" değil "öneri" eşiği olarak.
ONERI_ESIGI = 10

# Tabandan bu kadar puan aşağısı "belirgin düşük" sayılır. Küçük bir farkın
# gürültü olma ihtimali yüksek; her dalgalanmada üslup değiştirmek
# öğrenmek değil, savrulmaktır.
BELIRGIN_FARK_PUAN = 10.0

YETERSIZ = "YETERSIZ_ORNEK"
ALTINDA = "TABANIN_ALTINDA"
AYNI = "TABANLA_AYNI"
USTUNDE = "TABANIN_USTUNDE"


@dataclass
class Bulgu:
    urun: str
    soru_tipi: str
    yaklasim_id: Any
    yaklasim_surum: Any
    karar_verilen: int          # DONUS_VAR + DONUS_YOK
    donus_var: int
    donus_yuzde: float | None
    durum: str
    oneri_gerekli: bool
    aciklama: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "urun": self.urun, "soru_tipi": self.soru_tipi,
            "yaklasim_id": self.yaklasim_id, "yaklasim_surum": self.yaklasim_surum,
            "karar_verilen": self.karar_verilen, "donus_var": self.donus_var,
            "donus_yuzde": self.donus_yuzde, "durum": self.durum,
            "oneri_gerekli": self.oneri_gerekli, "aciklama": self.aciklama,
        }


def _sayi(deger: Any) -> int:
    try:
        return int(deger or 0)
    except (TypeError, ValueError):
        return 0


def degerlendir(kohortlar: Iterable[dict[str, Any]],
                taban: float = TABAN_DONUS_YUZDE,
                esik: int = ONERI_ESIGI) -> list[Bulgu]:
    """`mart.satis_kohort` satırlarını okur, hangisi için öneri gerektiğini söyler.

    Oran YALNIZ karar verilmiş kayıtlardan hesaplanır; penceresi açık kayıt
    paydaya girerse oran olduğundan düşük görünür ve boş yere üslup
    değiştiririz.
    """
    bulgular: list[Bulgu] = []
    for satir in kohortlar:
        donus_var = _sayi(satir.get("donus_var"))
        donus_yok = _sayi(satir.get("donus_yok"))
        karar = donus_var + donus_yok
        yuzde = (round(100.0 * donus_var / karar, 1) if karar else None)

        if karar < esik:
            durum, gerekli = YETERSIZ, False
            aciklama = (f"{karar} karar verilmiş cevap var, eşik {esik}. "
                        "Oran okunabilir ama hüküm verilmez (SMALL_SAMPLE).")
        elif yuzde is not None and yuzde <= taban - BELIRGIN_FARK_PUAN:
            durum, gerekli = ALTINDA, True
            aciklama = (f"Dönüş %{yuzde}; taban %{taban}. "
                        f"{BELIRGIN_FARK_PUAN} puandan fazla düşük — üslup "
                        "gözden geçirilmeli.")
        elif yuzde is not None and yuzde >= taban + BELIRGIN_FARK_PUAN:
            durum, gerekli = USTUNDE, False
            aciklama = f"Dönüş %{yuzde}; taban %{taban}. Bu üslup tutuyor, dokunma."
        else:
            durum, gerekli = AYNI, False
            aciklama = (f"Dönüş %{yuzde}; taban %{taban}. Fark belirgin değil, "
                        "dalgalanma olabilir.")

        bulgular.append(Bulgu(
            urun=str(satir.get("urun") or "(ürün yok)"),
            soru_tipi=str(satir.get("soru_tipi") or "?"),
            yaklasim_id=satir.get("yaklasim_id"),
            yaklasim_surum=satir.get("yaklasim_surum"),
            karar_verilen=karar, donus_var=donus_var, donus_yuzde=yuzde,
            durum=durum, oneri_gerekli=gerekli, aciklama=aciklama,
        ))
    # Önce öneri gerekenler, sonra en düşük oran.
    bulgular.sort(key=lambda b: (not b.oneri_gerekli,
                                 b.donus_yuzde if b.donus_yuzde is not None else 999))
    return bulgular


ONERI_ISTEMI = """Bir e-ticaret müşteri mesajı üslubunu iyileştir.

Ürün: {urun}
Soru tipi: {soru_tipi}
Şu anki üslup yönergesi: {mevcut}
Ölçüm: bu üslupla {karar} müşteriye cevap gidildi, {donus_var} tanesi tekrar
yazdı (%{yuzde}). Genel taban %{taban}.

Tekrar yazılmayan cevaplardan örnekler:
{ornekler}

Yeni bir üslup yönergesi yaz. Yalnız yönergeyi yaz, en fazla 2 cümle.
Fiyat, içerik veya süre gibi bilgiler yönergeye GİRMEZ; yönerge sadece
nasıl konuşulacağını anlatır."""


@dataclass
class Oneri:
    urun: str
    soru_tipi: str
    yeni_yonerge: str
    gerekce: str
    onceki_yaklasim_id: Any = None
    mevzuat: str = "BILINMIYOR"
    uygun: bool = False
    model: str | None = None
    hata: str = ""
    kanit: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"urun": self.urun, "soru_tipi": self.soru_tipi,
                "yeni_yonerge": self.yeni_yonerge, "gerekce": self.gerekce,
                "onceki_yaklasim_id": self.onceki_yaklasim_id,
                "mevzuat": self.mevzuat, "uygun": self.uygun,
                "model": self.model, "hata": self.hata, "kanit": self.kanit,
                "durum": "TASLAK"}


def yaklasim_oner(bulgu: Bulgu, mevcut_yonerge: str,
                  basarisiz_ornekler: list[str], layer: Any,
                  taban: float = TABAN_DONUS_YUZDE) -> Oneri:
    """Kreatif katmandan yeni bir üslup yönergesi ister.

    🔴 Örnekler UYDURULMAZ: `basarisiz_ornekler` gerçekten gönderilmiş ve
    dönüş almamış cevaplardır. Örnek yoksa öneri istenmez -- neye bakarak
    değiştireceğini bilmeyen bir öneri, üslubu rastgele savurmaktan farksızdır.
    """
    if not basarisiz_ornekler:
        return Oneri(urun=bulgu.urun, soru_tipi=bulgu.soru_tipi,
                     yeni_yonerge="", gerekce="", onceki_yaklasim_id=bulgu.yaklasim_id,
                     hata="dönüş almamış örnek yok; öneri istenmedi")

    istem = ONERI_ISTEMI.format(
        urun=bulgu.urun, soru_tipi=bulgu.soru_tipi, mevcut=mevcut_yonerge,
        karar=bulgu.karar_verilen, donus_var=bulgu.donus_var,
        yuzde=bulgu.donus_yuzde, taban=taban,
        ornekler="\n".join(f"- {o[:220]}" for o in basarisiz_ornekler[:5]),
    )
    try:
        sonuc, _, _ = layer.generate([{"role": "user", "content": istem}],
                                     max_tokens=180, escalate=True,
                                     is_anahtari="satis_ogrenme")
    except Exception as exc:  # noqa: BLE001
        return Oneri(urun=bulgu.urun, soru_tipi=bulgu.soru_tipi,
                     yeni_yonerge="", gerekce="",
                     onceki_yaklasim_id=bulgu.yaklasim_id,
                     hata=f"model çağrılamadı: {str(exc)[:120]}")

    yonerge = " ".join(str((sonuc or {}).get("text") or "").split())
    if not yonerge:
        return Oneri(urun=bulgu.urun, soru_tipi=bulgu.soru_tipi,
                     yeni_yonerge="", gerekce="",
                     onceki_yaklasim_id=bulgu.yaklasim_id,
                     hata="model boş yönerge döndü")

    # Yönerge müşteriye gitmez ama üsluba mevzuat dışı bir şey yazdırabilir
    # ("kesin sonuç vadet" gibi). Kademe 1 taraması burada da çalışır.
    inceleme = compliance.review(yonerge)
    return Oneri(
        urun=bulgu.urun, soru_tipi=bulgu.soru_tipi, yeni_yonerge=yonerge,
        gerekce=bulgu.aciklama, onceki_yaklasim_id=bulgu.yaklasim_id,
        mevzuat="TEMIZ" if inceleme.clean else "INCELE",
        uygun=inceleme.clean, model=(sonuc or {}).get("model"),
        kanit=[o[:220] for o in basarisiz_ornekler[:5]],
    )


def ozet(bulgular: list[Bulgu]) -> str:
    """Panelde/raporda gösterilecek tek paragraf. Sayı verir, hüküm vermez."""
    if not bulgular:
        return "Henüz gönderilmiş cevap yok; ölçecek bir şey bulunmuyor."
    oneri = [b for b in bulgular if b.oneri_gerekli]
    yetersiz = [b for b in bulgular if b.durum == YETERSIZ]
    parcalar = [f"{len(bulgular)} kohort ölçüldü."]
    if oneri:
        parcalar.append(
            f"{len(oneri)} kohortta dönüş oranı tabandan belirgin düşük: "
            + ", ".join(f"{b.urun}/{b.soru_tipi} %{b.donus_yuzde}" for b in oneri[:3])
            + ". Bu kohortlar için yeni üslup önerisi çıkarılabilir.")
    if yetersiz:
        parcalar.append(f"{len(yetersiz)} kohort henüz eşiğin altında "
                        "(SMALL_SAMPLE) — oranları okunabilir ama karar verilmez.")
    if not oneri and not yetersiz:
        parcalar.append("Ölçülen kohortların hiçbiri tabandan belirgin sapmıyor.")
    return " ".join(parcalar)

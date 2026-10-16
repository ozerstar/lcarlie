# -*- coding: utf-8 -*-
"""Sunucudaki tarayici kapisina SSH istemcisi.

Bu makine disariya HIC ACILMAZ. Tunel yok, port yok, gelen baglanti yok.
Tek yon var: buradan sunucuya dogru SSH.

Sunucu tarafinda anahtar ZORUNLU KOMUT ile baglidir
(`/opt/lcarlie/bin/tarayici-kapi`), yani bu anahtarla kabuk alinamaz.
Buradaki her cagri o kapinin alti alt komutundan biridir.

🔴 ANAHTAR NTFS'TE OLMAK ZORUNDA. exFAT dosya izni tutmaz; `icacls`
   sessizce hicbir sey yapmaz ve OpenSSH anahtari "bad permissions"
   diye reddeder. Belirtisi sinsi: gunluge "baglandi" yazar ama surec
   aninda olur. (gorsel-kuyruk/README.md, 24.09.2026'da olculdu.)
   Bu yuzden worker E: (NTFS) uzerinde kurulur, D: (exFAT) YASAK.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path


class KapiHatasi(RuntimeError):
    """Sunucu cagriyi reddetti ya da ulasilamadi."""


class Kapi:
    def __init__(self, host: str, kullanici: str, anahtar: Path,
                 known_hosts: Path, zaman_asimi_s: int = 120):
        self.hedef = f"{kullanici}@{host}"
        self.anahtar = Path(anahtar)
        self.known_hosts = Path(known_hosts)
        self.zaman_asimi_s = zaman_asimi_s

    # -- ssh ---------------------------------------------------------------
    def _ssh_args(self) -> list[str]:
        # 🔴 BUTUN SECENEKLER ACIKCA VERILIR. SYSTEM'in ve servis
        #    hesaplarinin profili farklidir; ~/.ssh/config okunmayabilir.
        #    Betigin davranisi makinedeki yapilandirmaya BAGLI OLMAMALI.
        return [
            "ssh",
            "-i", str(self.anahtar),
            "-o", "IdentitiesOnly=yes",
            "-o", f"UserKnownHostsFile={self.known_hosts}",
            "-o", "StrictHostKeyChecking=yes",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "RequestTTY=no",
            self.hedef,
        ]

    def _cagir(self, alt_komut: list[str], govde: dict | None = None,
               zaman_asimi_s: int | None = None) -> str:
        komut = self._ssh_args() + [" ".join(alt_komut)]
        girdi = json.dumps(govde, ensure_ascii=False) if govde is not None else ""
        try:
            sonuc = subprocess.run(
                komut, input=girdi, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=zaman_asimi_s or self.zaman_asimi_s, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise KapiHatasi("sunucu zaman asimi: %s" % alt_komut[0]) from None
        except OSError as hata:
            raise KapiHatasi("ssh calistirilamadi: %s" % hata) from None
        if sonuc.returncode:
            hata = (sonuc.stderr or "").strip() or "sebep bildirilmedi"
            raise KapiHatasi("kapi reddetti (%s): %s"
                             % (alt_komut[0], hata[:400]))
        return (sonuc.stdout or "").strip()

    # -- alt komutlar ------------------------------------------------------
    def al(self, worker: str) -> dict:
        """Siradaki isi kiralar. Is yoksa bos sozluk doner.

        🔴 Bos sozluk "is yok" demektir, "hata" demez. Ikisini
           karistirmak, kuyruk okunamadiginda sessizce bos beklemek
           olurdu -- ve kimse fark etmezdi.
        """
        ham = self._cagir(["al", worker])
        if not ham:
            return {}
        try:
            return json.loads(ham)
        except json.JSONDecodeError as hata:
            raise KapiHatasi("kapi gecersiz JSON dondurdu: %s" % hata) from None

    def girdi(self, is_id: int, sira: int) -> tuple[str, bytes]:
        """Girdi dosyasini indirir: (ad, icerik)."""
        ham = self._cagir(["girdi", str(int(is_id)), str(int(sira))])
        kayit = json.loads(ham)
        return kayit["ad"], base64.b64decode(kayit["b64"])

    def bitir(self, is_id: int, jeton: str, metin: str,
              dosyalar: list[tuple[str, bytes]] | None = None,
              ekran: bytes | None = None) -> None:
        govde = {
            "metin": metin or "",
            "dosyalar": [{"ad": ad, "b64": base64.b64encode(veri).decode("ascii")}
                         for ad, veri in (dosyalar or [])],
        }
        if ekran:
            govde["ekran_b64"] = base64.b64encode(ekran).decode("ascii")
        # Yukleme buyuk olabilir; zaman asimi kiradan (420 sn) kisa tutulur.
        self._cagir(["bitir", str(int(is_id)), str(jeton)], govde,
                    zaman_asimi_s=300)

    def hata(self, is_id: int, jeton: str, sebep: str,
             ekran: bytes | None = None) -> None:
        govde: dict = {"hata": (sebep or "")[:1000]}
        if ekran:
            govde["ekran_b64"] = base64.b64encode(ekran).decode("ascii")
        self._cagir(["hata", str(int(is_id)), str(jeton)], govde)

    def insan(self, is_id: int, jeton: str, sebep: str,
              ekran: bytes | None = None) -> None:
        govde: dict = {"sebep": (sebep or "")[:1000]}
        if ekran:
            govde["ekran_b64"] = base64.b64encode(ekran).decode("ascii")
        self._cagir(["insan", str(int(is_id)), str(jeton)], govde)

    def nabiz(self, worker: str, ayrinti: dict | None = None) -> None:
        self._cagir(["nabiz", worker], {"ayrinti": ayrinti or {}},
                    zaman_asimi_s=45)


def ortamdan() -> Kapi:
    """`.env` ve ortam degiskenlerinden kapi kurar."""
    kok = Path(__file__).resolve().parent
    env_yolu = kok / ".env"
    if env_yolu.is_file():
        for satir in env_yolu.read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            ad, _, deger = satir.partition("=")
            os.environ.setdefault(ad.strip(), deger.strip())
    eksik = [a for a in ("TARAYICI_SUNUCU", "TARAYICI_SSH_ANAHTAR")
             if not os.environ.get(a)]
    if eksik:
        raise KapiHatasi(".env eksik: " + ", ".join(eksik))
    return Kapi(
        host=os.environ["TARAYICI_SUNUCU"],
        kullanici=os.environ.get("TARAYICI_SSH_KULLANICI", "root"),
        anahtar=Path(os.environ["TARAYICI_SSH_ANAHTAR"]),
        known_hosts=Path(os.environ.get(
            "TARAYICI_KNOWN_HOSTS", str(kok / "ssh" / "known_hosts"))),
    )

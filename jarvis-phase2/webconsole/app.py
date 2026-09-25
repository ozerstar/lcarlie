"""L'CARLIE Jarvis Web Console -- thin API + static frontend server.

Reuses the existing Jarvis core untouched:
  jarvis.shadow.ShadowRunner   -- real chat pipeline (Phase 2C/2D, unmodified)
  jarvis.operator.OperatorSession -- real human-approver proposal boundary
  jarvis.memory.CompanyMemory  -- real Company Memory reads

This process never assumes ai_writer or human_approver as its OWN identity;
every DB call happens inside jarvis.memory / jarvis.operator, which each set
SESSION AUTHORIZATION per call exactly as already verified. This server adds
NOTHING to that boundary -- it is a browser-facing shell around it.

Binds 0.0.0.0:<port> because Caddy reaches it from inside a docker container
via the docker bridge, not loopback. Public exposure is blocked at the host
firewall (ufw allow only from the docker bridge subnet), not by this process.

Stdlib only: http.server + manual routing/sessions/CSRF/rate-limit. No new
framework, no new package install.
"""
from __future__ import annotations

import hashlib
import json
import re
import os
import sys
import subprocess
import threading
import time
import pathlib
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
JARVIS_ROOT = HERE.parent
sys.path.insert(0, str(JARVIS_ROOT))
sys.path.insert(0, str(HERE))

os.environ.setdefault("JARVIS_ENABLED", "true")
os.environ.setdefault("JARVIS_MODE", "SHADOW")
os.environ.setdefault("EXTERNAL_ACTIONS", "false")
os.environ.setdefault("JARVIS_MEMORY_TRANSPORT", "local-docker")

from jarvis import capabilities as caps  # noqa: E402
from jarvis import conversation_memory as _cmem  # noqa: E402
from jarvis.action_contract import ContractCache, ContractError  # noqa: E402
from jarvis.execution_planner import plan_request  # noqa: E402
from jarvis.execution_runtime import ExecutionDenied, ExecutionRuntime  # noqa: E402
from jarvis.context import ContextCompiler  # noqa: E402
from jarvis import degisiklik
from jarvis.memory import CompanyMemory, MemoryError as JarvisMemoryError  # noqa: E402
from jarvis.operator import OperatorSession  # noqa: E402
from jarvis.phase2 import Phase2Runtime  # noqa: E402
from jarvis.shadow import ShadowRunner  # noqa: E402
from jarvis.transport import memory_host  # noqa: E402

import auth  # noqa: E402
import meta_webhook  # noqa: E402
import isler  # noqa: E402
import katalog  # noqa: E402
import harita  # noqa: E402
import saha  # noqa: E402
import sistem  # noqa: E402

import chat  # noqa: E402

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
STATIC_DIR = HERE / "static"
# Uretilen reklam gorselleri. Statik klasorun ALTINDA DEGIL:
# oraya konsaydi oturum acmamis herkese acik olurdu.
KREATIF_DIR = (HERE.parent / "state" / "kreatif-brief").resolve()
# 🔴 Etiketlerde MÜŞTERİ ADI VE AÇIK ADRESİ var. Statik klasöre
# konsaydı kimlik kapısının dışında kalırdı; `/etiket/` yolu
# `_route_kreatif` ile aynı oturum kapısından geçer.
ETIKET_DIR = (HERE.parent / "state" / "kargo-etiket").resolve()
BIND_HOST = os.environ.get("JARVIS_WEB_BIND", "0.0.0.0")
BIND_PORT = int(os.environ.get("JARVIS_WEB_PORT", "8091"))

# Meta olay kuyruğu. STATE_DIR altında: `jarvis-web.service`'in
# ReadWritePaths'i zaten burayı kapsıyor, yeni yazma izni açılmıyor.
META_KUYRUK = STATE_DIR / "meta_webhook" / "gelen.jsonl"

SESSION_COOKIE = "jarvis_session"
CSRF_COOKIE = "jarvis_csrf"

sessions = auth.SessionStore()
throttle = auth.LoginThrottle()

_memory = CompanyMemory(host=memory_host())
_shadow_runner = ShadowRunner(Phase2Runtime(ContextCompiler(_memory)))
_operator = OperatorSession(host=memory_host())


def _live_registry() -> dict:
    """The capability registry the planner is checked against.

    Built from the same live evidence ContextCompiler already uses -- one
    Company Memory probe plus the loaded action contract. A failed probe or an
    unloadable contract yields absent evidence, which build_registry turns into
    UNKNOWN/MISSING rather than an optimistic guess, so the planner then blocks
    the affected step instead of planning around a capability nobody verified.
    """
    try:
        probe_evidence = _memory.get_capability_state()
        probe = probe_evidence.records[0] if probe_evidence.records else {}
    except JarvisMemoryError:
        probe = {}
    health = probe.get("health")
    memory_ok = isinstance(health, dict) and "checked_at" in health
    try:
        contract = ContractCache(_memory).get()
    except (ContractError, JarvisMemoryError):
        contract = None
    return caps.build_registry(probe=probe, contract=contract, memory_ok=memory_ok)


# ==========================================================================
# Host kaynak olcumu (CPU / RAM / DISK)
# ==========================================================================
# Panel bugune kadar bu ucu icin "N/A" yaziyordu ve notu "uc nokta yok"
# diyordu -- dogruydu: capabilities.host_resources() yalnizca TOPLAM RAM ve
# cekirdek SAYISINI veriyor, kullanimi degil, ve API'ye hic cikmiyordu.
# Burasi o bosluk. Uc deger de cekirdegin kendi sayaclarindan okunur:
#
#   CPU   /proc/stat       iki olcum ARASINDAKI fark. "Anlik CPU yuzdesi"
#                          diye bir sey yoktur; yuzde ancak bir zaman araligi
#                          icin tanimlidir, o yuzden aralik da raporlanir.
#   RAM   /proc/meminfo    MemTotal - MemAvailable. MemFree DEGIL: sayfa
#                          onbellegi geri alinabilir, onu "dolu" saymak
#                          sunucuyu oldugundan dolu gosterirdi.
#   DISK  os.statvfs("/")  kok dosya sistemi; yuzde df ile ayni yontemle,
#                          yani root'a ayrilan yedek haric hesaplanir.
#
# Okunamayan alan None doner ve panelde N/A kalir, sebebiyle birlikte.
# Tahmin, varsayilan veya "yaklasik" bir sayi hicbir yolda uretilmez.

_CPU_LOCK = threading.Lock()
_CPU_PREV: "tuple[float, float, float] | None" = None   # (zaman, toplam, bos)


def _read_cpu_sample() -> "tuple[float, float] | None":
    """/proc/stat'in toplu `cpu` satirindan (toplam, bos) jiffy."""
    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            line = handle.readline()
    except OSError:
        return None
    parts = line.split()
    if len(parts) < 6 or parts[0] != "cpu":
        return None
    try:
        values = [float(x) for x in parts[1:11]]
    except ValueError:
        return None
    # user nice system idle iowait irq softirq steal guest guest_nice
    return sum(values), values[3] + values[4]


def _cpu_percent() -> dict:
    """Iki olcum arasindaki farktan CPU kullanimi.

    Panel 12 saniyede bir /api/status cagirdigi icin normal durumda pencere o
    iki istek arasidir -- istegi hic bekletmez. Karsilastirilacak taze bir
    onceki ornek yoksa (ilk istek, ya da uzun aradan sonra) burada kendi
    200 ms'lik penceresini alir: kisa ama GERCEK bir olcum, "veri yok"
    demekten iyi ve uydurma degil.
    """
    global _CPU_PREV
    first = _read_cpu_sample()
    if first is None:
        return {"percent": None, "error": "/proc/stat okunamadi"}
    now = time.time()
    with _CPU_LOCK:
        prev = _CPU_PREV
        _CPU_PREV = (now, first[0], first[1])

    if prev is not None and 1.0 <= (now - prev[0]) <= 300.0:
        window = now - prev[0]
        total_delta = first[0] - prev[1]
        idle_delta = first[1] - prev[2]
    else:
        time.sleep(0.2)
        second = _read_cpu_sample()
        if second is None:
            return {"percent": None, "error": "/proc/stat okunamadi"}
        window = 0.2
        total_delta = second[0] - first[0]
        idle_delta = second[1] - first[1]
        with _CPU_LOCK:
            _CPU_PREV = (time.time(), second[0], second[1])

    if total_delta <= 0:
        return {"percent": None, "error": "olcum araligi bos"}
    busy = max(0.0, total_delta - idle_delta)
    return {"percent": round(min(100.0, busy / total_delta * 100.0), 1),
            "window_s": round(window, 1)}


def _ram_usage() -> dict:
    fields: dict[str, float] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    fields[key] = float(rest.split()[0])   # kB
                    if len(fields) == 2:
                        break
    except (OSError, ValueError, IndexError):
        return {"percent": None, "error": "/proc/meminfo okunamadi"}
    total = fields.get("MemTotal") or 0.0
    available = fields.get("MemAvailable")
    if total <= 0 or available is None:
        return {"percent": None, "error": "MemTotal/MemAvailable yok"}
    used = total - available
    kib_per_gib = 1024.0 * 1024.0
    return {"percent": round(used / total * 100.0, 1),
            "used_gib": round(used / kib_per_gib, 2),
            "total_gib": round(total / kib_per_gib, 2)}


def _disk_usage(mount: str = "/") -> dict:
    try:
        st = os.statvfs(mount)
    except OSError:
        return {"percent": None, "error": f"{mount} okunamadi"}
    block = st.f_frsize or st.f_bsize
    total = st.f_blocks * block
    free_user = st.f_bavail * block        # root yedegi HARIC
    used = total - st.f_bfree * block
    denom = used + free_user
    if total <= 0 or denom <= 0:
        return {"percent": None, "error": "bos dosya sistemi"}
    gib = 1024.0 ** 3
    return {"percent": round(used / denom * 100.0, 1),
            "used_gib": round(used / gib, 2),
            "total_gib": round(total / gib, 2),
            "mount": mount}


def _host_metrics() -> dict:
    cpu = _cpu_percent()
    cpu["cores"] = os.cpu_count()
    try:
        cpu["load"] = [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):
        cpu["load"] = None
    return {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "cpu": cpu, "ram": _ram_usage(), "disk": _disk_usage("/")}


def _client_ip(handler: "Handler") -> str:
    # Trusted only because Caddy sets it (header_up SET, matches the existing
    # X-Gercek-IP convention this project already relies on elsewhere).
    forwarded = handler.headers.get("X-Gercek-IP")
    return forwarded or handler.client_address[0]


def _read_json_body(handler: "Handler") -> dict:
    length = int(handler.headers.get("Content-Length", 0) or 0)
    if length <= 0 or length > 65536:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _parse_cookies(handler: "Handler") -> dict[str, str]:
    raw = handler.headers.get("Cookie", "")
    out = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            key, _, value = part.partition("=")
            out[key] = value
    return out


def _tail_jsonl(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


class _HizliYoklama:
    """Panel icin kisa zaman asimli saglik yoklamasi.

    🔴 Paylasilan yonlendiricinin provider_states()'i kullanilmaz. Iki sebep:

    1. Zaman asimi. Gercek cagri yolunda 3 saniye makul -- bir kademeyi
       erken elemek, calisan bir makineyi kaybetmek olur. Ekranda ise 3
       saniye pahali: llama soküldükten sonra gpu ucu olu ve her sekme
       acilisinda o sureyi bekletiyordu.
    2. Yan etki. Paylasilan yonlendiricinin zaman asimini ekran icin
       kisaltmak, gercek cagrilari da etkilerdi.

    1,2 saniyede saglik cevabi veremeyen bir uc zaten kullanilabilir degil.
    """

    ZAMAN_ASIMI_S = 1.2


def _kademe_canli_durum() -> dict:
    """Uc kademenin ANLIK durumu. Gecmisten DEGIL, su andan.

    external.state() ag istegi yapmaz (anahtar + kota kontrolu), bu yuzden
    ucuzdur; yalniz iki yerel uc yoklanir.
    """
    from jarvis import model_layer as ML

    class _Kisa(ML.LocalProvider):
        health_timeout_s = _HizliYoklama.ZAMAN_ASIMI_S

    durumlar = {}
    for ad, url, model in (("gpu", ML.GPU_URL, ML.GPU_MODEL),
                           ("local", ML.LOCAL_URL, ML.LOCAL_MODEL)):
        try:
            durumlar[ad] = _Kisa(url=url, model=model).state().value
        except Exception:  # noqa: BLE001 - yoklanamamak da bir durumdur
            durumlar[ad] = "BILINMIYOR"
    try:
        durumlar["external"] = ML.ExternalProvider().state().value
    except Exception:  # noqa: BLE001
        durumlar["external"] = "BILINMIYOR"
    return durumlar


def _kademe_gorunumu(limit: int = 200) -> dict:
    """Hangi kademe cevap veriyor: canli durum + son kayitlarin ozeti.

    Iki kaynak AYRI try icinde. Canli yoklama uc makineye HTTP saglik istegi
    atar; biri asili kalirsa gecmis kayitlar yine de gorunmelidir. Bos bir
    kademe ekrani "her sey yolunda" diye okunur -- en tehlikeli yanlis bu.

    "simdi" ANLIK durumdur, "ozet" GECMIStir. Ikisi celisebilir ve bu bir hata
    degildir: makine az once acilmis olabilir. Panelde ayri gosterilmeli.
    """
    gorunum: dict = {}
    try:
        gorunum["simdi"] = _kademe_canli_durum()
    except Exception as exc:  # noqa: BLE001
        gorunum["simdi"] = {"hata": str(exc)[:200]}
    try:
        from jarvis import kademe_kaydi
        kayitlar = kademe_kaydi.son_kayitlar(limit)
        gorunum["son"] = kayitlar[:30]
        gorunum["ozet"] = kademe_kaydi.ozet(kayitlar)
    except Exception as exc:  # noqa: BLE001
        gorunum["son"] = []
        gorunum["ozet"] = {"hata": str(exc)[:200]}
    return gorunum



# ══════════════════════════════════════════════════════════════════════
# SATIŞ MERKEZİ
#
# Sahip 21.09.2026: *"satışlar diye bir bölüm aç, tüm platformlardaki
# satışları orada topla… fiyatı olmayan gönderilerin yanına elle
# yazmam için kutu koy… hangi üründen kaç tane dağıtıldı orada
# yazılsın… stok takibi için panel aç."*
#
# 🔴 ÖLÇÜLEN SINIR, GİZLENMİYOR: `mart.siparis` içindeki 37 siparişin
# HEPSİ kanal='WEB' (Wix). `raw.trendyol_order` diye bir tablo YOK --
# Trendyol siparişleri hiç alınmıyor. Panel bunu "tüm platformlar" diye
# göstermez; hangi kanalın bağlı olduğunu ve hangisinin OLMADIĞINI yazar.
# Bağlı olmayan kanalı sessizce atlamak, eksik ciroyu tam göstermek olurdu.
# ══════════════════════════════════════════════════════════════════════

SATIS_TURLERI = ("SATIS", "UGC", "INFLUENCER", "NUMUNE", "HEDIYE",
                 "IADE", "DEGISIM", "BILINMIYOR")


def _sql_oku(sql: str, rol: str = "ai_reader", zaman: int = 25) -> list[dict]:
    """Salt okuma. row_to_json satirlarini dict listesine cevirir."""
    tam = (f"\\set ON_ERROR_STOP on\nBEGIN;\n"
           f"SET SESSION AUTHORIZATION {rol};\n{sql}\nCOMMIT;\n")
    p = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q", "-At",
         "-U", "n8n", "-d", "n8n", "-f", "-"],
        input=tam, capture_output=True, text=True, timeout=zaman, check=False)
    if p.returncode:
        raise JarvisMemoryError((p.stderr or p.stdout).strip()[:300])
    out = []
    for satir in (p.stdout or "").splitlines():
        satir = satir.strip()
        if not satir or satir in ("BEGIN", "COMMIT", "SET"):
            continue
        try:
            out.append(json.loads(satir))
        except ValueError:
            continue
    return out


def _satis_merkezi() -> dict:
    """Birleşik satış tablosu + dağıtım + stok + kanal durumu."""
    veri: dict = {}

    # --- siparişler (kalemleriyle)
    try:
        veri["siparisler"] = _sql_oku(
            "SELECT row_to_json(x) FROM (SELECT s.siparis_id AS entity_id,"
            " s.siparis_no, s.gun, s.kanal, s.odeme_durumu, s.odeme_yontemi,"
            " s.teslimat_durumu, s.toplam, s.ciro_sinifi,"
            " s.ciro_dogrulanmis_net, s.ciro_beyan_edilmis_net, s.olcumde,"
            " (SELECT count(*) FROM mart.siparis_kalem k"
            "    WHERE k.siparis_id = s.siparis_id) AS kalem_sayisi,"
            " (SELECT string_agg(k.urun_adi || ' x' || k.adet::int, ', ')"
            "    FROM mart.siparis_kalem k WHERE k.siparis_id = s.siparis_id) AS urunler,"
            " (SELECT count(*) FROM core.gonderi_notu n"
            "    WHERE n.siparis_ref = s.siparis_id::text) AS not_sayisi"
            " FROM mart.siparis s ORDER BY s.gun DESC, s.siparis_id DESC LIMIT 300) x;"
)
    except Exception as exc:  # noqa: BLE001
        veri["siparisler"], veri["siparis_hatasi"] = [], str(exc)[:200]

    # --- kanal durumu: neyin bağlı olduğu ve neyin OLMADIĞI
    kanallar: dict[str, int] = {}
    for sp in veri.get("siparisler") or []:
        k = str(sp.get("kanal") or "?")
        kanallar[k] = kanallar.get(k, 0) + 1
    veri["kanallar"] = kanallar
    veri["kanal_notu"] = (
        "Bu tabloda yalnız " + (", ".join(kanallar) or "hiçbir kanal") +
        " var. Trendyol siparişleri sisteme HİÇ alınmıyor "
        "(raw.trendyol_order tablosu yok); Trendyol satışları burada "
        "GÖRÜNMEZ. Toplam ciro bu yüzden eksiktir.")

    # --- ürün dağıtımı: satılan ve bedelsiz AYRI
    try:
        veri["dagitim"] = _sql_oku(
            "SELECT row_to_json(x) FROM (SELECT * FROM mart.urun_dagitim"
            " ORDER BY toplam_cikan DESC) x;")
    except Exception as exc:  # noqa: BLE001
        veri["dagitim"], veri["dagitim_hatasi"] = [], str(exc)[:200]

    # --- stok: en son sayım
    try:
        veri["stok"] = _sql_oku(
            "SELECT row_to_json(x) FROM (SELECT * FROM mart.stok_guncel"
            " ORDER BY urun_adi) x;")
    except Exception as exc:  # noqa: BLE001
        veri["stok"], veri["stok_hatasi"] = [], str(exc)[:200]

    # --- elle girilen gönderi notları
    try:
        veri["notlar"] = _sql_oku(
            "SELECT row_to_json(x) FROM (SELECT not_id, siparis_ref, tur, alici,"
            " urun_adi, adet, elle_fiyat, not_metni, giren, girildi"
            " FROM core.gonderi_notu ORDER BY girildi DESC LIMIT 200) x;")
    except Exception as exc:  # noqa: BLE001
        veri["notlar"], veri["not_hatasi"] = [], str(exc)[:200]

    # --- fiyatı olmayan / kararsız gönderiler: elle doldurulacaklar
    # 🔴 Bunlar "eksik veri" değil, HENÜZ AÇIKLANMAMIŞ gönderilerdir.
    # Panel bunları öne çıkarır ki sahip tek tek işaretleyebilsin.
    notlu = {str(n.get("siparis_ref")) for n in (veri.get("notlar") or [])}
    bekleyen = []
    for sp in veri.get("siparisler") or []:
        if str(sp.get("entity_id")) in notlu:
            continue
        bedelsiz = (sp.get("odeme_durumu") == "NOT_PAID"
                    or not sp.get("toplam")
                    or sp.get("ciro_sinifi") in ("IPTAL", "BEYAN_EDILMIS"))
        if bedelsiz:
            bekleyen.append(sp)
    veri["aciklama_bekleyen"] = bekleyen
    veri["turler"] = list(SATIS_TURLERI)
    return veri


def _gonderi_notu_ekle(siparis_ref: str, tur: str, alici: str, urun_adi: str,
                       adet, elle_fiyat, not_metni: str, giren: str) -> dict:
    """Gönderi notunu human_approver olarak yazar.

    🔴 `_pazar_bulgu_ekle` ile AYNI yol: değerler argv'den değil stdin'den,
    rastgele etiketli dolar-tırnak içinde JSON olarak gider. Bu projede
    kabuk tırnaklaması defalarca bozdu; argv yolu iki kez yorumlanır.
    """
    import secrets

    tur = (tur or "").strip().upper()
    if tur not in SATIS_TURLERI:
        return {"hata": f"tür şunlardan biri olmalı: {', '.join(SATIS_TURLERI)}"}
    urun_adi = (urun_adi or "").strip()[:300]
    if not urun_adi:
        return {"hata": "ürün adı zorunlu — hangi ürünün gittiği yazılmadan kayıt olmaz"}

    def _sayi(x):
        if x in (None, "", "-"):
            return None
        try:
            d = float(str(x).replace(",", "."))
        except ValueError:
            return None
        return d if d >= 0 else None

    yuk = json.dumps({
        "siparis_ref": (siparis_ref or "").strip()[:120] or None,
        "tur": tur, "alici": (alici or "").strip()[:200] or None,
        "urun_adi": urun_adi, "adet": _sayi(adet), "elle_fiyat": _sayi(elle_fiyat),
        "not_metni": (not_metni or "").strip()[:1000] or None,
        "giren": (giren or "operator")[:80],
    }, ensure_ascii=False)

    etiket = "gn" + secrets.token_hex(8)
    if f"${etiket}$" in yuk:
        return {"hata": "kodlama çakışması, kayıt yapılmadı"}
    sql = (
        "\\set ON_ERROR_STOP on\n"
        "BEGIN;\n"
        "SET SESSION AUTHORIZATION human_approver;\n"
        "INSERT INTO core.gonderi_notu"
        " (siparis_ref,tur,alici,urun_adi,adet,elle_fiyat,not_metni,giren)\n"
        "SELECT j->>'siparis_ref', j->>'tur', j->>'alici', j->>'urun_adi',\n"
        "       (j->>'adet')::numeric, (j->>'elle_fiyat')::numeric,\n"
        "       j->>'not_metni', j->>'giren'\n"
        f"  FROM (SELECT ${etiket}${yuk}${etiket}$::jsonb AS j) t;\n"
        "COMMIT;\n")
    try:
        r = subprocess.run(
            ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q",
             "-U", "n8n", "-d", "n8n", "-f", "-"],
            input=sql, capture_output=True, text=True, timeout=20, check=False)
    except Exception as exc:  # noqa: BLE001
        return {"hata": f"kayıt yapılamadı: {str(exc)[:160]}"}
    if r.returncode:
        return {"hata": f"kayıt reddedildi: {(r.stderr or '').strip()[:220]}"}
    return {"ok": True, "tur": tur, "urun_adi": urun_adi}


def _stok_sayim_ekle(urun_adi: str, adet, nerede: str, not_metni: str,
                     giren: str) -> dict:
    """Elle stok sayımını human_approver olarak yazar."""
    import secrets

    urun_adi = (urun_adi or "").strip()[:300]
    if not urun_adi:
        return {"hata": "ürün adı zorunlu"}
    try:
        sayi = int(float(str(adet).replace(",", ".")))
    except (TypeError, ValueError):
        return {"hata": "adet sayı olmalı"}
    if sayi < 0:
        return {"hata": "adet negatif olamaz"}

    yuk = json.dumps({
        "urun_adi": urun_adi, "adet": sayi,
        "nerede": (nerede or "DEPO").strip()[:80] or "DEPO",
        "not_metni": (not_metni or "").strip()[:500] or None,
        "giren": (giren or "operator")[:80]}, ensure_ascii=False)
    etiket = "st" + secrets.token_hex(8)
    if f"${etiket}$" in yuk:
        return {"hata": "kodlama çakışması, kayıt yapılmadı"}
    sql = (
        "\\set ON_ERROR_STOP on\n"
        "BEGIN;\n"
        "SET SESSION AUTHORIZATION human_approver;\n"
        "INSERT INTO core.stok_sayim (urun_adi,adet,nerede,not_metni,giren)\n"
        "SELECT j->>'urun_adi', (j->>'adet')::int, j->>'nerede',\n"
        "       j->>'not_metni', j->>'giren'\n"
        f"  FROM (SELECT ${etiket}${yuk}${etiket}$::jsonb AS j) t;\n"
        "COMMIT;\n")
    try:
        r = subprocess.run(
            ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q",
             "-U", "n8n", "-d", "n8n", "-f", "-"],
            input=sql, capture_output=True, text=True, timeout=20, check=False)
    except Exception as exc:  # noqa: BLE001
        return {"hata": f"kayıt yapılamadı: {str(exc)[:160]}"}
    if r.returncode:
        return {"hata": f"kayıt reddedildi: {(r.stderr or '').strip()[:220]}"}
    return {"ok": True, "urun_adi": urun_adi, "adet": sayi}


def _etiket_belgesi(siparisler: list) -> dict:
    """`scripts/kargo-etiket.py` ile HB-1006 sayfası üretir.

    🔴 Betik AYRI SÜREÇTE çağrılır, içeri import edilmez. Sebep: betik
    `python-docx` ve `Pillow` yükler ve altı etiketi uçtan indirir; bunu
    web sunucusunun içinde yapmak, uç yavaşladığında paneli kilitler.
    """
    idler = [str(x).strip() for x in siparisler if str(x).strip()][:60]
    if not idler:
        return {"hata": "etiketi alınacak gönderi seçilmedi"}
    try:
        r = subprocess.run(
            ["/opt/lcarlie/jarvis-phase2/venv/bin/python",
             "/opt/lcarlie/jarvis-phase2/scripts/kargo-etiket.py", *idler],
            capture_output=True, text=True, timeout=180, check=False,
            cwd="/opt/lcarlie/jarvis-phase2")
    except Exception as exc:  # noqa: BLE001
        return {"hata": f"etiket üretilemedi: {str(exc)[:200]}"}
    ciktilar = [s.strip() for s in (r.stdout or "").splitlines() if s.strip()]
    dosya = next((s for s in reversed(ciktilar) if s.endswith(".docx")), None)
    if r.returncode or not dosya:
        return {"hata": "etiket alınamadı: "
                        + ((r.stderr or "").strip()[:300] or "bilinmeyen sebep")}
    return {"ok": True, "dosya": Path(dosya).name,
            "baglanti": "/etiket/" + Path(dosya).name,
            "ozet": ciktilar[-2] if len(ciktilar) > 1 else ""}


def _kreatif_partiler(limit: int = 12) -> dict:
    """Diskteki kreatif partilerini panel icin ozetler.

    🔴 VERITABANINA GITMEZ. Brief ve inceleme zaten dosya olarak duruyor;
    ayni seyi bir de tabloya yazmak iki dogruluk kaynagi yaratirdi.

    🔴 EKSIK ASAMA GIZLENMEZ. Bir partinin gorseli yoksa `gorsel: 0` ve
    `durum: "ONAY_BEKLIYOR"` diye gorunur -- panelde bos birakip "yakinda"
    demek, hangi partinin nerede takildigini saklamak olurdu.
    """
    kok = KREATIF_DIR
    if not kok.is_dir():
        return {"partiler": [], "not": "henüz kreatif partisi yok"}
    partiler = []
    for brief_yolu in sorted(kok.glob("*.json"), reverse=True):
        if brief_yolu.stem.endswith("-gorseller"):
            continue
        try:
            b = json.loads(brief_yolu.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        parti = brief_yolu.stem
        gorsel_kok = kok / f"{parti}-gorseller"
        inceleme = None
        ince_yolu = gorsel_kok / "inceleme.json"
        if ince_yolu.is_file():
            try:
                inceleme = json.loads(ince_yolu.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                inceleme = None
        kareler = []
        for g in (inceleme or {}).get("gorseller") or []:
            o = g.get("olcum") or {}
            kareler.append({
                "dosya": g.get("dosya"), "oran": g.get("oran"),
                "ust_yazi": g.get("ust_yazi"), "alt_yazi": g.get("alt_yazi"),
                "karar": g.get("direktor_karari"),
                "gerekce": str(g.get("direktor_gerekce") or "")[:400],
                "beyaz_sapma": o.get("beyaz_sapma"),
                "urun_oran": o.get("urun_oran"),
                # 🔴 `departman` ARAYUZE GECMELI: sahip "bu gorselde logo
                # yanlis" dediginde muhatabin kim oldugu bu alandan okunur.
                # Eskiden yalniz `uye` (insan adi) geciyordu ve panel
                # kime yazilacagini soyleyemiyordu.
                "inceleme": [{"uye": i.get("uye"), "karar": i.get("karar"),
                              "departman": i.get("departman"),
                              "gerekce": str(i.get("gerekce") or "")[:300]}
                             for i in (g.get("inceleme") or [])],
                "url": f"/kreatif/{parti}-gorseller/{g.get('dosya')}",
                "etiket_url": f"/kreatif/{parti}-gorseller/etiket-kontrol/"
                              f"{str(g.get('dosya') or '')[:2]}.jpg",
            })
        urun = (b.get("urun") or {})
        fk = b.get("fiyat_konumu_olcumu") or {}
        partiler.append({
            "parti": parti,
            # 🔴 Klasor adi AYRI gonderilir. Gorsel baglantilari bir kez
            # "-gorseller" ekini kaybettigi icin 404 dondurmustu; arayuzun
            # bu eki kendisi uretmesi ayni hatayi tekrar davet eder.
            "parti_klasor": f"{parti}-gorseller",
            "urun_adi": urun.get("urun_adi"),
            "uretildi": b.get("uretildi"),
            "fiyat_cumlesi": fk.get("cumle"),
            "rakip_acilari": [r.get("aci") for r in (b.get("rakip") or [])],
            "kurul_sayisi": len(b.get("kurul") or []),
            "silinen_cumle": len(b.get("mevzuat_silinen") or []),
            "tutarsiz_reklam": len(b.get("tutarlilik") or []),
            "promptlar": [{"ad": g.get("ad"), "oran": g.get("oran"),
                           "hangi_aci": g.get("hangi_aci"),
                           "ust_yazi": g.get("ust_yazi"),
                           "alt_yazi": g.get("alt_yazi"),
                           "sahne_istemi": g.get("sahne_istemi")}
                          for g in (b.get("gorseller") or [])],
            "red_team": [{"agirlik": i.get("agirlik"),
                          "alinti": str(i.get("alinti") or "")[:200],
                          "itiraz": str(i.get("itiraz") or "")[:400],
                          "duzeltme": str(i.get("duzeltme") or "")[:300]}
                         for i in ((b.get("red_team") or {}).get("itirazlar") or [])],
            "kurul": [{"uye": k.get("uye"), "gorev": k.get("gorev"),
                       "soyledigi": str(k.get("soyledigi") or "")[:300]}
                      for k in (b.get("kurul") or [])],
            "kareler": kareler,
            "durum": ("GORSEL_INCELENDI" if kareler
                      else ("GORSEL_VAR" if gorsel_kok.is_dir()
                            else "ONAY_BEKLIYOR")),
            "brief_url": f"/kreatif/{parti}.md",
        })
        if len(partiler) >= limit:
            break
    return {"partiler": partiler, "toplam": len(partiler)}



class Handler(BaseHTTPRequestHandler):
    server_version = "JarvisWebConsole/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # quieter, no client details leaked
        sys.stderr.write("[web] " + (fmt % args) + "\n")

    # -- response helpers ---------------------------------------------------
    def _send_json(self, status: int, payload: dict, extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or []):
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        """Statik dosya. JS/CSS icin ETag ile DOGRULAMALI onbellek.

        🔴 24.09.2026'da olculdu: dagitim yapildi, sunucudaki app.js yenilendi,
        ama operatorun tarayicisi 'max-age=300' yuzunden eski dosyayi
        kullanmaya devam etti -- yeni sekme panelde HIC gorunmedi. Sayfanin
        kendisi zaten no-store oldugu icin HTML taze geliyordu; yani yeni HTML
        ile ESKI JS birlikte calisiyordu. Bu en kotu birlesim: hata vermez,
        sadece eksik davranir.

        Cozum surumleme degil DOGRULAMA: 'no-cache' tarayiciya "kullanmadan
        once sor" der. Dosya degismediyse ETag eslesir ve 304 doner -- govde
        hic gonderilmez, yani maliyet neredeyse sifir. Degistiyse aninda
        yeni dosya iner ve kimsenin Ctrl+F5 yapmasi gerekmez.

        HTML eskisi gibi no-store kalir: onun icin dogrulama bile gereksiz.
        """
        data = path.read_bytes()
        if path.suffix in (".html",):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        # ETag icerikten turetilir: mtime'a guvenmek, dagitimda `cp -p` ile
        # tarih korunan bir dosyayi "degismemis" saymak demekti.
        etag = '"%s"' % hashlib.sha256(data).hexdigest()[:32]
        if (self.headers.get("If-None-Match") or "").strip() == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _set_session_cookies(self, session: auth.Session) -> list[tuple[str, str]]:
        secure = "; Secure" if os.environ.get("JARVIS_WEB_INSECURE_COOKIES") != "1" else ""
        return [
            ("Set-Cookie", f"{SESSION_COOKIE}={session.session_id}; Path=/; HttpOnly{secure}; SameSite=Strict"),
            ("Set-Cookie", f"{CSRF_COOKIE}={session.csrf_token}; Path=/{secure}; SameSite=Strict"),
        ]

    def _clear_session_cookies(self) -> list[tuple[str, str]]:
        return [
            ("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; HttpOnly; Max-Age=0; SameSite=Strict"),
            ("Set-Cookie", f"{CSRF_COOKIE}=; Path=/; Max-Age=0; SameSite=Strict"),
        ]

    def _current_session(self) -> auth.Session | None:
        cookies = _parse_cookies(self)
        sid = cookies.get(SESSION_COOKIE)
        if not sid:
            return None
        return sessions.get(sid)

    def _require_csrf(self, session: auth.Session) -> bool:
        provided = self.headers.get("X-CSRF-Token", "")
        return bool(provided) and provided == session.csrf_token

    def _route_kargo_post(self, path: str, session) -> None:
        """Kargo işlemleri. Biri PARA HARCAR, üçü harcamaz.

        🔴 BU YOLA OTOMATİK GİRİLEMEZ. `_route_api_post` bu çağrıdan önce
        oturumu ve CSRF başlığını doğrular; döngünün, ajanların ve
        zamanlayıcının oturumu yoktur. Para harcayan tek uç
        (`/api/kargo/barkod`) böylece yalnız ekrandaki düğmeden geçer.
        """
        from jarvis import kargo_islem as ki

        body = _read_json_body(self)
        try:
            if path == "/api/kargo/taslak":
                # ÜCRETSİZ. Taslak açmak kargoyu çağırmaz, barkod üretmez.
                self._send_json(200, ki.taslak_olustur(
                    alici=str(body.get("alici", "")),
                    telefon=str(body.get("telefon", "")),
                    il=str(body.get("il", "")),
                    ilce=str(body.get("ilce", "")),
                    adres=str(body.get("adres", "")),
                    icerik=str(body.get("icerik", "")),
                    desi=body.get("desi"),
                    karsi_odemeli=bool(body.get("karsi_odemeli")),
                    kapida_tutar=body.get("kapida_tutar"),
                    kapida_tur=str(body.get("kapida_tur", "CASH")),
                    referans=str(body.get("referans", ""))))
                return

            if path == "/api/kargo/fiyat":
                # ÜCRETSİZ. Hangi taşıyıcı ne kadar.
                self._send_json(200, ki.ucret_sor(str(body.get("siparis_id", ""))))
                return

            if path == "/api/kargo/barkod":
                # 🔴 PARA HARCAR. `kargo_islem` çağrıdan ÖNCE fiyatı uçtan
                # doğrular ve `core.kargo_karar` tablosuna satır yazar.
                self._send_json(200, ki.barkod_uret(
                    siparis_id=str(body.get("siparis_id", "")),
                    tasiyici=str(body.get("tasiyici", "")),
                    gosterilen_ucret=body.get("gosterilen_ucret"),
                    karsi_odemeli=bool(body.get("karsi_odemeli")),
                    kapida_tutar=body.get("kapida_tutar"),
                    veren=session.username))
                return

            if path == "/api/kargo/etiket":
                # ÜCRETSİZ. Etiketleri HB-1006 sayfasına dizer.
                self._send_json(200, _etiket_belgesi(body.get("siparisler") or []))
                return
        except ki.IslemHatasi as hata:
            # Sahibin okuyacağı hata: Türkçe ve sebepli.
            self._send_json(400, {"error": str(hata)})
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send_json(502, {"error": f"kargo işlemi yapılamadı: {str(exc)[:200]}"})
            return

        self._send_json(404, {"error": "not found"})

    # -- routing --------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            # Meta webhook'u oturum AÇAMAZ; bu yol kimlik kapısından önce
            # gelir. Karşılığında kendi kapısı var: doğrulama anahtarı (GET)
            # ve HMAC imzası (POST). Başka hiçbir yol bu istisnayı almaz.
            if path == meta_webhook.WEBHOOK_PATH:
                self._meta_dogrulama(parse_qs(parsed.query))
            elif path.startswith("/api/"):
                self._route_api_get(path, parse_qs(parsed.query))
            elif path.startswith("/kreatif/"):
                self._route_kreatif(path)
            elif path.startswith("/gonderi-gorsel/"):
                self._route_gonderi_gorsel(path)
            elif path.startswith("/katalog-gorsel/"):
                self._route_katalog_gorsel(path)
            elif path.startswith("/karo/"):
                self._route_karo(path)
            elif path.startswith("/etiket/"):
                self._route_etiket(path)
            elif path.startswith("/canva/"):
                self._route_canva(path, parse_qs(parsed.query))
            else:
                self._route_static(path)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send_json(500, {"error": "internal error"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == meta_webhook.WEBHOOK_PATH:
                self._meta_olay()
            else:
                self._route_api_post(parsed.path)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send_json(500, {"error": "internal error"})

    # -- Meta webhook -------------------------------------------------------
    def _meta_dogrulama(self, query: dict) -> None:
        """Meta'nın ilk GET el sıkışması. Gövde DÜZ METİN döner, JSON değil."""
        kod, govde = meta_webhook.dogrulama_yanit_ver(query)
        ham = govde.encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(ham)))
        self.end_headers()
        self.wfile.write(ham)

    def _meta_olay(self) -> None:
        """Gelen mesaj olayı: imzayı doğrula, kuyruğa yaz, HIZLI 200 dön.

        🔴 Gövde her hâlükârda OKUNUR -- imza geçersiz olsa bile. Okumadan
        yanıt dönmek keep-alive bağlantısını bozuyor ve sonraki istek
        gövdenin içinden ayrıştırılıp 501 veriyordu; bu hata bu serviste
        daha önce yaşandı.
        """
        uzunluk = int(self.headers.get("Content-Length", 0) or 0)
        govde = self.rfile.read(uzunluk) if 0 < uzunluk <= 1_048_576 else b""

        giz = meta_webhook.uygulama_gizi()
        if not giz:
            # Sessizce güvensiz çalışmaktansa açıkça durmak: giz olmadan
            # bu uç, isteyen herkesin sahte müşteri mesajı yazabildiği bir
            # kapıdır.
            sys.stderr.write("[meta-webhook] META_APP_SECRET yok; olay reddedildi\n")
            self._send_json(503, {"error": "META_APP_SECRET tanimli degil"})
            return
        if not meta_webhook.imza_gecerli(
                govde, self.headers.get("X-Hub-Signature-256", ""), giz):
            self._send_json(403, {"error": "imza gecersiz"})
            return
        try:
            yuk = json.loads(govde.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "gecersiz json"})
            return

        olaylar = meta_webhook.olaylari_ayristir(yuk)
        yazilan = meta_webhook.kuyruga_yaz(olaylar, META_KUYRUK)
        # Meta yanıt gecikirse AYNI olayı tekrar gönderir; burada iş
        # yapılmaz, yalnız kuyruğa alınır.
        self._send_json(200, {"alindi": yazilan})

    # -- uretilen kreatif gorselleri ---------------------------------------
    @staticmethod
    def _kreatif_konusu(action_id: int) -> str:
        """Onerinin konusunu KARARDAN ONCE okur.

        🔴 ILK SURUM BOZUKTU VE SESSIZCE HIC CALISMAZDI. Kanca
        `_operator.decide(...)` sonucundan `payload.subject_ref` okumaya
        calisiyordu; oysa decide yalnizca
        {action_id, decision, reason, still_pending, confirmed} donuyor --
        yuk YOK. Sebebi de kodda yazili: core.ai_action_proposal owner-only,
        geri okunamiyor, karar "pending listesinden dustu mu" diye
        dogrulaniyor.

        Bu yuzden konu KARARDAN ONCE, oneri hala PENDING iken okunur;
        inspect() zaten yalnizca PENDING oneriyi gosteriyor.
        """
        try:
            oneri = _operator.inspect(int(action_id))
        except Exception:  # noqa: BLE001 - okunamazsa uretim baslamaz, o kadar
            return ""
        return str(((oneri or {}).get("payload") or {}).get("subject_ref") or "")

    @staticmethod
    def _kreatif_uretimi_baslat(konu: str, sonuc: dict) -> str | None:
        """Sahip bir kreatif BRIEF'ini onayladiysa gorsel uretimini baslatir.

        🔴 SAHIP KARARI (21.09.2026): "brief verilsin, uretim benim onayim
        olmadan yapilmasin ama promptlar hazirlansin."

        Haftalik kosu hic gorsel uretmez; sadece arastirma ve prompt uretir.
        Gorsel URETIMINI BASLATAN TEK SEY, sahibin bu ekranda verdigi onaydir.
        Bu yuzden tetik burada duruyor: bir zamanlayiciya baglansaydi onay
        kapisi dekor olurdu.

        🔴 Sadece APPROVED ve sadece `kreatif-brief:` konusu tetikler.
        Onaylanan baska bir seyin yanlislikla uretim baslatmasi, sahibin
        onayladigi seyden baskasini yapmak olurdu.
        """
        if str(sonuc.get("decision") or "") != "APPROVED":
            return None
        # 🔴 `confirmed` sarttir: karar pending listesinden dusmediyse
        # APPROVE gecmemis demektir ve uretim baslatilmaz.
        if not sonuc.get("confirmed"):
            return None
        if not konu.startswith("kreatif-brief:"):
            return None
        parti = konu.split(":", 1)[1].strip()
        # Parti adi dosya yoluna girecek: harf, rakam ve tire disinda bir sey
        # varsa calistirilmaz. Kabuk enjeksiyonuna acik tek nokta burasi.
        if not parti or not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", parti):
            return None
        betik = Path(__file__).resolve().parent.parent / "scripts" / "kreatif-uret.sh"
        if not betik.is_file():
            return None
        gunluk = KREATIF_DIR.parent / "kreatif-uretim.log"
        try:
            with open(gunluk, "ab") as f:
                subprocess.Popen(
                    ["/bin/bash", str(betik), parti],
                    cwd=str(betik.parent.parent),
                    env={**os.environ, "JARVIS_MEMORY_TRANSPORT": "local-docker"},
                    stdout=f, stderr=f, stdin=subprocess.DEVNULL,
                    start_new_session=True)
        except OSError as hata:
            return f"uretim baslatilamadi: {hata}"
        return parti

    def _route_kreatif(self, path: str) -> None:
        """Uretilen reklam gorsellerini servis eder.

        🔴 OTURUM ZORUNLU. Statik klasorun icine konup `_route_static` ile
        servis edilseydi kimlik kapisinin DISINDA kalirdi: yayina girmemis,
        heniz onaylanmamis kreatifler acik internete dusetdi. Onay kuyrugundaki
        bir seyin herkese acik olmasi, onay kavramini anlamsiz kilar.

        🔴 Yol kacisi ayrica engellenir: `..` iceren bir istek resolve()
        sonrasi KREATIF_DIR disina cikarsa reddedilir -- `_route_static`
        icindeki ayni desen.
        """
        if self._current_session() is None:
            self._send_json(401, {"error": "oturum gerekli"})
            return
        hedef = (KREATIF_DIR / path[len("/kreatif/"):]).resolve()
        if KREATIF_DIR not in hedef.parents:
            self._send_json(404, {"error": "not found"})
            return
        if not hedef.is_file():
            self._send_json(404, {"error": "not found"})
            return
        tur = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".json": "application/json; charset=utf-8",
               ".md": "text/markdown; charset=utf-8",
               }.get(hedef.suffix.lower(), "application/octet-stream")
        self._send_file(hedef, tur)

    def _route_gonderi_gorsel(self, path: str) -> None:
        """Uretilen gonderi gorseli. Oturum zorunlu -- onaylanmamis
        kreatif acik internete dusmemeli."""
        if self._current_session() is None:
            self._send_json(401, {"error": "oturum gerekli"})
            return
        try:
            hedef = katalog.gonderi_gorsel_yolu(path[len("/gonderi-gorsel/"):])
        except katalog.KatalogHatasi as hata:
            self._send_json(404, {"error": str(hata)})
            return
        veri = hedef.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(veri)))
        self.send_header("Cache-Control", "private, max-age=2592000")
        self.end_headers()
        self.wfile.write(veri)

    def _route_katalog_gorsel(self, path: str) -> None:
        """Urun gorseli: /katalog-gorsel/<dosya>

        🔴 OTURUM ZORUNLU. Gorseller statik klasorde DEGIL; oraya konsaydi
        kimlik kapisinin disinda kalir ve urun fotograflari acik internete
        duserdi. Katalog eczaneye sunum icin; herkese acik bir dosya deposu
        degil.

        Onbellek uzun: dosya adi ADRESIN karmasi, icerik degisirse ad da
        degisir -- bayat gorsel gosterme riski yok.
        """
        if self._current_session() is None:
            self._send_json(401, {"error": "oturum gerekli"})
            return
        try:
            hedef = katalog.gorsel_yolu(path[len("/katalog-gorsel/"):])
        except katalog.KatalogHatasi as hata:
            self._send_json(404, {"error": str(hata)})
            return
        veri = hedef.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/webp")
        self.send_header("Content-Length", str(len(veri)))
        self.send_header("Cache-Control", "private, max-age=2592000")
        self.end_headers()
        self.wfile.write(veri)

    def _route_karo(self, path: str) -> None:
        """Harita karosu: /karo/{z}/{x}/{y}.png

        🔴 OTURUM ZORUNLU. Kapı olmasaydı uç, herkesin kullanabildiği bir
        karo vekiline dönerdi -- yukarı akıştaki servisin şartlarını bizim
        adımıza çiğneyen, diskimizi dolduran bir uç.

        Önbellek başlığı UZUN: karo görüntüsü değişmez sayılır. Tazeliği
        sunucu tarafı yönetir (harita.TAZELIK_GUN); tarayıcıya her seferinde
        sordurmak, sahada mobil veriyi boşa harcardı.
        """
        if self._current_session() is None:
            self._send_json(401, {"error": "oturum gerekli"})
            return
        parcalar = path[len("/karo/"):].split("/")
        if len(parcalar) != 3 or not parcalar[2].endswith(".png"):
            self._send_json(404, {"error": "not found"})
            return
        try:
            z = int(parcalar[0])
            x = int(parcalar[1])
            y = int(parcalar[2][:-4])
        except ValueError:
            self._send_json(404, {"error": "not found"})
            return
        try:
            veri = harita.karo(z, x, y)
        except harita.HaritaHatasi as hata:
            # Sebep gizlenmez; ama gövde resim degil JSON oldugu icin
            # tarayici kirik kare gosterir ve konsolda sebebi okunur.
            self._send_json(404, {"error": str(hata)})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(veri)))
        self.send_header("Cache-Control", "public, max-age=604800")
        self.end_headers()
        self.wfile.write(veri)

    def _route_etiket(self, path: str) -> None:
        """Üretilen HB-1006 etiket belgesini servis eder.

        `_route_kreatif` ile AYNI kapı ve aynı yol-kaçışı kontrolü: oturum
        zorunlu, `..` ile dizin dışına çıkan istek reddedilir. Buradaki
        dosyalar alıcı adı ve açık adres taşır.
        """
        if self._current_session() is None:
            self._send_json(401, {"error": "oturum gerekli"})
            return
        hedef = (ETIKET_DIR / path[len("/etiket/"):]).resolve()
        if ETIKET_DIR not in hedef.parents or not hedef.is_file():
            self._send_json(404, {"error": "not found"})
            return
        tur = {".docx": "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document",
               ".png": "image/png"}.get(hedef.suffix.lower(),
                                        "application/octet-stream")
        self._send_file(hedef, tur)

    def _route_canva(self, path: str, query: dict) -> None:
        """Canva OAuth: baslatma (oturumlu) ve geri donus (state korumali)."""
        from jarvis import canva

        if path == "/canva/baslat":
            # 🔴 Oturum ZORUNLU: yetkilendirmeyi yalniz sahip baslatir.
            if self._current_session() is None:
                self._send_json(401, {"error": "oturum gerekli"})
                return
            try:
                url = canva.yetki_baglantisi(
                    "https://jarvis.lcarlie.shop/canva/geri")
            except canva.CanvaHatasi as hata:
                self._send_json(400, {"error": str(hata)})
                return
            # Tarayiciyi dogrudan Canva'ya yolla.
            self.send_response(302)
            self.send_header("Location", url)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path == "/canva/geri":
            # 🔴 Oturum ARANMAZ (Canva'dan gelen istek cerez tasimayabilir)
            # ama `state` PKCE kaydiyla karsilastirilir; uymazsa reddedilir.
            kod = (query.get("code") or [""])[0]
            durum = (query.get("state") or [""])[0]
            hata_k = (query.get("error") or [""])[0]
            if hata_k:
                govde = f"Canva yetkilendirmeyi reddetti: {hata_k}"
            else:
                try:
                    sonuc = canva.geri_donus(kod, durum)
                    govde = ("Canva bağlandı. Verilen yetkiler: "
                             + str(sonuc.get("kapsam", "")))
                except canva.CanvaHatasi as hata:
                    govde = f"Bağlanamadı: {hata}"
            # Duz metin: bu sayfa bir kez gorulur, tasarima gerek yok.
            ham = govde.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(ham)))
            self.end_headers()
            self.wfile.write(ham)
            return

        self._send_json(404, {"error": "not found"})

    # -- static frontend --------------------------------------------------
    def _route_static(self, path: str) -> None:
        if path == "/":
            path = "/index.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR not in target.parents and target != STATIC_DIR:
            self._send_json(404, {"error": "not found"})
            return
        if not target.is_file():
            self._send_json(404, {"error": "not found"})
            return
        content_type = {
            ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
            ".webmanifest": "application/manifest+json",
            ".jpg": "image/jpeg", ".webp": "image/webp", ".otf": "font/otf", ".woff2": "font/woff2",
        }.get(target.suffix, "application/octet-stream")
        self._send_file(target, content_type)

    # -- authenticated API --------------------------------------------------
    def _route_api_get(self, path: str, query: dict) -> None:
        if path == "/api/login":
            self._send_json(405, {"error": "use POST"})
            return

        session = self._current_session()
        if path == "/api/session":
            if session is None:
                self._send_json(200, {"authenticated": False})
                return
            self._send_json(200, {"authenticated": True, "username": session.username,
                                  "csrf_token": session.csrf_token})
            return

        if session is None:
            self._send_json(401, {"error": "authentication required"})
            return

        if path == "/api/status":
            self._send_json(200, self._build_status())
            return
        if path == "/api/activity":
            limit = int((query.get("limit") or ["30"])[0])
            limit = max(1, min(limit, 200))
            audit = _tail_jsonl(STATE_DIR / "audit.jsonl", limit)
            findings = _tail_jsonl(STATE_DIR / "findings.jsonl", limit)
            self._send_json(200, {"audit": audit, "findings": findings})
            return
        if path == "/api/kreatif":
            try:
                evidence = _memory._fetch("kreatif_performans")
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": "kreatif verisi okunamadi",
                                      "detail": str(exc)[:200]})
                return
            self._send_json(200, {
                "rows": evidence.records,
                "source": evidence.source,
                "latency_ms": evidence.latency_ms,
                # Panelin esigi kendi uydurmamasi icin sunucudan gelir.
                "ornek_esigi": 1000,
            })
            return
        if path == "/api/urun-alanlari":
            try:
                evidence = _memory._fetch("urun_alan_karsilastirma")
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": "urun alanlari okunamadi",
                                      "detail": str(exc)[:200]})
                return
            self._send_json(200, {
                "rows": evidence.records,
                "source": evidence.source,
                "latency_ms": evidence.latency_ms,
                # Panel bu satiri gostermeli: duzenleme dogrudan uygulanmaz.
                "uyari": ("Degisiklikler dogrudan uygulanmaz; onay kuyruguna "
                          "gonderilir. Dis platforma yazma izni kapali."),
            })
            return
        if path == "/api/fiyat-matrisi":
            try:
                evidence = _memory._fetch("platform_fiyat_matrisi")
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": "fiyat matrisi okunamadi",
                                      "detail": str(exc)[:200]})
                return
            self._send_json(200, {
                "rows": evidence.records,
                "source": evidence.source,
                "latency_ms": evidence.latency_ms,
                # Panelin "bu sayi ne kadar guvenilir" diyebilmesi icin.
                "uyari": ("Maliyet sahip beyanidir (tum urunlere ortalama "
                          "400 TL), gercek urun maliyeti degildir. Marj "
                          "yaklasiktir."),
            })
            return
        if path == "/api/sistem":
            # Uc makinenin kaynak kullanimi + kaynak politikasi.
            # Sunucu OLCULUR (anlik), PC'ler state/hosts/*.json'dan
            # OKUNUR -- onlar NAT arkasinda, kendileri iter.
            self._send_json(200, sistem.gorunum(STATE_DIR, _host_metrics()))
            return
        if path == "/api/kademe":
            self._send_json(200, _kademe_gorunumu())
            return
        if path == "/api/saha/konum":
            # Yonetici gorunumu: kim nerede. "BAYAT" hareketsizlik DEGILDIR;
            # cevapta bu uyari da doner ve panel onu AYNEN gosterir.
            try:
                self._send_json(200, saha.son_konumlar())
            except saha.SahaHatasi as hata:
                self._send_json(502, {"error": str(hata)})
            return
        if path == "/api/saha/konum/gecmis":
            # Kisi KENDI verisini gorur. Takip edilenin goremedigi bir kayit,
            # denetlenemeyen bir kayittir.
            s2 = query
            kim = (s2.get("kullanici") or [session.username])[0]
            if kim != session.username and not getattr(session, "admin", False):
                kim = session.username
            try:
                self._send_json(200, saha.konum_gecmisi(
                    kim, saat=(s2.get("saat") or [12])[0]))
            except saha.SahaHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/katalog":
            try:
                self._send_json(200, katalog.katalog())
            except katalog.KatalogHatasi as hata:
                # "Uretilmedi" ile "urun yok" ayri seyler; sebep aynen doner.
                self._send_json(503, {"error": str(hata)})
            return
        if path == "/api/ig-plan":
            try:
                self._send_json(200, katalog.ig_plan(
                    durum=(query.get("durum") or [""])[0],
                    limit=(query.get("limit") or [50])[0]))
            except katalog.KatalogHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/katalog/not":
            try:
                self._send_json(200, katalog.notlar(
                    urun_slug=(query.get("urun") or [""])[0],
                    hedef_anahtari=(query.get("hedef") or [""])[0],
                    limit=(query.get("limit") or [50])[0]))
            except katalog.KatalogHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/saha/filtreler":
            # Secenek SAYILARI mevcut secime gore hesaplanir; bu yuzden
            # filtre ucu da filtre parametreleri alir.
            try:
                self._send_json(200, saha.filtre_secenekleri(
                    tur=query.get("tur"), brans=query.get("brans"),
                    ilce=query.get("ilce"),
                    arama=(query.get("arama") or [None])[0],
                    ziyaret_durumu=(query.get("ziyaret") or [None])[0],
                    eleme=(query.get("eleme") or [None])[0]))
            except saha.SahaHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/saha":
            s = query
            def _ilk(ad, varsayilan=None):
                d = s.get(ad, [])
                return d[0] if d else varsayilan
            try:
                self._send_json(200, saha.hedefler(
                    tur=s.get("tur"), brans=s.get("brans"), ilce=s.get("ilce"),
                    enlem=_ilk("enlem"), boylam=_ilk("boylam"),
                    yaricap_m=_ilk("yaricap_m"),
                    ziyaret_durumu=_ilk("ziyaret"), arama=_ilk("arama"),
                    eleme=_ilk("eleme"), limit=_ilk("limit", 200)))
            except saha.SahaHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/isler":
            # Hatirlatma icin PC-2'nin rapor TAZELIGI gerekiyor. Burada
            # yeniden hesaplanmaz -- iki yerde iki farkli tanim olmasi bu
            # projede daha once yasanmis bir hata sinifi.
            self._send_json(200, isler.durum(
                None, pc2_durum=sistem.makine_durumu(STATE_DIR, "pc2")))
            return
        if path == "/api/hafiza":
            self._send_json(200, _hafiza_gorunumu())
            return
        if path == "/api/satislar":
            self._send_json(200, _satis_merkezi())
            return

        if path == "/api/asistan":
            from jarvis import asistan
            # 🔴 HER KAYNAK AYRI TRY. Hepsi tek blokta olsaydı bir arıza
            # bütün sekmeyi boş gösterirdi -- ve boş onay sekmesi
            # "imzalanacak iş yok" diye okunur. En tehlikeli yanlış bu.
            cevap: dict = {}
            hatalar: dict = {}
            for ad, fn in (
                ("hatirlaticilar", asistan.hatirlaticilar),
                ("haberler", asistan.haberler),
                ("gundem", asistan.gundem),
                ("tasarim_onay", asistan.tasarim_onay_bekleyen),
            ):
                try:
                    cevap[ad] = fn()
                except Exception as exc:  # noqa: BLE001
                    cevap[ad] = []
                    hatalar[ad] = str(exc)[:160]
            try:
                cevap["oneriler"] = _operator.list_pending()
            except Exception as exc:  # noqa: BLE001
                cevap["oneriler"] = []
                hatalar["oneriler"] = str(exc)[:160]
            if hatalar:
                cevap["hatalar"] = hatalar
            self._send_json(200, cevap)
            return

        if path == "/api/tasarim":
            from jarvis import tasarim
            try:
                self._send_json(200, {
                    "sablonlar": tasarim.sablonlar(),
                    "isler": tasarim.isler(adet=40),
                })
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": str(exc)[:200]})
            return

        if path == "/api/canva":
            from jarvis import canva
            try:
                self._send_json(200, canva.durum())
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": str(exc)[:200]})
            return

        if path == "/api/kreatif-itiraz":
            # Sahibin acik itirazlari ve muhatabin cevaplari.
            from jarvis import kreatif_itiraz
            parti = (query.get("parti") or [""])[0] or None
            try:
                self._send_json(200, {"itirazlar": kreatif_itiraz.liste(parti),
                                      "konular": list(kreatif_itiraz.KONULAR)})
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": f"itirazlar okunamadı: {str(exc)[:200]}"})
            return

        if path == "/api/kargo":
            # Gönderiler + verilmiş barkod kararları. Hiçbiri para harcamaz.
            from jarvis import kargo_islem
            try:
                self._send_json(200, kargo_islem.gonderiler(15))
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": f"kargo okunamadı: {str(exc)[:200]}"})
            return

        if path == "/api/musteri":
            # 🔴 Ad/telefon/e-posta İSTEK ANINDA okunur, hiçbir yere
            # yazılmaz. Oturum kapısının arkasında; `_route_api_get` bu
            # noktadan önce kimliği doğrulamış oluyor.
            from jarvis import musteri
            try:
                self._send_json(200, musteri.musteri_listesi())
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": f"müşteriler okunamadı: {str(exc)[:200]}"})
            return

        if path == "/api/musteri/kart":
            from jarvis import musteri
            kimlik = (query.get("id") or [""])[0]
            try:
                self._send_json(200, musteri.musteri_karti(kimlik))
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": f"kart okunamadı: {str(exc)[:200]}"})
            return

        if path == "/api/iade":
            from jarvis import musteri
            try:
                self._send_json(200, musteri.iade_ozeti())
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": f"iade okunamadı: {str(exc)[:200]}"})
            return

        if path == "/api/kargo/kapida":
            # Kapıda ödemeli gönderiler: Wix ciro hattında GÖRÜNMEYEN para.
            from jarvis import kargo_islem
            try:
                self._send_json(200, kargo_islem.kapida_ozet())
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": f"okunamadı: {str(exc)[:200]}"})
            return

        if path == "/api/kreatif-parti":
            # Uretilen kreatif partileri: brief, promptlar, gorseller,
            # ekip incelemesi ve direktor karari.
            self._send_json(200, _kreatif_partiler())
            return

        if path == "/api/panel":
            # Bolum listesi: uc nokta kesfedilebilir olsun, arayuz sabit
            # isim listesi tasimak zorunda kalmasin.
            self._send_json(200, {"sections": ["ekip", "veri", "ajanlar", "raporlar", "ayarlar"]})
            return
        if path.startswith("/api/panel/"):
            section = path.rsplit("/", 1)[-1]
            builder = {"ekip": _panel_ekip, "veri": _panel_veri, "ajanlar": _panel_ajanlar,
                       "raporlar": _panel_raporlar, "ayarlar": _panel_ayarlar}.get(section)
            if builder is None:
                self._send_json(404, {"error": "unknown panel"})
                return
            self._send_json(200, builder())
            return
        if path == "/api/proposals":
            try:
                pending = _operator.list_pending()
                self._send_json(200, {"pending": pending})
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
            return
        if path.startswith("/api/proposals/"):
            action_id = path.rsplit("/", 1)[-1]
            try:
                proposal = _operator.inspect(int(action_id))
            except (ValueError, TypeError):
                self._send_json(400, {"error": "invalid action id"})
                return
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
                return
            if proposal is None:
                self._send_json(404, {"error": "not found (pending only)"})
                return
            self._send_json(200, proposal)
            return

        self._send_json(404, {"error": "not found"})

    def _route_api_post(self, path: str) -> None:
        if path == "/api/login":
            self._handle_login()
            return

        session = self._current_session()
        if session is None:
            self._send_json(401, {"error": "authentication required"})
            return
        if not self._require_csrf(session):
            self._send_json(403, {"error": "csrf token missing or invalid"})
            return

        if path == "/api/logout":
            sessions.destroy(session.session_id)
            self._send_json(200, {"ok": True}, self._clear_session_cookies())
            return
        if path == "/api/fiyat-toplu-onizleme":
            # ONIZLEME: hicbir sey yazilmaz, yalniz hesaplanir.
            body = _read_json_body(self)
            if not isinstance(body, dict):
                self._send_json(400, {"error": "gecersiz govde"})
                return
            try:
                sonuc = _toplu_onizleme(body)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": "onizleme uretilemedi",
                                      "detail": str(exc)[:200]})
                return
            self._send_json(200, sonuc)
            return
        if path == "/api/pazar/bulgu":
            # Operatorun kendi gozlemi. Rakip fiyati otomatik alinamadigi icin
            # (olculdu: tum pazaryerleri 403) bu kanal gercek bir yetenek,
            # yedek degil. human_approver olarak yazilir -- insan beyanidir.
            body = _read_json_body(self)
            sonuc = _pazar_bulgu_ekle(
                kod=str(body.get("kod", "")),
                seviye=str(body.get("seviye", "")),
                bulgu=str(body.get("bulgu", "")),
                kaynak=str(body.get("kaynak", "")),
                tarih=str(body.get("tarih", "")),
                yorum=str(body.get("yorum", "")),
            )
            self._send_json(200 if sonuc.get("ok") else 400, sonuc)
            return
        if path == "/api/ekip/sor":
            # Departman sorumlusuna soru. Model cagrilir ama KANITA bagli:
            # kanit yoksa model hic cagrilmaz, cevaptaki dogrulanmayan
            # sayilar ayrica doner. Detay: _ekip_sor().
            body = _read_json_body(self)
            kod = str(body.get("kod", "")).strip().upper()[:40]
            soru = str(body.get("soru", ""))[:600]
            if not kod or not soru.strip():
                self._send_json(400, {"error": "kod ve soru zorunlu"})
                return
            try:
                sonuc = _ekip_sor(kod, soru)
            except Exception as exc:  # noqa: BLE001
                self._send_json(502, {"error": f"soru islenemedi: {str(exc)[:200]}"})
                return
            self._send_json(200, sonuc)
            return
        if path == "/api/saha/konum":
            body = _read_json_body(self)
            try:
                self._send_json(200, saha.konum_yaz(
                    session.username, body.get("enlem"), body.get("boylam"),
                    dogruluk_m=body.get("dogruluk_m"),
                    hiz_m_s=body.get("hiz_m_s"),
                    kaynak=body.get("kaynak", "TARAYICI"),
                    rota_id=body.get("rota_id")))
            except saha.SahaHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/saha/rota":
            body = _read_json_body(self)
            try:
                self._send_json(200, saha.rota(
                    body.get("enlem"), body.get("boylam"),
                    en_fazla_durak=body.get("en_fazla_durak", 20),
                    tur=body.get("tur"), brans=body.get("brans"),
                    ziyaret_durumu=body.get("ziyaret"),
                    yaricap_m=body.get("yaricap_m", 2000)))
            except saha.SahaHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/saha/ziyaret":
            body = _read_json_body(self)
            try:
                self._send_json(200, saha.ziyaret_kaydet(
                    body.get("hedef_anahtari", ""), body.get("sonuc", ""),
                    giden=session.username,
                    not_metni=body.get("not", ""),
                    enlem=body.get("enlem"), boylam=body.get("boylam"),
                    konum_dogruluk_m=body.get("konum_dogruluk_m"),
                    siparis_ref=body.get("siparis_ref", ""),
                    foto_b64=body.get("foto", "")))
            except saha.SahaHatasi as hata:
                # Gecersiz istek "tamam" gorunmez: sebebi AYNEN gosterilir.
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/katalog/not":
            # Sunum notu ve ilgi isareti. ILGI SATIS DEGILDIR -- ayri
            # tutulmazsa boru hatti oldugundan dolu gorunur.
            body = _read_json_body(self)
            try:
                self._send_json(200, katalog.not_yaz(
                    body.get("urun_slug", ""), giren=session.username,
                    ilgi=body.get("ilgi"), not_metni=body.get("not", ""),
                    hedef_anahtari=body.get("hedef_anahtari", ""),
                    ziyaret_id=body.get("ziyaret_id")))
            except katalog.KatalogHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/ig-plan/karar":
            # Sahip karari. Onay kapisi SEMADA: bulgulu ya da tartisilmamis
            # paket kisitla reddedilir ve sebebi aynen doner.
            body = _read_json_body(self)
            try:
                self._send_json(200, katalog.ig_karar(
                    body.get("plan_id"), body.get("durum", ""),
                    karar_veren=session.username))
            except katalog.KatalogHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/katalog/bayi":
            # Bayi (toptan) fiyati SAHIP KARARIDIR. Katalog onu oldugu gibi
            # gosterir; girilmeyen fiyat "—" kalir, uydurulmaz.
            body = _read_json_body(self)
            try:
                self._send_json(200, katalog.bayi_fiyat_yaz(
                    body.get("urun_slug", ""), body.get("bayi_fiyat"),
                    giren=session.username,
                    en_az_adet=body.get("en_az_adet")))
            except katalog.KatalogHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/saha/bilgi":
            # Sahada ogrenilen bilgi. Aylik tarama bunu SILMEZ.
            body = _read_json_body(self)
            try:
                self._send_json(200, saha.bilgi_kaydet(
                    body.get("hedef_anahtari", ""), giren=session.username,
                    ad=body.get("ad", ""), brans=body.get("brans", ""),
                    telefon=body.get("telefon", ""),
                    eposta=body.get("eposta", ""),
                    ilgili_kisi=body.get("ilgili_kisi", ""),
                    notlar=body.get("notlar", ""),
                    hedef_disi=body.get("hedef_disi")))
            except saha.SahaHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/saha/nokta":
            body = _read_json_body(self)
            try:
                self._send_json(200, saha.nokta_ekle(
                    body.get("ad", ""), body.get("tur", ""),
                    body.get("enlem"), body.get("boylam"),
                    ekleyen=session.username,
                    brans=body.get("brans", ""), telefon=body.get("telefon", ""),
                    eposta=body.get("eposta", ""), adres=body.get("adres", ""),
                    notlar=body.get("notlar", ""),
                    konum_kaynagi=body.get("konum_kaynagi", "ELLE"),
                    konum_dogruluk_m=body.get("konum_dogruluk_m")))
            except saha.SahaHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            return
        if path == "/api/isler":
            body = _read_json_body(self)
            try:
                kayit = isler.is_ekle(
                    None, body.get("istem", ""), body.get("negatif", ""),
                    body.get("adet", 1), isteyen=session.username)
            except isler.IsHatasi as exc:
                # Gecersiz istek "tamam" gorunmez: panelde basarili sanilip
                # kuyruga hic girmeyen is, bu projede yasanmis bir hata.
                self._send_json(400, {"error": str(exc)})
                return
            self._send_json(200, {"eklendi": kayit})
            return
        if path == "/api/uyandir":
            body = _read_json_body(self)
            try:
                sonuc = sistem.uyandirma_iste(
                    STATE_DIR, str(body.get("hedef", "")), session.username)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            self._send_json(200, sonuc)
            return
        if path == "/api/hafiza":
            # Not EKLEME. Hicbir sey cikarim yapmaz: buraya yalnizca
            # operatorun kendi yazdigi cumle girer. Hafizanin neyi
            # saklayacagina kendi karar vermesi, duzeltilemeyen bir
            # hafizadir -- jarvis.conversation_memory.remember()'in
            # varlik sebebi de bu.
            body = _read_json_body(self)
            note = str(body.get("note", ""))[:400]
            if not note.strip():
                self._send_json(400, {"error": "bos not kaydedilmez"})
                return
            eklendi = _cmem.remember(note, source="panel")
            if not eklendi:
                self._send_json(503, {"error": "not yazilamadi"})
                return
            payload = _hafiza_gorunumu()
            payload["eklendi"] = True
            self._send_json(200, payload)
            return
        if path == "/api/sistem/anahtar":
            # Kaynak politikasi anahtarini cevirir. Bu bir KARAR
            # kaydidir: kimin cevirdigi ve ne zaman cevirdigi
            # dosyaya yazilir, cunku "PC-2'nin CPU'su nicin acik"
            # sorusunun cevabi sonradan aranacak.
            body = _read_json_body(self)
            anahtar = str(body.get("anahtar", ""))[:64]
            acik = body.get("acik")
            if not isinstance(acik, bool):
                self._send_json(400, {"error": "acik alani true/false olmali"})
                return
            try:
                yeni = sistem.politika_yaz(STATE_DIR, anahtar, acik,
                                           session.username)
            except ValueError as hata:
                self._send_json(400, {"error": str(hata)})
                return
            self._send_json(200, {"politika": yeni})
            return
        if path == "/api/hafiza/sil":
            # SILME parcaya gore calisir (conversation_memory.forget).
            # Kac notun gittigini DONDURUYORUZ: metin baska bir notun
            # icinde de geciyorsa iki not birden gider ve operator bunu
            # sonradan degil, o anda gormeli.
            body = _read_json_body(self)
            fragment = str(body.get("fragment", ""))[:400]
            if not fragment.strip():
                self._send_json(400, {"error": "bos parca ile silinmez"})
                return
            silinen = _cmem.forget(fragment)
            payload = _hafiza_gorunumu()
            payload["silinen"] = silinen
            self._send_json(200, payload)
            return
        if path == "/api/asistan":
            # 🔴 Hatırlatıcı SAHİBİN notudur; oturum zorunlu.
            if self._current_session() is None:
                self._send_json(401, {"error": "oturum gerekli"})
                return
            from jarvis import asistan
            govde = _read_json_body(self)
            islem = str(govde.get("islem", ""))
            try:
                if islem == "ekle":
                    sonuc = asistan.ekle(
                        baslik=str(govde.get("baslik", ""))[:200],
                        zaman=str(govde.get("zaman", "")),
                        not_=(str(govde.get("not_", ""))[:500] or None),
                        tekrar=(str(govde.get("tekrar", "")) or None),
                        onem=str(govde.get("onem", "NORMAL")))
                elif islem == "tamamla":
                    sonuc = asistan.tamamla(int(govde.get("id", 0)))
                else:
                    self._send_json(400, {"error": "islem: ekle | tamamla"})
                    return
                self._send_json(200, sonuc)
            except asistan.AsistanHatasi as hata:
                self._send_json(400, {"error": str(hata)})
            except Exception as exc:  # noqa: BLE001
                self._send_json(503, {"error": str(exc)[:200]})
            return

        if path == "/api/chat":
            body = _read_json_body(self)
            message = str(body.get("message", ""))[:2000]
            try:
                result = chat.route(message, _shadow_runner, _operator)
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
                return
            self._send_json(200, result)
            return
        if path == "/api/chat/stream":
            self._handle_chat_stream()
            return
        if path == "/api/plan":
            # REQUEST -> PLAN -> DISPLAY. This endpoint plans and returns;
            # it never executes a step. jarvis.execution_planner touches no
            # database, spawns no subprocess and calls no model, so the only
            # I/O here is the read-only registry probe above.
            body = _read_json_body(self)
            message = str(body.get("message", ""))[:2000]
            try:
                plan = plan_request(message, registry=_live_registry())
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
                return
            self._send_json(200, plan.to_dict())
            return
        if path == "/api/run":
            # REQUEST -> PLAN -> ÇALIŞTIR -> KANIT/BULGU/ÖNERİ.
            #
            # NEDEN VAR: jarvis/execution_runtime.py 20.09.2026'da yazıldı ve
            # HTTP'de HİÇ YOKTU. Panelin yürütme yüzeyi (akış rayı, domain
            # kartları, kanıt tablosu, YÖNETİM ANALİZİ) hazırdı ama besleyen
            # uç nokta olmadığı için kalıcı olarak "plan yok" yazıyordu:
            # yetenek vardı, yüzü yoktu.
            #
            # 🔴 SINIR DEĞİŞMEDİ, ONU BURADA YAZIYORUM:
            # Runtime yalnız OKUMA analizi yapar. Eylem üreten adım asla
            # çalıştırılmaz -- değişmemiş jarvis.firewall'dan geçirilip
            # `PROPOSED` zarfı olarak KAYDEDİLİR; o zarfı gerçek eyleme
            # çeviren tek yol hâlâ mevcut insan onayı hattıdır (operatör
            # kuyruğu + /api/proposals/<id>/decide). Bu uç nokta
            # core.ai_action_proposal'a yazmaz, model çağırmaz (model_calls
            # yapı gereği 0), kodlama görevi üretemez, dış araştırma
            # yapmaz. Hepsi tests/test_execution_runtime.py'de kilitli.
            #
            # `originator` UYDURULMAZ: runtime adlandırılmış bir insan
            # olmadan çalışmayı reddediyor ("a plan cannot start itself").
            # Buraya giriş yapmış operatörün kullanıcı adı veriliyor, yani
            # her çalıştırma bunu isteyen insana kadar izlenebilir.
            body = _read_json_body(self)
            message = str(body.get("message", ""))[:2000]
            try:
                plan = plan_request(message, registry=_live_registry())
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
                return
            if not plan.steps:
                # Planlanamayan istek çalıştırılamaz. Boş bir "run" uydurmak
                # yerine planın kendi gerekçesi (REJECTED_AMBIGUOUS vb.)
                # olduğu gibi dönüyor; arayüz onu zaten gösteriyor.
                self._send_json(200, plan.to_dict())
                return
            try:
                contract = ContractCache(_memory).get()
            except (ContractError, JarvisMemoryError):
                contract = None
            try:
                record = ExecutionRuntime(_memory, contract=contract).execute(
                    plan, originator=session.username)
            except ExecutionDenied as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
                return
            payload = plan.to_dict()
            payload["run"] = record.to_dict()
            self._send_json(200, payload)
            return
        if path == "/api/satis/not":
            # Gönderi notu: bu gönderi neydi (satış, UGC, numune…) ve
            # fiyatsızsa değeri ne. İNSAN BEYANI -> human_approver.
            body = _read_json_body(self)
            self._send_json(200, _gonderi_notu_ekle(
                siparis_ref=str(body.get("siparis_ref", "")),
                tur=str(body.get("tur", "")),
                alici=str(body.get("alici", "")),
                urun_adi=str(body.get("urun_adi", "")),
                adet=body.get("adet"), elle_fiyat=body.get("elle_fiyat"),
                not_metni=str(body.get("not_metni", "")),
                giren=session.username))
            return

        if path == "/api/stok":
            # Elle stok sayımı. Platformun stok alanından AYRI bir şeydir:
            # bu, fiziksel sayımın beyanıdır.
            body = _read_json_body(self)
            self._send_json(200, _stok_sayim_ekle(
                urun_adi=str(body.get("urun_adi", "")),
                adet=body.get("adet"),
                nerede=str(body.get("nerede", "DEPO")),
                not_metni=str(body.get("not_metni", "")),
                giren=session.username))
            return

        if path in ("/api/kreatif-itiraz", "/api/kreatif-itiraz/muhatap"):
            from jarvis import kreatif_itiraz as kit
            body = _read_json_body(self)
            try:
                if path.endswith("/muhatap"):
                    # 🔴 ONIZLEME: sahip GONDERMEDEN once kime yazacagini
                    # ve o departmanin bu gorsele daha once ne dedigini
                    # gorur. Kime gittigi bilinmeyen bir itiraz, cevapsiz
                    # kalan itirazdir.
                    self._send_json(200, kit.muhatap_bul(
                        str(body.get("parti", "")),
                        str(body.get("dosya", "")) or None,
                        str(body.get("konu", ""))))
                    return
                self._send_json(200, kit.itiraz_ac(
                    parti=str(body.get("parti", "")),
                    dosya=str(body.get("dosya", "")) or None,
                    konu=str(body.get("konu", "")),
                    aciklama=str(body.get("aciklama", "")),
                    acan=session.username))
                return
            except kit.ItirazHatasi as hata:
                self._send_json(400, {"error": str(hata)})
                return
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self._send_json(502, {"error": f"itiraz işlenemedi: {str(exc)[:200]}"})
                return

        if path.startswith("/api/kargo/"):
            self._route_kargo_post(path, session)
            return

        if path == "/api/degisiklik":
            # Panelden gelen degisiklik onerisi -> diske sartname -> gorev ->
            # dongu oneriyi yazar -> sahip onaylar.
            #
            # 🔴 BU UC VERITABANINA DOGRUDAN YAZMAZ ve WIX'E DOKUNMAZ.
            # Yaptigi tek sey onay kuyruguna DUSECEK bir sartname hazirlamak.
            # Panelde "kaydedildi" yazan bir dugme olsaydi yalan olurdu:
            # sozlesmede bu eylem tiplerinin execution_enabled degeri false.
            body = _read_json_body(self)
            tur = str(body.get("tur") or "")
            gerekce = str(body.get("gerekce") or "")[:1000]
            isteyen = session.username
            try:
                if tur == "tek_alan":
                    hazir = degisiklik.tek_alan_onerisi(
                        str(body.get("urun_id") or "")[:120],
                        str(body.get("urun_adi") or "")[:200],
                        str(body.get("alan") or "")[:60],
                        body.get("eski"), body.get("yeni"), gerekce, isteyen, _memory)
                elif tur == "toplu_fiyat":
                    hazir = degisiklik.toplu_fiyat_onerisi(
                        body.get("satirlar") or [], gerekce, isteyen, _memory)
                else:
                    self._send_json(400, {"error": "bilinmeyen öneri türü"})
                    return
            except degisiklik.DegisiklikHatasi as exc:
                self._send_json(400, {"error": str(exc)})
                return
            try:
                gorev = _operator.create_task(hazir["intent"], hazir["slug"])
            except (ValueError, JarvisMemoryError) as exc:
                self._send_json(502, {"error": f"görev açılamadı: {exc}"})
                return
            self._send_json(200, {
                "ok": True, "slug": hazir["slug"], "intent": hazir["intent"],
                "task_id": gorev.get("task_id"),
                "ozet": hazir["reason"],
                "not": ("Öneri onay kuyruğuna hazırlandı. Jarvis döngüsü "
                        "görevi alınca ÖNERİLER'de görünecek. Onay, "
                        "değişikliğin yapılmasına karar verildiğini kaydeder; "
                        "Wix/Trendyol tarafında değişikliği insan uygular.")})
            return

        if path.startswith("/api/proposals/") and path.endswith("/decide"):
            action_id = path.split("/")[-2]
            body = _read_json_body(self)
            decision = str(body.get("decision", ""))
            reason = str(body.get("reason", ""))[:2000]
            try:
                konu = self._kreatif_konusu(int(action_id))
                result = _operator.decide(int(action_id), decision, reason)
                baslatilan = self._kreatif_uretimi_baslat(konu, result)
                if baslatilan:
                    result = {**result, "kreatif_uretimi": baslatilan}
                self._send_json(200, result)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except JarvisMemoryError as exc:
                self._send_json(502, {"error": str(exc)})
            return

        self._send_json(404, {"error": "not found"})

    def _handle_chat_stream(self) -> None:
        """Streams {"type":"stage"|"done", ...} frames as newline-delimited
        JSON (one object per line) over a single-use, Connection: close
        response. Chosen over EventSource because EventSource cannot send a
        POST body; a fetch() + ReadableStream reader on the frontend
        consumes this the same way it would consume real SSE, and the frame
        shape is what a future token-streaming model router extends (see
        chat.stream's docstring) -- so switching later needs no protocol
        change, only more frame types.
        """
        body = _read_json_body(self)
        message = str(body.get("message", ""))[:2000]
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for event in chat.stream(message, _shadow_runner, _operator):
                line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
        except (JarvisMemoryError, BrokenPipeError, ConnectionResetError) as exc:
            try:
                line = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"
                self.wfile.write(line.encode("utf-8"))
            except OSError:
                pass
        self.close_connection = True

    def _handle_login(self) -> None:
        source = _client_ip(self)
        allowed, retry_after = throttle.check(source)
        if not allowed:
            self._send_json(429, {"error": "too many attempts", "retry_after_s": retry_after})
            return
        body = _read_json_body(self)
        username = str(body.get("username", ""))
        password = str(body.get("password", ""))
        account = auth.load_account()
        ok = False
        if account and username == account["username"]:
            ok = auth.verify_password(password, account["password_hash"], account["salt"])
        if not ok:
            throttle.record_failure(source)
            self._send_json(401, {"error": "invalid credentials"})
            return
        throttle.record_success(source)
        session = sessions.create(username)
        self._send_json(200, {"ok": True, "username": username, "csrf_token": session.csrf_token},
                        self._set_session_cookies(session))

    # -- status -----------------------------------------------------------
    def _build_status(self) -> dict:
        started = time.time()
        health = None
        health_error = None
        try:
            evidence = _memory.get_system_status()
            health = evidence.records[0] if evidence.records else {}
        except Exception as exc:  # noqa: BLE001
            health_error = str(exc)

        contract_valid = None
        try:
            contract_valid = ContractCache(_memory).get().valid
        except Exception:  # noqa: BLE001
            contract_valid = None

        pending_count = None
        try:
            pending_count = len(_operator.list_pending())
        except Exception:  # noqa: BLE001
            pending_count = None

        audit = _tail_jsonl(STATE_DIR / "audit.jsonl", 1)
        last_cycle = audit[0] if audit else None
        recent_proposed = bool(last_cycle and last_cycle.get("result") == "PROPOSED"
                               and time.time() - started < 60)

        if health_error:
            visual_state = "OFFLINE"
        elif pending_count:
            visual_state = "WAITING_APPROVAL"
        elif recent_proposed:
            visual_state = "PROPOSING"
        else:
            visual_state = "IDLE"

        return {
            "visual_state": visual_state,
            "company_memory": {"healthy": health_error is None, "error": health_error, "health": health},
            "action_firewall": {"contract_valid": contract_valid},
            "pending_proposals": pending_count,
            "last_cycle": last_cycle,
            # Olculmus host kullanimi. Panelin CPU/RAM/DISK alanlari yalnizca
            # bunu basar; okunamayan alan None gelir ve N/A kalir.
            "host": _host_metrics(),
            "external_actions_enabled": os.environ.get("EXTERNAL_ACTIONS_ANNOUNCED", "false") == "true",
            "server_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }


def main() -> None:
    account = auth.ensure_operator_account()
    if account:
        username, password = account
        sys.stderr.write(
            f"\n[jarvis-web] Operator account created.\n  username: {username}\n  password: {password}\n"
            "  (shown once -- store it now; only the hash is kept)\n\n"
        )
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    sys.stderr.write(f"[jarvis-web] listening on {BIND_HOST}:{BIND_PORT}\n")
    server.serve_forever()


# ==========================================================================
# Panel bolumleri
# ==========================================================================
# Dort bolum de OLCULEN durumu gosterir. Okunamayan bir kaynak "yok" diye
# gizlenmez, hatasiyla birlikte gosterilir: panelin iki yonde de yalan
# soylememesi CR-001'in bulgusuydu.

def _panel_error(exc: Exception) -> dict:
    return {"status": "ERROR", "error": str(exc)[:300]}


# ---------------------------------------------------------------------
# HAFIZA
#
# Kisisel asistan katmani (jarvis.conversation_memory + jarvis.hatira)
# 20.09.2026'da kuruldu ve calisiyordu, ama panelde HICBIR yuzu yoktu:
# ne bir ekran, ne bir uc nokta. Gorunmeyen bir hafiza denetlenemez --
# operator neyin hatirlandigini goremiyorsa, yanlis hatirlanan bir seyi
# de duzeltemez. Bu uclar o boslugu kapatir.
#
# Iki kaynak bilerek AYRI raporlanir:
#   dosya  -- notun aslI (state/conversation/<thread>.notes.jsonl)
#   dizin  -- mem0/pgvector, yalnizca ARAMA katmani
# Ayni sayiyi tek etiketle gostermek, dizin coktugunde paneli yalanci
# yapardI. Ikisi ayrildigi icin panel "dizin geride kalmis" diyebiliyor.
# ---------------------------------------------------------------------

HAFIZA_UYARI = ("Notun aslı dosyada tutulur; dizin yalnızca aramayı "
                "hızlandırır. Dizin çökerse not kaybolmaz, arama körelir.")


def _hafiza_dizin_durumu() -> dict:
    """Arama dizininin OLCULEN durumu. Ithal bile tembel: mem0 agir bir
    bagimlilik ve panel acilmadan yuklenmesi icin sebep yok."""
    try:
        from jarvis import hatira
        return hatira.durum()
    except Exception as exc:  # noqa: BLE001
        # Dizin yoksa hafiza calismaya devam eder; bu bir arIza degil,
        # bildirilecek bir durum. Panel farki gorsun diye "kurulu: false".
        return {"kurulu": False, "telemetri_kapali": None,
                "hata": f"{type(exc).__name__}: {str(exc)[:200]}",
                "not_sayisi": None}


def _hafiza_gorunumu() -> dict:
    notlar = _cmem.note_rows()
    dizin = _hafiza_dizin_durumu()
    dosya = _cmem.status()
    tutarli = (dizin.get("not_sayisi") == len(notlar)) if dizin.get("kurulu") else None
    return {
        "notlar": notlar,
        "dosya": dosya,
        "dizin": dizin,
        "tutarli": tutarli,
        "sinir": _cmem.MAX_NOTES,
        "uyari": HAFIZA_UYARI,
    }


def _yeni_fiyat(mevcut: float, yontem: str, deger: float) -> float:
    """Toplu islemin urettigi yeni fiyat. Yuvarlama KURUSTA, asagi degil:
    899.99 gibi bir sayiyi 899.99 birakmak panelde okunmaz hale getirirdi."""
    if yontem == "YUZDE":
        return round(mevcut * (1 + deger / 100.0), 2)
    if yontem == "SABIT_EKLE":
        return round(mevcut + deger, 2)
    if yontem == "SABIT_FIYAT":
        return round(deger, 2)
    raise ValueError(f"bilinmeyen yontem: {yontem}")


def _marj_hesapla(fiyat: float, komisyon: float | None, kdv: float,
                  maliyet: float | None) -> dict:
    """Gorunumdeki formulun AYNISI. Iki yerde iki farkli hesap olmamali.

    Eksik girdi uydurulmaz: komisyon veya maliyet yoksa marj None doner ve
    uyari neyin eksik oldugunu soyler.
    """
    if komisyon is None:
        return {"marj": None, "marj_yuzde": None, "uyari": "KOMISYON_YOK"}
    if maliyet is None:
        return {"marj": None, "marj_yuzde": None, "uyari": "MALIYET_YOK"}
    net = (fiyat * (1 - komisyon / 100.0)) / (1 + kdv / 100.0)
    marj = net - maliyet
    yuzde = (100.0 * marj / net) if net else None
    if marj < 0:
        uyari = "ZARAR"
    elif yuzde is not None and yuzde < 10:
        uyari = "KRITIK"
    elif yuzde is not None and yuzde < 25:
        uyari = "DUSUK"
    else:
        uyari = "OK"
    return {"marj": round(marj, 2),
            "marj_yuzde": round(yuzde, 1) if yuzde is not None else None,
            "uyari": uyari}


def _toplu_onizleme(body: dict) -> dict:
    """Toplu fiyat islemini HESAPLAR, uygulamaz.

    Amac tek: onaya gitmeden once "bu islem kac urunu zarara sokuyor"
    sorusunu cevaplamak.
    """
    platform = str(body.get("platform") or "").strip()
    yontem = str(body.get("yontem") or "").strip().upper()
    if not platform:
        raise ValueError("platform zorunlu")
    try:
        deger = float(body.get("deger"))
    except (TypeError, ValueError):
        raise ValueError("deger sayi olmali") from None
    secili = body.get("urun_idler") or []

    rows = [r for r in _memory._fetch("platform_fiyat_matrisi").records
            if r.get("platform_kod") == platform]
    if secili:
        secili = set(secili)
        rows = [r for r in rows if r.get("urun_id") in secili]
    if not rows:
        raise ValueError("eslesen urun yok")

    satirlar, sayac = [], {"ZARAR": 0, "KRITIK": 0, "DUSUK": 0, "OK": 0,
                           "KOMISYON_YOK": 0, "MALIYET_YOK": 0, "FIYAT_YOK": 0}
    for r in rows:
        mevcut = r.get("gecerli_fiyat")
        if mevcut is None:
            sayac["FIYAT_YOK"] += 1
            satirlar.append({"urun_id": r.get("urun_id"),
                             "urun_adi": r.get("urun_adi"),
                             "eski_fiyat": None, "yeni_fiyat": None,
                             "uyari": "FIYAT_YOK"})
            continue
        yeni = _yeni_fiyat(float(mevcut), yontem, deger)
        if yeni <= 0:
            raise ValueError("islem sifir veya negatif fiyat uretiyor")
        komisyon = r.get("komisyon_yuzde")
        maliyet = r.get("birim_maliyet")
        marj = _marj_hesapla(
            yeni,
            float(komisyon) if komisyon is not None else None,
            float(r.get("kdv_yuzde") or 20),
            float(maliyet) if maliyet is not None else None)
        sayac[marj["uyari"]] = sayac.get(marj["uyari"], 0) + 1
        satirlar.append({
            "urun_id": r.get("urun_id"), "urun_adi": r.get("urun_adi"),
            "eski_fiyat": float(mevcut), "yeni_fiyat": yeni,
            "marj": marj["marj"], "marj_yuzde": marj["marj_yuzde"],
            "uyari": marj["uyari"],
        })

    return {
        "platform": platform, "yontem": yontem, "deger": deger,
        "urun_sayisi": len(satirlar), "ozet": sayac, "satirlar": satirlar,
        "uygulandi": False,
        "not": ("Bu bir ONIZLEMEDIR; hicbir fiyat degistirilmedi. "
                "Uygulanmasi icin onay kuyruguna gonderilmelidir."),
    }

def _panel_veri() -> dict:
    """Company Memory'nin gercek durumu: hangi sorgu calisiyor, kac satir."""
    # Modul zaten bir CompanyMemory ornegi tutuyor; ikincisini kurmak
    # transport ayarini ikiye bolerdi.
    memory = _memory
    domains = []
    for domain, names in getattr(type(memory), "DOMAIN_QUERIES", {}).items():
        queries = []
        for name in names:
            try:
                evidence = memory._fetch(name)
                queries.append({"name": name, "status": "OK",
                                "rows": len(evidence.records),
                                "latency_ms": evidence.latency_ms,
                                "source": evidence.source})
            except Exception as exc:  # noqa: BLE001
                queries.append({"name": name, "status": "FAIL",
                                "error": str(exc)[:160]})
        domains.append({"domain": domain, "queries": queries,
                        "ok": sum(1 for q in queries if q["status"] == "OK"),
                        "total": len(queries)})

    provenance, quality = [], []
    try:
        for row in memory.get_provenance().records:
            provenance.append({"alan": row.get("entity_id"),
                               "authority": row.get("authority"),
                               "freshness": row.get("freshness"),
                               "connection": row.get("current_connection"),
                               "observed_at": row.get("observed_at")})
    except Exception as exc:  # noqa: BLE001
        provenance = [_panel_error(exc)]
    try:
        for row in memory.get_data_quality().records:
            quality.append({"check": row.get("entity_id"),
                            "passed": row.get("passed"),
                            "detail": str(row.get("detail") or "")[:200]})
    except Exception as exc:  # noqa: BLE001
        quality = [_panel_error(exc)]

    return {"domains": domains, "provenance": provenance, "quality": quality}


def _role_reality() -> dict:
    """Rollerin gerçekte ne olduğu ve son koşuda ne ürettikleri.

    Panelin 28 satiri, 28 farkli yetenek DEGILDIR. Bunu yazmamak, sistemi
    oldugundan buyuk gostermek olur.
    """
    out: dict = {
        "note": ("8 ajans rolü kod tarafında yalnız etikettir; aralarında "
                 "davranış farkı yoktur. 20 uzmanın hepsi tek sınıftır "
                 "(DeterministicSpecialist) ve yalnız hangi veriyi "
                 "istedikleriyle ayrışır. Aşağıdaki tablo son ajans "
                 "koşusunda her rolün gerçekten ne ürettiğini gösterir."),
        "last_run": None, "contributions": [],
    }
    try:
        from jarvis import agency_store
        son = agency_store.recent(1)
        if not son:
            return out
        kayit = agency_store.get(son[0]["id"]) or {}
        teslimat = kayit.get("deliverable") or {}
        out["last_run"] = {"task": teslimat.get("task"),
                           "product": teslimat.get("product"),
                           "objective": teslimat.get("objective")}
        out["contributions"] = teslimat.get("role_contributions") or []
    except Exception as exc:  # noqa: BLE001 - panel hicbir zaman cokmez
        out["error"] = str(exc)[:200]
    return out


def _team_opinions() -> list:
    """Ekip üyeleri ve bu veriye bakınca söyledikleri. Sıfır model çağrısı."""
    try:
        from jarvis.roster import opinions
        return opinions(_memory)
    except Exception as exc:  # noqa: BLE001 - panel hicbir zaman cokmez
        return [_panel_error(exc)]


def _team_by_department() -> list:
    """Ekip, DEPARTMAN altinda ve SORUMLUSUYLA birlikte.

    🔴 Sahip 22.09.2026: "hepsinin kendi mudurleri var, ben onlarla
    konusurum. Hesap sorarim veya bilgi isterim."
    Duz bir 73 kisilik liste bunu karsilamiyordu: kimin kime bagli oldugu
    ve kime soru sorulacagi gorunmuyordu.

    🔴 Ayrica "VERI YOK" ile "ISLEV YAZILMADI" ayrildi (roster.py). Panel
    bu ikisini ayni gosterirse kullanici veri arar, oysa yazilmasi gereken
    sey kod olabilir. Sayaclar bu yuzden durum bazinda doner.
    """
    try:
        from jarvis import roster
    except Exception as exc:  # noqa: BLE001 - panel hicbir zaman cokmez
        return [_panel_error(exc)]

    gorusler = {g.get("key"): g for g in _team_opinions() if isinstance(g, dict)}
    birim_adlari, misyonlar = {}, {}
    try:
        for d in _memory._fetch("departments").records:
            kod = str(d.get("kod") or "")
            if kod:
                birim_adlari[kod] = str(d.get("ad") or kod)
                misyonlar[kod] = str(d.get("misyon") or "")
    except Exception:  # noqa: BLE001 - departman adi sustur, kadro yine dursun
        pass

    cikti = []
    for kod, uyeler in sorted(roster.departman_uyeleri().items()):
        sorumlu = None
        try:
            sorumlu = roster.departman_sorumlusu(kod)
        except Exception:  # noqa: BLE001
            sorumlu = None
        kadro, sayac = [], {}
        for m in uyeler:
            g = gorusler.get(m.key, {})
            durum = str(g.get("status") or "?")
            sayac[durum] = sayac.get(durum, 0) + 1
            kadro.append({
                "key": m.key, "name": m.name, "job": m.job,
                "status": durum,
                "statement": g.get("statement") or "",
                "reads": list(getattr(m, "reads", ()) or ()),
                "sorumlu_mu": bool(sorumlu and sorumlu.key == m.key),
            })
        kadro.sort(key=lambda k: (not k["sorumlu_mu"], k["name"]))
        cikti.append({
            "kod": kod,
            "ad": birim_adlari.get(kod, kod),
            "misyon": misyonlar.get(kod, ""),
            "sorumlu": ({"key": sorumlu.key, "name": sorumlu.name}
                        if sorumlu else None),
            "kisi": len(kadro),
            "konusan": sayac.get("KONUŞTU", 0),
            "durum_sayaci": sayac,
            "kadro": kadro,
            # Soru sorulabilir mi: _ekip_sor departman koduyla calisir.
            "soru_sorulabilir": True,
        })
    cikti.sort(key=lambda d: (-d["kisi"], d["kod"]))
    return cikti


def _panel_ajanlar() -> dict:
    """Roller, saglayicilar ve motor adaylari -- hangisi gercekten kullanilabilir."""
    roles, providers, engines = [], [], []
    reality = _role_reality()
    try:
        from jarvis import agency
        for role in agency.ROLES:
            roles.append({"id": role, "kind": "agency"})
    except Exception as exc:  # noqa: BLE001
        roles.append(_panel_error(exc))
    try:
        from jarvis.specialist_pool import SPECIALISTS
        for spec in SPECIALISTS:
            roles.append({"id": getattr(spec, "specialist_id", str(spec)),
                          "kind": "specialist",
                          "domain": getattr(spec, "domain", None)})
    except Exception:  # noqa: BLE001
        pass
    try:
        from webconsole.conversation import _router
        states = _router().provider_states()
        providers = [{"provider": k, "state": v} for k, v in states.items()] \
            if isinstance(states, dict) else [{"provider": str(states), "state": "?"}]
    except Exception as exc:  # noqa: BLE001
        providers = [_panel_error(exc)]
    try:
        from jarvis.adapter_factory import AdapterFactory
        for candidate in AdapterFactory.candidates():
            engines.append({"name": candidate.name, "version": candidate.version,
                            "state": candidate.state.value,
                            "evidence": candidate.evidence})
    except Exception as exc:  # noqa: BLE001
        engines = [_panel_error(exc)]
    return {"team": _team_opinions(), "departmanlar": _team_by_department(),
            "role_reality": reality, "roles": roles,
            "providers": providers, "engines": engines}


def _panel_raporlar() -> dict:
    """Bulgular ve dongu ozeti -- uretilmis gercek kayitlar."""
    findings = _tail_jsonl(STATE_DIR / "findings.jsonl", 60)
    audit = _tail_jsonl(STATE_DIR / "audit.jsonl", 60)

    by_code: dict = {}
    for row in findings:
        key = row.get("signal_code") or row.get("signature") or "infra"
        entry = by_code.setdefault(key, {"code": key, "count": 0,
                                         "severity": row.get("severity"),
                                         "last": None, "reason": row.get("reason")})
        entry["count"] += 1
        entry["last"] = row.get("observed_at") or entry["last"]

    cycles = [r for r in audit if r.get("cycle")]
    results: dict = {}
    for row in cycles:
        results[row.get("result", "?")] = results.get(row.get("result", "?"), 0) + 1
    last = cycles[-1] if cycles else {}

    # Gecmis kararlarin sonucundan cikan dersler. Okunamazsa uydurulmaz:
    # learning.run zaten status=UNAVAILABLE dondurur ve panel onu gosterir.
    try:
        from jarvis import learning
        lessons = learning.run(_memory)
    except Exception as exc:  # noqa: BLE001
        lessons = {"status": "ERROR", "error": str(exc)[:200]}

    return {
        "lessons": lessons,
        "findings": sorted(by_code.values(), key=lambda e: -e["count"]),
        "finding_total": len(findings),
        "cycle_results": [{"result": k, "count": v} for k, v in
                          sorted(results.items(), key=lambda kv: -kv[1])],
        "last_cycle": {"cycle": last.get("cycle"), "result": last.get("result"),
                       "business": last.get("business"),
                       "model_calls": last.get("model_calls"),
                       "external_actions": last.get("external_actions"),
                       "total_ms": last.get("total_ms")},
    }


def _panel_usage() -> dict:
    """Son 7 günün model kullanımı. Para tahmin edilmez, token sayılır."""
    try:
        from jarvis.usage import summary
        return summary(days=7)
    except Exception as exc:  # noqa: BLE001 - panel hicbir zaman cokmez
        return {"error": str(exc)[:200], "providers": [], "total_calls": 0,
                "paid_calls": 0}


PAZAR_SEVIYELERI = ("FACT", "INTERPRETATION", "HYPOTHESIS", "NOT_CONNECTED")


def _pazar_bulgu_ekle(kod: str, seviye: str, bulgu: str, kaynak: str,
                      tarih: str, yorum: str = "") -> dict:
    """Operatorun gozlemini core.pazar_bulgu'ya yazar.

    🔴 NEDEN BU KANAL VAR: rakip fiyat istihbarati OTOMATIK ALINAMIYOR.
    Olculdu (20.09.2026): Trendyol/Hepsiburada/N11/akakce/cimri hepsi 403
    donuyor ve satici API'si yalnizca kendi verimizi veriyor. Elle giris
    calisan TEK yol; bu yuzden surtunmesiz olmasi konfor degil, kapasite.

    🔴 human_approver OLARAK YAZILIR, ai_writer olarak DEGIL. Bu bir INSAN
    BEYANIDIR, onay akisiyla ayni sinif. Jarvis kendi uydurdugu bir "pazar
    bulgusunu" kendi kanitina ceviremesin diye yazma yetkisi yok.

    🔴 METIN SQL'E GOMULMEZ. Degerler argv'den DEGIL stdin'den, rastgele
    etiketli dolar-tirnak icinde JSON olarak gider. Sebep olculmus: bu
    projede kabuk tirnaklamasi defalarca bozdu (uzak bash '$$'i PID'e
    acti, uzun jeton terminalde bozuldu). Argv yolu hem kabuk hem psql
    tarafindan iki kez yorumlanir; stdin yolu hicbirinde yorumlanmaz.
    """
    import secrets

    kod = (kod or "").strip().upper()[:60]
    seviye = (seviye or "").strip().upper()
    bulgu = (bulgu or "").strip()[:2000]
    kaynak = (kaynak or "").strip()[:300]
    tarih = (tarih or "").strip()[:40]
    yorum = (yorum or "").strip()[:2000]

    if seviye not in PAZAR_SEVIYELERI:
        return {"hata": f"seviye şunlardan biri olmalı: {', '.join(PAZAR_SEVIYELERI)}"}
    if len(bulgu) < 8:
        return {"hata": "bulgu metni çok kısa"}
    # 🔴 Kaynaksiz bulgu IDDIADIR. Veritabaninda da CHECK var; burada da
    #    engellenir ki kullanici hatayi formda gorsun, 500 almasin.
    if len(kaynak) < 3:
        return {"hata": "kaynak zorunlu — nereden gördüğün yazılmadan kayıt olmaz"}
    if not kod:
        return {"hata": "departman kodu zorunlu"}

    # 🔴 'departman' o bulgunun SAHIBI birim, 'kod' ise KONU kodu. Ikisi ayri:
    #    tasinan eski kayitlarda kod 'ADJACENT_CATEGORY_REFERENCE' gibi tematik
    #    bir etiketti ve hicbir departmana denk gelmiyordu. Panelden girilen
    #    gozlemin konu kodu OPERATOR_GOZLEMI'dir -- makinenin bulmadigi,
    #    insanin gorup beyan ettigi kayit oldugu her zaman ayirt edilebilsin.
    yuk = json.dumps({"departman": kod, "kod": "OPERATOR_GOZLEMI",
                      "seviye": seviye, "bulgu": bulgu,
                      "kaynak": kaynak, "tarih": tarih or "-",
                      "yorum": yorum or None}, ensure_ascii=False)

    # Nonce: payload'da gecmedigi DOGRULANIR. Gecerse (astronomik olarak
    # imkansiz) yazmayi reddeder -- sessizce devam etmek yerine durur.
    etiket = "pb" + secrets.token_hex(8)
    if f"${etiket}$" in yuk:
        return {"hata": "kodlama çakışması, kayıt yapılmadı"}

    sql = (
        "\\set ON_ERROR_STOP on\n"
        "BEGIN;\n"
        "SET SESSION AUTHORIZATION human_approver;\n"
        "INSERT INTO core.pazar_bulgu (departman,kod,seviye,bulgu,kaynak,tarih,yorum)\n"
        "SELECT j->>'departman', j->>'kod', j->>'seviye', j->>'bulgu', j->>'kaynak',\n"
        "       j->>'tarih', j->>'yorum'\n"
        f"  FROM (SELECT ${etiket}${yuk}${etiket}$::jsonb AS j) t;\n"
        "COMMIT;\n"
    )
    try:
        sonuc = subprocess.run(
            ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-q",
             "-U", "n8n", "-d", "n8n", "-f", "-"],
            input=sql, capture_output=True, text=True, timeout=20, check=False)
    except Exception as exc:  # noqa: BLE001
        return {"hata": f"kayıt yapılamadı: {str(exc)[:160]}"}
    if sonuc.returncode:
        return {"hata": f"kayıt reddedildi: {(sonuc.stderr or '').strip()[:220]}"}
    return {"ok": True, "kod": kod, "seviye": seviye}


_ARASTIRMA_LOG = STATE_DIR / "departman_arastirma.jsonl"


def _arastirma_bulgulari(tavan: int = 3000) -> dict:
    """Departman -> o birimin dis arastirma bulgulari.

    🔴 BU FONKSIYONUN VARLIK SEBEBI: bulgular uretiliyordu ama HICBIR YERDE
    GORUNMUYORDU -- bu projede defalarca yasanan "uretilen ama okunmayan
    rapor" hatasinin aynisi. Panoya baglanmayan arastirma, yapilmamis
    arastirmadan farksizdir; ustelik yapildigi sanildigi icin daha kotudur.

    Dosya buyudukce sadece SON tavan satiri okunur; pano yavaslamaz.
    """
    out: dict[str, dict] = {}
    try:
        with _ARASTIRMA_LOG.open("r", encoding="utf-8") as f:
            satirlar = f.readlines()[-tavan:]
    except OSError:
        return {"_yok": True, "_sebep": "arastirma kaydi henuz yok"}
    for ham in satirlar:
        ham = ham.strip()
        if not ham:
            continue
        try:
            r = json.loads(ham)
        except ValueError:
            continue
        dep = str(r.get("departman") or "")
        if not dep:
            continue
        kova = out.setdefault(dep, {"toplam": 0, "son_zaman": "", "bulgular": [],
                                    "enjeksiyon": 0})
        kova["toplam"] += 1
        z = str(r.get("zaman") or "")
        if z > kova["son_zaman"]:
            kova["son_zaman"] = z
        if r.get("enjeksiyon"):
            kova["enjeksiyon"] += 1
        kova["bulgular"].append({
            "baslik": r.get("baslik") or "(başlıksız)",
            "yayinci": r.get("yayinci"),
            "url": r.get("url"),
            "konu": r.get("konu"),
            "zaman": z,
            "ozet": (r.get("ozet") or "")[:240],
        })
    # Her departman icin en yeniler ustte, en fazla 5 tanesi panoya.
    for kova in out.values():
        kova["bulgular"].sort(key=lambda b: b.get("zaman") or "", reverse=True)
        kova["bulgular"] = kova["bulgular"][:5]
    return out


def _panel_ekip() -> dict:
    """EKIP PANOSU: departman departman kim var, kim calisiyor, kim calismiyor.

    🔴 IKI AYRI 'CALISIYOR' VAR, KARISTIRMA:
      departman.durum  -- birimin veri kaynagi var mi (core.departman alani)
      uye.status       -- o uye SU AN veriden konusabildi mi (canli olcum)
    Bir departman 'CALISIYOR' isaretli olup uyesi o an okuyamiyor olabilir
    (sorgu dustu). Pano ikisini de gosterir; birini digerinin yerine koymak
    yesil bir panoda olu bir birimi gizlerdi.

    Renk KURALI -- tahmin degil, sayim:
      yesil  departmanin EN AZ BIR uyesi veriden konustu
      sari   uyesi var ama hicbiri konusamadi (arastirma/girdi bekliyor)
      kirmizi uyesi var ve okumasi gereken veri ACIK DEGIL
      gri    hic uyesi yok -- birim tanimli ama kadrosu kurulmamis
    """
    try:
        from jarvis import roster
    except Exception as exc:  # noqa: BLE001
        return {"error": f"roster okunamadi: {exc}", "departmanlar": []}

    # 1) Departman tablosu (tek dogru kaynak).
    departmanlar: list[dict] = []
    try:
        departmanlar = list(_memory._fetch("departments").records)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"departman tablosu okunamadi: {exc}", "departmanlar": []}

    # 2) Canli uye durumu. Tek cagri, sorgular icerde onbellege aliniyor.
    try:
        gorusler = roster.opinions(_memory)
    except Exception as exc:  # noqa: BLE001
        gorusler = []
        uye_hatasi = str(exc)
    else:
        uye_hatasi = ""
    gorus_by_key = {g["key"]: g for g in gorusler}
    uyeler_by_dept = roster.departman_uyeleri()
    arastirma = _arastirma_bulgulari()
    arastirma_var = not arastirma.get("_yok")
    # Operatorun ELLE girdigi pazar gozlemleri. Bunlar dis arastirmadan da
    # ayridir: birini makine buldu, digerini insan gordu ve beyan etti.
    try:
        pazar = list(_memory._fetch("market_research").records)
    except Exception:  # noqa: BLE001
        pazar = []

    KONUSTU = "KONUŞTU"
    VERI_YOK = "VERİ YOK"

    satirlar: list[dict] = []
    for d in departmanlar:
        kod = str(d.get("kod") or "")
        uyeler = []
        for m in uyeler_by_dept.get(kod, ()):
            g = gorus_by_key.get(m.key, {})
            uyeler.append({
                "key": m.key,
                "ad": m.name,
                "gorev": m.job,
                "mod": m.mode,
                "okur": list(m.reads),
                "durum": g.get("status", "BİLİNMİYOR"),
                "soyledigi": g.get("statement", ""),
                "eksik": g.get("missing", []),
            })
        konusan = sum(1 for u in uyeler if u["durum"] == KONUSTU)
        veri_yok = sum(1 for u in uyeler if u["durum"] == VERI_YOK)
        if not uyeler:
            renk = "gri"
        elif konusan:
            renk = "yesil"
        elif veri_yok:
            renk = "kirmizi"
        else:
            renk = "sari"
        ar = arastirma.get(kod) or {}
        satirlar.append({
            "pazar_bulgulari": [b for b in pazar if str(b.get("departman")) == kod][:5],
            "pazar_toplam": sum(1 for b in pazar if str(b.get("departman")) == kod),
            "arastirma_toplam": ar.get("toplam", 0),
            "arastirma_son": ar.get("son_zaman", ""),
            "arastirma": ar.get("bulgular", []),
            "arastirma_enjeksiyon": ar.get("enjeksiyon", 0),
            "kod": kod,
            "ad": d.get("ad"),
            "aile": d.get("aile"),
            "misyon": d.get("misyon"),
            "birim_durumu": d.get("durum"),
            "veri_kaynagi": d.get("veri_kaynagi"),
            "otonomi_tavani": d.get("otonomi_tavani"),
            "escalation": d.get("escalation"),
            "renk": renk,
            "uye_sayisi": len(uyeler),
            "konusan": konusan,
            "uyeler": uyeler,
            # Soru sorulabilir mi: kadrosu olan her departmana sorulabilir.
            "soru_sorulabilir": bool(uyeler),
        })

    sayim = {"yesil": 0, "sari": 0, "kirmizi": 0, "gri": 0}
    for s in satirlar:
        sayim[s["renk"]] = sayim.get(s["renk"], 0) + 1

    return {
        "departmanlar": satirlar,
        "ozet": {
            "departman": len(satirlar),
            "kadrosu_olan": sum(1 for s in satirlar if s["uye_sayisi"]),
            "uye": sum(s["uye_sayisi"] for s in satirlar),
            "konusan_uye": sum(s["konusan"] for s in satirlar),
            "renk": sayim,
        },
        "arastirma_var": arastirma_var,
        "arastirma_son_kosu": max(
            (s["arastirma_son"] for s in satirlar if s["arastirma_son"]), default=""),
        "arastirma_toplam": sum(s["arastirma_toplam"] for s in satirlar),
        "uyari": uye_hatasi,
        "not": ("Renk, o departmanin uyelerinin SU ANKI okuma sonucudur; "
                "birim_durumu ise core.departman alanidir. Ikisi ayri seydir."),
    }


_SAYI = __import__("re").compile(r"\d[\d.,]*")


def _sayilari(metin: str) -> set:
    """Metindeki sayilari ayrac farkindan bagimsiz kumeye cevirir."""
    out = set()
    for ham in _SAYI.findall(metin or ""):
        sade = ham.replace(".", "").replace(",", "").lstrip("0") or "0"
        if len(sade) >= 2:          # tek haneliler cok yanlis pozitif uretir
            out.add(sade)
    return out


def _ekip_sor(kod: str, soru: str) -> dict:
    """Bir departmanin sorumlusuna soru sorar. Cevap KANITA baglidir.

    🔴 UYDURMAYA KARSI UC YAPISAL KAPI (istem degil, kod):
      1. KANIT KAPISI  -- departmanin uyeleri veriden okuyamadiysa model HIC
         cagrilmaz. Cagrilan her model bir uydurma firsatidir.
      2. KANIT BAGI    -- evidence_refs modelin metninden AYIKLANMAZ, verilen
         kanittan kopyalanir; model okunmamis bir kaynak uyduramaz.
      3. SAYI KAPISI   -- cevapta gecip kanitta gecmeyen her sayi
         'dogrulanmayan_sayilar' olarak DONER ve arayuzde gosterilir.
         Sessizce gecirmek, rakami dogrulanmis gostermek olurdu.
    """
    try:
        from jarvis import roster
        from jarvis.model_layer import ModelRouter
    except Exception as exc:  # noqa: BLE001
        return {"hata": f"model katmani yuklenemedi: {exc}"}

    soru = (soru or "").strip()
    if not soru:
        return {"hata": "soru bos"}

    uyeler = roster.departman_uyeleri().get(kod, ())
    if not uyeler:
        return {"hata": f"{kod} departmaninin kadrosu yok; soru sorulamaz.",
                "kod": kod}

    # --- departman kimligi (misyon core.departman'dan, uydurulmaz) ---------
    misyon, birim_adi, birim_durumu = "", kod, ""
    try:
        for d in _memory._fetch("departments").records:
            if str(d.get("kod")) == kod:
                misyon = str(d.get("misyon") or "")
                birim_adi = str(d.get("ad") or kod)
                birim_durumu = str(d.get("durum") or "")
                break
    except Exception:  # noqa: BLE001
        pass

    # --- kanit topla ------------------------------------------------------
    # 🔴 BICIM SOZLESMESI: compile_context her parcada 'ref'/'source' ve
    #    'summary'/'detail' arar. Ilk yazimda {'source':..,'record':{..}}
    #    yollanmisti: 'summary' bulunmayinca her satir "- kaynak: " diye BOS
    #    render edildi ve model dogru bir sekilde "kanitta rakam yok" dedi.
    #    87 satir toplanmisti ama modele hicbiri ULASMAMISTI. Sessiz hataydi;
    #    hata da vermedi, sadece cevap fakirlesti.
    # 🔴 BUTCE: compile_context yalniz ILK 12 parcayi ve 6000 karakteri alir.
    #    O yuzden satir basina bir parca DEGIL, sorgu basina TEK YOGUN ozet
    #    uretilir ve uyelerin damitilmis bulgulari ONE konur.
    kanit: list[dict] = []
    okunamayan: list[str] = []
    sorgular: list[str] = []

    # 1) Uyelerin kendi deterministik bulgulari -- en damitilmis kanit, once.
    try:
        gorusler = roster.opinions(_memory, only=tuple(m.key for m in uyeler))
    except Exception:  # noqa: BLE001
        gorusler = []
    for g in gorusler:
        if g.get("statement"):
            kanit.append({"ref": f"roster:{g['key']}",
                          "summary": f"{g.get('name')} ({g.get('status')}): "
                                     f"{g.get('statement')}"})

    # 1b) DIS ARASTIRMA BULGULARI -- "kendini gelistirme" burada kapanir.
    # 🔴 Arastirma yapip bulguyu kullanmamak, arastirma yapmamakla ayni.
    #    Mudurun okudugu dis kaynak, sirket verisiyle AYNI kanit yiginina
    #    girer; boylece "bu neden boyle" sorusuna hem ic olcumle hem
    #    disaridan ogrendigiyle cevap verebilir.
    # 🔴 IC VERI ILE DIS KAYNAK KARISTIRILMAZ: ref onegi 'arastirma:' oldugu
    #    icin cevabin kaynagi her zaman ayirt edilebilir. Dis kaynak bir
    #    IDDIADIR, sirket olcumu degildir.
    ar_dep = (_arastirma_bulgulari().get(kod) or {}).get("bulgular", [])
    if ar_dep:
        satirlar_ar = []
        for b in ar_dep[:5]:
            satirlar_ar.append(
                f"{b.get('baslik')} [{b.get('yayinci')}] {(b.get('ozet') or '')[:160]}")
        kanit.append({
            "ref": f"arastirma:{kod}",
            "summary": ("DIŞ KAYNAK (şirket ölçümü değil, iddia): "
                        + " | ".join(satirlar_ar))[:1400],
        })

    # 1c) O BIRIME ELLE GIRILMIS GOZLEMLER.
    # 🔴 NEDEN AYRICA EKLENIYOR: bir departmanin gozlemi, ancak uyelerinden
    #    biri 'market_research' sorgusunu OKUYORSA kanita giriyordu. Ama
    #    COMPETITOR_INT'in iki uyesi de arastirma modunda -- hic sorgu
    #    okumuyorlar. Sonuc: operator o birime gozlem giriyor, o birimin
    #    muduru gozlemi GORMUYORDU. Olculdu ve burada kapatildi.
    # 🔴 Seviye (FACT/INTERPRETATION/HYPOTHESIS) metne YAZILIR: bir gozlemi
    #    yorumla ayni kesinlikte sunmak, elle girisin tum degerini bitirirdi.
    try:
        pazar_dep = [b for b in _memory._fetch("market_research").records
                     if str(b.get("departman")) == kod]
    except Exception:  # noqa: BLE001
        pazar_dep = []
    if pazar_dep:
        satirlar_pz = [
            f"[{b.get('seviye')}] {b.get('bulgu')} (kaynak: {b.get('kaynak')}, {b.get('tarih')})"
            for b in pazar_dep[:6]]
        kanit.append({
            "ref": f"gozlem:{kod}",
            "summary": ("OPERATÖRÜN ELLE GİRDİĞİ GÖZLEM — seviye etiketine uy: "
                        "FACT gözlemdir, INTERPRETATION yorumdur, HYPOTHESIS "
                        "sınanmamış tahmindir. " + " | ".join(satirlar_pz))[:1400],
        })

    # 2) Ham sorgular -- sorgu basina tek satir, kolon=deger biciminde.
    def _satir_ozeti(satir: dict, tavan: int = 220) -> str:
        parcalar = []
        for k, v in satir.items():
            if k in ("entity_id", "source", "source_record_id") or v in (None, ""):
                continue
            parcalar.append(f"{k}={v}")
        return "; ".join(parcalar)[:tavan]

    for m in uyeler:
        for q in m.reads:
            if q in sorgular:
                continue
            sorgular.append(q)
            try:
                e = _memory._fetch(q)
            except Exception:  # noqa: BLE001
                okunamayan.append(q)
                continue
            if not e.records:
                kanit.append({"ref": e.source, "summary": "kayıt yok (0 satır)"})
                continue
            satirlar = [_satir_ozeti(r) for r in e.records[:12]]
            ozet = " | ".join(s for s in satirlar if s)[:1400]
            kanit.append({"ref": e.source,
                          "summary": f"{len(e.records)} satır. {ozet}"})

    # 1. KANIT KAPISI
    if not kanit:
        return {"kod": kod, "departman": birim_adi,
                "cevap": (f"{birim_adi} şu an veriden konuşamıyor: okuması gereken "
                          f"kaynaklar açık değil ({', '.join(okunamayan) or 'kaynak yok'}). "
                          f"Bu soruya cevap üretmek uydurma olurdu."),
                "model_kullanildi": False, "kanit_sayisi": 0,
                "okunamayan": okunamayan, "uyeler": [m.name for m in uyeler]}

    # 🔴 ISTEM BIR YAPI DAYATIR, "dikkatli ol" DEMEZ.
    #    Ilk surumde yalnizca "kanittan konus, bilmiyorsan bilinmiyor de"
    #    yaziyordu ve model OLCULEN RAKAMI HIC YAZMADAN dogrudan
    #    "bu veriyle bilinmiyor" dedi -- oysa kanit fiyatin sorularin %56'si
    #    oldugunu soyluyordu. Cekingenlik de bir hatadir: elindeki olcumu
    #    saklayan cevap, uyduran cevap kadar ise yaramaz.
    #    Cozum istemde "daha iyi ol" demek degil, BOLUM DAYATMAK.
    sistem = (
        f"Sen L'CARLIÉ şirketinde {birim_adi} biriminin sorumlususun. "
        f"Görevin: {misyon or 'bu birimin işi'}. "
        "SADECE sana verilen kanıttan konuş; kanıtta olmayan rakamı, ürünü veya "
        "olguyu ASLA yazma.\n"
        "Kanıtta 'DIŞ KAYNAK' ile başlayan satırlar şirketin kendi ölçümü "
        "DEĞİLDİR, dışarıdan okunan iddialardır. Onları kullanırken 'dışarıda "
        "şöyle deniyor' diye ayır; şirket ölçümüyle aynı kesinlikte sunma.\n"
        "Cevabını TAM OLARAK şu dört başlıkla ver:\n"
        "ÖLÇÜLEN: kanıttaki somut rakamları yaz (kaç, yüzde kaç, hangi kaynak). "
        "Bu bölüm boş geçilemez; kanıtta rakam varsa yazılır.\n"
        "OKUMA: bu rakamlar bu birimin işi açısından ne anlama geliyor. "
        "Nedensellik iddia etme; örtüşme ile nedeni ayır.\n"
        "SEÇENEKLER: en fazla üç yol. Her birinin yanında ÇÜRÜTÜCÜSÜ olsun — "
        "yani hangi ölçüm görülürse o yolun yanlış olduğu anlaşılır.\n"
        "BİLİNMEYEN: bu veriyle cevaplanamayan kısım ve onu cevaplamak için "
        "hangi ölçümün gerektiği.\n"
        "Kesin sonuç vaat etme. Türkçe yaz, toplam 12 cümleyi geçme."
    )

    router = ModelRouter()
    try:
        sonuc = router.synthesize(soru, kanit, missing_data=okunamayan,
                                  escalate=True, max_tokens=900, system=sistem)
    except Exception as exc:  # noqa: BLE001
        return {"kod": kod, "departman": birim_adi,
                "hata": f"model cevap veremedi: {str(exc)[:200]}",
                "kanit_sayisi": len(kanit)}

    # 🔴 ModelResult'ta alan adi 'answer'. 'text' diye bir alan YOK; ilk
    #    yazimda oyle varsayilmisti ve cevap sessizce None donuyordu --
    #    kanit toplama calisirken metin bos geliyordu, hata da vermiyordu.
    cevap = getattr(sonuc, "answer", "") or ""
    refs = list(getattr(sonuc, "evidence_refs", ()) or ())

    # 3. SAYI KAPISI
    kanit_metni = json.dumps(kanit, ensure_ascii=False)
    dogrulanmayan = sorted(_sayilari(cevap) - _sayilari(kanit_metni))

    return {
        "kod": kod,
        "departman": birim_adi,
        "birim_durumu": birim_durumu,
        "soru": soru,
        "cevap": cevap,
        "uyeler": [m.name for m in uyeler],
        "kanit_sayisi": len(kanit),
        "kanit_kaynaklari": sorted({k["ref"] for k in kanit}),
        "evidence_refs": refs,
        "okunamayan": okunamayan,
        "dogrulanmayan_sayilar": dogrulanmayan,
        "model_kullanildi": True,
        "guven": getattr(sonuc, "confidence", None),
        "model": getattr(sonuc, "model", "") or "",
    }


def _panel_ayarlar() -> dict:
    """Yonetisim anahtarlari -- SALT OKUNUR.

    Panelden degistirilemez: EXTERNAL_ACTIONS ve kill switch sahibin kararidir
    ve tarayicidan degistirilebilir olmasi Action Firewall'un anlamini bozar.
    """
    env = {}
    try:
        for line in pathlib.Path("/etc/lcarlie/jarvis-phase2.env").read_text(
                encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                if any(s in key.upper() for s in ("TOKEN", "KEY", "SECRET", "PASS")):
                    continue  # sir degeri panele tasinmaz
                env[key.strip()] = value.strip()
    except Exception as exc:  # noqa: BLE001
        env = {"error": str(exc)[:200]}

    thresholds = {}
    try:
        from jarvis.business_signals import DEFAULT_THRESHOLDS
        thresholds = dict(DEFAULT_THRESHOLDS)
    except Exception:  # noqa: BLE001
        pass

    compliance = {}
    try:
        from jarvis.compliance import PUBLISHED_TEXT_ACTIONS, RULES_SOURCE
        compliance = {"rules_source": RULES_SOURCE,
                      "gated_actions": sorted(PUBLISHED_TEXT_ACTIONS)}
    except Exception:  # noqa: BLE001
        pass

    return {"model_usage": _panel_usage(),
        "env": env, "thresholds": thresholds, "compliance": compliance,
        "readonly": True,
        "note": ("Bu degerler panelden degistirilemez. EXTERNAL_ACTIONS ve kill "
                 "switch sunucuda, sahibin karariyla degisir."),
        "kill_switch": ("systemctl stop jarvis-phase2.timer && "
                        "systemctl disable jarvis-phase2.timer"),
    }


if __name__ == "__main__":
    main()

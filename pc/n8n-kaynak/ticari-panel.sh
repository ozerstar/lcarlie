#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - TICARI DURUM PANELI  (CR-007)
#
# Ticari aynayi (CR-004/005/006) telefondan okunabilir hale getirir.
#
# 🔴 CADDY'YE DOKUNULMAZ.  Mevcut yapilandirma /durum-<TOKEN>* yolunu
#    /opt/lcarlie/durum dizinine baglayip file_server ile TUM DIZINI
#    servis ediyor. Bu yuzden sayfa oraya ticari.html olarak yazilir:
#    yeni yol, yeni token, yeni Caddy kurali GEREKMEZ. Uretim
#    yapilandirmasina dokunmamak, dokunup geri almaktan iyidir.
#
# 🔴 OLCUM 1 EKIM'DE BASLIYOR.  O tarihe kadar ticari sayilar BOS olacak.
#    Panel bunu "0 TL ciro" diye GOSTERMEZ - "olcum henuz baslamadi" der.
#    Sifir ile yokluk ayni sey degildir; panelin en kolay yalan soyleme
#    yolu budur.
#
# 🔴 TEK "CIRO" SAYISI YOK.  Dogrulanmis (PayTR) ve beyan edilmis
#    (cevrim disi/kapida) AYRI gosterilir. ROAS da ayni sebeple iki ayri.
#
# 🔴 MARJ, KAPSAMA ORANI OLMADAN GOSTERILMEZ.  Cironun yuzde kacinin
#    maliyeti biliniyorsa o rakam marjin yaninda durur.
#
# 🔴 PII YOK.  Musteri adi, telefonu, e-postasi, adresi bu sayfada
#    hicbir kosulda gorunmez.
#
# Kullanim: /opt/lcarlie/ticari-panel.sh
# Adres   : https://n8n.lcarlie.shop/durum-<DURUM_TOKEN>/ticari.html
# =============================================================================
set -uo pipefail

KOK=/opt/lcarlie
KAP=lcarlie-postgres

# 🔴 VERITABANI VE CIKTI ADI PARAMETRELI.  Uretim disinda bir kopya
#    uzerinde prova yapabilmek icin sart; aksi halde "1 Ekim'de ne
#    olacak" sorusu ancak 1 Ekim'de cevaplanir - yani en gec anda.
#    Varsayilanlar uretimdir, hicbir cagirma degismez.
VT="${LCARLIE_VT:-n8n}"
WEB="${LCARLIE_WEB:-$KOK/durum}"
SAYFA="${LCARLIE_SAYFA:-ticari.html}"
mkdir -p "$WEB"

sorgu() {
  docker exec -i "$KAP" psql -U n8n -d "$VT" -tA -F'|' -v ON_ERROR_STOP=1 2>/dev/null
}

kacis() { printf '%s' "${1:-}" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g'; }

# --- Veri ---------------------------------------------------------------------
# 🔴 Tek sorguda tek satir: parcali sorgu, parcali basarisizlik demektir.
#    Sorgu calismazsa panel "veri yok" degil "OKUNAMADI" gosterir.
OZET=$(sorgu <<'SQL'
WITH kesim AS (SELECT (mart.kesim() AT TIME ZONE 'Europe/Istanbul')::date AS g),
s AS (
  SELECT count(*) FILTER (WHERE ciro_sinifi='DOGRULANMIS')   AS ad_dogr,
         count(*) FILTER (WHERE ciro_sinifi='BEYAN_EDILMIS') AS ad_beyan,
         count(*) FILTER (WHERE ciro_sinifi='ODENMEDI')      AS ad_odenmedi,
         count(*) FILTER (WHERE ciro_sinifi='IPTAL')         AS ad_iptal,
         coalesce(sum(ciro_dogrulanmis),0)   AS tl_dogr,
         coalesce(sum(ciro_beyan_edilmis),0) AS tl_beyan,
         coalesce(sum(tutar_bekleyen),0)     AS tl_bekleyen
    FROM mart.siparis WHERE olcumde
),
g AS (
  SELECT count(*) FILTER (WHERE sinif='SATIS')  AS gon_satis,
         count(*) FILTER (WHERE sinif='NUMUNE') AS gon_numune,
         count(*) FILTER (WHERE sinif='IADE')   AS gon_iade,
         count(*) FILTER (WHERE alarm)          AS gon_alarm,
         count(*) FILTER (WHERE sinif='ELLE_SATIS') AS gon_elle,
         count(*) FILTER (WHERE sinif='UNKNOWN') AS gon_bilinmeyen,
         coalesce(sum(elle_ciro_tahsil),0)      AS tl_elle_tahsil,
         coalesce(sum(elle_ciro_bekleyen),0)    AS tl_elle_bekleyen,
         coalesce(sum(kargo_ucreti),0)          AS tl_kargo
    FROM mart.gonderi WHERE olcumde
),
r AS (
  SELECT coalesce(sum(harcama),0) AS tl_reklam
    FROM raw.meta_harcama, kesim
   WHERE kampanya_id <> '_HESAP' AND gun >= kesim.g
),
m AS (
  SELECT coalesce(sum(brut_marj),0) AS tl_marj,
         coalesce(round(100.0*sum(satir_ciro) FILTER (WHERE maliyeti_biliniyor)
                  /nullif(sum(satir_ciro),0),1),0) AS kapsama
    FROM mart.siparis_kalem WHERE olcumde AND ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')
),
a AS (SELECT count(*) AS acik FROM mart.acik_isler),
mu AS (SELECT count(*) AS musteri FROM core.customer)
SELECT kesim.g, (kesim.g - CURRENT_DATE) AS kalan_gun,
       s.ad_dogr, s.ad_beyan, s.ad_odenmedi, s.ad_iptal,
       s.tl_dogr, s.tl_beyan, s.tl_bekleyen,
       g.gon_satis, g.gon_numune, g.gon_iade, g.gon_alarm,
       g.gon_elle, g.gon_bilinmeyen, g.tl_elle_tahsil, g.tl_elle_bekleyen, g.tl_kargo,
       r.tl_reklam, m.tl_marj, m.kapsama, a.acik, mu.musteri
  FROM kesim, s, g, r, m, a, mu;
SQL
)
OZET_KOD=$?

if [ "$OZET_KOD" -ne 0 ] || [ -z "$OZET" ]; then
  # 🔴 Veritabani okunamadiysa panel SIFIR GOSTERMEZ. Bos bir panel
  #    "is yok" demektir; okunamayan panel "bilmiyoruz" demelidir.
  cat > "$WEB/$SAYFA" <<'HATA'
<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>L'CARLIÉ · Ticari Durum</title>
<style>body{font:16px/1.6 system-ui,sans-serif;background:#1a1416;color:#f4ecec;
margin:0;padding:24px;max-width:720px;margin-inline:auto}
.k{background:#3a1c22;border:1px solid #7a2f3a;border-radius:12px;padding:20px}</style></head>
<body><div class="k"><h1>Veri okunamadı</h1>
<p>Ticari veritabanı sorgusu çalışmadı. Bu <strong>&ldquo;iş yok&rdquo; demek değildir</strong> —
durum bilinmiyor.</p>
<p>Kontrol: <code>ssh lcarlie "/opt/lcarlie/ticari-panel.sh"</code></p></div></body></html>
HATA
  echo "HATA: ozet sorgusu calismadi, panel 'okunamadi' olarak yazildi." >&2
  exit 1
fi

IFS='|' read -r KESIM KALAN AD_DOGR AD_BEYAN AD_ODENMEDI AD_IPTAL \
  TL_DOGR TL_BEYAN TL_BEKLEYEN GON_SATIS GON_NUMUNE GON_IADE GON_ALARM \
  GON_ELLE GON_BILINMEYEN TL_ELLE_TAHSIL TL_ELLE_BEKLEYEN TL_KARGO TL_REKLAM TL_MARJ KAPSAMA ACIK MUSTERI <<< "$OZET"

# Olcum basladi mi
OLCUM_BASLADI=0
[ "${KALAN:-1}" -le 0 ] && OLCUM_BASLADI=1

# Kaynak sagligi: her kaynagin SON durumu
KAYNAK=$(sorgu <<'SQL'
SELECT DISTINCT ON (kaynak) kaynak, durum,
       to_char(bitis AT TIME ZONE 'Europe/Istanbul','DD.MM HH24:MI'),
       round(extract(epoch FROM (now()-bitis))/3600.0,1)
  FROM raw.yukleme_log ORDER BY kaynak, id DESC;
SQL
)

# Acik isler: tur bazinda
ISLER=$(sorgu <<'SQL'
SELECT tur, count(*), left(min(yapilacak),80) FROM mart.acik_isler GROUP BY 1 ORDER BY 2 DESC;
SQL
)

# Maliyet kapsamasi: en cok satan maliyetsiz urunler
MALIYET=$(sorgu <<'SQL'
SELECT left(urun_adi,34), to_char(olculemeyen_ciro,'FM999999990'), satilan_kalem
  FROM mart.maliyet_eksik ORDER BY olculemeyen_ciro DESC LIMIT 5;
SQL
)

# Konusma hacmi ve cevapsizlik  (CR-011)
# 🔴 ATIF YOK: bu rakamlar "hangi konusma satis getirdi" demez. Hacim ve
#    cevapsizlik olcer - ikisi de kendi basina is degeri tasir.
KONUSMA=$(sorgu <<'SQL'
SELECT (SELECT count(*) FROM mart.konusma_cevapsiz WHERE bekleme_saat > 24),
       (SELECT coalesce(round(max(bekleme_saat)/24.0,1),0) FROM mart.konusma_cevapsiz),
       (SELECT coalesce(sum(yeni_konusma),0) FROM mart.konusma_gunluk WHERE olcumde),
       (SELECT coalesce(sum(gelen_mesaj),0) FROM mart.konusma_gunluk WHERE olcumde);
SQL
)
IFS='|' read -r KON_CEVAPSIZ KON_EN_ESKI KON_YENI KON_GELEN <<< "$KONUSMA"

# Olcum oncesi referans - "olcum disi" etiketiyle gosterilir
ONCESI=$(sorgu <<'SQL'
SELECT to_char(coalesce(sum(ciro_dogrulanmis),0),'FM999999990'),
       to_char(coalesce(sum(ciro_beyan_edilmis),0),'FM999999990'),
       count(*) FILTER (WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS'))
  FROM mart.siparis WHERE NOT olcumde;
SQL
)
IFS='|' read -r ONC_DOGR ONC_BEYAN ONC_ADET <<< "$ONCESI"

tl() { printf "%'d" "${1%.*}" 2>/dev/null | tr ',' '.' || printf '%s' "$1"; }

# 🔴 OLCUM BASLAMADAN ONCE HER OLCUM RAKAMI "—" GOSTERILIR, "0" DEGIL.
#    Ilk surumde ciro "—" ama reklam/kargo "₺0" gosteriyordu; ikisi de ayni
#    seyi (veri yok) soylemesi gerekirken biri yoklugu, digeri SIFIRI
#    soyluyordu. Panelde tutarsizlik, okuyanin hangisine inanacagini
#    bilememesi demektir.
olc() { if [ "$OLCUM_BASLADI" -eq 1 ]; then printf '%s' "$1"; else printf '—'; fi; }
olc_tl() { if [ "$OLCUM_BASLADI" -eq 1 ]; then printf '₺%s' "$(tl "$1")"; else printf '—'; fi; }

# --- ROAS: iki ayri, sifira bolme NULL ---------------------------------------
roas() {  # $1=ciro $2=harcama
  awk -v c="$1" -v h="$2" 'BEGIN{ if (h+0==0) print "—"; else printf "%.2f", c/h }'
}
ROAS_DOGR=$(roas "$TL_DOGR" "$TL_REKLAM")
# 🔴 ELLE SATIS CIROSU DA PAYA GIRER (sahip kurali 16.09.2026).
#    Kapida odemeli + Wix kaydi olmayan gonderiler WhatsApp/telefon
#    siparisidir; cirolari BasitKargo'dan gelir. Onceki halinde bu para
#    hic sayilmiyordu ve ROAS oldugundan DUSUK gorunuyordu.
#    YALNIZ TAHSIL EDILMIS olan sayilir - bekleyen para henuz ciro degil.
TL_BEYAN_TUM=$(awk -v a="$TL_BEYAN" -v b="$TL_ELLE_TAHSIL" 'BEGIN{print a+b}')
ROAS_TUM=$(roas "$(awk -v a="$TL_DOGR" -v b="$TL_BEYAN_TUM" 'BEGIN{print a+b}')" "$TL_REKLAM")

# --- Hazirlik kapisi (CR-012) -------------------------------------------------
HAZIRLIK=$(sorgu <<'SQL'
SELECT kosul, saglandi, left(detay,60) FROM mart.hazirlik ORDER BY saglandi, kosul;
SQL
)
KARAR_HAZIR=$(sorgu <<'SQL'
SELECT karar_hazir FROM mart.hazirlik_ozet;
SQL
)
# 🔴 Sorgu calismadiysa "hazir" VARSAYILMAZ. Bilinmiyorsa kapi KAPALI kalir -
#    bu projede sessiz basari yasak. Bos deger 't' degildir, 'f' sayilir.
[ "$KARAR_HAZIR" = "t" ] || KARAR_HAZIR="f"

# --- P0 OLCUM TEMELI KAPISI (16.09.2026, Chief Architect kurali) --------------
# 🔴 mart.hazirlik TEK BASINA YETMIYOR. Onun 5 kosulu arasinda ne numune
#    siniflandirmasi ne de BasitKargo isaretinin okunabilirligi var. Yani
#    1 Ekim geldiginde mart.hazirlik "hazir" diyebilir ve panel ROAS
#    gosterebilirdi - oysa gonderilerin sinifi hala bilinmiyor olurdu.
#    Kural acikti: "ilk ucu gecmiyorsa 1 Ekim geldi diye ROAS'i karar
#    metrigi yapma". Kural yalniz gunluk betikte dursaydi TAVSIYE olurdu;
#    ROAS'in GOSTERILDIGI yerde durmasi gerekir, cunku kapanin islevi
#    sayiyi ekrana birakmamaktir.
P0_KAPI=$(sorgu <<'SQL'
SELECT p0_gecti, p0_eksikler FROM mart.roas_kapisi;
SQL
)
IFS='|' read -r P0_GECTI P0_EKSIKLER <<< "$P0_KAPI"
[ "$P0_GECTI" = "t" ] || P0_GECTI="f"
# Iki kapi da acik olmadan ROAS SAYISI yazilmaz.
[ "$P0_GECTI" = "t" ] || KARAR_HAZIR="f"

# --- Maliyet kalitesi (CR-012) ------------------------------------------------
# 🔴 KAPSAMA ile KALITE AYRI: 36 urunun 36'sinda maliyet var ama hepsi ayni
#    400 TL sahip tahmini. Kapsama %96, olculmus maliyet 0.
MKALITE=$(sorgu <<'SQL'
SELECT count(*) FILTER (WHERE kalite='OLCULMUS'),
       count(*) FILTER (WHERE kalite='TAHMIN'),
       count(*),
       coalesce(max(kdv_tabani),'TEYIT_EDILMEDI')
  FROM mart.maliyet_kalite;
SQL
)
IFS='|' read -r MK_OLCULMUS MK_TAHMIN MK_TOPLAM MK_KDV <<< "$MKALITE"

# --- Para zinciri (CR-012) ----------------------------------------------------
PARA=$(sorgu <<'SQL'
SELECT count(*), count(*) FILTER (WHERE kargolandi), count(*) FILTER (WHERE teslim_edildi),
       count(*) FILTER (WHERE iade_var), count(*) FILTER (WHERE NOT gonderi_kaydi_var),
       to_char(coalesce(sum(kdv),0),'FM999999990.00'),
       to_char(coalesce(sum(cod_bekleyen),0),'FM999999990.00')
  FROM mart.siparis_para WHERE olcumde;
SQL
)
IFS='|' read -r P_SIP P_KARGO P_TESLIM P_IADE P_KAYITSIZ P_KDV P_COD_BEK <<< "$PARA"

URETIM=$(date '+%d.%m.%Y %H:%M')
URETIM_EPOCH=$(date +%s)

# --- HTML ---------------------------------------------------------------------
{
cat <<'HTML'
<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>L'CARLIÉ · Ticari Durum</title>
<style>
:root{--bg:#141013;--kart:#1e1a1d;--cizgi:#302a2e;--metin:#f2ecee;--sol:#a79aa0;
--yesil:#4ba873;--sari:#d9a441;--kirmizi:#d4636f;--mavi:#6b93c9}
*{box-sizing:border-box}
body{font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
background:var(--bg);color:var(--metin);margin:0;padding:16px;
max-width:760px;margin-inline:auto;-webkit-text-size-adjust:100%}
h1{font-size:19px;margin:0 0 4px;letter-spacing:.2px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:var(--sol);
margin:26px 0 10px;font-weight:600}
.alt{color:var(--sol);font-size:13px;margin:0 0 18px}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:14px;
padding:16px;margin-bottom:12px}
/* 🔴 flex-wrap SART: dar ekranda uzun etiket + buyuk rakam yan yana
   sigmazsa satir tasar ve sayfa yatay kayar. Sarmalayinca rakam alt
   satira iner, okunurluk bozulmaz. Panel telefondan okunacak. */
.sr{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;
gap:4px 12px;padding:9px 0;border-bottom:1px solid var(--cizgi)}
.sr:last-child{border-bottom:0}
.et{color:var(--sol);font-size:14px;min-width:0;overflow-wrap:anywhere}
.sr>div{min-width:0;flex:1 1 auto}
.dg{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
.buyuk{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;
letter-spacing:-.5px}
.kucuk{font-size:12px;color:var(--sol);margin-top:3px;line-height:1.45}
.yesil{color:var(--yesil)}.sari{color:var(--sari)}.kirmizi{color:var(--kirmizi)}
.mavi{color:var(--mavi)}.sol{color:var(--sol)}
.uyari{background:#2b1f22;border:1px solid #5e3a41;border-radius:12px;
padding:14px;margin-bottom:12px;font-size:14px;line-height:1.5}
.bilgi{background:#1a2027;border:1px solid #2f3f4d;border-radius:12px;
padding:14px;margin-bottom:12px;font-size:14px;line-height:1.5}
.rozet{display:inline-block;padding:2px 9px;border-radius:99px;font-size:11px;
font-weight:700;letter-spacing:.4px}
.r-ok{background:#1d3a2a;color:#78d39b}.r-yok{background:#3a3222;color:#e0b95f}
.r-hata{background:#3d2329;color:#e88b96}
table{width:100%;border-collapse:collapse;font-size:14px;table-layout:fixed}
td{padding:7px 0;border-bottom:1px solid var(--cizgi);vertical-align:top;
overflow-wrap:anywhere}
td.s{width:33%}
tr:last-child td{border-bottom:0}
td.s{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;padding-left:10px}
.dn{font-size:12px;color:var(--sol);text-align:center;margin:22px 0 8px;line-height:1.6}
a{color:var(--mavi)}
#bayat{display:none;background:#3d2329;border:1px solid #6b3a42;border-radius:12px;
padding:14px;margin-bottom:12px;font-size:14px}
</style></head><body>
HTML

echo "<h1>L'CARLIÉ · Ticari Durum</h1>"
echo "<p class=\"alt\">Üretildi: $URETIM · <a href=\"./\">sistem durumu →</a></p>"
echo '<div id="bayat"><strong>Bu sayfa bayat.</strong> Son üretimden bu yana 90 dakikadan fazla geçti — rakamlar güncel olmayabilir.</div>'

# --- Olcum durumu -------------------------------------------------------------
if [ "$OLCUM_BASLADI" -eq 0 ]; then
  cat <<HTML
<div class="bilgi">
<strong>Ölçüm henüz başlamadı.</strong><br>
Ticari ölçüm <strong>$(kacis "$KESIM")</strong> tarihinde başlıyor — <strong>$KALAN gün</strong> kaldı.
Aşağıdaki ölçüm rakamları o tarihe kadar boş kalacak; bu bir arıza değil.
<div class="kucuk" style="margin-top:8px">Sıfır ile yokluk aynı şey değildir: bu panel
ölçüm başlamadan &ldquo;0 TL ciro&rdquo; demez.</div>
</div>
HTML
else
  GECEN=$(( -KALAN ))
  echo "<div class=\"bilgi\"><strong>Ölçüm sürüyor.</strong> $(kacis "$KESIM") tarihinden bu yana <strong>$GECEN gün</strong>.</div>"
fi

# --- BUGUNKU TICARI NABIZ (CR-013) --------------------------------------------
# 🔴 EN USTTE DURUR ve OLCUM KESIMINE BAKMAZ.  Asagidaki tum bolumler
#    1 Ekim penceresine bagli oldugu icin panel bir aydir hicbir ticari
#    rakam gostermedi - o sirada reklam harcamasi ciroyu asiyordu ve bu
#    hicbir ekranda gorunmedi. Susmasi gereken sey atifli ROAS'ti, nakit degil.
nabiz_kart() {   # $1 = gun sayisi, $2 = baslik
  local sat; sat=$(sorgu <<SQL
SELECT siparis, to_char(net_ciro,'FM999999990.00'), to_char(tahsil_beyan,'FM999999990.00'),
       to_char(tahsil_edilmemis,'FM999999990.00'), to_char(bilinen_cogs,'FM999999990.00'),
       -- 🔴 bilinmeyen_kargo DA TOPLANIR. Katki hesabindan dusuluyor; karttan
       --    dusulmezse kart kendi icinde tutmaz ve "kargo" oldugundan kucuk
       --    gorunur. Sinifi bilmemek, parayi harcamamis olmak degildir.
       coalesce(cogs_olculmus_yuzde,0),
       to_char(satis_kargosu+numune_kargosu+bilinmeyen_kargo,'FM999999990.00'),
       to_char(meta_harcama,'FM999999990.00'), meta_kapsama,
       to_char(reklam_oncesi,'FM999999990.00'), to_char(reklam_sonrasi,'FM999999990.00'),
       coalesce(katki_yuzde,0), coalesce(ciro_harcama_orani,0),
       harcamali_satissiz_gun, nakit_durum, to_char(wixdisi_bekleyen,'FM999999990.00')
  FROM mart.nakit_ozet($1);
SQL
)
  [ -z "$sat" ] && { echo "<div class=\"kart\"><div class=\"kucuk\">$2 — veri okunamadı</div></div>"; return; }
  IFS='|' read -r n_sip n_net n_tah n_tahs n_cogs n_cq n_krg n_har n_kap n_once n_sonra n_kyuz n_oran n_hsg n_dur n_wbek <<< "$sat"
  local renk rozet
  case "$n_dur" in
    CRITICAL)          renk=kirmizi; rozet='r-hata' ;;
    WATCH)             renk=sari;    rozet='r-yok'  ;;
    HEALTHY)           renk=yesil;   rozet='r-ok'   ;;
    *)                 renk=sol;     rozet='r-yok'  ;;
  esac
  cat <<HTML
<div class="kart">
<div class="sr"><div><span class="et"><strong>$2</strong></span></div>
<span class="rozet $rozet">$(kacis "$n_dur")</span></div>
<div class="sr"><span class="et">Sipariş (iptal hariç)</span><span class="dg">$n_sip</span></div>
<div class="sr"><span class="et">Net ciro (KDV hariç)</span><span class="dg">₺$(tl "$n_net")</span></div>
<div class="sr"><span class="et kucuk">— tahsil beyan edilen</span><span class="dg sol">₺$(tl "$n_tah")</span></div>
<div class="sr"><span class="et kucuk">— tahsil edilmemiş</span><span class="dg sol">₺$(tl "$n_tahs")</span></div>
<div class="sr"><span class="et">Bilinen ürün maliyeti</span><span class="dg">₺$(tl "$n_cogs")</span></div>
<div class="sr"><span class="et">Kargo (satış + numune + sınıfsız)</span><span class="dg">₺$(tl "$n_krg")</span></div>
<div class="sr"><span class="et">Reklam öncesi katkı</span><span class="dg">₺$(tl "$n_once")</span></div>
<div class="sr"><div><span class="et">Meta harcaması</span>
<div class="kucuk">hesap kapsaması <strong>$(kacis "$n_kap")</strong> — bu bir <strong>taban</strong>, gerçek daha yüksek olabilir</div></div>
<span class="dg">₺$(tl "$n_har")</span></div>
<div class="sr"><span class="et"><strong>Reklam sonrası</strong></span><span class="dg buyuk $renk">₺$(tl "$n_sonra")</span></div>
<div class="sr"><span class="et">Ciro ÷ harcama</span><span class="dg $renk">$n_oran</span></div>
<div class="sr"><span class="et">Harcama var, sipariş yok</span><span class="dg $([ "${n_hsg:-0}" -gt 0 ] && echo kirmizi)">$n_hsg gün</span></div>
HTML
  # 🔴 Maliyet kalitesi ve Wix disi bekleyen para GIZLENMEZ.
  echo "<div class=\"kucuk\" style=\"margin-top:8px\">Ürün maliyetinin <strong>%$n_cq</strong>'i ölçülmüş
(gerisi sahip tahmini) · Wix dışı bekleyen kapıda ödeme <strong>₺$(tl "$n_wbek")</strong> bu ciroya
<strong>dahil değil</strong>.</div></div>"
}

echo '<h2>Bugünkü ticari nabız</h2>'
cat <<'HTML'
<div class="bilgi">🔴 Bu görünüm <strong>attribution/ROAS raporu değildir</strong>.
Bağlı kaynaklardan ölçülebilen <strong>ticari nakit ve maliyet</strong> görünümüdür —
ve <strong>1 Ekim ölçüm penceresini beklemez</strong>.
&ldquo;Bu satışı şu reklam getirdi&rdquo; demez, diyemez.</div>
HTML
nabiz_kart 7  "Son 7 gün"
nabiz_kart 30 "Son 30 gün"

# 🔴 EKSIK MALIYETLER PANELDE SAKLANMAZ: katki rakamlarinin ne kadar
#    iyimser oldugu okuyana acikca soylenir.
NKALITE=$(sorgu <<'SQL'
SELECT kalem, durum, etki FROM mart.nakit_veri_kalitesi
 WHERE durum IN ('MISSING','TAHMIN','PARTIAL') ORDER BY
   CASE durum WHEN 'MISSING' THEN 1 WHEN 'TAHMIN' THEN 2 ELSE 3 END, kalem;
SQL
)
if [ -n "$NKALITE" ]; then
  echo '<div class="kart"><div class="kucuk" style="margin-bottom:8px"><strong>Bu hesaba GİREMEYEN kalemler</strong>
— eksik maliyetler sıfır sayılmadı, bu yüzden yukarıdaki katkı rakamları <strong>olduğundan iyimser</strong>:</div><table>'
  while IFS='|' read -r kk dd ee; do
    [ -z "$kk" ] && continue
    r=sol; [ "$dd" = "MISSING" ] && r=kirmizi; [ "$dd" = "TAHMIN" ] && r=sari
    echo "<tr><td>$(kacis "$kk")<div class=\"kucuk\">$(kacis "$ee")</div></td><td class=\"s $r\">$dd</td></tr>"
  done <<< "$NKALITE"
  echo '</table></div>'
fi

# --- GROWTH BRIEF (CR-014) ----------------------------------------------------
# 🔴 PANELDEN AKSIYON BUTONU YOK.  Bu bolum yalniz brief'in VARLIGINI ve
#    ozetini gosterir; hicbir seye tiklanarak butce/kampanya/fiyat degismez.
BRIEF=$(sorgu <<'SQL'
SELECT a.anlik_id,
       to_char(a.alindi AT TIME ZONE 'Europe/Istanbul','DD.MM HH24:MI'),
       a.kanit_sinifi, a.kanit_puani,
       (SELECT count(*) FROM core.buyume_bulgu b
         WHERE b.anlik_id=a.anlik_id AND b.modul='RED_TEAM' AND b.sinif='CHALLENGE'),
       round(extract(epoch FROM now()-a.alindi)/3600.0,1)
  FROM core.kanit_anlik a ORDER BY a.anlik_id DESC LIMIT 1;
SQL
)
if [ -n "$BRIEF" ]; then
  IFS='|' read -r B_ID B_ZAMAN B_SINIF B_PUAN B_MEYDAN B_SAAT <<< "$BRIEF"
  case "$B_SINIF" in HIGH) bk=yesil ;; MEDIUM) bk=sari ;; *) bk=kirmizi ;; esac
  echo '<h2>Growth brief</h2><div class="kart">'
  echo "<div class=\"sr\"><span class=\"et\">Son brief</span><span class=\"dg\">$(kacis "$B_ZAMAN")</span></div>"
  echo "<div class=\"sr\"><span class=\"et\">Kanıt kalitesi</span><span class=\"dg $bk\">$(kacis "$B_SINIF") ($B_PUAN/12)</span></div>"
  echo "<div class=\"sr\"><span class=\"et\">Red Team itirazı</span><span class=\"dg $([ "${B_MEYDAN:-0}" -gt 0 ] && echo sari)\">$B_MEYDAN</span></div>"
  # 🔴 BAYAT BRIEF SESSIZ KALMAZ: eski brief guncel sanilirsa yanlis karar verilir.
  awk -v s="${B_SAAT:-0}" 'BEGIN{exit !(s+0>36)}' && \
    echo "<div class=\"kucuk kirmizi\">Brief ${B_SAAT} saat önce üretildi — güncel olmayabilir</div>"
  # En onemli 3 sinyal ve 3 bosluk
  SINYAL=$(sorgu <<SQL
SELECT left(baslik,54) FROM core.buyume_bulgu
 WHERE anlik_id=$B_ID AND modul IN ('META','URUN')
   AND coalesce(sinif,'') IN ('CRITICAL','FIX_FUNNEL_FIRST','SCALE_CANDIDATE')
 ORDER BY bulgu_id LIMIT 3;
SQL
)
  BOSLUK=$(sorgu <<'SQL'
SELECT kalem FROM mart.nakit_veri_kalitesi WHERE durum='MISSING' ORDER BY kalem LIMIT 3;
SQL
)
  [ -n "$SINYAL" ] && { echo '<div class="kucuk" style="margin-top:10px"><strong>En önemli 3 sinyal</strong></div><table>'
    while IFS= read -r s; do [ -z "$s" ] && continue; echo "<tr><td>$(kacis "$s")</td></tr>"; done <<< "$SINYAL"
    echo '</table>'; }
  [ -n "$BOSLUK" ] && { echo '<div class="kucuk" style="margin-top:6px"><strong>En önemli 3 veri boşluğu</strong></div><table>'
    while IFS= read -r s; do [ -z "$s" ] && continue; echo "<tr><td>$(kacis "$s")<span class=\"s kirmizi\"> MISSING</span></td></tr>"; done <<< "$BOSLUK"
    echo '</table>'; }
  echo '<div class="kucuk" style="margin-top:10px">🔴 Brief <strong>karar vermez</strong>; her öneri insan onayı bekler.
AI/LLM çağrısı <strong>yapılmıyor</strong> — tüm çıkarımlar deterministik kural.</div></div>'
fi

# --- DECISION MEMORY (CR-015) -------------------------------------------------
# 🔴 PANELDEN AKSIYON YOK.  Bu bolum yalniz kararlarin DURUMUNU gosterir;
#    hicbir butona basilarak butce/kampanya/fiyat degismez.
KARAR=$(sorgu <<'SQL'
SELECT acik_karar, insan_onayi_bekleyen, uygulandi_olculuyor, sonuclanan,
       sonucsuz, red_team_itirazi, toplam, itiraz_alan_karar FROM mart.karar_ozet;
SQL
)
if [ -n "$KARAR" ]; then
  IFS='|' read -r K_ACIK K_BEK K_OLC K_SON K_SONSUZ K_RT K_TOP K_RTK <<< "$KARAR"
  echo '<h2>Karar hafızası</h2><div class="kart">'
  if [ "${K_TOP:-0}" -eq 0 ]; then
    # 🔴 BOS LISTE YESIL GOSTERILMEZ: "karar yok" ile "her sey yolunda" ayni sey degil.
    echo '<div class="sr"><span class="et">Kayıtlı karar</span><span class="dg sol">—</span></div>
<div class="kucuk" style="margin-top:8px">Henüz hiçbir brief önerisi karar adayına dönüştürülmedi.
Bu <strong>&ldquo;karar gerekmiyor&rdquo; demek değil</strong> — akış henüz işletilmedi.</div>'
  else
    echo "<div class=\"sr\"><span class=\"et\">Açık karar</span><span class=\"dg\">$K_ACIK</span></div>"
    echo "<div class=\"sr\"><span class=\"et\">İnsan onayı bekleyen</span><span class=\"dg $([ "${K_BEK:-0}" -gt 0 ] && echo sari)\">$K_BEK</span></div>"
    echo "<div class=\"sr\"><span class=\"et\">Uygulandı · ölçülüyor</span><span class=\"dg\">$K_OLC</span></div>"
    echo "<div class=\"sr\"><span class=\"et\">Sonuçlanan</span><span class=\"dg\">$K_SON</span></div>"
    echo "<div class=\"sr\"><span class=\"et\">Sonuçsuz (yetersiz kanıt)</span><span class=\"dg sol\">$K_SONSUZ</span></div>"
    # 🔴 TEKIL itiraz gosterilir; ayni itiraz her karara baglandigi icin
    #    ham satir sayimi sisik gorunuyordu (7 itiraz x 6 karar = 42).
    echo "<div class=\"sr\"><div><span class=\"et\">Red Team itirazı</span>
<div class=\"kucuk\">$K_RTK kararın tamamına uygulanıyor</div></div><span class=\"dg $([ "${K_RT:-0}" -gt 0 ] && echo sari)\">$K_RT tekil</span></div>"
    SONKARAR=$(sorgu <<'SQL'
SELECT tarih, oneri, insan_karari, durum, sonuc FROM mart.karar_son LIMIT 5;
SQL
)
    if [ -n "$SONKARAR" ]; then
      echo '<div class="kucuk" style="margin-top:10px"><strong>Son 5 karar</strong></div><table>'
      while IFS='|' read -r t o ik d s; do
        [ -z "$t" ] && continue
        echo "<tr><td>$(kacis "$o")<div class=\"kucuk\">$(kacis "$t") · insan: $(kacis "$ik") · $(kacis "$d")</div></td><td class=\"s\">$(kacis "$s")</td></tr>"
      done <<< "$SONKARAR"
      echo '</table>'
    fi
  fi
  echo '<div class="kucuk" style="margin-top:10px">🔴 Panelden <strong>aksiyon alınmaz</strong>.
İnsan onayı olmadan hiçbir karar <strong>EXECUTED</strong> olamaz (veritabanı kısıtı).
Test senaryoları bu sayımlara <strong>dahil değildir</strong>.</div></div>'
fi

# --- Ciro ---------------------------------------------------------------------
echo '<h2>Ciro · ölçüm penceresi</h2><div class="kart">'
if [ "$OLCUM_BASLADI" -eq 1 ]; then
  cat <<HTML
<div class="sr"><div><span class="et">Doğrulanmış</span>
<div class="kucuk">PayTR ile tahsil edildi · $AD_DOGR sipariş</div></div>
<div class="dg buyuk yesil">₺$(tl "$TL_DOGR")</div></div>
<div class="sr"><div><span class="et">Beyan edilmiş</span>
<div class="kucuk">Çevrim dışı / kapıda · elle işaretlendi · $AD_BEYAN sipariş</div></div>
<div class="dg buyuk sari">₺$(tl "$TL_BEYAN")</div></div>
<div class="sr"><div><span class="et">WhatsApp / telefon</span>
<div class="kucuk">BasitKargo kapıda ödeme · Wix kaydı yok · $GON_ELLE gönderi</div></div>
<div class="dg buyuk sari">₺$(tl "$TL_ELLE_TAHSIL")</div></div>
<div class="sr"><span class="et">Ödeme bekleyen</span><span class="dg">₺$(tl "$TL_BEKLEYEN") · $AD_ODENMEDI sipariş</span></div>
<div class="sr"><span class="et">Kapıda tahsilat bekleyen</span><span class="dg">₺$(tl "$TL_ELLE_BEKLEYEN")</span></div>
<div class="sr"><span class="et">İptal</span><span class="dg sol">$AD_IPTAL sipariş</span></div>
HTML
else
  echo '<div class="sr"><span class="et">Doğrulanmış (PayTR)</span><span class="dg sol">—</span></div>'
  echo '<div class="sr"><span class="et">Beyan edilmiş</span><span class="dg sol">—</span></div>'
fi
cat <<'HTML'
<div class="kucuk" style="margin-top:10px">🔴 Bu iki rakam <strong>bilerek ayrı</strong>.
Toplanıp tek &ldquo;ciro&rdquo; gösterilseydi, doğrulanmamış para doğrulanmış gibi görünürdü.
Toplamak isteyen ikisini görerek toplar.</div></div>
HTML

# --- Reklam ve verimlilik -----------------------------------------------------
echo '<h2>Reklam</h2><div class="kart">'
echo "<div class=\"sr\"><span class=\"et\">Harcama (ölçüm penceresi)</span><span class=\"dg\">$(olc_tl "$TL_REKLAM")</span></div>"
# 🔴 HAZIRLIK KAPISI (CR-012).  Bagimsiz denetimin en sert cumlesi:
#      "PARTIAL yazsa bile insan ekranda 4,8 gordugunde 4,8'i HATIRLAR."
#    Onceki hali sayiyi gosterip yanina uyari koyuyordu. Yetmez.
#    3 Meta hesabinin 1'i bagli - eksik harcama ROAS'i YUKARI sisirir.
#    Kosullar saglanmadikca SAYI URETILMEZ; yerine EKSIGIN ADI yazilir.
if [ "$KARAR_HAZIR" = "t" ]; then
  echo "<div class=\"sr\"><div><span class=\"et\">Karma ROAS · doğrulanmış</span><div class=\"kucuk\">doğrulanmış ciro ÷ harcama</div></div><span class=\"dg\">$ROAS_DOGR</span></div>"
  echo "<div class=\"sr\"><div><span class=\"et\">Karma ROAS · beyan dahil</span><div class=\"kucuk\">iki ciro toplamı ÷ harcama</div></div><span class=\"dg\">$ROAS_TUM</span></div>"
else
  echo '<div class="sr"><div><span class="et">Karma ROAS</span>
<div class="kucuk">karar metriği olarak <strong>gösterilmiyor</strong></div></div>
<div class="dg sol">PARTIAL</div></div>'
  echo '<div class="kucuk" style="margin-top:8px">Bir oranın gösterilebilmesi için
payının ve paydasının <strong>tam</strong> olması gerekir. Şu an değil:</div>'
  # 🔴 P0 KAPISI AYRI VE ONCE GOSTERILIR. Digerleri "oran eksik olabilir"
  #    der; bunlar "oranin yonu bile bilinemez" der. Ayni tabloya karisirsa
  #    ikisi ayni agirlikta okunur, oysa degiller.
  if [ "$P0_GECTI" != "t" ]; then
    echo '<div class="sr" style="margin-top:8px"><div><span class="et kirmizi">
Ölçüm temeli kurulmadı (P0)</span><div class="kucuk">Takvim hazırlık değildir:
1 Ekim gelse bile bunlar kapanmadan ROAS <strong>karar metriği yapılmaz</strong>,
çünkü çıkacak sayının hangi yöne yanlış olduğu bilinemez.</div></div></div><table>'
    P0SAT=$(sorgu <<'SQL'
SELECT anahtar, CASE WHEN gecti THEN 't' ELSE 'f' END, left(detay,70)
  FROM mart.gunluk_hazirlik WHERE kapi='P0' ORDER BY sira;
SQL
)
    while IFS='|' read -r pk pg pd; do
      [ -z "$pk" ] && continue
      case "$pk" in
        manual_order_capture_complete)  pad="WhatsApp/telefon siparişleri sisteme giriliyor" ;;
        sample_classification_explicit) pad="Numune AÇIKÇA işaretli (varsayımla değil)" ;;
        gonderi_sinifi_biliniyor)       pad="Her gönderinin sınıfı biliniyor (numune/satış ayrımı)" ;;
        *)                              pad="$pk" ;;
      esac
      if [ "$pg" = "t" ]; then
        echo "<tr><td>$(kacis "$pad")<div class=\"kucuk\">$(kacis "$pd")</div></td><td class=\"s yesil\">tamam</td></tr>"
      else
        echo "<tr><td><strong>$(kacis "$pad")</strong><div class=\"kucuk\">$(kacis "$pd")</div></td><td class=\"s kirmizi\">eksik</td></tr>"
      fi
    done <<< "$P0SAT"
    echo '</table><div class="kucuk" style="margin-top:6px">Günlük kontrol:
<code>ssh lcarlie "/opt/lcarlie/hazirlik-gunluk.sh"</code></div>'
  fi
  echo '<table>'
  # 🔴 Kosul adlari SQL'de kod formatinda (OLCUM_BASLADI); panel sahibin
  #    okudugu sayfadir, kod adi degil Turkce cumle gosterilir.
  #    Eslesmeyen bir ad gelirse ham hali yazilir - sessizce gizlenmez.
  while IFS='|' read -r ks sg dt; do
    [ -z "$ks" ] && continue
    case "$ks" in
      OLCUM_BASLADI)        ad="Ölçüm penceresi açıldı" ;;
      REKLAM_HARCAMASI_TAM) ad="Reklam harcamasının tamamı bağlı" ;;
      SIPARIS_KAYDI_TAM)    ad="Tüm siparişler Wix'e girilmiş" ;;
      CIRO_TANIMI_GECERLI)  ad="KDV okunabiliyor (net ciro hesaplanabilir)" ;;
      GONDERI_SINIFLANDI)   ad="Her gönderi sınıflandırılmış" ;;
      *)                    ad="$ks" ;;
    esac
    if [ "$sg" = "t" ]; then
      echo "<tr><td>$(kacis "$ad")<div class=\"kucuk\">$(kacis "$dt")</div></td><td class=\"s yesil\">tamam</td></tr>"
    else
      echo "<tr><td><strong>$(kacis "$ad")</strong><div class=\"kucuk\">$(kacis "$dt")</div></td><td class=\"s kirmizi\">eksik</td></tr>"
    fi
  done <<< "$HAZIRLIK"
  echo '</table>'
fi
# 🔴 ROAS'IN YANINDA "CIRO EKSIK OLABILIR" UYARISI (1 Ekim provasinda bulundu).
#    Provada panel ROAS 0,72 gosterdi - ama ayni anda 12 gonderi Wix
#    siparisiyle ESLESMIYORDU. O satislarin cirosu olcume hic girmiyor,
#    yani ROAS oldugundan DUSUK gorunuyor. Panel bu baglantiyi kurmuyordu.
#    Sahip "reklam zarar ettiriyor" diye yanlis karar verebilirdi.
#    Kural: paydasi eksik olabilen bir oran, eksikligi YAZILMADAN gosterilmez.
if [ "$OLCUM_BASLADI" -eq 1 ] && [ "${GON_ALARM:-0}" -gt 0 ]; then
  cat <<HTML
<div class="sr"><div><span class="et kirmizi">⚠ Ciro eksik ölçülüyor olabilir</span>
<div class="kucuk">$GON_ALARM gönderi Wix siparişiyle eşleşmiyor · o satışların cirosu
yukarıdaki ROAS'a <strong>girmiyor</strong>, yani ROAS olduğundan <strong>düşük</strong> görünür.
WhatsApp/telefon siparişleri Wix'e girilmedikçe bu fark sürer.</div></div></div>
HTML
fi
cat <<'HTML'
<div class="kucuk" style="margin-top:10px">🔴 Bunlar <strong>atıf değil</strong>: günün tüm cirosu ÷
günün tüm harcaması. &ldquo;Bu satışı şu reklam getirdi&rdquo; demiyor, diyemez.
Meta'nın kendi dönüşüm iddiası ayrı tutulur, bu rakamla toplanmaz.</div></div>
HTML

# --- Marj ---------------------------------------------------------------------
echo '<h2>Marj</h2><div class="kart">'
KAP_INT=${KAPSAMA%.*}
if [ "$OLCUM_BASLADI" -eq 0 ]; then
  # Olcum penceresinde hic satis yokken kapsama orani "%0" DEGILDIR -
  # hesaplanacak bir sey yoktur. "%0" yazmak "maliyetleri hic girmemisiz"
  # gibi okunur; oysa sorun olcumun henuz baslamamis olmasi.
  echo '<div class="sr"><span class="et">Brüt marj</span><span class="dg sol">—</span></div>'
  echo '<div class="sr"><span class="et">Maliyeti bilinen ciro</span><span class="dg sol">—</span></div>'
  echo '<div class="kucuk" style="margin-top:6px">Ölçüm başlayınca hesaplanır.
Aşağıdaki liste <strong>şimdiden</strong> doldurulabilir.</div>'
elif [ "${KAP_INT:-0}" -lt 50 ]; then
  cat <<HTML
<div class="sr"><div><span class="et">Maliyeti bilinen ciro</span>
<div class="kucuk">bu oran düşükken marj rakamı anlamlı değil</div></div>
<div class="dg kirmizi">%$KAPSAMA</div></div>
<div class="kucuk" style="margin-top:6px">Brüt marj <strong>gösterilmiyor</strong>:
cironun yalnızca %$KAPSAMA'sının maliyeti biliniyor. Maliyeti girilmemiş kalemin
marjı <strong>NULL</strong> — sıfır veya tahmin üretilmiyor.</div>
HTML
else
  echo "<div class=\"sr\"><span class=\"et\">Brüt marj</span><span class=\"dg buyuk\">₺$(tl "$TL_MARJ")</span></div>"
  echo "<div class=\"sr\"><span class=\"et\">Maliyeti bilinen ciro</span><span class=\"dg yesil\">%$KAPSAMA</span></div>"
fi
echo "<div class=\"sr\"><span class=\"et\">Kargo maliyeti</span><span class=\"dg\">$(olc_tl "$TL_KARGO")</span></div>"

# 🔴 KAPSAMA TEK BASINA GOSTERILMEZ (CR-012).  "%96,2 maliyet kapsamasi"
#    tehlikeli derecede iyimser bir cumle: kapsama yuksek ama 36 urunun
#    36'si ayni 400 TL TAHMINI. SKU bazinda reklam karari bu ayrim
#    olmadan verilirse yanlis urun secilir.
cat <<HTML
<div class="sr"><div><span class="et">Maliyet kalitesi</span>
<div class="kucuk">kaçının maliyeti gerçekten <strong>ölçüldü</strong></div></div>
<div class="dg $([ "${MK_OLCULMUS:-0}" -gt 0 ] && echo yesil || echo kirmizi)">$MK_OLCULMUS / $MK_TOPLAM</div></div>
HTML
if [ "${MK_TAHMIN:-0}" -gt 0 ]; then
  echo "<div class=\"kucuk\" style=\"margin-top:6px\">$MK_TAHMIN ürünün maliyeti
<strong>sahip tahmini</strong> (ortalama ₺400) — gerçek ürün maliyeti değil.
Kapsama oranı yüksek görünse de <strong>ürün bazında karlılık karşılaştırması
bu veriyle yapılamaz</strong>: hepsi aynı sayı.</div>"
fi
# 🔴 KDV: marjin hangi tabanda hesaplandigi YAZILIR. 16.09.2026'da bulundu ki
#    marj KDV DAHIL ciradan hesaplaniyordu ve %24,6 sisikti.
cat <<HTML
<div class="kucuk" style="margin-top:10px">Marj <strong>KDV hariç</strong> cirodan
hesaplanır — KDV bizim paramız değil. Ölçülen KDV oranı <strong>%20</strong>.
Maliyetin KDV tabanı: <strong>$(kacis "${MK_KDV:-TEYIT_EDILMEDI}")</strong>$([ "${MK_KDV:-}" = "TEYIT_EDILMEDI" ] && echo " — ₺400'ün KDV dahil mi hariç mi olduğu sorulmadı; KDV hariç varsayılıyor")</div>
HTML
echo '</div>'

# --- Para zinciri (CR-012) ----------------------------------------------------
# 🔴 NEDEN AYRI BOLUM: ciro ayrimimiz (dogrulanmis/beyan) VERIYE NE KADAR
#    GUVENDIGIMIZI olcuyor. Bu bolum PARANIN NEREDE oldugunu olcer.
#    Siparis verilmis olmasi teslim edildigini, teslim edilmis olmasi
#    tahsil edildigini IMA ETMEZ. Kapida odemede iade riski burada durur.
echo '<h2>Para nerede</h2><div class="kart">'
if [ "$OLCUM_BASLADI" -eq 0 ]; then
  echo '<div class="sr"><span class="et">Zincir</span><span class="dg sol">—</span></div>
<div class="kucuk" style="margin-top:8px">Ölçüm penceresi açılınca dolar.
Zincir: sipariş → kargolandı → teslim edildi → tahsil edildi → iade.</div>'
else
  echo "<div class=\"sr\"><span class=\"et\">Sipariş</span><span class=\"dg\">$P_SIP</span></div>"
  echo "<div class=\"sr\"><span class=\"et\">Kargolandı</span><span class=\"dg\">$P_KARGO</span></div>"
  echo "<div class=\"sr\"><span class=\"et\">Teslim edildi</span><span class=\"dg\">$P_TESLIM</span></div>"
  echo "<div class=\"sr\"><span class=\"et\">İade</span><span class=\"dg $([ "${P_IADE:-0}" -gt 0 ] && echo kirmizi)\">$P_IADE</span></div>"
  echo "<div class=\"sr\"><span class=\"et\">Kapıda ödeme · bekleyen</span><span class=\"dg $([ "${P_COD_BEK%%.*}" != "0" ] && echo sari)\">₺$(tl "${P_COD_BEK:-0}")</span></div>"
  echo "<div class=\"sr\"><span class=\"et\">KDV (bize ait değil)</span><span class=\"dg sol\">₺$(tl "${P_KDV:-0}")</span></div>"
  # 🔴 "Gonderi kaydi yok" ile "kargolanmadi" AYRI SEY. Ilki bilgisizlik,
  #    ikincisi olgu. Karistirmak, teslim oranini oldugundan kotu gosterir.
  if [ "${P_KAYITSIZ:-0}" -gt 0 ]; then
    echo "<div class=\"kucuk kirmizi\" style=\"margin-top:8px\">$P_KAYITSIZ siparişin
BasitKargo kaydı <strong>bulunamadı</strong> — bunlar &ldquo;kargolanmadı&rdquo;
<strong>değil</strong>, <strong>bilinmiyor</strong>. Teslim oranı bu yüzden
olduğundan düşük görünür.</div>"
  fi
fi
echo '<div class="kucuk" style="margin-top:10px">🔴 Sipariş verilmiş olması teslim edildiği,
teslim edilmiş olması tahsil edildiği anlamına <strong>gelmez</strong>.
Kart ödemesinde &ldquo;onaylı&rdquo; bilgisi Wix beyanıdır — PayTR mutabakatı
<strong>yapılmıyor</strong>.</div></div>'

if [ -n "$MALIYET" ]; then
  echo '<h2>Maliyeti girilmemiş · en çok satanlar</h2><div class="kart">'
  echo '<div class="kucuk" style="margin-bottom:10px">Bu liste <strong>tüm satış geçmişinden</strong>
gelir (ölçüm penceresiyle sınırlı değil) — böylece maliyetler 1 Ekim''den önce girilebilir.</div><table>'
  while IFS='|' read -r ad ciro kalem; do
    [ -z "$ad" ] && continue
    echo "<tr><td>$(kacis "$ad")<div class=\"kucuk\">$kalem kalem</div></td><td class=\"s\">₺$(tl "$ciro")</td></tr>"
  done <<< "$MALIYET"
  echo '</table><div class="kucuk" style="margin-top:10px">Wix → Ürünler → ürün → <strong>Maliyet</strong>
alanına gir. Sistem gerisini yapar ve değişimi tarihleyerek saklar.</div></div>'
fi

# --- Gonderi ------------------------------------------------------------------
echo '<h2>Gönderi</h2><div class="kart">'
echo "<div class=\"sr\"><span class=\"et\">Satış</span><span class=\"dg\">$(olc "$GON_SATIS")</span></div>"
echo "<div class=\"sr\"><span class=\"et\">Numune / UGC</span><span class=\"dg sol\">$(olc "$GON_NUMUNE") <span class=\"kucuk\">(pazarlama gideri, satış değil)</span></span></div>"
echo "<div class=\"sr\"><span class=\"et\">İade</span><span class=\"dg sol\">$(olc "$GON_IADE")</span></div>"
if [ "${GON_BILINMEYEN:-0}" -gt 0 ]; then
  # 🔴 ESKIDEN BURADA "Varsayilan numune" YAZIYORDU. Yaziyi degil KURALI
  #    degistirdik: isaret yoksa artik numune VARSAYILMIYOR, UNKNOWN deniyor.
  #    Havale/EFT ile alinmis bir telefon siparisi de bu dala duser - onu
  #    numune saymak, bir SATISI pazarlama gideri diye okumak demekti.
  #    Panel artik ne oldugunu soylemiyor; BILINMEDIGINI soyluyor.
  echo "<div class=\"sr\"><div><span class=\"et sari\">Sınıfı bilinmeyen</span><div class=\"kucuk\">Ne olduğu belirlenemedi - numune de olabilir, havale/EFT ile alınmış satış da. Varsayım yapılmıyor; kargosu gidere yazılır, cirosu sayılmaz</div></div><span class=\"dg sari\">$(olc "$GON_BILINMEYEN")</span></div>"
fi
if [ "${GON_ALARM:-0}" -gt 0 ]; then
  echo "<div class=\"sr\"><span class=\"et kirmizi\">Yönü bilinmeyen</span><span class=\"dg kirmizi\">$GON_ALARM</span></div>"
fi
echo '</div>'

# --- Konusma ------------------------------------------------------------------
echo '<h2>Konuşma</h2><div class="kart">'
if [ "${KON_CEVAPSIZ:-0}" -gt 0 ]; then
  echo "<div class=\"sr\"><div><span class=\"et kirmizi\">Cevapsız müşteri mesajı</span><div class=\"kucuk\">24 saati geçmiş · en eskisi ${KON_EN_ESKI} gündür bekliyor</div></div><span class=\"dg buyuk kirmizi\">$KON_CEVAPSIZ</span></div>"
else
  echo '<div class="sr"><span class="et">Cevapsız müşteri mesajı</span><span class="dg yesil">yok</span></div>'
fi
echo "<div class=\"sr\"><span class=\"et\">Yeni konuşma (ölçüm penceresi)</span><span class=\"dg\">$(olc "${KON_YENI:-0}")</span></div>"
echo "<div class=\"sr\"><span class=\"et\">Gelen mesaj</span><span class=\"dg\">$(olc "${KON_GELEN:-0}")</span></div>"
cat <<'HTML'
<div class="kucuk" style="margin-top:10px">🔴 Konuşma sayısı ile satış arasında
<strong>bağ kurulamıyor</strong>: Messenger müşteriyi Meta'ya özel bir kimlikle (PSID)
tanır, Wix'te karşılığı yok. Ad eşleştirmesi denendi — <strong>sıfır</strong> tam eşleşme.
Bu rakamlar hacim ölçer, <strong>atıf değildir</strong>.</div></div>
HTML

# --- Acik isler ---------------------------------------------------------------
echo '<h2>Açık işler</h2>'
# 🔴 SIRA DUZELTILDI (CR-011): once LISTE DOLU MU diye bakilir.
#    Onceki hali once "olcum basladi mi" soruyordu ve olcum baslamadan
#    listeyi "—" gosteriyordu. Ama cevapsiz musteri mesaji OLCUM
#    PENCERESINE BAGLI DEGIL - bugun cevaplanmali, 1 Ekim'i beklemez.
#    Sonuc: panelde 10 cevapsiz mesaj varken "Bekleyen is —" yaziyordu,
#    yani panel KENDI VERISIYLE CELISIYORDU.
if [ -n "$ISLER" ]; then
  echo '<div class="kart"><table>'
  while IFS='|' read -r tur adet yap; do
    [ -z "$tur" ] && continue
    echo "<tr><td><strong>$(kacis "$tur")</strong><div class=\"kucuk\">$(kacis "$yap")</div></td><td class=\"s sari\">$adet</td></tr>"
  done <<< "$ISLER"
  echo '</table></div>'
  if [ "$OLCUM_BASLADI" -eq 0 ]; then
    # 🔴 Liste dolu ama TAM DEGIL: dallarin cogu olcum penceresine bagli
    #    ve o pencere henuz acilmadi. "Gorunen hepsi" sanilmasin.
    echo '<div class="kucuk" style="margin-top:-6px">Bu liste <strong>eksiktir</strong>:
ölçüm penceresine bağlı dallar (ödenmemiş sipariş, sınıflandırılmamış gönderi,
maliyeti girilmemiş ürün…) 1 Ekim&rsquo;e kadar <strong>hiç bakılmaz</strong>.
Burada yalnızca ölçümden bağımsız işler var.</div>'
  fi
elif [ "$OLCUM_BASLADI" -eq 0 ]; then
  # 🔴 BOS LISTE YESIL GOSTERILMEZ.  Acik islerin cogu olcum penceresine bagli;
  #    olcum baslamadan o dallar ZORUNLU OLARAK bos olur. Bunu yesil "yok"
  #    diye gostermek, CR-002'de duzelttigimiz "trafik yoksa hata da yok,
  #    demek ki saglikli" yanilsamasinin aynisidir. Notr gosterilir.
  echo '<div class="kart"><div class="sr"><span class="et">Bekleyen iş</span><span class="dg sol">—</span></div>
<div class="kucuk" style="margin-top:8px">Açık işlerin çoğu ölçüm penceresine bakar; ölçüm
başlamadığı için o dallar <strong>zorunlu olarak boş</strong>. Bu &ldquo;iş yok&rdquo; demek
<strong>değil</strong> — henüz bakılacak dönem yok. Ölçümden bağımsız iş de
(cevapsız mesaj gibi) şu an yok.</div></div>'
else
  echo '<div class="kart"><div class="sr"><span class="et">Bekleyen iş</span><span class="dg yesil">yok</span></div>
<div class="kucuk" style="margin-top:8px">Boş olması <strong>iş yok</strong> demektir, hata değil.</div></div>'
fi

# --- Kaynak sagligi -----------------------------------------------------------
echo '<h2>Kaynaklar</h2><div class="kart"><table>'
while IFS='|' read -r kay dur zaman saat; do
  [ -z "$kay" ] && continue
  case "$dur" in
    SUCCESS) rozet='<span class="rozet r-ok">SUCCESS</span>' ;;
    NO_DATA) rozet='<span class="rozet r-yok">VERİ YOK</span>' ;;
    PARTIAL) rozet='<span class="rozet r-yok">KISMİ</span>' ;;
    *)       rozet='<span class="rozet r-hata">HATA</span>' ;;
  esac
  # 🔴 Bayat kaynak da uyaridir: "SUCCESS" ama 30 saat once ise hat durmus olabilir.
  ek=""
  awk -v s="$saat" 'BEGIN{exit !(s+0>30)}' && ek='<div class="kucuk kirmizi">30 saatten eski — hat durmuş olabilir</div>'
  echo "<tr><td>$(kacis "$kay")<div class=\"kucuk\">$(kacis "$zaman") · ${saat} saat önce</div>$ek</td><td class=\"s\">$rozet</td></tr>"
done <<< "$KAYNAK"
echo '</table></div>'

# --- Olcum oncesi referans ----------------------------------------------------
cat <<HTML
<h2>Ölçüm öncesi · referans</h2><div class="kart">
<div class="sr"><span class="et">Doğrulanmış</span><span class="dg sol">₺$(tl "${ONC_DOGR:-0}")</span></div>
<div class="sr"><span class="et">Beyan edilmiş</span><span class="dg sol">₺$(tl "${ONC_BEYAN:-0}")</span></div>
<div class="sr"><span class="et">Sipariş</span><span class="dg sol">${ONC_ADET:-0}</span></div>
<div class="sr"><span class="et">Kayıtlı müşteri</span><span class="dg sol">$MUSTERI</span></div>
<div class="kucuk" style="margin-top:10px">🔴 Bu rakamlar <strong>ölçüm dışıdır</strong> ve
ROAS/marj hesabına girmez. O dönemde WhatsApp ve telefon siparişleri Wix'e
girilmiyordu, yani <strong>ciro eksik</strong>. Eksik ciroyla hesaplanan oran gerçek değildir.</div>
</div>
HTML

cat <<HTML
<p class="dn">Ticari ayna · CR-004…CR-007<br>
Kaynaklar günde bir kez 08:30'da tazelenir · bu sayfa her tazelemeden sonra üretilir</p>
<script>
(function(){
  // 🔴 Sayfanin kendi tazeligi TARAYICIDA kontrol edilir. Panel ureticisi
  //    olurse sunucu tarafinda bunu fark edecek kimse yok; sayfayi acan
  //    kisi yine de bayat veriye bakmamali.
  var u = $URETIM_EPOCH * 1000, dk = (Date.now() - u) / 60000;
  if (dk > 90) document.getElementById('bayat').style.display = 'block';
})();
</script>
</body></html>
HTML
} > "$WEB/$SAYFA.yeni"

# 🔴 ONCE gecici dosyaya yaz, SONRA tasi. Betik yarida kalirsa panel
#    yarim HTML gostermez; eski (bayat ama tutarli) hali durur.
if [ -s "$WEB/$SAYFA.yeni" ]; then
  mv "$WEB/$SAYFA.yeni" "$WEB/$SAYFA"
  chmod 644 "$WEB/$SAYFA"
  echo "Ticari panel yazildi: $WEB/$SAYFA ($(wc -c < "$WEB/$SAYFA") bayt)"
else
  rm -f "$WEB/$SAYFA.yeni"
  echo "HATA: panel bos uretildi, eski hali korundu." >&2
  exit 1
fi

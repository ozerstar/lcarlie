from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from time import perf_counter
from typing import Any


class MemoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class Evidence:
    source: str
    authority: str
    retrieved_at: str
    records: list[dict[str, Any]]
    latency_ms: float


class CompanyMemory:
    """Fixed-query adapter. User/model text is never interpolated into SQL."""

    QUERIES = {
        "system": "SELECT core.ai_orchestrator_health();",
        "agenda": (
            "SELECT row_to_json(x) FROM (SELECT soru_id,hedef,oncelik,soru,"
            "neden_onemli,kaynak_plani,durum,olusturma FROM mart.sirket_gundemi "
            "ORDER BY olusturma DESC LIMIT 25) x;"
        ),
        "open_work": (
            "SELECT row_to_json(x) FROM (SELECT tur,anahtar,detay,zaman,yapilacak "
            "FROM mart.acik_isler ORDER BY zaman DESC LIMIT 25) x;"
        ),
        "decision_summary": "SELECT row_to_json(x) FROM (SELECT * FROM mart.karar_ozet) x;",
        "capabilities": "SELECT core.ai_get_model_policy();",
        "company_dashboard": (
            "SELECT row_to_json(x) FROM (SELECT * FROM "
            "mart.ai_company_intelligence_dashboard) x;"
        ),
        # Phase 2D / F-1: the canonical action contract. Only the six columns
        # ai_reader is granted are named; `description` and `created_at` are
        # deliberately absent and would be denied.
        "action_contract": (
            "SELECT row_to_json(x) FROM (SELECT action_type,risk_class,"
            "approval_mode,proposal_enabled,execution_enabled,schema_version "
            "FROM core.ai_action_type ORDER BY action_type) x;"
        ),
        # Phase 2D / F-2: infrastructure facts for the capability registry.
        # pg_catalog only -- readable by PUBLIC, and unlike
        # information_schema it is not filtered by the caller's privileges,
        # so a missing EXECUTE grant cannot masquerade as a missing function.
        "capability_state": (
            "SELECT row_to_json(x) FROM (SELECT "
            "(SELECT extversion FROM pg_extension WHERE extname='vector') "
            "AS pgvector_version,"
            "(SELECT count(*) FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname='ai_semantic' "
            "AND c.relname='memory_embedding') AS semantic_table,"
            "(SELECT count(*) FROM pg_indexes WHERE schemaname='ai_semantic') "
            "AS semantic_indexes,"
            "(SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
            "ON n.oid=p.pronamespace WHERE n.nspname='core' AND p.proname IN "
            "('ai_save_jarvis_task_state','ai_load_jarvis_task_state')) "
            "AS state_functions,"
            "(SELECT core.ai_orchestrator_health()) AS health) x;"
        ),

        # ------------------------------------------------------------------
        # Company data fabric. Every column below exists in the named view --
        # nothing is computed here that the source does not already carry.
        # Each row leads with the canonical entity id, the source relation and
        # the source record id so a finding can always be traced back.
        # ------------------------------------------------------------------
        "provenance": (
            "SELECT row_to_json(x) FROM (SELECT alan AS entity_id,"
            "'core.source_authority' AS source,alan AS source_record_id,"
            "dogrulama_zamani AS observed_at,authority,freshness,"
            "current_connection,dogrulama_yontemi "
            "FROM core.source_authority ORDER BY alan) x;"
        ),
        "data_quality": (
            "SELECT row_to_json(x) FROM (SELECT check_name AS entity_id,"
            "'mart.ai_data_quality_gate' AS source,check_name AS source_record_id,"
            "checked_at AS observed_at,passed,detail "
            "FROM mart.ai_data_quality_gate ORDER BY check_name) x;"
        ),

        # --- sales (ai_reader already held these grants) -------------------
        "sales_orders": (
            "SELECT row_to_json(x) FROM (SELECT siparis_id AS entity_id,"
            "'mart.siparis' AS source,siparis_no AS source_record_id,"
            "olusturma AS observed_at,gun,kanal,odeme_durumu,odeme_yontemi,"
            "teslimat_durumu,toplam,toplam_kdv_haric,kdv,ciro_sinifi,"
            "ciro_dogrulanmis_net,ciro_beyan_edilmis_net,tutar_bekleyen,"
            "tutar_bilinmiyor,olcumde,customer_id "
            "FROM mart.siparis ORDER BY olusturma DESC LIMIT 50) x;"
        ),
        "sales_items": (
            "SELECT row_to_json(x) FROM (SELECT siparis_id AS entity_id,"
            "'mart.siparis_kalem' AS source,sku AS source_record_id,"
            "olusturma AS observed_at,gun,urun_id,urun_adi,adet,birim_fiyat,"
            "indirim,satir_ciro_net,birim_maliyet,satir_maliyet,brut_marj,"
            "maliyeti_biliniyor,olcumde "
            "FROM mart.siparis_kalem ORDER BY olusturma DESC LIMIT 100) x;"
        ),

        # --- advertising (migration 005) -----------------------------------
        "advertising_performance": (
            "SELECT row_to_json(x) FROM (SELECT ad_id AS entity_id,"
            "'mart.reklam_performans' AS source,ad_id AS source_record_id,"
            "pencere,ad_adi,kampanya_adi,adset_adi,harcama,gosterim,erisim,"
            "tiklama,link_tiklama,ctr_yuzde,cpc,cpm,etkin_durum,"
            "meta_satis_iddiasi,meta_gelir_iddiasi,meta_conversion_signal,"
            "commercial_confirmation,kapsama "
            "FROM mart.reklam_performans ORDER BY harcama DESC NULLS LAST LIMIT 50) x;"
        ),
        "advertising_spend": (
            "SELECT row_to_json(x) FROM (SELECT kampanya_id AS entity_id,"
            "'mart.harcama' AS source,kampanya_id AS source_record_id,"
            "gun AS observed_at,hesap_id,hesap_adi,kampanya_adi,kaynak,harcama,"
            "gosterim,tiklama,link_tiklama,meta_donusum,meta_donusum_degeri,olcumde "
            "FROM mart.harcama ORDER BY gun DESC LIMIT 60) x;"
        ),

        # --- e-commerce (migration 005) ------------------------------------
        "ecommerce_profitability": (
            "SELECT row_to_json(x) FROM (SELECT urun_id AS entity_id,"
            "'mart.urun_karlilik' AS source,sku AS source_record_id,"
            "urun_adi,kalem,adet,ciro,ciro_net,maliyet,brut_marj,"
            "brut_marj_yuzde,maliyeti_bilinen_kalem,kapsama_yuzde "
            "FROM mart.urun_karlilik ORDER BY ciro_net DESC NULLS LAST LIMIT 40) x;"
        ),
        "ecommerce_price": (
            "SELECT row_to_json(x) FROM (SELECT urun_id AS entity_id,"
            "'mart.fiyat_gercegi' AS source,urun_id AS source_record_id,"
            "urun_adi,base_price,kampanya_fiyati,fiyat_durumu,wix_liste,"
            "wix_satis,wix_yayinda,musteriye_soylenecek_fiyat,durum,aciklama,fiyat_kaynagi "
            "FROM mart.fiyat_gercegi ORDER BY urun_id LIMIT 40) x;"
        ),
        # --- finans (20.09.2026) -------------------------------------------
        # 🔴 NEDEN SONRADAN EKLENDI: roster'daki "Finans Uzmani" ve "Muhasebe
        # Kontrol" uyeleri 'financial' adli bir sorgu okuyordu ve o sorgu bu
        # sozlukte HIC YOKTU. Ikisi de yapisal olarak sessizdi: kadroda
        # gorunuyor, veriden tek cumle kuramiyorlardi. Veri hep vardi
        # (mart.ekonomi_gunluk 60 satir, mart.nakit_gunluk 75 satir); eksik
        # olan sey baglantiydi. ai_reader'a SELECT yetkisi de ayni gun verildi
        # -- oncesinde iki gorunumde de hicbir yetkisi yoktu.
        #
        # Ikisi AYRI sorgu cunku iki uyenin isi ayri: biri birim ekonomiye
        # (katki, reklam sonrasi kar) bakar, digeri kaydin TUTARLILIGINA
        # (tahsil edilmemis, cogs kalitesi, hesap kapsamasi) bakar.
        "financial": (
            "SELECT row_to_json(x) FROM (SELECT gun AS entity_id,"
            "'mart.ekonomi_gunluk' AS source,gun::text AS source_record_id,"
            "gun AS observed_at,siparis,gerceklesmis_siparis,net_ciro,"
            "dogrulanmis_katki,katki_ust_siniri,reklam_harcamasi,"
            "reklam_sonrasi_katki,ekonomi_tamlik_yuzde,ekonomi_durumu "
            "FROM mart.ekonomi_gunluk ORDER BY gun DESC LIMIT 30) x;"
        ),
        "financial_cash": (
            "SELECT row_to_json(x) FROM (SELECT gun AS entity_id,"
            "'mart.nakit_gunluk' AS source,gun::text AS source_record_id,"
            "gun AS observed_at,siparis,brut_ciro,net_ciro,"
            "tahsil_beyan_edilen,tahsil_edilmemis,bilinen_cogs,cogs_kalite,"
            "cogs_olculmus_yuzde,meta_hesap_kapsamasi,ciro_harcama_orani,"
            "nakit_durum FROM mart.nakit_gunluk ORDER BY gun DESC LIMIT 30) x;"
        ),

        "gunluk_brief": (
            "SELECT row_to_json(x) FROM (SELECT b.brief_key AS entity_id,"
            "'mart.gunluk_brief' AS source,b.brief_key AS source_record_id,"
            "b.brief_key,b.provider,b.model,b.created_at,"
            "b.konu,b.icerik,b.kimden,b.kime,b.durum "
            "FROM mart.gunluk_brief b LIMIT 5) x;"
        ),
        "kreatif_performans": (
            "SELECT row_to_json(x) FROM (SELECT ad_id AS entity_id,"
            "'mart.kreatif_performans' AS source,ad_id AS source_record_id,"
            "ad_id,ad_adi,etkin_durum,bicim,cta,baslik,left(govde,160) AS govde,"
            "video_mu,gun_sayisi,harcama,gosterim,tiklama,link_tiklama,"
            "ctr,link_ctr,link_basi_maliyet,cpm,en_yuksek_frekans,"
            "yeterli_ornek,olcum_durumu "
            "FROM mart.kreatif_performans ORDER BY gosterim DESC NULLS LAST) x;"
        ),
        # --- kreatif ve marka (20.09.2026) ---------------------------------
        # Sahip talebi: "kreatif ekibi ve brand tarafini da aktif et, ekip
        # sayisini arttir, farkli fikirler istiyorum." Yeni uye eklemenin
        # sarti VERI: kaynagi olmayan uye "girdi bekler" diyen bir isimden
        # ibaret kalir ve paneli doldurup hicbir sey soylemez.
        "creative_decisions": (
            "SELECT row_to_json(x) FROM (SELECT ad_id AS entity_id,"
            "'mart.kreatif_karar' AS source,ad_id AS source_record_id,"
            "pencere,reklam,kampanya,harcama,gosterim,tiklama,ctr_yuzde,cpc,"
            "attention,meta_conversion_signal,commercial_confirmation,etiket,not_ "
            "FROM mart.kreatif_karar ORDER BY harcama DESC NULLS LAST LIMIT 60) x;"
        ),
        "creative_hypotheses": (
            "SELECT row_to_json(x) FROM (SELECT kod AS entity_id,"
            "'mart.kreatif_hipotez' AS source,kod AS source_record_id,"
            "kod,hipotez,kanit,adet,toplam,yuzde,kanit_kaynagi,beklenen_etki,"
            "risk,yanlislama,olcum_yontemi FROM mart.kreatif_hipotez ORDER BY kod) x;"
        ),
        # 🔴 'ornekler' KOLONU BILEREK YOK. O kolon musteri mesajlarinin
        # kendisini tasiyor; ai_reader'a sutun duzeyinde de kapatildi
        # (SELECT denemesi "permission denied" ile reddediliyor, olculdu).
        # Marka icgorusu icin toplam sayilar yeterli -- ham mesaj PII sinirinin
        # otesinde kalir.
        "customer_voice": (
            "SELECT row_to_json(x) FROM (SELECT konu AS entity_id,"
            "'mart.soru_konu' AS source,konu AS source_record_id,"
            "konu,aciklama,distinct_konusma,eslesen_mesaj,konusma_yuzde,"
            "olcum_yontemi FROM mart.soru_konu ORDER BY konusma_yuzde DESC) x;"
        ),
        # Organik Instagram icerigi (20.09.2026). CONTENT/SOCIAL/ART
        # departmanlarinin veri kaynagi YOKTU; reklam olculuyor, organik taraf
        # hic okunmuyordu. 123 gonderi, 26.11.2025'ten beri.
        # 🔴 ERISIM/GOSTERIM YOK: insights ucu "(#10) permission" ile reddediliyor,
        #    o yuzden ETKILESIM bir SAYIDIR, oran degil. 'olcum_siniri' alani
        #    bunu her satirda tasir ve cevaplarda gizlenmez.
        "content_performance": (
            "SELECT row_to_json(x) FROM (SELECT medya_id AS entity_id,"
            "'mart.icerik_performans' AS source,medya_id AS source_record_id,"
            "gun AS observed_at,bicim,tur,icerik_basi,icerik_uzunluk,etiket_sayisi,"
            "reklam_ibaresi,yz_beyani,begeni,yorum,etkilesim,olcum_siniri "
            "FROM mart.icerik_performans ORDER BY zaman DESC LIMIT 130) x;"
        ),
        "market_research": (
            "SELECT row_to_json(x) FROM (SELECT kod AS entity_id,"
            "'mart.pazar_arastirma' AS source,kod AS source_record_id,"
            "kod,seviye,bulgu,kaynak,tarih,yorum FROM mart.pazar_arastirma "
            "ORDER BY tarih DESC NULLS LAST) x;"
        ),

        "urun_karti": (
            "SELECT row_to_json(x) FROM (SELECT urun_id AS entity_id,"
            "'mart.urun_karti' AS source,urun_id AS source_record_id,"
            "urun_id,urun_adi,sku,left(aciklama_duz,400) AS aciklama_duz,"
            "wix_satis,wix_liste,wix_stok,wix_yayinda,wix_gorsel,"
            "trendyolda_var,trendyol_satis,trendyol_stok,"
            "birim_maliyet,maliyet_kaynagi,satilan_adet,ciro,satis_marj_yuzde,"
            "platform_sayisi,fiyat_ozeti,en_dusuk_marj,farkli_alan "
            "FROM mart.urun_karti ORDER BY urun_adi) x;"
        ),
        # Musteriye cevap yazarken gereken TAM urun metni.
        #
        # NEDEN AYRI BIR SORGU: "urun_karti" aciklamayi left(...,400) ile
        # kesiyor ve panel icin bu dogru -- ama ICINDEKILER listesi metnin
        # SONUNDA duruyor, yani 400 karakterde her zaman kesiliyor. Olculdu
        # (20.09.2026): 540 musteri mesajinin 166'si icindekileri soruyor,
        # yani en sik ikinci soru. Kesik metinle o soru dogru cevaplanamaz.
        #
        # Guvenlik yuzeyi GENISLEMEDI: ayni tablo, ayni kolonlar, ayni
        # ai_reader yetkisi -- yalnizca kirpma kalkti.
        "urun_bilgi": (
            "SELECT row_to_json(x) FROM (SELECT urun_id AS entity_id,"
            "'mart.urun_karti' AS source,urun_id AS source_record_id,"
            "urun_id,urun_adi,sku,aciklama_duz,"
            "wix_satis,wix_liste,wix_stok,wix_yayinda,"
            "trendyolda_var,trendyol_satis "
            "FROM mart.urun_karti ORDER BY urun_adi) x;"
        ),
        # Öğrenme döngüsünün baktığı tek yer. Oran GÖRÜNÜMDE hesaplanıyor
        # ki panel ile döngü iki farklı sayı söylemesin.
        "satis_kohort": (
            "SELECT row_to_json(x) FROM (SELECT "
            "coalesce(yaklasim_id::text,'0') AS entity_id,"
            "'mart.satis_kohort' AS source,"
            "coalesce(yaklasim_id::text,'0') AS source_record_id,"
            "son_gonderim AS observed_at,"
            "yaklasim_id,yaklasim_surum,yaklasim_durum,urun,soru_tipi,"
            "gonderilen,donus_var,donus_yok,pencere_acik,donus_yuzde,"
            "olcum_durumu,ilk_gonderim,son_gonderim,ort_donus_sn "
            "FROM mart.satis_kohort ORDER BY gonderilen DESC) x;"
        ),
        "satis_yaklasim": (
            "SELECT row_to_json(x) FROM (SELECT id AS entity_id,"
            "'lcarlie.satis_yaklasim' AS source,id AS source_record_id,"
            "olusturma AS observed_at,"
            "id,surum,urun,soru_tipi,yonerge,gerekce,durum,olusturan,"
            "onaylayan,onay_zamani,olusturma "
            "FROM lcarlie.satis_yaklasim ORDER BY surum DESC,id DESC) x;"
        ),
        "urun_alan_karsilastirma": (
            "SELECT row_to_json(x) FROM (SELECT urun_id AS entity_id,"
            "'mart.urun_alan_karsilastirma' AS source,urun_id AS source_record_id,"
            "urun_id,urun_adi,sku,content_id,sira,alan,grup,"
            "wix_deger,trendyol_deger,wix_yazilabilir,trendyol_yazilabilir,durum "
            "FROM mart.urun_alan_karsilastirma "
            "ORDER BY urun_adi,sira) x;"
        ),
        "platform_fiyat_matrisi": (
            "SELECT row_to_json(x) FROM (SELECT urun_id AS entity_id,"
            "'mart.platform_fiyat_matrisi' AS source,urun_id AS source_record_id,"
            "urun_id,urun_adi,platform_kod,platform_adi,platform_aktif,"
            "yazma_izni,komisyon_yuzde,komisyon_istisnasi,kdv_yuzde,"
            "referans_fiyat,referans_kaynagi,platform_fiyati,gecerli_fiyat,"
            "yontem,fark_durumu,fark_yuzde,birim_maliyet,maliyet_kaynagi,"
            "komisyon_tutari,net_kdvsiz,marj,marj_yuzde,marj_uyari "
            "FROM mart.platform_fiyat_matrisi "
            "ORDER BY urun_adi,platform_kod) x;"
        ),
        "ecommerce_funnel": (
            "SELECT row_to_json(x) FROM (SELECT ust_kod||'>'||alt_kod AS entity_id,"
            "'mart.funnel_orani' AS source,alt_kod AS source_record_id,"
            "ust_ad,alt_ad,oran_yuzde,oran_durumu,dusus_yuzde,ifade "
            "FROM mart.funnel_orani ORDER BY ust_kod,alt_kod) x;"
        ),

        # --- crm (musteri via migration 005; konusma_cevapsiz already held) -
        # PII minimisation: lcarlie.konusma / lcarlie.mesaj carry customer
        # names and raw message text and are deliberately NOT queried. These
        # two expose identifiers, counts and a pseudonym only.
        "crm_customers": (
            "SELECT row_to_json(x) FROM (SELECT customer_id AS entity_id,"
            "'mart.musteri' AS source,customer_id AS source_record_id,"
            "son_siparis AS observed_at,identity_status,match_method,"
            "siparis_olcumde,siparis_tum_zaman,ciro_dogrulanmis,"
            "ciro_beyan_edilmis,ilk_siparis "
            "FROM mart.musteri ORDER BY son_siparis DESC NULLS LAST LIMIT 50) x;"
        ),
        "crm_unanswered": (
            "SELECT row_to_json(x) FROM (SELECT konusma_id AS entity_id,"
            "'mart.konusma_cevapsiz' AS source,konusma_id AS source_record_id,"
            "son_mesaj AS observed_at,gun,kanal,musteri_takma,mesaj_sayisi,"
            "bekleme_saat FROM mart.konusma_cevapsiz "
            "ORDER BY bekleme_saat DESC NULLS LAST LIMIT 50) x;"
        ),

        # --- operations (ai_reader already held this grant) -----------------
        # --- ogrenme: gecmis kararlarin sonucu ---------------------------
        # Bu uc gorunum ai_reader'a ZATEN acikti (olculdu); yeni grant
        # gerekmedi. Jarvis'in KENDI onerileri (core.ai_action_proposal)
        # hala kapali -- ogrenme dongusunun o yarisi ayri bir izin isi.
        "decision_outcomes": (
            "SELECT row_to_json(x) FROM (SELECT karar_id AS entity_id,"
            "'mart.ai_human_approval_dashboard' AS source,"
            "karar_id AS source_record_id,olusturma AS observed_at,"
            "karar_tipi,durum,onay_hazirligi,red_team_sonucu,kanit_kalitesi,"
            "kanal,urun FROM mart.ai_human_approval_dashboard "
            "ORDER BY olusturma DESC LIMIT 200) x;"
        ),
        "learning_loop": (
            "SELECT row_to_json(x) FROM (SELECT provider AS entity_id,"
            "'mart.ai_learning_loop' AS source,model AS source_record_id,"
            "provider,model,karar_sayisi,olumlu,olumsuz,basari_orani,"
            "is_puani,deneme FROM mart.ai_learning_loop "
            "ORDER BY karar_sayisi DESC NULLS LAST) x;"
        ),
        "evidence_readiness": (
            "SELECT row_to_json(x) FROM (SELECT karar_id AS entity_id,"
            "'mart.ai_evidence_readiness' AS source,"
            "karar_id AS source_record_id,karar_tipi,readiness,kanit_sinifi,"
            "kanit_puani,veri_kalitesi,eksik_kaynak FROM mart.ai_evidence_readiness "
            "ORDER BY karar_id DESC LIMIT 100) x;"
        ),

        "operations_shipments": (
            "SELECT row_to_json(x) FROM (SELECT gonderi_id AS entity_id,"
            "'mart.gonderi' AS source,siparis_no AS source_record_id,"
            "olusturma AS observed_at,gun,durum,tasiyici,sehir,kargo_ucreti,"
            "cod_var,cod_tutar,cod_durum,toplam_maliyet,transit_gun,alarm,"
            "sinif,olcumde FROM mart.gonderi ORDER BY olusturma DESC LIMIT 50) x;"
        ),
    }

    # Which allowlisted queries answer a business domain. The execution
    # planner resolves DOMAINS against these names; a domain whose tuple is
    # empty stays DATA_UNAVAILABLE rather than borrowing another domain's
    # data.
    # mart.urun_sinyal, mart.meta_sinyal and mart.roas_kapisi are absent by
    # measurement, not oversight: each resolves further mart views
    # (maliyet_kalite, meta_kapsama, ekonomi_gunluk, siparis_ekonomi) that
    # ai_reader cannot read, and chasing that dependency chain would keep
    # widening the read surface for no bounded gain. The profitability, price
    # and funnel queries already cover the same ground from granted sources.
    DOMAIN_QUERIES: dict[str, tuple[str, ...]] = {
        "sales": ("sales_orders", "sales_items"),
        "ecommerce": ("ecommerce_profitability", "ecommerce_price",
                      "ecommerce_funnel"),
        "advertising": ("advertising_performance", "advertising_spend"),
        "crm": ("crm_customers", "crm_unanswered", "open_work"),
        # mart.ai_operations_dashboard is deliberately absent: it resolves
        # core.ai_provider_allowed internally, and granting ai_reader EXECUTE
        # on that function is explicitly out of bounds. open_work + system
        # already carry the operational picture.
        "operations": ("operations_shipments", "open_work", "system"),
    }

    def __init__(self, host: str | None = "lcarlie", timeout_s: int = 12):
        self.host = host
        self.timeout_s = timeout_s

    def _fetch(self, query_name: str) -> Evidence:
        if query_name not in self.QUERIES:
            raise ValueError("query is not allowlisted")
        sql = f"BEGIN; SET SESSION AUTHORIZATION ai_reader; {self.QUERIES[query_name]} ROLLBACK;"
        psql = ["docker", "exec", "lcarlie-postgres", "psql", "-X", "-q",
                "-U", "n8n", "-d", "n8n", "-Atc", sql]
        command = (["ssh", self.host, " ".join(
            ["docker exec lcarlie-postgres psql -X -q -U n8n -d n8n -Atc", f'"{sql}"']
        )] if self.host else psql)
        started = perf_counter()
        result = subprocess.run(
            command, capture_output=True, text=True,
            timeout=self.timeout_s, check=False,
        )
        latency = (perf_counter() - started) * 1000
        if result.returncode:
            raise MemoryError(result.stderr.strip() or "company memory query failed")
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            rows.append(value if isinstance(value, dict) else {"value": value})
        return Evidence(
            source=f"postgres:{query_name}", authority="CANONICAL_COMPANY_MEMORY",
            retrieved_at="live", records=rows, latency_ms=round(latency, 3),
        )

    def get_system_status(self) -> Evidence:
        return self._fetch("system")

    def get_company_context(self) -> Evidence:
        return self._fetch("decision_summary")

    def get_open_tasks(self) -> Evidence:
        status = self.get_system_status()
        return Evidence(status.source, status.authority, status.retrieved_at,
                        [{"open_tasks": status.records[0].get("open_tasks", 0)}], status.latency_ms)

    def get_open_proposals(self) -> Evidence:
        status = self.get_system_status()
        return Evidence(status.source, status.authority, status.retrieved_at,
                        [{"pending_actions": status.records[0].get("pending_actions", 0)}], status.latency_ms)

    def get_executive_brief(self) -> Evidence:
        return self._fetch("company_dashboard")

    def get_company_agenda(self) -> Evidence:
        return self._fetch("agenda")

    def get_open_work(self) -> Evidence:
        return self._fetch("open_work")

    def get_decision_outcomes(self) -> Evidence:
        return self._fetch("decision_outcomes")

    def get_learning_loop(self) -> Evidence:
        return self._fetch("learning_loop")

    def get_evidence_readiness(self) -> Evidence:
        return self._fetch("evidence_readiness")

    def get_provenance(self) -> Evidence:
        return self._fetch("provenance")

    def get_data_quality(self) -> Evidence:
        return self._fetch("data_quality")

    def get_domain(self, domain: str) -> dict[str, Evidence]:
        """Every allowlisted query behind one business domain.

        Raises ValueError for an unknown domain rather than returning an empty
        dict: a caller must not be able to mistake "domain does not exist" for
        "domain has no data".
        """
        if domain not in self.DOMAIN_QUERIES:
            raise ValueError(f"unknown domain: {domain!r}")
        return {name: self._fetch(name) for name in self.DOMAIN_QUERIES[domain]}


    def get_model_policy(self) -> Evidence:
        return self._fetch("capabilities")

    def get_action_contract(self) -> Evidence:
        return self._fetch("action_contract")

    def get_capability_state(self) -> Evidence:
        return self._fetch("capability_state")

    def get_product_context(self, entity: str) -> Evidence:
        agenda = self.get_company_agenda()
        needle = entity.casefold()
        records = [row for row in agenda.records if needle in json.dumps(row, ensure_ascii=False).casefold()]
        return Evidence(agenda.source, agenda.authority, agenda.retrieved_at, records, agenda.latency_ms)

-- lcarlie YEREL TEST FIXTURE'LARI - URETIM VERISI DEGILDIR.
-- schema-only dump veri icermez; mart view'lari core.ayar('olcum_baslangici') olmadan hata verir
-- ve FakeProvider'in PROPOSED karar yazabilmesi icin en az bir core.kanit_anlik satiri gerekir.
BEGIN;
INSERT INTO core.ayar(anahtar,deger,aciklama)
SELECT 'olcum_baslangici','2026-09-17T00:00:00+03:00','YEREL FIXTURE: olcum penceresi baslangici (uretim degeri bilinmiyor)'
WHERE NOT EXISTS (SELECT 1 FROM core.ayar WHERE anahtar='olcum_baslangici');

INSERT INTO core.kanit_anlik(surum,pencere_7,pencere_30,urun,kanal,konusma,veri_kalitesi,eksik_kaynak,kanit_puani,kanit_sinifi)
SELECT 'yerel-fixture-v1','{}'::jsonb,'{}'::jsonb,'[]'::jsonb,'[]'::jsonb,'{}'::jsonb,'{"not":"yerel fixture"}'::jsonb,'[]'::jsonb,10,'LOW'
WHERE NOT EXISTS (SELECT 1 FROM core.kanit_anlik WHERE surum='yerel-fixture-v1');
COMMIT;

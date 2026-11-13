-- 075 · Panel (jarvis_web) pazaryeri siparişlerini ve kanal nabzını okuyabilsin.
--
-- 13.11.2026: siparişler `core.pazaryeri_siparis`e düşüyordu ama panelde
-- gösteren sayfa yoktu; E-TİCARET › PAZARYERİ SATIŞLARI bölümü bu tabloyu okur.
-- Yetki SÜTUN düzeyinde: `ham` (pazaryerinin tam cevabı: adres, telefon,
-- e-posta, kimlik no) panele AÇILMAZ.
GRANT SELECT (kanal, siparis_no, paket_no, durum, siparis_zamani, tutar,
              para_birimi, musteri_ad, sehir, kalem_sayisi, kalemler,
              ilk_gorulme, son_guncelleme, kaynak)
  ON core.pazaryeri_siparis TO jarvis_web;
GRANT SELECT ON core.kanal_nabiz TO jarvis_web;

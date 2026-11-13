-- Jarvis paneli (jarvis_web) gelen kutusunda eczane adı + ilçe ve kampanya
-- teslim durumunu gösterir. Yalnız bu sütunlar: eczacı adı, telefon, adres
-- gibi kişisel alanlar panel rolüne AÇILMAZ.
GRANT USAGE ON SCHEMA core TO jarvis_web;
GRANT SELECT (id, eczane, ilce) ON core.eczane_hedef TO jarvis_web;
GRANT SELECT (wamid, durum) ON core.eczane_gonderim TO jarvis_web;

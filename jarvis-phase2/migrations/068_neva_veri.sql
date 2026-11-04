-- NEVA İnovasyon faturaları (02.11.2026): satıcı "T.C. Ziraat Bankası" okunmuştu (faturadaki ödeme notu),
-- tester adetleri binlik ayraçla yazılmış ("4.900 Adet") ve 4,9 diye okunmuştu. Tutarlar zaten doğruydu.
BEGIN;
UPDATE core.jarvis_invoice SET party='NEVA INOVASYON VE KIMYA ANONIM SIRKETI', party_key='nevainovasyonvekimyaanon'
 WHERE owner='operator' AND document_id IN ('1ba899d0-bc53-487c-8999-9b4484b27cf0','ea3ba902-3873-4882-899c-d2edd007db78')
   AND party ILIKE '%ziraat%';
UPDATE core.jarvis_invoice_line SET quantity = quantity * 1000
 WHERE owner='operator' AND document_id='1ba899d0-bc53-487c-8999-9b4484b27cf0' AND line_no IN (2,3,4,5) AND quantity < 10;
COMMIT;

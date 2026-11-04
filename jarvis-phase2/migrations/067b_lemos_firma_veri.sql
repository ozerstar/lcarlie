-- Satıcı adı okunamamış ya da fatura notu ad sanılmış faturalar; adlar PDF'ten okundu.
BEGIN;
UPDATE core.jarvis_invoice SET party='ESME ECZANESİ (Metin Gürleyen)', party_key='esmeeczanesimetingurleye' WHERE owner='operator' AND book='lemos' AND number='ECZ2026000000138' AND (party='' OR party ILIKE 'e-Ar%');
UPDATE core.jarvis_invoice SET party='ESME ECZANESİ (Metin Gürleyen)', party_key='esmeeczanesimetingurleye' WHERE owner='operator' AND book='lemos' AND number='ECZ2026000000125' AND (party='' OR party ILIKE 'e-Ar%');
UPDATE core.jarvis_invoice SET party='PODİUM ECZANESİ (Reyhan Aliusta Eser)', party_key='podiumeczanesireyhanaliu' WHERE owner='operator' AND book='lemos' AND number='ECZ2026000000037' AND (party='' OR party ILIKE 'e-Ar%');
UPDATE core.jarvis_invoice SET party='MEHMET ALİ ARDIÇ (Ardıç Jant)', party_key='mehmetaliardicardicjant' WHERE owner='operator' AND book='lemos' AND number='GIB2026000000365' AND (party='' OR party ILIKE 'e-Ar%');
UPDATE core.jarvis_invoice SET party='NAM PROMOSYON (Satılmış Arı)', party_key='nampromosyonsatilmisari' WHERE owner='operator' AND book='lemos' AND number='NAM2026000003664' AND (party='' OR party ILIKE 'e-Ar%');
UPDATE core.jarvis_invoice SET party='ERGİNAY TEKNOLOJİ (Akın Erginay)', party_key='erginayteknolojiakinergi' WHERE owner='operator' AND book='lemos' AND number='EF12026000000515' AND (party='' OR party ILIKE 'e-Ar%');
UPDATE core.jarvis_invoice SET party='MERT HIRDAVAT (Bengül Şengöz)', party_key='merthirdavatbengulsengoz' WHERE owner='operator' AND book='lemos' AND number='MHD2026000000320' AND (party='' OR party ILIKE 'e-Ar%');
UPDATE core.jarvis_invoice SET party='SÜMEYRA GÜLYAVŞAN', party_key='sumeyragulyavsan' WHERE owner='operator' AND book='lemos' AND number='GLY2026000000006' AND (party='' OR party ILIKE 'e-Ar%');
UPDATE core.jarvis_invoice SET party='VOLKAN DEMİRKAN (faturadaki IBAN sahibi)', party_key='volkandemirkanfaturadaki' WHERE owner='operator' AND book='lemos' AND number='VE02026000000158' AND (party='' OR party ILIKE 'e-Ar%');
COMMIT;

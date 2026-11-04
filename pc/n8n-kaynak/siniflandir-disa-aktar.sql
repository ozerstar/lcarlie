\pset pager off
\t on
\a
SELECT row_to_json(t)::text FROM (SELECT id, metin FROM lcarlie.mesaj WHERE yon = 'gelen' ORDER BY id) t;

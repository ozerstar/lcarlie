"""One-time server-side setup for the unprivileged web database login.

Run as root on the server; never print the generated password.
"""
from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path

secret_path = Path('/etc/lcarlie/jarvis-web-db.pass')
if secret_path.exists():
    raise SystemExit('database secret already exists; refusing to replace it')
password = secrets.token_hex(32)
tables_read = '''
core.bayi_kampanya core.ig_gonderi_plani core.katalog_not
core.urun_bayi_fiyat core.saha_bilgi core.saha_elle_nokta
core.saha_konum core.saha_rota_durak core.saha_ziyaret
core.saha_ziyaret_foto core.kreatif_konsept core.tasarim_isi
core.guncel_olay core.hatirlatici core.kargo_karar
core.kreatif_itiraz core.gonderi_notu core.tasarim_sablon
lcarlie.konusma lcarlie.mesaj
mart.urun_karti mart.bayi_fiyat_gecerli mart.katalog_ilgi
mart.saha_hedef mart.saha_kaynak mart.saha_son_konum
mart.saha_tum mart.hatirlatici_guncel mart.sirket_gundemi
mart.tasarim_guncel mart.gonderi mart.gunluk
mart.kargo_karar_ozet mart.kreatif_itiraz_guncel
mart.siparis_kalem mart.tasarim_sablon_kutuk
'''.split()
tables_write = '''
core.ig_gonderi_plani core.katalog_not core.urun_bayi_fiyat
core.saha_bilgi core.saha_elle_nokta core.saha_konum
core.saha_ziyaret core.saha_ziyaret_foto core.guncel_olay
core.hatirlatici core.kargo_karar core.kreatif_itiraz
core.gonderi_notu core.tasarim_isi lcarlie.konusma
'''.split()

sql = [
    'BEGIN;',
    "CREATE ROLE jarvis_web LOGIN NOINHERIT PASSWORD '%s';" % password,
    'GRANT CONNECT ON DATABASE n8n TO jarvis_web;',
    'GRANT ai_reader TO jarvis_web WITH INHERIT FALSE, SET TRUE;',
    'GRANT human_approver TO jarvis_web WITH INHERIT FALSE, SET TRUE;',
    'GRANT USAGE ON SCHEMA core,mart,lcarlie TO jarvis_web;',
]
sql += ['GRANT SELECT ON %s TO jarvis_web;' % t for t in tables_read]
sql += ['GRANT INSERT,UPDATE ON %s TO jarvis_web;' % t for t in tables_write]
sql += ["""DO $$ DECLARE seq regclass; BEGIN
  FOR seq IN SELECT DISTINCT pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname)::regclass
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_attribute a ON a.attrelid=c.oid
   WHERE n.nspname='core' AND c.relkind='r' AND a.attnum > 0
     AND NOT a.attisdropped AND pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) IS NOT NULL
  LOOP EXECUTE format('GRANT USAGE ON SEQUENCE %s TO jarvis_web', seq); END LOOP;
END $$;"""]
sql += ['COMMIT;']
result = subprocess.run(['docker', 'exec', '-i', 'lcarlie-postgres', 'psql', '-X', '-q',
                         '-v', 'ON_ERROR_STOP=1', '-U', 'n8n', '-d', 'n8n', '-f', '-'],
                        input='\n'.join(sql), text=True, capture_output=True)
if result.returncode:
    raise SystemExit('database role setup failed: ' + result.stderr[-500:])
fd = os.open(secret_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640)
try:
    os.write(fd, (password+'\n').encode())
finally:
    os.close(fd)
print('restricted web DB login created')

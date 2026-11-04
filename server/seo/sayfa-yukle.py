import json, subprocess, sys
kayit = json.load(open("/tmp/sayfa-olcum.json", encoding="utf-8"))
def q(x):
    if x is None: return "NULL"
    return "'" + str(x).replace("'", "''")[:900] + "'"
sat = []
for r in kayit:
    sat.append("(%s,%s,%s,%s,%d,%d,%d,%s,%d,%s,%d)" % (
        q(r["url"]), q(r["tur"]), r["http"] or 0, q(r["baslik"]),
        r["baslik_uz"], r["meta_uz"], r["h1_adet"], q(r["h1"]),
        r["kelime"], q(r["kanonik"]), r["bayt"]))
sql = ("INSERT INTO core.sayfa_olcum (url,tur,http_kodu,baslik,baslik_uzunluk,"
       "meta_uzunluk,h1_adet,h1_metni,kelime_sayisi,kanonik,ham_bayt) VALUES "
       + ",".join(sat) + " ON CONFLICT (url) DO UPDATE SET "
       "olcum_zamani=clock_timestamp(),tur=EXCLUDED.tur,"
       "http_kodu=EXCLUDED.http_kodu,baslik=EXCLUDED.baslik,"
       "baslik_uzunluk=EXCLUDED.baslik_uzunluk,meta_uzunluk=EXCLUDED.meta_uzunluk,"
       "h1_adet=EXCLUDED.h1_adet,h1_metni=EXCLUDED.h1_metni,"
       "kelime_sayisi=EXCLUDED.kelime_sayisi,kanonik=EXCLUDED.kanonik,"
       "ham_bayt=EXCLUDED.ham_bayt;")
r = subprocess.run(["docker","exec","-i","lcarlie-postgres","psql","-U","n8n",
                    "-d","n8n","-v","ON_ERROR_STOP=1"],
                   input=sql.encode("utf-8"), capture_output=True, timeout=120)
if r.returncode:
    print(r.stderr.decode()[:300], file=sys.stderr); sys.exit(1)
print("yazilan satir:", len(sat))

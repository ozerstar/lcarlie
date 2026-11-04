"""Haftalık içerik taslakları. Her taslak TİTCK ön taramasından geçer; YASAK çıkan taslak
'engellendi' olarak işaretlenir ve yayına önerilmez.

LLM opsiyoneldir (OpenAI uyumlu uç nokta: ör. Gemini, Groq, OpenRouter ücretsiz katmanları).
LLM yoksa ürün rotasyonuna göre şablon taslak üretilir.
"""
import datetime as dt
import os

from . import claims
from .db import jdump
from .util import http_post_json, iso, now

GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
ACILAR = ["İçerik hikâyesi (bitkisel bileşen)", "Bakım ritüeli (adım adım kullanım)", "Ürün dokusu / duyusal deneyim",
          "Yaygın uygulama hatası ve doğrusu", "Kampanya / satış noktası", "Bileşenin bilinen kökeni ve kullanım geçmişi",
          "Ritüel hatırlatması"]

SISTEM = ("Sen L'CARLİÉ markası için Instagram metni yazan bir metin yazarısın. Minimalist, lüks, premium bir ton kullan. "
          "Kozmetik ürün için TİTCK kurallarına uy: tedavi, iyileştirme, şifa, hastalık adı, kesin sonuç, mucize, "
          "'yan etkisiz' gibi ifadeler KESİNLİKLE yasak. Sadece bakım, his, ritüel, içerik ve kullanım anlat. "
          "En fazla 90 kelime ve 5 hashtag.")


def _llm(cfg, prompt, post):
    c = cfg["llm"]
    base, key, model = (os.environ.get(c[k]) for k in ("base_url_env", "api_key_env", "model_env"))
    if not (base and key and model):
        return None
    res = post(base.rstrip("/") + "/chat/completions",
               {"model": model, "temperature": 0.7,
                "messages": [{"role": "system", "content": SISTEM}, {"role": "user", "content": prompt}]},
               {"Authorization": f"Bearer {key}"})
    return res["choices"][0]["message"]["content"].strip()


def weekly(conn, cfg, book, post=http_post_json, today=None):
    today = today or now().date()
    monday = today - dt.timedelta(days=today.weekday()) + dt.timedelta(days=7 if today.weekday() else 0)
    week = monday.isoformat()
    if conn.execute("SELECT 1 FROM content_drafts WHERE week=?", (week,)).fetchone():
        return {"hafta": week, "durum": "zaten var"}
    start = (monday.toordinal() // 7) * 7 % len(book.items)
    out = {"hafta": week, "taslak": 0, "engellenen": 0, "llm": False}
    for i, gun in enumerate(GUNLER):
        p = book.items[(start + i) % len(book.items)]
        aci = ACILAR[i]
        prompt = f"Ürün: {p['ad']} ({p['aciklama']}). Açı: {aci}. Instagram gönderi metni yaz."
        text = None
        try:
            text = _llm(cfg, prompt, post)
            out["llm"] = out["llm"] or bool(text)
        except Exception as e:
            out.setdefault("hatalar", []).append(str(e))
        if not text:
            text = f"[ŞABLON] {p['ad']} — {p['aciklama']}\nAçı: {aci}\nGörsel: minimal, ürün kutusu ve etiketi değiştirilmeden."
        chk = claims.check(text)
        status = "engellendi" if chk["durum"] == "YASAK" else "draft"
        out["engellenen" if status == "engellendi" else "taslak"] += 1
        conn.execute("INSERT INTO content_drafts(week,day,channel,product,text,check_result,status,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?)", (week, gun, "instagram", p["ad"], text, jdump(chk), status, iso(now())))
    conn.commit()
    return out

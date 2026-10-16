# -*- coding: utf-8 -*-
"""Worker hata siniflari.

Ayrim onemli, cunku her biri sunucuda BASKA bir duruma yazilir:

    InsanGerekli  -> INSAN_GEREKLI  (TERMINAL, yeniden DENENMEZ)
    HandlerHatasi -> HATA/BEKLIYOR  (deneme hakki varsa tekrar denenir)

🔴 "Giris istendi" ile "arayuz degismis" ayni sey DEGILDIR. Ilkinde
   tekrar denemek bot dogrulamasini asmaya calismak olur; worker bunu
   YAPMAZ. Ikincisinde tekrar denemek mesru. Bu iki hali ayni istisnaya
   dusurmek, CAPTCHA'yi dongu halinde yeniden denemek demekti.
"""
from __future__ import annotations


class HandlerHatasi(RuntimeError):
    """Is yapilamadi ama sebebi insan mudahalesi gerektirmiyor."""


class ZamanAsimi(HandlerHatasi):
    """Yanit tavan suresi icinde gelmedi."""


class InsanGerekli(RuntimeError):
    """Giris ekrani, bot dogrulamasi ya da hesap uyarisi goruldu.

    Worker DURUR. Dogrulamayi asmaya calismaz.
    """

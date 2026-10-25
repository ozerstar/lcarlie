# Jarvis Ofisi

`Organizasyon → Ofis` ekranının kaynak kodu. Üretim çıktıları
`../webconsole/static/office.html`, `office.css`, `office.js` ve `office/`
altında tutulur. Kaynak kodu değiştirdikten sonra:

```sh
npm ci
npm run build
```

Derleme çıktısındaki `office.html`, `office.css`, `office.js` ve `office/`
klasörü `../webconsole/static/` içine kopyalanır. Derleme mevcut statik
klasörü temizlemez.

Veri kaynakları:

- `/api/panel/ajanlar`, `/api/panel/ekip`: tam kadro, yöneticiler ve birimler
- `/api/office/activity`: son ekip döngüsü ve yeni aktif çalışma özeti
- `/api/office/events`: oturum gerektiren olay akışı
- `/api/orchestration`, `/api/actions`: görev ve onay durumu

Yeşil/sarı/kırmızı birim renkleri son veri ölçümüdür. Yalnız gerçek
`WORKING` olayları çalışanı "Şimdi görevde" gösterir. Kaybolmuş bir
`WORKING` olayı en geç 10 dakika içinde canlı durumdan çıkar.

3D ofis ve karakter modelleri Arturo Paracuellos'un
[The Delegation](https://github.com/arturitu/the-delegation) projesinden,
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) koşullarıyla
alınmıştır. Kaynak kodu MIT lisanslıdır; `UPSTREAM-LICENSE.txt` saklanır.

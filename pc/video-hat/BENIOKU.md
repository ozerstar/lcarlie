# L'CARLIÉ video hattı (HTML sahne → Playwright → ffmpeg)

Video bir modele üretilmez, **kod olarak yazılır**. Her render birebir aynı çıkar.
Bir sahneyi değiştirmek = bir satırı değiştirmek.

## Kurulum (sunucuda bir kez yapıldı, 11.10.2026)
    cd /opt/lcarlie/video-hat
    npm i playwright && npx playwright install chromium && npx playwright install-deps chromium

## Kullanım
    # ürün fotoğrafını kadraja hazırla (pikseller yeniden çizilmez, sadece kırpılır)
    ffmpeg -y -i /opt/lcarlie/urun-ham/kinesis.jpg -vf 'crop=2100:2940:680:1480,scale=1080:-1' kinesis.jpg

    node cek.js --t 6 --cikti /tmp/kare.png        # tek kare, gözle kontrol için
    node cek.js --sure 10 --fps 30 --dizin kare    # tüm kareler (4 çekirdekte ~112 sn)

    ffmpeg -y -framerate 30 -i kare/%05d.png \
      -c:v libx264 -pix_fmt yuv420p -preset slow -crf 18 -movflags +faststart \
      cikti/kinesis-10sn.mp4

## Tasarım kuralları (bozulursa görsel reddedilir)
- **Dokunulmaz alan:** ürün y=0..1512. Metin bandı y=1508'den aşağısı. Yazı ürüne BİNMEZ.
- Ürün fotoğrafı **tam genişlik (1080)** olmalı; dar bırakılırsa kenarda dikiş görünür.
- Ken Burns `transform-origin: 50% 100%` ile — büyürken aşağı taşmaz.
- Fiyat **"1.950 TL"** yazılır, "₺1.950" değil: marka fontlarında ₺ glifi yok.
- Zemin, fotoğrafın ölçülen kenar renklerine eşit (#B6CBD9 → #C9CFD2).

## Mevzuat
Cümlenin NESNESİ izinli olmalı: görünüm · his · doku · nem · konfor · koku.
Kullanılan: "Spor sonrası ferahlık hissi" (nesne = his). Kas/ağrı/dolaşım/toparlanma YAZILMAZ.

## Not
Sunucudaki /opt/lcarlie/video-hat dağıtımda silinebilir. Kaynak BURASI.

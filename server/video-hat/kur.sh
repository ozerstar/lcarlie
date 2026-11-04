#!/bin/sh
# L'CARLIE - KINESIS+ 15 sn reklam filmi montaji
#   A 0-3   urun (HTML, gercek fotograf)
#   B 3-5   lavanta/nane/ardic  + "15'ten fazla bitkisel yag"
#   C 5-7   greyfurt/tarcin     + "bes mineral"
#   D 7-11  krem dokusu         + "kolay emilen yapi"
#   E 11-15 kapanis (HTML)
# Flow klipleri 24 fps; hepsi 30 fps'e ve 1080x1920'ye getirilir.
set -eu
cd /opt/lcarlie/video-hat
mkdir -p parca

FPS=30
echo "=== metin katmanlari (seffaf) ==="
node katmancek.js

# --- A: urun girisi 0-3 sn (film.html'in ilk 3 saniyesi) ---
echo "=== A: urun girisi ==="
node cekfilm.js --sure 3 --fps $FPS --dizin kare-A >/dev/null
ffmpeg -y -v error -framerate $FPS -i kare-A/%05d.png -c:v libx264 -pix_fmt yuv420p -crf 18 parca/A.mp4
rm -rf kare-A

# --- E: kapanis 11-15 sn ---
echo "=== E: kapanis ==="
node cekfilm.js --sure 15 --fps $FPS --dizin kare-E >/dev/null
# 11. saniyeden sonrasini al (kare 330'dan itibaren)
ffmpeg -y -v error -framerate $FPS -start_number 330 -i kare-E/%05d.png \
  -frames:v 120 -c:v libx264 -pix_fmt yuv420p -crf 18 parca/E.mp4
rm -rf kare-E

# --- klip + metin katmani birlestirme ---
# $1 kaynak, $2 baslangic, $3 sure, $4 katman no, $5 cikti
klip() {
  # 🔴 -loop 1 SART: PNG tek karedir, loop verilmezse metin yalnizca BIR kare
  #    gorunup kaybolur (14.10'da bu hata yapildi).
  ffmpeg -y -v error -ss "$2" -t "$3" -i "flow/$1" -loop 1 -i "katman-$4.png" \
    -filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=$FPS,setsar=1[v];\
[1:v]format=rgba,fps=$FPS,fade=t=in:st=0:d=0.4:alpha=1,fade=t=out:st=$(echo "$3 - 0.4" | bc):d=0.4:alpha=1[o];\
[v][o]overlay=0:0:format=auto:shortest=1" \
    -t "$3" -c:v libx264 -pix_fmt yuv420p -crf 18 -an "parca/$5"
}

echo "=== B: lavanta ==="; klip lavanta.mp4  1.2 2 1 B.mp4
echo "=== C: greyfurt ==="; klip greyfurt.mp4 1.5 2 2 C.mp4
echo "=== D: krem ==="    ; klip krem.mp4     1.0 4 3 D.mp4

echo "=== birlestirme ==="
printf "file 'A.mp4'\nfile 'B.mp4'\nfile 'C.mp4'\nfile 'D.mp4'\nfile 'E.mp4'\n" > parca/liste.txt
ffmpeg -y -v error -f concat -safe 0 -i parca/liste.txt \
  -c:v libx264 -pix_fmt yuv420p -preset slow -crf 18 -movflags +faststart \
  cikti/kinesis-reklam-15sn.mp4

ffprobe -v error -show_entries format=duration,size:stream=width,height,r_frame_rate -of default=nw=1 cikti/kinesis-reklam-15sn.mp4
echo "=== BITTI ==="

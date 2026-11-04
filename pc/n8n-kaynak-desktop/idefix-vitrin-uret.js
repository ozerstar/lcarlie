/**
 * Idefix magaza vitrini banner fabrikasi.
 *
 * NEDEN HTML -> PNG
 * Idefix slotlari TAM piksel olcusu istiyor (1216x203, 152x152, 588x294,
 * 384x384, 1220x305). Playwright viewport'u tam o olcuye kurup ekran goruntusu
 * aliyor; boylece olcu sapmasi ve yeniden olceklemeden kaynakli bulaniklik
 * olmuyor, yazi keskin kaliyor.
 *
 * KAYNAKLAR (hepsi olculdu, uydurulmadi)
 *   Palet   : canli siteden (www.lcarlie.shop) cikarilan renk sayimi
 *             #303B40 ana koyu, #153C41/#264B50 derin teal, #C9DDDC soluk nane,
 *             #FAF8F3 sicak kirik beyaz
 *   Fontlar : sitenin kendi @font-face dosyalari
 *             LCMetropolis = f1.woff2, LCMonument = f2.woff2
 *   Logo    : sitenin businessLogo PNG'si (gri tonlu, siyah kelime markasi)
 *   Urun    : /opt/lcarlie/urun-ham gercek studyo cekimleri
 *
 * 🔴 AMBALAJ KURALI: urun ambalaji AI ile yeniden cizilmez. Kare bannerlardaki
 * sise gorselleri GERCEK fotograftir; AI yalnizca ARKA PLAN dokusu uretir ve
 * o dokularda ambalaj/yazi bulunmaz.
 *
 * 🔴 METIN KURALI: her metin jarvis/compliance.py review()'dan gecirildi
 * (23.10.2026, 19 metin, 0 bulgu). Metin degistirilirse TEKRAR gecirilmeli.
 */
const { chromium } = require("/opt/lcarlie/video-hat/node_modules/playwright");
const fs = require("fs");
const path = require("path");

const KOK = "/opt/lcarlie/idefix-vitrin";
const KAYNAK = path.join(KOK, "kaynak");
const CIKTI = path.join(KOK, "cikti");
const HAM = "/opt/lcarlie/urun-ham";

const RENK = {
  koyu: "#303B40",
  teal: "#153C41",
  teal2: "#264B50",
  nane: "#C9DDDC",
  kagit: "#FAF8F3",
};

function b64(dosya) {
  return fs.readFileSync(dosya).toString("base64");
}

const FONT_CSS = `
@font-face{font-family:LCMetropolis;src:url(data:font/woff2;base64,${b64(path.join(KAYNAK, "f1.woff2"))}) format("woff2");font-display:block}
@font-face{font-family:LCMonument;src:url(data:font/woff2;base64,${b64(path.join(KAYNAK, "f2.woff2"))}) format("woff2");font-display:block}
`;

// 🔴 logo.png 7095x3980 ve cevresi bos; oldugu gibi kullanilinca kelime
// markasi minicik kaliyor ve beyaz zemini kutu gibi gorunuyor. Kirpilmis nusha:
const LOGO = `data:image/png;base64,${b64(path.join(KAYNAK, "logo-kirpik.png"))}`;

// Urun gorselleri kirp.py'nin sinir kutusuyla sikica kirpilmis nushalardir
// (ham kareler 3072x4608 ve sise karede kucuk kaliyor).
const URUN = path.join(KAYNAK, "urun-kesik");   // fonu kaldirilmis saydam PNG
// Not: fotograflarin fonu kes.py'de kaldirildigi icin panel rengi olcumune
// (kaynak/urun/fon.json) artik gerek yok; saydam PNG dogrudan marka zemininin
// uzerine oturuyor.
function urunVeri(ad) {
  return `data:image/png;base64,${b64(path.join(URUN, ad))}`;
}

function arkaPlan(ad) {
  // Arka plan gorseli yoksa marka gradyani ile devam edilir (bos kalmaz).
  const y = path.join(KAYNAK, "arkaplan", ad);
  if (fs.existsSync(y)) return `data:image/png;base64,${b64(y)}`;
  return null;
}

const TABAN = (w, h, govde, ek = "") => `<!doctype html><html lang="tr"><head><meta charset="utf-8">
<style>
${FONT_CSS}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:${w}px;height:${h}px;overflow:hidden}
body{font-family:LCMetropolis,Arial,sans-serif;background:${RENK.kagit};
  -webkit-font-smoothing:antialiased}
.cerceve{position:relative;width:${w}px;height:${h}px;overflow:hidden}
.mono{font-family:LCMonument,LCMetropolis,Arial,sans-serif}
${ek}
</style></head><body><div class="cerceve">${govde}</div></body></html>`;

/* ---------------- 1. KAPAK  1216 x 203 ---------------- */
function kapak() {
  const ap = arkaPlan("kapak.png");
  const gorsel = ap
    ? `<div class="ap" style="background-image:url('${ap}')"></div>`
    : `<div class="ap apyedek"></div>`;
  return TABAN(1216, 203, `
    ${gorsel}
    <div class="perde"></div>
    <div class="icerik">
      <img class="logo" src="${LOGO}">
      <div class="ayrac"></div>
      <div class="yazi">
        <div class="ust">CİLT &middot; SAÇ &middot; BEBEK &middot; VÜCUT BAKIMI</div>
        <div class="alt">Bitkisel içerikli kişisel bakım</div>
      </div>
    </div>
    <div class="sayi"><b>36</b><span>ÜRÜN</span></div>
  `, `
    .ap{position:absolute;inset:0;background-size:cover;background-position:center}
    .apyedek{background:linear-gradient(100deg,${RENK.kagit} 0%,${RENK.nane} 55%,${RENK.teal2} 100%)}
    .perde{position:absolute;inset:0;background:linear-gradient(90deg,
      ${RENK.kagit} 0%,${RENK.kagit}f2 42%,${RENK.kagit}99 62%,transparent 100%)}
    .icerik{position:absolute;left:56px;top:0;height:100%;display:flex;align-items:center;gap:30px}
    .logo{height:26px;width:auto;display:block;mix-blend-mode:multiply}
    .ayrac{width:1px;height:46px;background:${RENK.koyu}33}
    .ust{font-size:19px;letter-spacing:.14em;color:${RENK.koyu}}
    .alt{margin-top:7px;font-size:15px;letter-spacing:.04em;color:${RENK.teal2}}
    .sayi{position:absolute;right:58px;top:50%;transform:translateY(-50%);
      text-align:right;color:#fff;text-shadow:0 1px 14px ${RENK.teal}66}
    .sayi b{display:block;font-family:LCMonument,Arial,sans-serif;font-size:42px;line-height:.9}
    .sayi span{font-size:13px;letter-spacing:.3em;opacity:.9}
  `);
}

/* ---------------- 2. LOGO  152 x 152 ---------------- */
function logoKare() {
  return TABAN(152, 152, `
    <div class="kutu"><img src="${LOGO}"></div>
  `, `
    body{background:#fff}
    .kutu{width:100%;height:100%;display:flex;align-items:center;justify-content:center;
      background:#fff;padding:0 18px}
    .kutu img{width:100%;height:auto;display:block}
  `);
}

/* ---------------- 3. KATEGORI  588 x 294 (x4) ---------------- */
const KATEGORILER = [
  { ad: "kategori-yuz", baslik: "YÜZ<br>BAKIMI",
    alt: "Nemlendirici, temizleyici ve gece bakımı",
    urun: "hydravie.png", renk: RENK.teal, ap: "yuz.png" },
  { ad: "kategori-vucut", baslik: "VÜCUT<br>BAKIMI",
    alt: "Günlük vücut ve bölgesel bakım",
    urun: "dermavasc.png", renk: RENK.teal2, ap: "vucut.png" },
  { ad: "kategori-bebek", baslik: "BEBEK<br>BAKIMI",
    alt: "Bebek ve çocuklar için nazik bakım",
    urun: "babysoft.png", renk: "#176578", ap: "bebek.png" },
  { ad: "kategori-kisi", baslik: "ERKEK VE<br>KADIN",
    alt: "Kişiye özel günlük bakım ürünleri",
    urun: "vireon-for-men.png", renk: RENK.koyu, ap: "kisi.png" },
];

function kategori(k) {
  const ap = arkaPlan(k.ap);
  const sag = ap
    ? `<div class="sag" style="background-image:url('${ap}')"></div>`
    : `<div class="sag sagyedek"></div>`;
  return TABAN(588, 294, `
    ${sag}
    <div class="sol">
      <div class="mono baslik">${k.baslik}</div>
      <div class="alt">${k.alt}</div>
      <div class="cizgi"></div>
    </div>
    <div class="urunpanel"><img src="${urunVeri(k.urun)}"></div>
  `, `
    body{background:${RENK.kagit}}
    .sag{position:absolute;right:0;top:0;width:58%;height:100%;
      background-size:cover;background-position:center}
    .sagyedek{background:linear-gradient(145deg,${k.renk} 0%,${RENK.teal} 100%)}
    .sag:after{content:"";position:absolute;inset:0;
      background:linear-gradient(90deg,${RENK.kagit} 0%,transparent 38%)}
    .sol{position:absolute;left:34px;top:34px;width:270px;z-index:2}
    .baslik{font-size:33px;line-height:1.08;letter-spacing:.02em;color:${RENK.koyu}}
    .alt{margin-top:14px;font-size:14px;line-height:1.5;color:${RENK.teal2};max-width:215px}
    .cizgi{margin-top:18px;width:46px;height:3px;background:${k.renk}}
    .urunpanel{position:absolute;right:16px;bottom:0;width:206px;height:294px;z-index:3}
    .urunpanel img{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);
      height:252px;width:auto;filter:drop-shadow(0 12px 18px ${RENK.koyu}30)}
  `);
}

/* ---------------- 4. URUN KARESI  384 x 384 (x6) ---------------- */
const KARELER = [
  { ad: "kare-vireon", urun: "vireon-for-men.png",
    isim: "VIREON<br>FOR MEN", alt: "Erkek Bakım Kremi", hacim: "50 ml", renk: "#176578" },
  { ad: "kare-femisia", urun: "femisia-for-women.png",
    isim: "FEMISIA<br>FOR WOMEN", alt: "Bakım Kremi", hacim: "50 ml", renk: RENK.teal2 },
  { ad: "kare-dermanova", urun: "dermanova.png",
    isim: "DERMANOVA", alt: "Bitkisel Cilt Bakım Kremi", hacim: "50 ml", renk: RENK.teal },
  { ad: "kare-kinesis", urun: "kinesis.png",
    isim: "KINESIS+", alt: "Sporcu Bakım Kremi", hacim: "150 ml", renk: RENK.koyu },
  { ad: "kare-hydravie", urun: "hydravie.png",
    isim: "HYDRAVIE", alt: "Nemlendirici Yüz Kremi", hacim: "50 ml", renk: "#176578" },
  { ad: "kare-babysoft", urun: "babysoft.png",
    isim: "BABYSOFT", alt: "Bebek Vücut Losyonu", hacim: "200 ml", renk: RENK.teal2 },
];

function kare(k) {
  return TABAN(384, 384, `
    <div class="panel">
      <div class="hale"></div>
      <img class="urun" src="${urunVeri(k.urun)}">
      <img class="logo" src="${LOGO}">
      <div class="rozet">${k.hacim}</div>
    </div>
    <div class="etiket">
      <div class="mono isim">${k.isim}</div>
      <div class="alt">${k.alt}</div>
    </div>
  `, `
    body{background:${RENK.kagit}}
    /* Sise fonundan ayrilmis saydam PNG; panel marka zemini. */
    .panel{position:absolute;left:0;top:0;width:384px;height:250px;overflow:hidden;
      background:radial-gradient(130% 100% at 50% 8%,#ffffff 0%,${RENK.kagit} 58%,${RENK.nane}88 100%)}
    .hale{position:absolute;left:50%;bottom:16px;width:190px;height:26px;
      transform:translateX(-50%);border-radius:50%;
      background:radial-gradient(closest-side,${RENK.koyu}2e,transparent)}
    .urun{position:absolute;left:50%;bottom:20px;transform:translateX(-50%);
      height:208px;width:auto;filter:drop-shadow(0 10px 16px ${RENK.koyu}26)}
    .rozet{position:absolute;right:16px;top:16px;background:${k.renk};color:#fff;
      font-size:12px;letter-spacing:.1em;padding:5px 11px;border-radius:2px}
    .logo{position:absolute;left:18px;top:18px;height:11px;width:auto;
      mix-blend-mode:multiply;opacity:.75}
    .etiket{position:absolute;left:22px;right:22px;top:272px}
    .isim{font-size:25px;line-height:1.08;color:${RENK.koyu};letter-spacing:.01em}
    .alt{margin-top:8px;font-size:13px;color:${RENK.teal2};letter-spacing:.02em}
  `);
}

/* ---------------- 5. GENIS SERIT  1220 x 305 ---------------- */
function serit() {
  const ap = arkaPlan("serit.png");
  const zemin = ap
    ? `<div class="ap" style="background-image:url('${ap}')"></div>`
    : `<div class="ap apyedek"></div>`;
  const siseler = ["seralimbo.png", "dermastra.png", "liftelle.png", "luciderm.png"]
    .map((u, i) => `<img class="s s${i}" src="${urunVeri(u)}">`).join("");
  return TABAN(1220, 305, `
    ${zemin}
    <div class="perde"></div>
    <div class="sol">
      <img class="logo" src="${LOGO}">
      <div class="mono baslik">KİŞİSEL BAKIMDA<br>BİTKİSEL İÇERİK</div>
      <div class="alt">Yüz, vücut, saç ve bebek bakımında 36 ürün</div>
    </div>
    <div class="sag">${siseler}</div>
  `, `
    body{background:${RENK.teal}}
    .ap{position:absolute;inset:0;background-size:cover;background-position:center}
    .apyedek{background:linear-gradient(115deg,${RENK.teal} 0%,${RENK.teal2} 58%,#176578 100%)}
    .perde{position:absolute;inset:0;background:linear-gradient(90deg,
      ${RENK.teal}f7 0%,${RENK.teal}e0 46%,${RENK.teal}66 70%,transparent 100%)}
    .sol{position:absolute;left:62px;top:50%;transform:translateY(-50%);z-index:2}
    .logo{height:22px;width:auto;display:block;filter:invert(1);
      mix-blend-mode:screen}
    .baslik{margin-top:20px;font-size:38px;line-height:1.12;color:#fff;letter-spacing:.015em}
    .alt{margin-top:14px;font-size:16px;color:${RENK.nane};letter-spacing:.03em}
    .sag{position:absolute;right:0;top:0;width:52%;height:100%;z-index:3}
    .s{position:absolute;bottom:14px;height:250px;width:auto;
      filter:drop-shadow(0 14px 22px #00000055)}
    .s0{right:384px;height:232px}
    .s1{right:258px;height:262px}
    .s2{right:132px;height:242px}
    .s3{right:12px;height:218px}
  `);
}

/* ---------------- uretim ---------------- */
async function main() {
  fs.mkdirSync(CIKTI, { recursive: true });
  const isler = [
    { ad: "kapak", w: 1216, h: 203, html: kapak() },
    { ad: "logo", w: 152, h: 152, html: logoKare() },
    ...KATEGORILER.map((k) => ({ ad: k.ad, w: 588, h: 294, html: kategori(k) })),
    ...KARELER.map((k) => ({ ad: k.ad, w: 384, h: 384, html: kare(k) })),
    { ad: "serit", w: 1220, h: 305, html: serit() },
  ];

  const tarayici = await chromium.launch({ args: ["--no-sandbox"] });
  for (const is of isler) {
    const sayfa = await tarayici.newPage({
      viewport: { width: is.w, height: is.h },
      deviceScaleFactor: 1,
    });
    await sayfa.setContent(is.html, { waitUntil: "load" });
    await sayfa.evaluate(() => document.fonts.ready);
    await sayfa.waitForTimeout(300);
    const hedef = path.join(CIKTI, `${is.ad}.png`);
    await sayfa.screenshot({ path: hedef });
    const boy = fs.statSync(hedef).size;
    console.log(`${is.ad.padEnd(18)} ${is.w}x${is.h}  ${(boy / 1024).toFixed(0)} KB`);
    await sayfa.close();
  }
  await tarayici.close();
  console.log(`\n${isler.length} gorsel: ${CIKTI}`);
}

main().catch((e) => {
  console.error("HATA:", e.message);
  process.exit(1);
});

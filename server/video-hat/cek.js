// L'CARLIE - sahne.html'i kare kare yakalar.
//   tek kare : node cek.js --t 5 --cikti /tmp/kare.png
//   tum video: node cek.js --sure 10 --fps 30 --dizin kare
// Deterministik: ayni t her zaman ayni kareyi verir.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const arg = (ad, varsayilan) => {
  const i = process.argv.indexOf('--' + ad);
  return i > -1 ? process.argv[i + 1] : varsayilan;
};

const W = 1080, H = 1920;
const sahneYolu = 'file://' + path.resolve(__dirname, 'sahne.html');

(async () => {
  const tarayici = await chromium.launch();
  const sayfa = await tarayici.newPage({
    viewport: { width: W, height: H },
    deviceScaleFactor: 1,
  });

  async function kare(t, hedef) {
    await sayfa.goto(`${sahneYolu}?t=${t}`, { waitUntil: 'load' });
    // fontlar ve urun fotografi gelmeden cekme - yoksa yazi fallback fontla cikar
    await sayfa.waitForFunction('window.__hazir === true', null, { timeout: 20000 });
    await sayfa.screenshot({ path: hedef });
  }

  const tekT = arg('t', null);
  if (tekT !== null) {
    const hedef = arg('cikti', '/tmp/kare.png');
    await kare(parseFloat(tekT), hedef);
    console.log('tek kare yazildi:', hedef);
  } else {
    const sure = parseFloat(arg('sure', '10'));
    const fps = parseInt(arg('fps', '30'), 10);
    const dizin = path.resolve(__dirname, arg('dizin', 'kare'));
    fs.mkdirSync(dizin, { recursive: true });
    const toplam = Math.round(sure * fps);
    const t0 = Date.now();
    for (let i = 0; i < toplam; i++) {
      const t = i / fps;
      const ad = path.join(dizin, String(i).padStart(5, '0') + '.png');
      await kare(t, ad);
      if (i % 30 === 0 || i === toplam - 1) {
        const gecen = (Date.now() - t0) / 1000;
        console.log(`${i + 1}/${toplam}  ${gecen.toFixed(0)} sn`);
      }
    }
    console.log('bitti:', dizin);
  }

  await tarayici.close();
})().catch(e => { console.error('HATA:', e.message); process.exit(1); });

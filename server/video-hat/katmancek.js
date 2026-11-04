// katman.html'den SEFFAF (alfa kanalli) PNG uretir.
// node katmancek.js   ->  katman-1.png, katman-2.png, katman-3.png
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const tarayici = await chromium.launch();
  const sayfa = await tarayici.newPage({
    viewport: { width: 1080, height: 1920 },
    deviceScaleFactor: 1,
  });
  const yol = 'file://' + path.resolve(__dirname, 'katman.html');
  for (const b of ['1', '2', '3']) {
    await sayfa.goto(`${yol}?b=${b}`, { waitUntil: 'load' });
    await sayfa.waitForFunction('window.__hazir === true', null, { timeout: 20000 });
    const hedef = path.resolve(__dirname, `katman-${b}.png`);
    await sayfa.screenshot({ path: hedef, omitBackground: true });   // alfa korunur
    console.log('yazildi:', hedef);
  }
  await tarayici.close();
})().catch(e => { console.error('HATA:', e.message); process.exit(1); });

'use strict';
/**
 * AJAN KOMUTA KONSOLU — ana surec.
 *
 * Claude Code ve Codex'i tek ekrandan calistirir, masaustu uygulamalarini
 * baslatir/izler. Her is KULLANICININ acik komutuyla baslar; bu surec
 * kendiliginden hicbir ajan calistirmaz.
 */
const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const ajanlar = require('./ajanlar');
const masaustu = require('./masaustu');

let pencere = null;
// Varsayilan calisma dizini: kullanici secene kadar bu proje.
let calismaDizini = app.getPath('home');

const KAYIT_DIZINI = path.join(app.getPath('userData'), 'kosular');

function pencereKur() {
  pencere = new BrowserWindow({
    width: 1480,
    height: 920,
    minWidth: 1040,
    backgroundColor: '#0f1416',
    title: 'Ajan Komuta Konsolu',
    webPreferences: {
      // 🔴 Guvenlik: render surecinde Node yok, izolasyon acik.
      //    Arayuz yalniz preload'un actigi ucuncu yoldan is isteyebilir.
      preload: path.join(__dirname, 'onyukleme.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
    },
  });
  pencere.removeMenu();
  pencere.loadFile(path.join(__dirname, 'arayuz', 'index.html'));
  pencere.on('closed', () => (pencere = null));
}

app.whenReady().then(() => {
  fs.mkdirSync(KAYIT_DIZINI, { recursive: true });
  pencereKur();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) pencereKur();
  });
});

app.on('window-all-closed', () => app.quit());

// ----------------------------------------------------------- IPC uclari

ipcMain.handle('ajan:surumler', () => ajanlar.surumler());

ipcMain.handle('ajan:calistir', (_o, { ajan, istem }) => {
  // Cikti parca parca arayuze gider; boylece bekleme sirasinda bos ekran olmaz.
  return ajanlar.calistir(ajan, istem, calismaDizini, (olay) => {
    if (pencere && !pencere.isDestroyed()) pencere.webContents.send('ajan:olay', olay);
  });
});

ipcMain.handle('ajan:durdur', (_o, id) => ajanlar.durdur(id));

ipcMain.handle('masaustu:durum', () => masaustu.durum());
ipcMain.handle('masaustu:ac', (_o, anahtar) => masaustu.baslatVeyaOdakla(anahtar));

ipcMain.handle('dizin:sec', async () => {
  const r = await dialog.showOpenDialog(pencere, {
    title: 'Ajanların çalışacağı dizini seç',
    properties: ['openDirectory'],
    defaultPath: calismaDizini,
  });
  if (!r.canceled && r.filePaths[0]) calismaDizini = r.filePaths[0];
  return calismaDizini;
});

ipcMain.handle('dizin:oku', () => calismaDizini);

/**
 * Bir kosuyu diske yazar. Karsilastirmali calismada "hangi ajan ne dedi"
 * sorusu sonradan sorulur; ekranda kalan cevap yeterli degildir.
 */
ipcMain.handle('kosu:kaydet', (_o, kayit) => {
  const ad = new Date().toISOString().replace(/[:.]/g, '-') + '.json';
  const yol = path.join(KAYIT_DIZINI, ad);
  fs.writeFileSync(yol, JSON.stringify(kayit, null, 1), 'utf8');
  return yol;
});

ipcMain.handle('kosu:klasoru-ac', () => shell.openPath(KAYIT_DIZINI));

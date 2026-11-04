'use strict';
/**
 * ON YUKLEME — arayuz ile ana surec arasindaki TEK kapi.
 *
 * 🔴 Arayuze Node verilmiyor. Burada acilan uclar disinda hicbir sey
 *    cagrilamaz; boylece bir arayuz hatasi dosya sistemine ulasamaz.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('konsol', {
  surumler: () => ipcRenderer.invoke('ajan:surumler'),
  calistir: (ajan, istem) => ipcRenderer.invoke('ajan:calistir', { ajan, istem }),
  durdur: (id) => ipcRenderer.invoke('ajan:durdur', id),

  masaustuDurum: () => ipcRenderer.invoke('masaustu:durum'),
  masaustuAc: (anahtar) => ipcRenderer.invoke('masaustu:ac', anahtar),

  dizinSec: () => ipcRenderer.invoke('dizin:sec'),
  dizinOku: () => ipcRenderer.invoke('dizin:oku'),

  kosuKaydet: (kayit) => ipcRenderer.invoke('kosu:kaydet', kayit),
  kayitKlasoruAc: () => ipcRenderer.invoke('kosu:klasoru-ac'),

  olayDinle: (geriCagri) => {
    const sarmal = (_o, olay) => geriCagri(olay);
    ipcRenderer.on('ajan:olay', sarmal);
    return () => ipcRenderer.removeListener('ajan:olay', sarmal);
  },
});

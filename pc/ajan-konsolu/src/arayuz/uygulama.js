'use strict';
/* Arayuz mantigi. Node yok; her sey window.konsol uzerinden gider. */

const $ = (s, k = document) => k.querySelector(s);
const $$ = (s, k = document) => [...k.querySelectorAll(s)];

const panolar = {};
for (const p of $$('.pano')) {
  panolar[p.dataset.ajan] = {
    kok: p,
    cikti: $('[data-cikti]', p),
    durum: $('[data-durum]', p),
    dur: $('[data-dur]', p),
    kosuId: null,
    metin: '',
  };
}

let sonKosu = null; // kaydetmek icin

// ------------------------------------------------------------ yardimci
function durumYaz(ajan, metin, sinif) {
  const p = panolar[ajan];
  p.durum.textContent = metin;
  p.durum.className = 'durum' + (sinif ? ' ' + sinif : '');
}

function ciktiEkle(ajan, metin, stderrMi) {
  const p = panolar[ajan];
  p.metin += metin;
  if (stderrMi) {
    const s = document.createElement('span');
    s.className = 'stderr';
    s.textContent = metin;
    p.cikti.appendChild(s);
  } else {
    p.cikti.appendChild(document.createTextNode(metin));
  }
  p.cikti.scrollTop = p.cikti.scrollHeight;
}

function panoSifirla(ajan) {
  const p = panolar[ajan];
  p.cikti.textContent = '';
  p.metin = '';
  p.kosuId = null;
  p.dur.hidden = true;
  durumYaz(ajan, 'hazır');
}

// ------------------------------------------------------------ calistir
async function calistir(ajanlar, istem) {
  if (!istem.trim()) return;
  sonKosu = { istem, zaman: new Date().toISOString(), ciktilar: {} };
  $('#kaydet').disabled = true;

  for (const a of ajanlar) {
    panoSifirla(a);
    durumYaz(a, 'başlatılıyor…', 'kosuyor');
    try {
      const id = await window.konsol.calistir(a, istem);
      panolar[a].kosuId = id;
      panolar[a].dur.hidden = false;
    } catch (e) {
      durumYaz(a, 'başlatılamadı', 'hata');
      ciktiEkle(a, String(e.message || e), true);
    }
  }
}

window.konsol.olayDinle((olay) => {
  // Olaydaki id hangi panoya aitse oraya yaz.
  const ajan = Object.keys(panolar).find((a) => panolar[a].kosuId === olay.id);
  if (!ajan) return;

  if (olay.tip === 'basladi') durumYaz(ajan, 'çalışıyor…', 'kosuyor');
  else if (olay.tip === 'cikti') ciktiEkle(ajan, olay.veri, false);
  else if (olay.tip === 'hata_akisi') ciktiEkle(ajan, olay.veri, true);
  else if (olay.tip === 'bitti') {
    const sn = (olay.sure / 1000).toFixed(1);
    const iyi = olay.kod === 0;
    durumYaz(ajan, (iyi ? 'bitti' : 'hata (kod ' + olay.kod + ')') + ' · ' + sn + ' sn',
             iyi ? 'bitti' : 'hata');
    if (olay.hata) ciktiEkle(ajan, '\n' + olay.hata, true);
    panolar[ajan].dur.hidden = true;
    panolar[ajan].kosuId = null;
    if (sonKosu) {
      sonKosu.ciktilar[ajan] = { metin: panolar[ajan].metin, kod: olay.kod, sure_ms: olay.sure };
      $('#kaydet').disabled = false;
    }
  }
});

// ------------------------------------------------------------ dugmeler
$('#ikisine').onclick = () => calistir(['claude', 'codex'], $('#istem').value);
$('#yalnizClaude').onclick = () => calistir(['claude'], $('#istem').value);
$('#yalnizCodex').onclick = () => calistir(['codex'], $('#istem').value);
$('#temizle').onclick = () => { panoSifirla('claude'); panoSifirla('codex'); };

$('#istem').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    calistir(['claude', 'codex'], $('#istem').value);
  }
});

for (const [ajan, p] of Object.entries(panolar)) {
  p.dur.onclick = async () => {
    if (p.kosuId) await window.konsol.durdur(p.kosuId);
    durumYaz(ajan, 'durduruldu', 'hata');
    p.dur.hidden = true;
  };
}

$('#kaydet').onclick = async () => {
  if (!sonKosu) return;
  const yol = await window.konsol.kosuKaydet(sonKosu);
  $('#not').textContent = 'kaydedildi: ' + yol;
};
$('#kayitlar').onclick = () => window.konsol.kayitKlasoruAc();

$('#dizinDugme').onclick = async () => {
  const d = await window.konsol.dizinSec();
  $('#dizinMetin').textContent = d;
};

// ------------------------------------------------------------ durum
async function cliDurumYukle() {
  const s = await window.konsol.surumler();
  $('#cliDurum').innerHTML = '';
  for (const a of s) {
    const d = document.createElement('span');
    d.className = 'rozet ' + (a.kurulu ? 'var' : 'yok');
    d.textContent = a.ad + ' · ' + (a.kurulu ? a.surum : 'kurulu değil');
    $('#cliDurum').appendChild(d);
    if (!a.kurulu) {
      panolar[a.anahtar] && durumYaz(a.anahtar, 'CLI bulunamadı', 'hata');
    }
  }
}

async function masaustuYukle() {
  const d = await window.konsol.masaustuDurum();
  const k = $('#masaustuKartlar');
  k.innerHTML = '';
  for (const [anahtar, u] of Object.entries(d)) {
    const el = document.createElement('button');
    el.className = 'kart';
    el.innerHTML =
      '<span class="nokta" style="background:' + (u.calisiyor ? u.renk : '#3f5257') + '"></span>' +
      '<span>' + u.ad + '</span>' +
      '<span class="bilgi">' +
      (u.calisiyor ? u.surec_adedi + ' süreç · ' + u.ram_mb + ' MB' : 'kapalı') +
      '</span>';
    el.title = u.calisiyor ? 'Öne getir' : 'Başlat';
    el.onclick = async () => {
      el.disabled = true;
      const r = await window.konsol.masaustuAc(anahtar);
      $('#not').textContent = u.ad + ' → ' + r.islem + ': ' + r.sonuc;
      setTimeout(masaustuYukle, 1500);
    };
    k.appendChild(el);
  }
}

$('#yenileDurum').onclick = () => { cliDurumYukle(); masaustuYukle(); };

(async function baslat() {
  $('#dizinMetin').textContent = await window.konsol.dizinOku();
  await cliDurumYukle();
  await masaustuYukle();
  setInterval(masaustuYukle, 20000);
})();

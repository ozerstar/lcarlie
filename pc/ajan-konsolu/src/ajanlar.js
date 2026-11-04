'use strict';
/**
 * AJAN KOSUCULARI — Claude Code ve Codex'i etkilesimsiz kipte calistirir.
 *
 * NEDEN ETKILESIMSIZ KIP:
 *   Iki TUI'yi yan yana gommek "ikisine birden hukmetmek" degil, iki ayri
 *   pencereye bakmaktir. Etkilesimsiz kipte cikti AYRISTIRILABILIR: ayni
 *   istemi ikisine gonderip cevaplari karsilastirabilir, kaydedebilir,
 *   birini digerine girdi yapabiliriz. Terminal kipi ayrica eklenir.
 *
 * 🔴 SINIR: bu modul kendi basina hicbir sey calistirmaz. Her kosu
 *   kullanicinin acik komutuyla baslar ve calisma dizini disina cikmaz.
 */
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

/**
 * Verilen dizin bir git calisma agacinin icinde mi?
 * Codex guvenilmeyen (= git disi) dizinde calismayi REDDEDER; bunu onceden
 * bilip anlasilir hata vermek, anlasilmaz bir ingilizce stderr'den iyidir.
 * Kontrolu bypass ETMIYORUZ — yalniz aciklayici hale getiriyoruz.
 */
function gitAgacindaMi(dizin) {
  let d = path.resolve(dizin);
  for (;;) {
    if (fs.existsSync(path.join(d, '.git'))) return true;
    const ust = path.dirname(d);
    if (ust === d) return false;
    d = ust;
  }
}

// Olculdu 22.10.2026 — bu makinede kurulu surumler.
const AJANLAR = {
  claude: {
    ad: 'Claude Code',
    komut: 'claude',
    // -p: print (etkilesimsiz). --output-format text: ayristirilabilir.
    // 🔴 Istem ARGUMAN DEGIL, stdin'den gider — asagidaki nota bak.
    //    Olculdu 23.10.2026: `echo metin | claude -p --output-format text` calisiyor.
    argumanlar: () => ['-p', '--output-format', 'text'],
    renk: '#C96442',
  },
  codex: {
    ad: 'Codex',
    komut: 'codex',
    // codex exec: etkilesimsiz calistirma. '-' => istemi stdin'den oku
    // (`codex exec --help`: "or if `-` is used, instructions are read from stdin").
    argumanlar: () => ['exec', '-'],
    renk: '#10A37F',
  },
};

/** Calisan kosular: id -> child process. Iptal icin tutulur. */
const kosanlar = new Map();

/**
 * Bir ajani etkilesimsiz calistirir, ciktiyi parca parca bildirir.
 * @param {string} ajanAnahtari 'claude' | 'codex'
 * @param {string} istem kullanicinin yazdigi metin
 * @param {string} calismaDizini
 * @param {(olay: {tip: string, veri?: string, kod?: number}) => void} bildir
 * @returns {string} kosu kimligi (iptal icin)
 */
function calistir(ajanAnahtari, istem, calismaDizini, bildir) {
  const ajan = AJANLAR[ajanAnahtari];
  if (!ajan) throw new Error('bilinmeyen ajan: ' + ajanAnahtari);
  if (!istem || !istem.trim()) throw new Error('bos istem calistirilmaz');

  const id = ajanAnahtari + '-' + Date.now().toString(36);
  const baslangic = Date.now();

  // Olculdu 23.10.2026: `codex exec` git calisma agaci disinda
  // "Not inside a trusted directory" ile cikis 1 verir. Varsayilan dizin ev
  // klasoru oldugu icin bu, duzeltilmezse ILK kosuda herkeste olusur.
  if (ajanAnahtari === 'codex' && !gitAgacindaMi(calismaDizini)) {
    const mesaj =
      'Codex yalniz git deposu icinde calisir. Secili dizin bir git deposu degil: ' +
      calismaDizini + ' — ustteki dizin seciciden bir depo secin.';
    bildir({ tip: 'basladi', id, ajan: ajanAnahtari });
    bildir({ tip: 'hata_akisi', id, veri: mesaj + String.fromCharCode(10) });
    bildir({ tip: 'bitti', id, kod: -1, sure: 0, hata: mesaj });
    return id;
  }

  // shell:true Windows'ta .ps1/.cmd sarmalayicilari icin gerekli
  // (codex npm global olarak codex.ps1 ile geliyor — olculdu).
  //
  // 🔴 NEDEN ISTEM ARGUMAN DEGIL:
  //    shell:true altinda Node argumanlari KACISSIZ birlestirip cmd.exe'ye verir.
  //    Istemde " & | > % gecen her metin ya komutu bozar ya da enjeksiyon olur —
  //    ve bu uygulamanin TEK isi kullanici metnini CLI'a gecirmek. O yuzden argv'de
  //    yalniz SABIT bayraklar var; kullanici metni stdin'den gidiyor. Boylece
  //    kabugun metni hic gormemesi garanti, cok satirli istem de bozulmuyor.
  const surec = spawn(ajan.komut, ajan.argumanlar(), {
    cwd: calismaDizini,
    shell: true,
    windowsHide: true,
    env: { ...process.env, FORCE_COLOR: '0' },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  // Istem stdin'den. EPIPE: surec biz yazmadan oldugunde dusebilir — kosuyu
  // dusurmesin, zaten 'error'/'close' olaylari durumu bildiriyor.
  surec.stdin.on('error', () => {});
  surec.stdin.end(istem);

  kosanlar.set(id, surec);
  bildir({ tip: 'basladi', id, ajan: ajanAnahtari });

  surec.stdout.on('data', (b) => bildir({ tip: 'cikti', id, veri: b.toString() }));
  surec.stderr.on('data', (b) => bildir({ tip: 'hata_akisi', id, veri: b.toString() }));

  surec.on('error', (e) =>
    bildir({ tip: 'bitti', id, kod: -1, sure: Date.now() - baslangic, hata: e.message }));

  surec.on('close', (kod) => {
    kosanlar.delete(id);
    bildir({ tip: 'bitti', id, kod, sure: Date.now() - baslangic });
  });

  return id;
}

/** Calisan bir kosuyu durdurur. Kullanici istemeden cagrilmaz. */
function durdur(id) {
  const s = kosanlar.get(id);
  if (!s) return false;
  s.kill();
  kosanlar.delete(id);
  return true;
}

function kosanSayisi() {
  return kosanlar.size;
}

/** Her ajanin kurulu olup olmadigini ve surumunu dondurur. */
function surumler() {
  return Promise.all(
    Object.entries(AJANLAR).map(([anahtar, a]) =>
      new Promise((coz) => {
        const s = spawn(a.komut, ['--version'], { shell: true, windowsHide: true });
        let v = '';
        s.stdout.on('data', (b) => (v += b.toString()));
        s.on('error', () => coz({ anahtar, ad: a.ad, kurulu: false, surum: null }));
        s.on('close', (kod) =>
          coz({
            anahtar, ad: a.ad, renk: a.renk,
            kurulu: kod === 0,
            surum: v.trim().split('\n')[0] || null,
          }));
      })
    )
  );
}

module.exports = { AJANLAR, calistir, durdur, kosanSayisi, surumler };

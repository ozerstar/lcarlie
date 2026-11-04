'use strict';
/**
 * MASAUSTU UYGULAMALARI — Claude ve ChatGPT masaustu uygulamalarini
 * baslatir, odaklar ve durumlarini izler.
 *
 * 🔴 NEDEN GOMULMUYOR — OLCULDU 22.10.2026:
 *   Iki uygulama da MSIX (WindowsApps) paketi:
 *     Claude  : WindowsApps\Claude_3.1623.3.0_x64__pzs8sxrjxfjjc\app\claude.exe
 *     ChatGPT : WindowsApps\OpenAI.Codex_26.1013.4894.0_x64__2p2nqsd0c76g0\app\ChatGPT.exe
 *   MSIX uygulamalari kendi sandbox'inda calisir. Pencerelerini baska bir
 *   uygulamanin icine almak (SetParent) hem kirilgan hem sandbox'i bozar.
 *   Bu yuzden burada YALNIZ baslatma/odaklama/izleme var; icerik kontrolu
 *   yok ve varmis gibi gosterilmiyor.
 */
const { exec } = require('node:child_process');

const UYGULAMALAR = {
  claude_masaustu: {
    ad: 'Claude (masaüstü)',
    surecAdi: 'claude',
    // claude:// protokolu kayitli — olculdu. En saglam baslatma yolu bu.
    protokol: 'claude://',
    renk: '#C96442',
  },
  chatgpt_masaustu: {
    ad: 'ChatGPT (masaüstü)',
    surecAdi: 'ChatGPT',
    // Protokol kaydi YOK — olculdu. Paket aile adiyla baslatilir.
    paketAilesi: 'OpenAI.Codex_2p2nqsd0c76g0',
    renk: '#10A37F',
  },
};

function ps(komut) {
  return new Promise((coz) => {
    exec(
      'powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ' +
        JSON.stringify(komut),
      { windowsHide: true, timeout: 15000 },
      (hata, cikti, hataCikti) =>
        coz({ ok: !hata, cikti: (cikti || '').trim(), hata: (hataCikti || '').trim() })
    );
  });
}

/** Hangi uygulama calisiyor, kac surec, ne kadar bellek. */
async function durum() {
  const sonuc = {};
  for (const [anahtar, u] of Object.entries(UYGULAMALAR)) {
    const r = await ps(
      `$p = Get-Process -Name '${u.surecAdi}' -ErrorAction SilentlyContinue; ` +
        `if ($p) { '{0}|{1}' -f @($p).Count, [math]::Round((($p | Measure-Object WorkingSet64 -Sum).Sum)/1MB) } else { '0|0' }`
    );
    const [adet, ram] = (r.cikti || '0|0').split('|');
    sonuc[anahtar] = {
      ad: u.ad,
      renk: u.renk,
      calisiyor: Number(adet) > 0,
      surec_adedi: Number(adet) || 0,
      ram_mb: Number(ram) || 0,
    };
  }
  return sonuc;
}

/**
 * Uygulamayi baslatir (kapaliysa) veya one getirir (aciksa).
 * Kullanici dugmeye basmadan CAGRILMAZ.
 */
async function baslatVeyaOdakla(anahtar) {
  const u = UYGULAMALAR[anahtar];
  if (!u) throw new Error('bilinmeyen uygulama: ' + anahtar);

  const d = await durum();
  if (d[anahtar].calisiyor) {
    // Aciksa: ana penceresini one getir.
    const r = await ps(
      `$p = Get-Process -Name '${u.surecAdi}' -ErrorAction SilentlyContinue | ` +
        `Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1; ` +
        `if ($p) { ` +
        `Add-Type -Name W -Namespace N -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);'; ` +
        `[N.W]::ShowWindow($p.MainWindowHandle, 9) | Out-Null; ` +
        `[N.W]::SetForegroundWindow($p.MainWindowHandle) | Out-Null; 'odaklandi' } else { 'pencere-yok' }`
    );
    return { islem: 'odakla', sonuc: r.cikti || 'bilinmiyor' };
  }

  // Kapaliysa: baslat.
  if (u.protokol) {
    const r = await ps(`Start-Process '${u.protokol}'`);
    return { islem: 'baslat', sonuc: r.ok ? 'baslatildi' : r.hata.slice(0, 120) };
  }
  if (u.paketAilesi) {
    const r = await ps(
      `$a = Get-StartApps | Where-Object { $_.AppID -like '*${u.paketAilesi}*' } | Select-Object -First 1; ` +
        `if ($a) { Start-Process ('shell:AppsFolder\\' + $a.AppID); 'baslatildi' } else { 'uygulama-bulunamadi' }`
    );
    return { islem: 'baslat', sonuc: r.cikti || 'bilinmiyor' };
  }
  return { islem: 'baslat', sonuc: 'baslatma-yolu-tanimli-degil' };
}

module.exports = { UYGULAMALAR, durum, baslatVeyaOdakla };

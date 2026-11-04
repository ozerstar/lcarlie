# =============================================================================
# L'CARLIE - MASAUSTUNDEN TEK KOMUTLA YAYINLAMA
#
# Bu klasordeki kaynak dosyalari sunucuya gonderir ve yayinlama hattini
# calistirir: test -> yedek -> uret -> aktar -> yayinla -> dogrula.
#
# 🔴 Testler gecmezse hicbir sey yayinlanmaz.
# 🔴 Yayinlama yarida kesilirse workflow'lar otomatik yayina geri alinir.
#
# Kullanim:
#   .\yayinla.ps1              Tam yayinlama
#   .\yayinla.ps1 -SadeceTest  Sadece testler (canliya dokunmaz)
#   .\yayinla.ps1 -GeriDon     Onceki surume don
# =============================================================================
param(
  [switch]$SadeceTest,
  [switch]$GeriDon
)

$ErrorActionPreference = 'Stop'
$kaynak = $PSScriptRoot

function Yaz($metin, $renk = 'Gray') { Write-Host $metin -ForegroundColor $renk }

if ($GeriDon) {
  # 🔴 ssh -t SART: geri donus betigi "EVET yazin" onayi istiyor.
  # Pty ayrilmazsa read komutu bos okur, betik "Iptal edildi" deyip
  # EXIT 0 ile cikar - yani BASARIYLA BITMIS gibi gorunur ama canli
  # sistem bozuk kalir. Hem de en kritik anda.
  Yaz "`nOnceki surume donuluyor..." Yellow
  Yaz "(Onay istenecek: EVET yazin)" DarkGray
  ssh -t lcarlie "/opt/lcarlie/n8n-geri-don.sh"
  $kod = $LASTEXITCODE
  if ($kod -ne 0) { Yaz "`nGeri donus TAMAMLANMADI (cikis kodu $kod)." Red }
  exit $kod
}

# --- 0a) KAYNAK SURUMU: ne yayinlaniyor? -------------------------------------
# 🔴 Git PATH'te yok (olculdu). Tam yolla aranir; yoksa yayin durmaz,
#    damga "gitsiz" olur - surum kaydi olmamasi yayini engellemeyecek
#    kadar kucuk, sessizce gecistirilemeyecek kadar onemli.
$gitExe = @(
  "$env:ProgramFiles\Git\cmd\git.exe",
  "${env:ProgramFiles(x86)}\Git\cmd\git.exe",
  "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

$gitSurum = 'gitsiz'
if ($gitExe) {
  $gitKimlik = & $gitExe -C $kaynak rev-parse --short HEAD 2>$null
  if ($LASTEXITCODE -eq 0) {
    $gitKirli = & $gitExe -C $kaynak status --porcelain 2>$null
    if ($gitKirli) {
      $gitSayi = ($gitKirli | Measure-Object -Line).Lines
      Yaz "`nUYARI: kaynakta islenmemis $gitSayi degisiklik var." Yellow
      Yaz "  Yayinlanan hal git'te YOK - sorun cikarsa donulecek surum de yok." Yellow
      $gitSurum = "$gitKimlik+islenmemis$gitSayi"
    } else {
      $gitSurum = $gitKimlik
    }
  }
} else {
  Yaz "`nUYARI: git bulunamadi - yayinlanan surum kaydedilemiyor." Yellow
}

# --- 0) YAYIN KORUMA: sunucuda elle yapilmis duzeltme var mi? ----------------
# 🔴 NEDEN: bu betik masaustundeki kaynagi sunucuya BASAR. Sunucuda elle
#    yapilmis bir duzeltme sessizce silinir. 20-22.09.2026'da iki kez oldu;
#    dort dosya kayboldu ve gunler sonra fark edildi. Kapi artik burada.
Yaz "`n=== YAYIN KORUMA: sunucu kontrol ediliyor ===" Cyan
ssh lcarlie "/opt/lcarlie/yayin-koruma.sh kontrol"
if ($LASTEXITCODE -ne 0) {
  Yaz "`nYAYIN DURDURULDU: sunucuda, kaynakta olmayan degisiklikler var." Red
  Yaz "Yukaridaki iki secenekten birini uygulayin, sonra tekrar deneyin." Yellow
  exit 1
}

# --- 1) Kaynaklari sunucuya gonder -------------------------------------------
Yaz "`n=== KAYNAK DOSYALARI GONDERILIYOR ===" Cyan
$dosyalar = Get-ChildItem "$kaynak\*.js" -File
if (-not $dosyalar) { Yaz "  Gonderilecek .js dosyasi bulunamadi: $kaynak" Red; exit 1 }

# Tek scp cagrisi - dosya basina baglanti acmaktan cok daha hizli
$yollar = $dosyalar | ForEach-Object { "`"$($_.FullName)`"" }
$komut = "scp -q $($yollar -join ' ') lcarlie:/root/"
Invoke-Expression $komut
if ($LASTEXITCODE -ne 0) { Yaz "  Dosyalar gonderilemedi." Red; exit 1 }
Yaz "  $($dosyalar.Count) dosya gonderildi" Green

# Bakim betikleri degistiyse onlari da guncelle
# 🔴 'bash -n' SART: bu betikler yayinlama ve GERI DONUS yolunu tutuyor.
#    Sozdizimi bozuk bir dosyayi kurmak, geri donusu gerektigi an
#    calismaz hale getirir - yani en kotu anda.
#
# 🔴 LISTE EKSIKTI (14.09.2026): backup.sh, geri-yukle.sh ve durum-uret.sh
#    kaynak klasorde duruyordu ama HICBIR betik onlari sunucuya kurmuyordu.
#    Masaustunde duzeltip ".\yayinla.ps1" calistiran biri "Yayinlama
#    tamamlandi" gorup duzeltmenin gittigini sanirdi - gitmemis olurdu.
#    Hedef yol her dosya icin ayri, hepsi /opt/lcarlie koklerinde degil.
#
# 🔴 CR-002: yapilandirma dosyasi da bu listede olmali. Workflow listesi
#    artik uretim-workflowlari.conf'tan geliyor; masaustunde guncelleyip
#    sunucuya gonderilmezse yayinlama hatti ESKI listeyle calisir ve
#    "guncellendi" der - tam da bu listenin 14.09'da yasattigi hata.
# yayin-koruma'nin izledigi dosyalar - ayrisma kontrolu icin bir kez okunur.
$izlenen = @()
try {
  $izlenen = (ssh lcarlie "grep -vE '^\s*(#|$)' /opt/lcarlie/yayin-dosyalari.conf") -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
} catch { Yaz "  UYARI: izlenen dosya listesi okunamadi - ayrisma kontrolu atlandi." Yellow }

$betikler = @(
  @{ Ad = 'uretim-workflowlari.conf'; Hedef = '/opt/lcarlie/uretim-workflowlari.conf' },
  @{ Ad = 'karantina.conf';    Hedef = '/opt/lcarlie/karantina.conf' },
  @{ Ad = 'alarm.sh';        Hedef = '/opt/lcarlie/alarm.sh' },
  @{ Ad = 'saglik.sh';       Hedef = '/opt/lcarlie/saglik.sh' },
  # 🔴 Listede DEGILDI. Kaynakta duruyordu ama hicbir sey sunucuya kurmuyordu -
  #    yani masaustunde duzeltip "yayinlama tamamlandi" goren biri duzeltmenin
  #    gittigini sanirdi. 14.09'da ayni sey backup.sh/geri-yukle.sh/durum-uret.sh
  #    icin yasanmisti; eposta-kur.sh atlanmis.
  @{ Ad = 'eposta-kur.sh';   Hedef = '/opt/lcarlie/eposta-kur.sh' },
  @{ Ad = 'eposta-kur-dosyadan.sh'; Hedef = '/opt/lcarlie/eposta-kur-dosyadan.sh' },
  @{ Ad = 'n8n-yayinla.sh';  Hedef = '/opt/lcarlie/n8n-yayinla.sh' },
  @{ Ad = 'n8n-geri-don.sh'; Hedef = '/opt/lcarlie/n8n-geri-don.sh' },
  @{ Ad = 'hiz-sifirla.sh';  Hedef = '/opt/lcarlie/hiz-sifirla.sh' },
  @{ Ad = 'durum-uret.sh';   Hedef = '/opt/lcarlie/durum-uret.sh' },
  @{ Ad = 'backup.sh';       Hedef = '/opt/lcarlie/backup/backup.sh' },
  @{ Ad = 'geri-yukle.sh';   Hedef = '/opt/lcarlie/backup/geri-yukle.sh' },
  @{ Ad = 'fiyat-log.sh';    Hedef = '/opt/lcarlie/fiyat-log.sh' },
  @{ Ad = 'ticari-kontrol.sh'; Hedef = '/opt/lcarlie/ticari-kontrol.sh' },
  @{ Ad = 'ticari-panel.sh'; Hedef = '/opt/lcarlie/ticari-panel.sh' },
  @{ Ad = 'jeton-koy.sh';    Hedef = '/opt/lcarlie/jeton-koy.sh' },
  # 🔴 Bu ikisi 16.09 denetimine kadar listede DEGILDI - ikisi de cron'da
  #    calisiyor ve ikisi de API anahtari tasiyor. Listede olmayan dosya,
  #    masaustunde duzeltilip sunucuda eski haliyle calismaya devam eder.
  @{ Ad = 'stok-sifirla.sh'; Hedef = '/opt/lcarlie/stok-sifirla.sh' },
  @{ Ad = 'kalip-tazele.sh'; Hedef = '/opt/lcarlie/kalip-tazele.sh' },
  # 🔴 Yayin korumanin KENDISI de yonetilmeli - yoksa masaustunde
  #    duzeltilir, sunucuda eski hali calismaya devam eder.
  @{ Ad = 'yayin-koruma.sh'; Hedef = '/opt/lcarlie/yayin-koruma.sh' },
  @{ Ad = 'yayin-dosyalari.conf'; Hedef = '/opt/lcarlie/yayin-dosyalari.conf' },
  @{ Ad = 'saglik-test.sh'; Hedef = '/opt/lcarlie/saglik-test.sh' },
  # Alarm postasinin canliligini MAIL ATMADAN olcer; saglik.sh cagirir.
  @{ Ad = 'posta-yoklama.sh'; Hedef = '/opt/lcarlie/posta-yoklama.sh' },
  # Ham AI hata metinlerini eyleme donusebilir siniflara cevirir.
  @{ Ad = 'ai-saglayici-tani.sh'; Hedef = '/opt/lcarlie/ai-saglayici-tani.sh' }
)
# 🔴 BUTUN BETIKLER KURULUM DONGUSUNDEN ONCE GONDERILIR.
#    Onceki surumde her dosya kendi siras geldiginde gonderiliyordu.
#    Ama saglik.sh'nin test kapisi, listede DAHA SONRA gelen
#    saglik-test.sh ve posta-yoklama.sh dosyalarina ihtiyac duyuyor -
#    o an /root'ta ya hic yoklar ya da onceki yayindan kalma eski
#    hallerdir. Olculdu: kapi, 8396 baytlik yeni test dosyasi yerine
#    5448 baytlik eskisini calistiriyordu; yeni testler hic kosmadan
#    "gecti" yaziyordu.
#
# 🔴 scp'nin cikis kodu AYRICA kontrol edilmeli. Sadece ssh sonrasi
#    bakilirsa, gonderim basarisiz olsa bile ssh SUNUCUDAKI ESKI dosyayi
#    sozdizimi kontrolunden gecirip kurar ve "guncellendi" yazilir.
$gonderilecek = $betikler | Where-Object { Test-Path (Join-Path $kaynak $_.Ad) }
$betikYollari = $gonderilecek | ForEach-Object { "`"$(Join-Path $kaynak $_.Ad)`"" }
Invoke-Expression "scp -q $($betikYollari -join ' ') lcarlie:/root/"
if ($LASTEXITCODE -ne 0) { Yaz "  Betikler gonderilemedi - yayinlama durduruldu." Red; exit 1 }

foreach ($b in $betikler) {
  $yol = Join-Path $kaynak $b.Ad
  if (-not (Test-Path $yol)) { continue }

  # 🔴 IKI LISTE AYRISMASIN. Bu dosya yayin-koruma'nin izledigi listede
  #    degilse, sunucuda elle degistirilmesi FARK EDILMEZ.
  if ($izlenen -and ($izlenen -notcontains $b.Hedef)) {
    Yaz "  UYARI: $($b.Hedef) yayin-dosyalari.conf'ta YOK - koruma bu dosyayi izlemiyor." Yellow
  }

  # 🔴 SAGLIK KONTROLU KURULMADAN ONCE SINANIR.
  #    21-22.09.2026'da uc yanlis alarm ayni anda calisiyordu ve ucu de
  #    olcum hatasiydi; aylardir oyleydiler cunku bu kontrollerin testi
  #    yoktu. Test kurulumdan SONRA kosarsa, bozuk kontrol zaten yayinda
  #    olur. /root'taki kopya once sinanir.
  if ($b.Ad -eq 'saglik.sh') {
    # 🔴 TESTLER DE /root'tan KOSAR, kurulu kopyadan DEGIL.
    #    saglik-test.sh listede saglik.sh'den SONRA kuruluyor. Kurulu
    #    kopya cagrilirsa kapi, yeni saglik.sh'yi BIR ONCEKI yayinin
    #    testleriyle sinar: bu yayinla gelen yeni testler hic kosmaz ve
    #    "gecti" yazisi yanlis guven verir. Once test dosyasinin kendi
    #    sozdizimi dogrulanir, sonra staged hali kullanilir.
    $kapiDosyalari = 'saglik.sh saglik-test.sh alarm.sh posta-yoklama.sh ai-saglayici-tani.sh'
    $sedList = ($kapiDosyalari -split ' ' | ForEach-Object { "/root/$_" }) -join ' '
    $nList = ($kapiDosyalari -split ' ' | ForEach-Object { "bash -n /root/$_" }) -join ' && '
    ssh lcarlie "sed -i 's/\r`$//' $sedList && $nList && bash /root/saglik-test.sh /root/saglik.sh"
    if ($LASTEXITCODE -ne 0) {
      Yaz "  saglik.sh TESTLERI GECMEDI - kurulmadi, yayinlama durduruldu." Red
      exit 1
    }
    Yaz "  saglik.sh testleri gecti" DarkGray
  }

  # 🔴 kaydet-tek kancasi YAYINI DURDURMAZ (`|| true`): kaydin kendisi
  #    yayinin basarisi degildir, ve sunucudaki yayin-koruma.sh henuz bu
  #    alt komutu bilmiyor olabilir (kendisi de bu listeyle guncelleniyor).
  #    Nihai ve yetkili kayit, yayin sonundaki tam 'kaydet' ile alinir;
  #    bu kanca yalnizca YARIM kalan yayinlarin bir sonraki kontrolu
  #    kilitlemesini onler.
  ssh lcarlie "sed -i 's/\r`$//' /root/$($b.Ad) && bash -n /root/$($b.Ad) && install -m 700 /root/$($b.Ad) $($b.Hedef) && { /opt/lcarlie/yayin-koruma.sh kaydet-tek $($b.Hedef) >/dev/null 2>&1 || true; }"
  if ($LASTEXITCODE -ne 0) {
    Yaz "  $($b.Ad) SOZDIZIMI HATALI veya kurulamadi - yayinlama durduruldu." Red
    exit 1
  }

  # Kurulanin gonderilenle ayni oldugunu dogrula (sessiz bozulmaya karsi)
  $yerelHash = (Get-FileHash $yol -Algorithm MD5).Hash.ToLower()
  $uzakHash = (ssh lcarlie "sed 's/\r`$//' '$($b.Hedef)' | md5sum | cut -d' ' -f1").Trim()
  if ($yerelHash -ne $uzakHash) {
    Yaz "  $($b.Ad) KURULDU AMA ICERIK TUTMUYOR - yayinlama durduruldu." Red
    exit 1
  }
  Yaz "  $($b.Ad) guncellendi" DarkGray
}

# 🔴 CR-004: veri katmani dosyalari (.sql/.py) DA bu hatta girmeli.
#    Ustteki dongu her dosyaya 'bash -n' uyguluyor - .sql ve .py oradan
#    gecemez. Listeye eklemeyip "elle scp ederim" demek, 14.09'da
#    backup.sh ile yasanan sessiz surumlenmenin aynisidir: masaustunde
#    duzeltirsin, sunucuda eski surum calismaya devam eder.
#    SEMA/FONKSIYON KENDILIGINDEN UYGULANMAZ - yalniz kurulur. Uygulamak
#    ayri ve bilincli bir istir:  ssh lcarlie "/opt/lcarlie/raw-uygula.sh"
Yaz "`n=== VERI KATMANI DOSYALARI ===" Cyan
$veri = @('raw-sema.sql','raw-cikarma.sql','core-sema.sql','core-kimlik-fn.sql',
          'core-authority-seed.sql','core-kimlik-test.sql','core-doldur.sql',
          'mart-sema.sql','raw-dogrula.sql',
          'meta-harcama-sema.sql','mart-harcama.sql','core-authority-guncelle.sql',
          'urun-maliyet-sema.sql','mart-marj.sql','mutabakat.sql','mart-konusma.sql','mart-acik-isler.sql',
          'raw-yukle.py','kimlik-dogrulama.py','meta-harcama-yukle.py','urun-yukle.py','raw-uygula.sh')
foreach ($d in $veri) {
  $yol = Join-Path $kaynak $d
  if (-not (Test-Path $yol)) { continue }
  $hedef = "/opt/lcarlie/sql/$d"
  $mod = '644'
  if ($d -like '*.py' -or $d -like '*.sh') { $mod = '700' }

  scp -q $yol "lcarlie:/root/$d"
  if ($LASTEXITCODE -ne 0) { Yaz "  $d GONDERILEMEDI - yayinlama durduruldu." Red; exit 1 }

  # Sozdizimi: .py icin gercek derleme, .sh icin bash -n. .sql icin
  # derleyici yok - uygulama zaten islem icinde (BEGIN/COMMIT) yapiliyor.
  $kontrol = switch -Wildcard ($d) {
    '*.py' { "python3 -m py_compile /root/$d" }
    '*.sh' { "bash -n /root/$d" }
    default { "test -s /root/$d" }
  }
  ssh lcarlie "mkdir -p /opt/lcarlie/sql && sed -i 's/\r`$//' /root/$d && $kontrol && install -m $mod /root/$d $hedef"
  if ($LASTEXITCODE -ne 0) { Yaz "  $d SOZDIZIMI HATALI veya kurulamadi - durduruldu." Red; exit 1 }

  $yerelHash = (Get-FileHash $yol -Algorithm MD5).Hash.ToLower()
  $uzakHash = (ssh lcarlie "sed 's/\r`$//' '$hedef' | md5sum | cut -d' ' -f1").Trim()
  if ($yerelHash -ne $uzakHash) { Yaz "  $d KURULDU AMA ICERIK TUTMUYOR - durduruldu." Red; exit 1 }
  Yaz "  $d guncellendi" DarkGray
}

# --- 1c) YAYIN KORUMA: kurulan hali gecmise isle -----------------------------
# Betikler ve veri katmani KURULDU. Bundan sonraki her elle degisiklik,
# bir sonraki yayinda "sunucuda elle degistirilmis" diye yakalanabilsin
# diye kayit SIMDI aliniyor -- n8n hatti calismadan once, cunku o hattin
# basarisiz olmasi dosyalarin kurulmus olmasini degistirmiyor.
$damga = Get-Date -Format 'yyyy-MM-dd HH:mm'
ssh lcarlie "/opt/lcarlie/yayin-koruma.sh kaydet 'yayin $damga kaynak=$gitSurum'"
if ($LASTEXITCODE -ne 0) { Yaz "  UYARI: yayin koruma kaydi alinamadi." Yellow }

# --- 2) Yayinlama hattini calistir -------------------------------------------
$bayrak = if ($SadeceTest) { '--test-only' } else { '' }
Yaz "`n=== YAYINLAMA HATTI ===" Cyan
ssh lcarlie "/opt/lcarlie/n8n-yayinla.sh $bayrak"
$kod = $LASTEXITCODE

Write-Host ""
if ($kod -eq 0) {
  if ($SadeceTest) { Yaz "Testler gecti. (yayinlama yapilmadi)" Green }
  else             { Yaz "Yayinlama tamamlandi." Green }
} else {
  Yaz "Yayinlama basarisiz (cikis kodu $kod)." Red
  Yaz "Canli sistem korundu; gerekirse: .\yayinla.ps1 -GeriDon" Yellow
}
exit $kod

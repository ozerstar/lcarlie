# =============================================================================
# URUN BILGILENDIRME DOSYASI (UBD) TAMLIK DENETIMI
#
# Kozmetik Yonetmeligi her urun icin bir Urun Bilgilendirme Dosyasi tutulmasini
# ve son piyasaya arzdan itibaren 10 yil saklanmasini sart kosuyor.
# Bu betik her urun icin hangi belgenin VAR / EKSIK oldugunu cikarir.
#
# 🔴 BELGELER TEK KLASORDE DEGIL. Uc ayri yerde duruyorlar:
#     urun-icerik\urun-bilgilendirme-dosyalari\<urun>\   (etiket, kutu, formul, MoCRA)
#     test-guvenlik-raporlari\guvenlik-raporlari\        (urun guvenlilik raporlari)
#     test-guvenlik-raporlari\analiz-testleri\           (challenge, stabilite, mikrobiyolojik, spf)
#   Yalniz ilkine bakan bir denetim "37 urunun guvenlilik raporu yok" gibi
#   SAHTE ALARM uretir. Bu betik ucunu birden tarar.
#
# Isaretler:  +  var    -  EKSIK    .  bu urun icin gerekli degil
#
# Kullanim:  .\ubd-denetim.ps1
# =============================================================================
param(
  # Klasor yapisinin capasi (UBD / guvenlik / spf yollari buna gore bulunur)
  [string]$Kok = "C:\Users\ozery\OneDrive\Masaüstü\01 LCARLIE",
  # 🔴 DOSYA ARAMASI DAHA GENIS YAPILIR.
  # Guvenlilik raporlari ve analiz testleri bastan beri BASKA klasordeydi;
  # "eksik" demeden once TUM masaustune bakilmali. Dar tarama sahte alarm uretir.
  [string]$TaramaKoku = "C:\Users\ozery\OneDrive\Masaüstü"
)

if (-not (Test-Path $Kok)) { Write-Host "Klasor yok: $Kok" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $TaramaKoku)) { Write-Host "Klasor yok: $TaramaKoku" -ForegroundColor Red; exit 1 }

# --- Turkce normalizasyon --------------------------------------------------
# 🔴 .ToLower() Turkce yerel ayarda 'I' -> 'ı' yapar; ayrica dosya adlarinda
#    İ/ı/ş/ğ/ç/ö/ü karisik kullanilmis ("HAİR NOUSHİER", "İNTİMBLANC").
function Duzle([string]$s) {
  if (-not $s) { return "" }
  $s = $s -replace '[İIıi]','i' -replace '[Şş]','s' -replace '[Ğğ]','g'
  $s = $s -replace '[Çç]','c' -replace '[Öö]','o' -replace '[Üü]','u'
  return ($s.ToLowerInvariant() -replace '[^a-z0-9]','')
}

# --- Urun listesi (satistaki 36 + bakanlik onayi bekleyen 3) ---------------
$urunler = @(
  @{ ad='AUROLIS';        anahtar=@('aurolis') }
  @{ ad='BABYDENT';       anahtar=@('babydent') }
  @{ ad='BABYRESCUE';     anahtar=@('babyrescue') }
  @{ ad='BABYSHOWER';     anahtar=@('babyshower') }
  @{ ad='BABYSOFT';       anahtar=@('babysoft') }
  @{ ad='BABYSOL';        anahtar=@('babysol'); gunes=$true }
  @{ ad='BRIGHT SMILE';   anahtar=@('brightsmile','brigtsmile') }
  @{ ad='BUGUARD';        anahtar=@('buguard','buguar') }
  @{ ad='CAL JAW';        anahtar=@('caljaw','calmjaw') }
  @{ ad='CALMAROS';       anahtar=@('calmaros') }
  @{ ad='CALMORIS';       anahtar=@('calmoris') }
  @{ ad='DERMABED';       anahtar=@('dermabed') }
  @{ ad='DERMACORN';      anahtar=@('dermacorn') }
  @{ ad='DERMAGUARD';     anahtar=@('dermaguard','dermaguards','dermagurd') }
  @{ ad='DERMAMOVERA';    anahtar=@('dermamovera') }
  @{ ad='DERMANOVA';      anahtar=@('dermanova') }
  @{ ad='DERMARNICA';     anahtar=@('dermarnica') }
  @{ ad='DERMASTRA';      anahtar=@('dermastra','demastra') }
  @{ ad='DERMAVASC';      anahtar=@('dermavasc','dermavs','dermavsc') }
  @{ ad='DORSIVIA';       anahtar=@('dorsivia') }
  @{ ad='EARCLIA';        anahtar=@('earclia','earlica') }
  @{ ad='EASYCOMB';       anahtar=@('easycomb') }
  @{ ad='FEMISIA';        anahtar=@('femisia') }
  @{ ad='HAIR NOURISHER'; anahtar=@('hairnourisher','hairnouriisher','hairnoushier') }
  @{ ad='HYDRAVIE';       anahtar=@('hydravie') }
  @{ ad='INTIMBLANC';     anahtar=@('intimblanc') }
  @{ ad='KINESIS+';       anahtar=@('kinesis') }
  @{ ad='LIFTELLE';       anahtar=@('liftelle','liftella') }
  @{ ad='LIPVORA';        anahtar=@('lipvora') }
  @{ ad='LUCIDERM';       anahtar=@('luciderm','lucidem') }
  @{ ad='MENTHALIS';      anahtar=@('menthalis') }
  @{ ad='MINISOOTH';      anahtar=@('minisooth') }
  @{ ad='NOMORE';         anahtar=@('nomore') }
  @{ ad='OPTYWAVE';       anahtar=@('optywave') }
  @{ ad='ORAGARDE';       anahtar=@('oragarde') }
  @{ ad='SERALIMBO';      anahtar=@('seralimbo') }
  @{ ad='SOFTGUARD';      anahtar=@('softguard') }
  @{ ad='SUNACNEA';       anahtar=@('sunacnea'); gunes=$true }
  @{ ad='VIREON';         anahtar=@('vireon') }
)

# --- Belge turleri ---------------------------------------------------------
$turler = [ordered]@{
  'Etiket'      = @('etiket','label','cmyk')
  'Kutu'        = @('kutu','karton','box')
  # 🔴 Formul dosyalari her zaman "formul" adini tasimiyor:
  #    LIPVORA'da 'lipvora.xlsx' (INCI/CAS/EC tablosu),
  #    INTIMBLANC'ta 'İçerik Oran.docx'. Ikisi de once EKSIK sanildi.
  'Formul'      = @('formul','uts','icerikoran','icerik oran')
  # 'mikrob' gevsek tutuldu: klasor adi 'mikrob,yolojik kalite anal,z'
  # (virguller bozulmus İ harfi), dosya adlari da 'mikrobiyolik' gibi degisik.
  'Mikrobiyo'   = @('mikrob','microbio')
  'Stabilite'   = @('stabilite','stability')
  'Challenge'   = @('challenge','challange')
  'SPF'         = @()   # yalniz klasor yolundan bulunur, asagiya bak
  'MoCRA'       = @('mocra','fda')
  'GuvenlilikR' = @('guvenlilik','ugr','safety','cpsr')
}

# --- Tum dosyalari topla ---------------------------------------------------
$ubdKok = Join-Path $Kok "urun-icerik\urun-bilgilendirme-dosyalari"
$spfKok = Duzle (Join-Path $Kok "test-guvenlik-raporlari\analiz-testleri\spf")
$guvKok = Duzle (Join-Path $Kok "test-guvenlik-raporlari\guvenlik-raporlari")
$testKok = Duzle (Join-Path $Kok "test-guvenlik-raporlari")

$hepsi = Get-ChildItem $TaramaKoku -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
  # 🔴 Urun klasoru icindeki dosya, ADI yanlis yazilmis olsa bile o urune aittir.
  #    Sadece dosya adiyla eslestirince "dermagurd etıket.jpg" ve
  #    "dermavs etıket.jpg" bulunamadi, iki etiket YOK sanildi.
  $ubdUrun = ""
  if ($_.FullName.StartsWith($ubdKok, 'OrdinalIgnoreCase')) {
    $kalan = $_.FullName.Substring($ubdKok.Length).TrimStart('\')
    $ubdUrun = Duzle ($kalan -split '\\')[0]
  }
  [pscustomobject]@{
    Ad         = Duzle $_.Name
    Yol        = Duzle $_.DirectoryName
    KlasorAdi  = Duzle (Split-Path $_.DirectoryName -Leaf)
    UbdUrun    = $ubdUrun
  }
}
if ($hepsi.Count -eq 0) { Write-Host "BASARISIZ - hic dosya taranamadi" -ForegroundColor Red; exit 1 }
Write-Host "Taranan dosya: $($hepsi.Count)"

$sonuc = @()
foreach ($u in $urunler) {
  $satir = [ordered]@{ Urun = $u.ad }
  $eslesen = @($hepsi | Where-Object {
    $ad = $_.Ad; $ubd = $_.UbdUrun
    ($u.anahtar | Where-Object { $ad.Contains($_) }) -or
    ($ubd -and ($u.anahtar | Where-Object { $ubd.Contains($_) }))
  })

  foreach ($t in $turler.Keys) {
    # 🔴 SPF olcum testi SADECE gunes urunleri icin gereklidir.
    if ($t -eq 'SPF' -and -not $u.gunes) { $satir[$t] = '.'; continue }

    $var = $false
    foreach ($d in $eslesen) {
      if ($t -eq 'SPF') {
        # 🔴 SPF KURALI UC KEZ YANLIS KURULDU. Sirasiyla:
        #    1) Dosya adinda "spf" arandi -> "SUNACNEA 30 SPF.pdf" (guvenlilik
        #       raporu) ve "Babysol +50spf" (KLASOR adi) yanlis "var" uretti.
        #    2) Yalniz analiz-testleri\spf klasoru sayildi -> bu sefer GERCEK
        #       raporlar kacirildi ve "SPF olcumu hic yok" denildi. Yanlisti.
        #    3) Ad + tek klasor birlestirildi -> BABYSOL'unki yine kacti,
        #       cunku dosyanin adi sadece "babysol.pdf" ve BASKA bir spf
        #       klasorunde: test-guvenlik-raporlari\spf\ (analiz-testleri
        #       altindaki spf klasoru BOS bir kopya).
        #
        #    Dogru kural: adi TAM 'spf' olan HERHANGI bir klasordeki dosya
        #    sayilir; ayrica adinda "spf" gecen dosyalar (guvenlilik raporu
        #    klasoru ve MoCRA/FDA kayitlari haric).
        #    'Babysol +50spf' klasoru elenir cunku adi TAM 'spf' degil.
        if ($d.KlasorAdi -eq 'spf') { $var = $true; break }
        if ($d.Ad.Contains('spf') -and -not $d.Yol.StartsWith($guvKok) `
            -and -not $d.Ad.Contains('mocra') -and -not $d.Ad.Contains('fda')) {
          $var = $true; break
        }
        continue
      }
      if ($t -eq 'GuvenlilikR' -and $d.Yol.StartsWith($guvKok)) { $var = $true; break }

      # 🔴 BELGE TURU KLASOR ADINDA DA OLABILIR - AMA SADECE TEST KLASORLERINDE.
      #
      # test-guvenlik-raporlari altindaki asil klasorler dosyalari
      # '<urun>.pdf' diye adlandiriyor; test turu KLASOR adinda duruyor
      # (challange\babysol.pdf, stabilite\babysol.pdf ...).
      #
      # Ama bu kural HER YERDE uygulanirsa yanlis pozitif uretir:
      #   · 'calmoris ugr eksık' klasor adi 'ugr' iceriyor -> raporun YOK
      #     oldugunu soyleyen not, raporun VAR olmasi sayildi
      #   · 'kutu-icerik-son' klasoru 'kutu' iceriyor -> kutu metni,
      #     ambalaj dosyasi sanildi
      # Bu yuzden klasor adindan tur cikarimi YALNIZ test klasorlerinde gecerli.
      $klasordenSay = $d.Yol.StartsWith($testKok)
      foreach ($kalip in $turler[$t]) {
        if ($d.Ad.Contains($kalip)) { $var = $true; break }
        if ($klasordenSay -and $d.KlasorAdi.Contains($kalip)) { $var = $true; break }
      }
      if ($var) { break }
      # Urun klasorundeki, MoCRA olmayan bir xlsx formul sayilir
      # (LIPVORA'nin formulu 'lipvora.xlsx' adiyla duruyordu).
      if ($t -eq 'Formul' -and $d.UbdUrun -and $d.Ad.EndsWith('xlsx') `
          -and -not $d.Ad.Contains('mocra') -and -not $d.Ad.Contains('fda')) {
        $var = $true; break
      }
    }
    $satir[$t] = if ($var) { '+' } else { '-' }
  }
  $satir['Dosya'] = $eslesen.Count
  $sonuc += [pscustomobject]$satir
}

Write-Host "Denetlenen urun: $($sonuc.Count)"
Write-Host ""
$sonuc | Format-Table -AutoSize

Write-Host ""
Write-Host "=== BELGE TURUNE GORE EKSIK ===" -ForegroundColor Cyan
foreach ($t in $turler.Keys) {
  $eksikler = @()
  foreach ($s in $sonuc) { if ($s.$t -eq '-') { $eksikler += $s.Urun } }
  $gecerli = @($sonuc | Where-Object { $_.$t -ne '.' }).Count
  $renk = if ($eksikler.Count -eq 0) { 'Green' } elseif ($eksikler.Count -le 3) { 'Yellow' } else { 'Red' }
  Write-Host ("  {0,-12} eksik: {1,2} / {2}" -f $t, $eksikler.Count, $gecerli) -ForegroundColor $renk
  if ($eksikler.Count -gt 0) {
    Write-Host ("      " + ($eksikler -join ', ')) -ForegroundColor DarkGray
  }
}

Write-Host ""
Write-Host "=== HIC BELGESI OLMAYAN URUNLER ===" -ForegroundColor Cyan
$bos = @($sonuc | Where-Object { $_.Dosya -eq 0 })
if ($bos.Count -eq 0) { Write-Host "  yok" -ForegroundColor Green }
else { foreach ($b in $bos) { Write-Host "  $($b.Urun)" -ForegroundColor Red } }

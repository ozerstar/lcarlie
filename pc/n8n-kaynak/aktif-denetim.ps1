# urunler.js icindeki 'aktifler' listelerini resmi kutu belgeleriyle karsilastirir.
# Amac: INCI'de olmayan bir bileseni ajanin saymasini engellemek.
param(
  [string]$UrunlerJs = "C:\Users\ozery\OneDrive\Masaüstü\07 YAZILIM\LCARLIE-n8n-kaynak\urunler.js",
  [string]$KutuKlasor = "C:\Users\ozery\AppData\Local\Temp\claude\C--Users-ozery\60812845-7eec-41bc-8de3-b3471b3ac11d\scratchpad\kutu"
)

$js = Get-Content -LiteralPath $UrunlerJs -Raw -Encoding UTF8

# Kutu metinlerini yukle
$kutular = @{}
Get-ChildItem $KutuKlasor -Filter *.txt | ForEach-Object {
  $ad = ($_.BaseName -replace '^\d+\s*-?\s*','').Trim().ToLowerInvariant()
  $kutular[$ad] = (Get-Content $_.FullName -Raw -Encoding UTF8).ToLowerInvariant()
}

# Turkce -> Latince/INCI karsiliklari (kutu belgeleri iki dilde de yaziyor)
$esler = @{
  'lavanta'   = @('lavanta','lavandula','lavender')
  'nane'      = @('nane','mentha','peppermint')
  'bergamot'  = @('bergamot','aurantium bergamia')
  'niaouli'   = @('niaouli','quinquenervia')
  'palmarosa' = @('palmarosa','cymbopogon martinii')
  'servi'     = @('servi','cypress','cupressus')
  'ylang'     = @('ylang','cananga')
  'badem'     = @('badem','amygdalus','almond')
  'aloe'      = @('aloe','barbadensis')
  'papatya'   = @('papatya','chamomilla','matricaria','chamomile')
  'jojoba'    = @('jojoba','simmondsia')
  'shea'      = @('shea','butyrospermum')
  'vetiver'   = @('vetiver','vetiveria')
  'pacul'     = @('pacul','patchouli','pogostemon')
  'melisa'    = @('melisa','melissa')
  'aynisefa'  = @('aynisefa','aynısefa','calendula')
  'tamanu'    = @('tamanu','calophyllum')
  'hodan'     = @('hodan','borago','borage')
  'avokado'   = @('avokado','persea','avocado')
  'gunluk'    = @('gunluk','günlük','boswellia','frankincense','akgunluk','akgünlük')
  'vitamin'   = @('vitamin','tocopherol','tokoferol')
  'cay agaci' = @('cay agaci','çay ağacı','melaleuca alternifolia','tea tree')
  'sogut'     = @('sogut','söğüt','salix')
  'yesil cay' = @('yesil cay','yeşil çay','camellia sinensis','green tea')
  'gul'       = @('gul suyu','gül suyu','rosa damascena','rose water')
  'pantenol'  = @('pantenol','panthenol')   # kutuda 'Panthenol', bizde 'Pantenol'
  'centella'  = @('centella','cica')
  'arnica'    = @('arnica','arnika')
  'kantaron'  = @('kantaron','hypericum')
  'zerdecal'  = @('zerdecal','zerdeçal','curcuma','turmeric')
  'nar'       = @('nar ','punica','pomegranate')
  'uzum'      = @('uzum','üzüm','vitis')
  'zeytin'    = @('zeytin','olea','olive')
  'hindistan' = @('hindistan','cocos','coconut')
  'kekik'     = @('kekik','thymus','origanum')
  'biberiye'  = @('biberiye','rosmarinus','rosemary')
  'okaliptus' = @('okaliptus','eucalyptus')
  'sedir'     = @('sedir','cedrus','cedarwood')
  'limon'     = @('limon','citrus limon','lemongrass','cymbopogon')
  'karanfil'  = @('karanfil','eugenia','clove')
  'tarcin'    = @('tarcin','tarçın','cinnamom','cinnamon')
  'neem'      = @('neem','azadirachta')
  'cinko'     = @('cinko','çinko','zinc')
  'hyaluron'  = @('hyaluron','hiyaluron','sodium hyaluronate')
  'niasinamid'= @('niasinamid','niacinamide')
  'seramid'   = @('seramid','ceramide')
  'skualan'   = @('skualan','squalane')
  'bakuchiol' = @('bakuchiol','babchi')
  'yulaf'     = @('yulaf','avena','oat')
  'bisabolol' = @('bisabolol')
  'allantoin' = @('allantoin','alantoin')
}

$bulgular = @()
$kontrolEdilen = 0
$atlanan = @()

# Her urun blogunu yakala
$bloklar = [regex]::Matches($js, "ad:\s*'([^']+)'[\s\S]{0,12000}?aktifler:\s*\[([^\]]*)\]")

# 🔴 Dosyada kac 'aktifler' varsa o kadar blok yakalanmali.
# Pencere dar kalirsa uzun aciklamali urunler SESSIZCE atlanir (ilk denemede
# 4000 karakter yetmedi, 30 urunun 14'u denetlenmeden gecti).
$toplamAktif = ([regex]::Matches($js, "aktifler:\s*\[")).Count
Write-Host "Dosyadaki 'aktifler' sayisi : $toplamAktif"
Write-Host "Yakalanan blok sayisi       : $($bloklar.Count)"
if ($bloklar.Count -lt $toplamAktif) {
  Write-Host "BASARISIZ - $($toplamAktif - $bloklar.Count) urun blogu yakalanamadi" -ForegroundColor Red
  exit 1
}
foreach ($b in $bloklar) {
  $urunAd = $b.Groups[1].Value.Trim()
  $aktifHam = $b.Groups[2].Value
  $aktifler = [regex]::Matches($aktifHam, "'([^']+)'") | ForEach-Object { $_.Groups[1].Value }
  if (-not $aktifler) { continue }

  # Kutu dosyasini bul
  # 🔴 .ToLowerInvariant() SART. Turkce yerel ayarda .ToLower() 'I' harfini
  #    'ı' (noktasiz) yapar; "LUCIDERM" -> "lucıderm" olur ve dosya adiyla
  #    eslesmez. Ilk calistirmada adinda I olan 12 urun bu yuzden SESSIZCE
  #    denetlenmeden gecti.
  $anahtar = ($urunAd -replace "[^A-Za-z]","").ToLowerInvariant()

  # Dosya adi urun adindan farkli olanlar (yazim hatasi veya eski ad)
  $takmaAdlar = @{
    'caljaw'        = 'calmjaw'          # dosya: 19-calmjaw
    'hairnourisher' = 'hairnouriisher'   # dosya adinda fazladan 'i' var
  }
  if ($takmaAdlar.ContainsKey($anahtar)) { $anahtar = $takmaAdlar[$anahtar] }

  $kutu = $null
  foreach ($k in $kutular.Keys) {
    $kk = ($k -replace "[^a-z]","")
    if ($kk -and ($kk -eq $anahtar -or $kk.StartsWith($anahtar) -or $anahtar.StartsWith($kk))) { $kutu = $kutular[$k]; break }
  }
  if (-not $kutu) { $atlanan += $urunAd; continue }
  $kontrolEdilen++

  foreach ($a in $aktifler) {
    $aLower = $a.ToLowerInvariant()
    # Hangi es anahtarina denk geliyor?
    $adaylar = @()
    foreach ($e in $esler.Keys) {
      if ($aLower -like "*$e*") { $adaylar += $esler[$e] }
    }
    if (-not $adaylar) {
      # Es tablosunda yoksa ilk kelimeyi ara
      $ilk = ($aLower -split '[ &]')[0]
      if ($ilk.Length -lt 4) { continue }
      $adaylar = @($ilk)
    }
    $var = $false
    foreach ($ad in $adaylar) { if ($kutu.Contains($ad)) { $var = $true; break } }
    if (-not $var) {
      $bulgular += [pscustomobject]@{ Urun = $urunAd; Bilesen = $a }
    }
  }
}

Write-Host "Kontrol edilen urun : $kontrolEdilen"
Write-Host "Kutu belgesi bulunamayan: $($atlanan.Count)  ($($atlanan -join ', '))"
Write-Host ""
# 🔴 SIFIR KONTROL = BASARISIZ. Yoksa regex bozulunca "TEMIZ" yazip
#    hicbir sey denetlemeden yesil yanar - bu tuzaga bir kez dusuldu.
if ($kontrolEdilen -eq 0) {
  Write-Host "BASARISIZ - hic urun kontrol edilemedi (regex veya yol hatasi)" -ForegroundColor Red
  exit 1
}
if ($bulgular.Count -eq 0) {
  Write-Host "TEMIZ - ajanin saydigi tum bilesenler kutu belgesinde geciyor" -ForegroundColor Green
} else {
  Write-Host "SUPHELI - kutu belgesinde bulunamayan bilesenler:" -ForegroundColor Yellow
  $bulgular | Format-Table -AutoSize
}


# xlsx -> TSV (Office kurulu olmadan, dogrudan XML'den)
param([string]$Kok, [string]$Cikti)

$ns = @{ s = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main' }

# 1) Paylasilan metinler
$ss = @()
$ssPath = Join-Path $Kok 'xl\sharedStrings.xml'
if (Test-Path $ssPath) {
    [xml]$ssXml = Get-Content $ssPath -Encoding UTF8 -Raw
    foreach ($si in $ssXml.sst.si) {
        # <si> icinde tek <t> ya da birden cok <r><t> olabilir
        if ($si.t) {
            $ss += [string]($si.t.'#text' ?? $si.t)
        } elseif ($si.r) {
            $ss += (($si.r | ForEach-Object { [string]($_.t.'#text' ?? $_.t) }) -join '')
        } else { $ss += '' }
    }
}
Write-Host "Paylasilan metin sayisi: $($ss.Count)"

# 2) Sayfa adlari
[xml]$wb = Get-Content (Join-Path $Kok 'xl\workbook.xml') -Encoding UTF8 -Raw
$adlar = @($wb.workbook.sheets.sheet | ForEach-Object { $_.name })

# Sutun harfini indekse cevir (A=0, B=1, ... AA=26)
function Col-Index([string]$ref) {
    $h = ($ref -replace '\d', '')
    $n = 0
    foreach ($c in $h.ToCharArray()) { $n = $n * 26 + ([int][char]$c - 64) }
    return $n - 1
}

for ($i = 1; $i -le $adlar.Count; $i++) {
    $sp = Join-Path $Kok "xl\worksheets\sheet$i.xml"
    if (-not (Test-Path $sp)) { continue }
    [xml]$sh = Get-Content $sp -Encoding UTF8 -Raw

    $satirlar = @()
    foreach ($row in $sh.worksheet.sheetData.row) {
        $hucreler = @{}
        $maxIdx = -1
        foreach ($c in $row.c) {
            $idx = Col-Index $c.r
            $deger = ''
            if ($c.t -eq 's') {
                $k = [int]$c.v
                if ($k -lt $ss.Count) { $deger = $ss[$k] }
            } elseif ($c.t -eq 'inlineStr') {
                $deger = [string]($c.is.t.'#text' ?? $c.is.t)
            } elseif ($null -ne $c.v) {
                $deger = [string]($c.v.'#text' ?? $c.v)
            }
            # TSV'yi bozmasin
            $deger = $deger -replace "`r?`n", ' | ' -replace "`t", ' '
            $hucreler[$idx] = $deger
            if ($idx -gt $maxIdx) { $maxIdx = $idx }
        }
        if ($maxIdx -lt 0) { $satirlar += ''; continue }
        $dizi = @(0..$maxIdx | ForEach-Object { if ($hucreler.ContainsKey($_)) { $hucreler[$_] } else { '' } })
        $satirlar += ($dizi -join "`t")
    }

    $ad = $adlar[$i-1] -replace '[^\w -]', '_'
    $hedef = Join-Path $Cikti ("{0}_{1}.tsv" -f $i, $ad)
    $satirlar | Set-Content -LiteralPath $hedef -Encoding UTF8
    Write-Host ("{0} -> {1} satir" -f $adlar[$i-1], $satirlar.Count)
}

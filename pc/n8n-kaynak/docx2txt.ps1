# DOCX -> duz metin (Word kurulu olmadan, dogrudan XML'den)
param([string]$Klasor, [string]$Cikti)

Add-Type -AssemblyName System.IO.Compression.FileSystem
New-Item -ItemType Directory -Force -Path $Cikti | Out-Null

$dosyalar = Get-ChildItem -LiteralPath $Klasor -Filter *.docx -File |
            Where-Object { -not $_.Name.StartsWith('~$') }

foreach ($d in $dosyalar) {
    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($d.FullName)
        try {
            $entry = $zip.Entries | Where-Object { $_.FullName -eq 'word/document.xml' }
            if (-not $entry) { Write-Host "ATLA $($d.Name) - document.xml yok"; continue }
            $sr = New-Object System.IO.StreamReader($entry.Open(), [Text.Encoding]::UTF8)
            $xml = $sr.ReadToEnd()
            $sr.Close()
        } finally { $zip.Dispose() }

        # Paragraf ve satir sonlarini korumak icin once isaretle
        $xml = $xml -replace '</w:p>', "`n"
        $xml = $xml -replace '<w:br[^>]*/>', "`n"
        $xml = $xml -replace '</w:tc>', "`t"
        $xml = $xml -replace '</w:tr>', "`n"
        # Tum etiketleri sil
        $metin = [regex]::Replace($xml, '<[^>]+>', '')
        # XML varliklari
        $metin = $metin -replace '&amp;','&' -replace '&lt;','<' -replace '&gt;','>' -replace '&quot;','"' -replace '&#39;',"'"
        # Fazla bosluklari topla
        $metin = ($metin -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }) -join "`n"

        $ad = [IO.Path]::GetFileNameWithoutExtension($d.Name) -replace '[^\w\-. ]','_'
        $hedef = Join-Path $Cikti "$ad.txt"
        $metin | Set-Content -LiteralPath $hedef -Encoding UTF8
        Write-Host ("{0,-46} -> {1,6} karakter" -f $d.Name, $metin.Length)
    } catch {
        Write-Host "HATA $($d.Name): $($_.Exception.Message)"
    }
}

# Fotograftan bolge kirpip buyutur (etiket okumak icin)
param(
  [Parameter(Mandatory=$true)][string]$Kaynak,
  [Parameter(Mandatory=$true)][string]$Hedef,
  [int]$X, [int]$Y, [int]$G, [int]$Y2,     # sol, ust, genislik, yukseklik
  [double]$Kat = 3.0
)
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile($Kaynak)
try {
  if ($G -le 0) { $G = $img.Width - $X }
  if ($Y2 -le 0) { $Y2 = $img.Height - $Y }
  $rect = New-Object System.Drawing.Rectangle $X, $Y, $G, $Y2
  $crop = New-Object System.Drawing.Bitmap $G, $Y2
  $g1 = [System.Drawing.Graphics]::FromImage($crop)
  $g1.DrawImage($img, (New-Object System.Drawing.Rectangle 0,0,$G,$Y2), $rect, [System.Drawing.GraphicsUnit]::Pixel)
  $g1.Dispose()

  $nw = [int]($G * $Kat); $nh = [int]($Y2 * $Kat)
  $big = New-Object System.Drawing.Bitmap $nw, $nh
  $g2 = [System.Drawing.Graphics]::FromImage($big)
  $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g2.SmoothingMode     = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
  $g2.DrawImage($crop, 0, 0, $nw, $nh)
  $g2.Dispose()

  $big.Save($Hedef, [System.Drawing.Imaging.ImageFormat]::Png)
  Write-Host ("Kaynak {0}x{1} -> kirpim {2}x{3} -> cikti {4}x{5}" -f $img.Width,$img.Height,$G,$Y2,$nw,$nh)
  $crop.Dispose(); $big.Dispose()
} finally { $img.Dispose() }

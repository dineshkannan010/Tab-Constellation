Add-Type -AssemblyName System.Drawing

$majors = @(
  @{ X=30; Y=36; R=4.5 },
  @{ X=60; Y=58; R=6.5 },
  @{ X=92; Y=42; R=4.0 },
  @{ X=50; Y=92; R=4.0 },
  @{ X=86; Y=96; R=5.0 }
)
$lines = @(
  @(30,36,60,58),
  @(60,58,92,42),
  @(60,58,50,92),
  @(50,92,86,96),
  @(92,42,86,96)
)
$smalls = @(
  @{ X=20;  Y=78;  R=1.6 },
  @{ X=108; Y=70;  R=1.4 },
  @{ X=74;  Y=22;  R=1.4 },
  @{ X=40;  Y=110; R=1.2 },
  @{ X=100; Y=112; R=1.2 }
)

$sizes = @(16, 32, 48, 128)
$outDir = "F:\Tab_Constellation\extension\icons"

foreach ($size in $sizes) {
    $scale = $size / 128.0
    $bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)

    # Rounded rect background
    $bgColor = [System.Drawing.Color]::FromArgb(255, 11, 26, 58)
    $bgBrush = New-Object System.Drawing.SolidBrush($bgColor)
    $radius = [Math]::Max(1, [int]($size * (24.0 / 128.0)))
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $radius * 2
    $w = $size; $h = $size
    if ($radius -gt 0) {
        $path.AddArc(0, 0, $d, $d, 180, 90)
        $path.AddArc($w - $d, 0, $d, $d, 270, 90)
        $path.AddArc($w - $d, $h - $d, $d, $d, 0, 90)
        $path.AddArc(0, $h - $d, $d, $d, 90, 90)
        $path.CloseFigure()
        $g.FillPath($bgBrush, $path)
    } else {
        $g.FillRectangle($bgBrush, 0, 0, $w, $h)
    }

    # Connecting lines (skip for the smallest size, too noisy)
    if ($size -ge 32) {
        $lineColor = [System.Drawing.Color]::FromArgb(217, 59, 108, 201)
        $penWidth = [float]([Math]::Max(0.8, 1.5 * $scale))
        $pen = New-Object System.Drawing.Pen($lineColor, $penWidth)
        $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        foreach ($l in $lines) {
            $g.DrawLine($pen,
                [float]($l[0] * $scale), [float]($l[1] * $scale),
                [float]($l[2] * $scale), [float]($l[3] * $scale))
        }
        $pen.Dispose()
    }

    # Major stars
    $majorBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 232, 240, 255))
    foreach ($s in $majors) {
        $r = [float]([Math]::Max(0.8, $s.R * $scale))
        $cx = [float]($s.X * $scale)
        $cy = [float]($s.Y * $scale)
        $g.FillEllipse($majorBrush, $cx - $r, $cy - $r, 2 * $r, 2 * $r)
    }

    # Small stars (skip for 16px)
    if ($size -ge 32) {
        $smallBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 159, 182, 232))
        foreach ($s in $smalls) {
            $r = [float]([Math]::Max(0.6, $s.R * $scale))
            $cx = [float]($s.X * $scale)
            $cy = [float]($s.Y * $scale)
            $g.FillEllipse($smallBrush, $cx - $r, $cy - $r, 2 * $r, 2 * $r)
        }
        $smallBrush.Dispose()
    }

    $outPath = Join-Path $outDir ("icon{0}.png" -f $size)
    $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)

    $majorBrush.Dispose()
    $bgBrush.Dispose()
    $path.Dispose()
    $g.Dispose()
    $bmp.Dispose()

    Write-Output "Wrote $outPath"
}

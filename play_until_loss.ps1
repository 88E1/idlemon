# Requires env vars: PS_USERNAME, PS_PASSWORD
# Optional: CURSOR_API_KEY (only needed for --decision-mode llm)

if (-not $env:PS_USERNAME -or -not $env:PS_PASSWORD) {
    Write-Error "Set PS_USERNAME and PS_PASSWORD environment variables before running."
    exit 1
}

$winCount = 0
while ($true) {
    Write-Host "========================================"
    Write-Host "Queueing game $($winCount + 1)..."
    Write-Host "========================================"
    if (Test-Path bot.out.txt) { Remove-Item bot.out.txt -Force }
    if (Test-Path bot.err.txt) { Remove-Item bot.err.txt -Force }

    $proc = Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList @(
        "run.py",
        "--websocket-uri", "wss://sim3.psim.us/showdown/websocket",
        "--ps-username", $env:PS_USERNAME,
        "--ps-password", $env:PS_PASSWORD,
        "--bot-mode", "search_ladder",
        "--pokemon-format", "gen9championsvgc2026regmb",
        "--team-name", "gen9vgc/sample",
        "--decision-mode", "agent",
        "--log-level", "INFO",
        "--run-count", "1"
    ) -RedirectStandardOutput "bot.out.txt" -RedirectStandardError "bot.err.txt" -NoNewWindow -PassThru

    $lastLineCount = 0
    while (-not $proc.HasExited) {
        Start-Sleep -Seconds 3
        if (Test-Path bot.out.txt) {
            try {
                $content = Get-Content bot.out.txt -ErrorAction SilentlyContinue
                if ($content -and $content.Count -gt $lastLineCount) {
                    $content[$lastLineCount..($content.Count-1)] | ForEach-Object { Write-Host $_ }
                    $lastLineCount = $content.Count
                }
            } catch {}
        }
    }

    # Print any remaining output
    if (Test-Path bot.out.txt) {
        try {
            $content = Get-Content bot.out.txt -ErrorAction SilentlyContinue
            if ($content -and $content.Count -gt $lastLineCount) {
                $content[$lastLineCount..($content.Count-1)] | ForEach-Object { Write-Host $_ }
            }
        } catch {}
    }

    # Check if we won or lost
    if (Test-Path bot.out.txt) {
        $outText = Get-Content bot.out.txt -Raw
        if ($outText -like "*Lost with team*") {
            Write-Host "========================================"
            Write-Host "We lost! Stopping the queue."
            Write-Host "Final streak: $winCount wins."
            Write-Host "========================================"
            break
        } elseif ($outText -like "*Won with team*") {
            $winCount++
            Write-Host "========================================"
            Write-Host "We won! Current streak: $winCount wins."
            Write-Host "Queueing next game in 10 seconds..."
            Write-Host "========================================"
            Start-Sleep -Seconds 10
        } else {
            Write-Host "Battle ended unexpectedly (no win/loss found). Stopping."
            break
        }
    } else {
        Write-Host "No output file found. Stopping."
        break
    }
}

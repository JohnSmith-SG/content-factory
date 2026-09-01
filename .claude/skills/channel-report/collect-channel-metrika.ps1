# Метрика для /channel-report (см. SKILL.md, шаг 2). Один вызов — без окон подтверждения.
# Тянет из того же счётчика Яндекс.Метрики, что и /site-report (111567095):
#   1. цель click_channel — переходы САЙТ -> КАНАЛ (точно, это цель);
#   2. визиты с источником Telegram — переходы КАНАЛ -> САЙТ (приблизительно:
#      браузер Telegram часто режет реферер, тогда визит уходит в "прямые").
# Токен и id целей переиспользуются из секретов проекта Career (read-only).

$secretsDir = "C:\Users\kitrina.lashonne\Documents\KitrinaClaudeCode\Career\.claude\secrets"
$token   = (Get-Content "$secretsDir\yandex-metrika-token.txt" -Raw).Trim()
$goalIds = Get-Content "$secretsDir\metrika-goal-ids.json" -Raw | ConvertFrom-Json
$headers = @{ Authorization = "OAuth $token" }
$base    = "https://api-metrika.yandex.net/stat/v1/data"
$counter = "111567095"

$today   = Get-Date
$d2      = $today.ToString("yyyy-MM-dd")
$d1_day  = $today.AddDays(-1).ToString("yyyy-MM-dd")
$d1_7d   = $today.AddDays(-6).ToString("yyyy-MM-dd")
$d1_30d  = $today.AddDays(-29).ToString("yyyy-MM-dd")

$cc = $goalIds.click_channel
$goalMetrics = "ym:s:visits,ym:s:goal${cc}reaches,ym:s:goal${cc}conversionRate"

function Get-Row($date1, $date2, $metrics) {
    $r = Invoke-RestMethod -Uri "$base`?ids=$counter&date1=$date1&date2=$date2&metrics=$metrics" -Headers $headers
    if ($r.data.Count -gt 0) { $r.data[0].metrics } else { @() }
}

function Get-Breakdown($date1, $date2, $dimension) {
    $uri = "$base`?ids=$counter&date1=$date1&date2=$date2&metrics=ym:s:visits&dimensions=$dimension&sort=-ym:s:visits&limit=20"
    $r = Invoke-RestMethod -Uri $uri -Headers $headers
    $r.data | ForEach-Object { [PSCustomObject]@{ n = $_.dimensions[0].name; v = $_.metrics[0] } }
}

# click_channel: [visits, reaches, conversionRate]
Write-Output "=== CLICK_CHANNEL:day ==="  ; ConvertTo-Json -InputObject @(Get-Row $d1_day $d2 $goalMetrics) -Compress
Write-Output "=== CLICK_CHANNEL:7d ==="   ; ConvertTo-Json -InputObject @(Get-Row $d1_7d  $d2 $goalMetrics) -Compress
Write-Output "=== CLICK_CHANNEL:30d ==="  ; ConvertTo-Json -InputObject @(Get-Row $d1_30d $d2 $goalMetrics) -Compress

# источники: соцсети (Telegram обычно тут) и общая раскладка по типам источника
Write-Output "=== SOCIAL:7d ==="   ; ConvertTo-Json -InputObject @(Get-Breakdown $d1_7d  $d2 "ym:s:lastSocialNetwork") -Compress
Write-Output "=== SOCIAL:30d ==="  ; ConvertTo-Json -InputObject @(Get-Breakdown $d1_30d $d2 "ym:s:lastSocialNetwork") -Compress
Write-Output "=== SOURCES:30d ===" ; ConvertTo-Json -InputObject @(Get-Breakdown $d1_30d $d2 "ym:s:lastTrafficSource") -Compress

Write-Output "OK"

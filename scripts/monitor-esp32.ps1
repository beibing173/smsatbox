# ============================================================================
#  SMSATBOX · ESP32 串口实时监控脚本
#  ---------------------------------------------------------------------------
#  用途：持续监听 ESP32 串口，实时高亮 SIM / eUICC / 网络状态变化。
#        适合边插拔 SIM 卡边观察设备反应。
#
#  用法：
#    pwsh -File scripts\monitor-esp32.ps1
#    pwsh -File scripts\monitor-esp32.ps1 -Port COM5 -ShowAll
#
#  参数：
#    -Port    串口名，默认 COM4
#    -Baud    波特率，默认 115200
#    -ShowAll 显示全部日志（默认只显示关键事件）
#    -LogFile 日志文件路径，默认 .shots/esp32-monitor.log
# ============================================================================
param(
    [string]$Port = "COM4",
    [int]$Baud = 115200,
    [switch]$ShowAll,
    [string]$LogFile = "D:\SMSATBOX\.shots\esp32-monitor.log"
)

$ErrorActionPreference = "Stop"

# 确保日志目录存在
$logDir = Split-Path -Parent $LogFile
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force $logDir | Out-Null
}

function Write-Color($text, $color) {
    $prev = $Host.UI.RawUI.ForegroundColor
    $Host.UI.RawUI.ForegroundColor = $color
    Write-Host $text
    $Host.UI.RawUI.ForegroundColor = $prev
}

function Write-Both($text, $color) {
    Write-Color $text $color
    Add-Content -Path $LogFile -Value $text -Encoding UTF8
}

# 状态追踪
$script:lastSim = ""
$script:lastEuicc = ""
$script:lastReg = ""
$script:lastCarrier = ""

# 关键事件正则（只有匹配这些才高亮显示）
$patterns = @(
    @{ Regex = 'SIM=READY';                 Level = 'OK';      Msg = 'SIM 就绪' },
    @{ Regex = 'SIM=ABSENT';                Level = 'WARN';    Msg = 'SIM 未检测到' },
    @{ Regex = 'SIM not ready after retries'; Level = 'WARN';  Msg = 'SIM 初始化失败' },
    @{ Regex = 'cpin_ok=0 raw=';            Level = 'INFO';    Msg = 'CPIN 失败详情' },
    @{ Regex = 'eUICC detected';            Level = 'OK';      Msg = '检测到 eUICC' },
    @{ Regex = 'not an eUICC card';         Level = 'INFO';    Msg = '非 eUICC 卡' },
    @{ Regex = 'eUICC probe done';          Level = 'OK';      Msg = 'eUICC 探测完成' },
    @{ Regex = 'euicc report ok';           Level = 'OK';      Msg = 'eUICC 上报成功' },
    @{ Regex = 'AT handshake OK';           Level = 'OK';      Msg = '模组握手成功' },
    @{ Regex = 'modem stopped responding';  Level = 'WARN';    Msg = '模组失联' },
    @{ Regex = 'hard-resetting modem';      Level = 'WARN';    Msg = '硬复位模组' },
    @{ Regex = 'reg raw=';                  Level = 'INFO';    Msg = '网络注册' },
    @{ Regex = 'identity carrier=';         Level = 'INFO';    Msg = '运营商识别' },
    @{ Regex = 'new SMS';                   Level = 'OK';      Msg = '收到短信' },
    @{ Regex = 'incoming call';             Level = 'OK';      Msg = '收到来电' },
    @{ Regex = 'SMS sent';                  Level = 'OK';      Msg = '短信发送成功' },
    @{ Regex = 'report failed';             Level = 'WARN';    Msg = '云端上报失败' },
    @{ Regex = 'wifi connected';            Level = 'OK';      Msg = 'WiFi 已连接' },
    @{ Regex = 'cloud ready';               Level = 'INFO';    Msg = '云端就绪' },
    @{ Regex = 'not configured';            Level = 'WARN';    Msg = '未配网' }
)

$colorMap = @{
    'OK'   = 'Green'
    'WARN' = 'Yellow'
    'ERR'  = 'Red'
    'INFO' = 'DarkGray'
}

Write-Both "==============================================================" 'Cyan'
Write-Both "  SMSATBOX 串口监控" 'Cyan'
Write-Both "  端口: $Port @ $Baud" 'Cyan'
Write-Both "  日志: $LogFile" 'Cyan'
Write-Both "  只显示关键事件（加 -ShowAll 看全部）" 'Cyan'
Write-Both "  按 Ctrl+C 停止" 'Cyan'
Write-Both "==============================================================" 'Cyan'
Write-Both "" 'White'

# 打开串口
$serial = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
$serial.ReadTimeout = 500

try {
    $serial.Open()
    Write-Both "[$(Get-Date -Format 'HH:mm:ss')] 串口已打开，等待设备输出..." 'Cyan'

    # 触发一次复位，让主人能看到完整启动流程
    $serial.DtrEnable = $false
    $serial.RtsEnable = $true
    Start-Sleep -Milliseconds 150
    $serial.RtsEnable = $false
    Start-Sleep -Milliseconds 100
    $serial.DtrEnable = $true
    Start-Sleep -Milliseconds 100
    $serial.DtrEnable = $false
    Write-Both "[$(Get-Date -Format 'HH:mm:ss')] 已发送复位信号" 'Cyan'
    Write-Both "" 'White'

    $buffer = ""
    $lineCount = 0
    $startTime = Get-Date

    while ($true) {
        try {
            $chunk = $serial.ReadExisting()
        } catch {
            $chunk = ""
        }

        if ($chunk) {
            $buffer += $chunk

            # 按行处理
            while ($buffer.Contains("`n")) {
                $idx = $buffer.IndexOf("`n")
                $line = $buffer.Substring(0, $idx).TrimEnd("`r")
                $buffer = $buffer.Substring($idx + 1)

                if (-not $line) { continue }
                $lineCount++

                # 只处理带时间戳的固件日志
                if ($line -match '^\[(\d{2}):(\d{2}):(\d{2})\]') {
                    $matched = $false

                    foreach ($p in $patterns) {
                        if ($line -match $p.Regex) {
                            $matched = $true
                            $color = $colorMap[$p.Level]
                            $ts = Get-Date -Format 'HH:mm:ss'
                            Write-Both "[$ts] $($p.Msg): $line" $color
                            break
                        }
                    }

                    if (-not $matched -and $ShowAll) {
                        Write-Both "         $line" 'DarkGray'
                    }
                } elseif ($ShowAll) {
                    Write-Host "         $line" -ForegroundColor DarkGray
                }
            }
        }

        Start-Sleep -Milliseconds 40
    }
} catch [System.IO.IOException] {
    Write-Host ""
    Write-Both "串口错误: $($_.Exception.Message)" 'Red'
    Write-Both "请检查：" 'Yellow'
    Write-Both "  1. 设备是否插好" 'Yellow'
    Write-Both "  2. 串口是否被其他程序占用（串口监视器、PlatformIO 等）" 'Yellow'
    Write-Both "  3. 端口名是否正确（当前用 $Port）" 'Yellow'
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    Write-Both "" 'White'
    Write-Both "==============================================================" 'Cyan'
    Write-Both "  监控结束，共处理 $lineCount 行" 'Cyan'
    Write-Both "  日志已保存: $LogFile" 'Cyan'
    Write-Both "==============================================================" 'Cyan'
}

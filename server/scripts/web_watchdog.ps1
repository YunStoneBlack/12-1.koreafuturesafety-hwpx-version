# 웹판 자동 실행·감시 — API 서버, PDF 렌더 워커, (선택) Cloudflare 터널을 띄우고, 꺼지면 다시 띄운다.
#
# 왜 Windows 서비스(NSSM)가 아니라 이 방식인가(server/README_DEPLOY.md 5번 참고):
#  - PDF 워커는 한글 프로그램을 자동 조작하는데, 서비스(로그인 화면 없는 세션 0)에서는 한글 자동화가 안 되는 경우가 흔하다
#    → 로그인한 사용자 세션에서 돌아야 한다.
#  - 서비스 등록은 관리자 권한이 필요하지만, 이 방식은 필요 없다(시작프로그램 바로가기로 로그인 시 자동 실행).
#  재부팅 후 아무도 로그인 안 해도 켜지게 하려면 Windows 자동 로그인을 따로 켜야 한다.
#
# 실행: powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File web_watchdog.ps1 [-Tunnel]
#   -Tunnel : Cloudflare 임시 주소(https://xxxx.trycloudflare.com)로 외부 접속을 연다. 주소는 재시작할 때마다
#             바뀌고, 현재 주소는 data\logs\tunnel_url.txt에 적힌다(도메인을 정하면 고정 주소 방식으로 교체).
# 로그: data\logs\{api,worker,tunnel}.log (+ .err.log), 감시 기록 data\logs\watchdog.log
param([switch]$Tunnel)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null

# 같은 감시 스크립트가 두 번 뜨지 않게(로그인 때 자동 실행 + 수동 실행이 겹쳐도 하나만)
$mutex = New-Object System.Threading.Mutex($false, "Local\KfscReportWebWatchdog")
if (-not $mutex.WaitOne(0)) { exit 0 }

function Write-Log($msg) {
    Add-Content -Path (Join-Path $LogDir "watchdog.log") -Value ("[{0:yyyy-MM-dd HH:mm:ss}] {1}" -f (Get-Date), $msg) -Encoding UTF8
}

$Python = (Get-Command python -ErrorAction Stop).Source
$Cloudflared = Join-Path $env:LOCALAPPDATA "cloudflared\cloudflared.exe"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

$Targets = [ordered]@{
    api    = @{ File = $Python; Args = "-m uvicorn server.api.main:app --host 0.0.0.0 --port 8000" }
    worker = @{ File = $Python; Args = "-m server.worker.supervisor_entry" }
}
if ($Tunnel) {
    if (Test-Path $Cloudflared) {
        $Targets.tunnel = @{ File = $Cloudflared; Args = "tunnel --no-autoupdate --url http://127.0.0.1:8000" }
    } else {
        Write-Log "cloudflared.exe가 없어 터널은 건너뜀: $Cloudflared"
    }
}

$Procs = @{}
function Start-Target($name) {
    $t = $Targets[$name]
    $out = Join-Path $LogDir "$name.log"
    $err = Join-Path $LogDir "$name.err.log"
    # 직전 실행 로그는 .prev로 보관(죽은 원인 확인용 — Start-Process는 로그 파일을 새로 덮어쓴다)
    foreach ($f in @($out, $err)) { if (Test-Path $f) { Move-Item $f "$f.prev" -Force -ErrorAction SilentlyContinue } }
    $Procs[$name] = Start-Process -FilePath $t.File -ArgumentList $t.Args -WorkingDirectory $Root `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    Write-Log "$name 시작 (PID $($Procs[$name].Id))"
    if ($name -eq "tunnel") { Remove-Item (Join-Path $LogDir "tunnel_url.txt") -ErrorAction SilentlyContinue }
}

function Update-TunnelUrl {
    $urlFile = Join-Path $LogDir "tunnel_url.txt"
    if (-not $Procs.ContainsKey("tunnel") -or (Test-Path $urlFile)) { return }
    $errLog = Join-Path $LogDir "tunnel.err.log"  # cloudflared는 안내 문구를 stderr로 낸다
    if (-not (Test-Path $errLog)) { return }
    $m = Select-String -Path $errLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -Last 1
    if ($m) {
        $url = $m.Matches[0].Value
        [IO.File]::WriteAllText($urlFile, $url)  # BOM 없이(다른 프로그램이 읽어도 안전)
        Write-Log "외부 접속 주소: $url"
    }
}

Write-Log "감시 시작 (Tunnel=$Tunnel, python=$Python)"
while ($true) {
    foreach ($name in @($Targets.Keys)) {
        $p = $Procs[$name]
        if ($null -eq $p -or $p.HasExited) {
            if ($null -ne $p) { Write-Log "$name 종료 감지(코드 $($p.ExitCode)) — 다시 시작" }
            try { Start-Target $name } catch { Write-Log "$name 시작 실패: $_" }
        }
    }
    Update-TunnelUrl
    Start-Sleep -Seconds 20
}

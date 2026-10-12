$ErrorActionPreference = 'Stop'
$clientPath = Join-Path $env:ProgramFiles 'Tailscale/tailscale.exe'
if (-not (Test-Path -LiteralPath $clientPath)) {
    Write-Host '请先从 https://tailscale.com/download/windows 安装 Tailscale，并在电脑和手机登录同一私人账户。'
    Start-Process 'https://tailscale.com/download/windows'
    Read-Host '安装并登录后，再运行本文件。按 Enter 退出'
    exit
}
try {
    $status = & $clientPath status --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Tailscale 状态读取失败' }
} catch {
    Write-Host '暂时无法连接 Tailscale，请先打开客户端并确认已登录、已连接。'
    Read-Host '按 Enter 退出'
    exit 1
}
if ($status.BackendState -ne 'Running') {
    Write-Host '请在 Tailscale 客户端登录并连接后重试。'
    Read-Host '按 Enter 退出'
    exit
}
try {
    Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/auth/status' -UseBasicParsing -TimeoutSec 5 | Out-Null
} catch {
    Write-Host '病历工具尚未启动，请先双击 启动病历工具.cmd，再运行手机访问设置。'
    Read-Host '按 Enter 退出'
    exit 1
}
Write-Host '将通过已登录的私人 Tailscale 网络提供访问，不启用公网 Funnel。'
Write-Host '如果出现启用 HTTPS 的链接，请在电脑浏览器中打开并完成提示，再重新运行本文件。'
& $clientPath serve --bg http://127.0.0.1:8765
if ($LASTEXITCODE -ne 0) {
    Write-Host '私人访问尚未设置成功，请完成上方提示后重试。'
    Read-Host '按 Enter 退出'
    exit 1
}
& $clientPath serve status
Write-Host '手机连接同一 Tailscale 账户后，在浏览器打开上方 HTTPS 地址，再输入病历工具密码。'
Write-Host '请保持电脑开机且不休眠；可以把网址添加到手机主屏幕。手机不能用 127.0.0.1 这个本机地址。'
Read-Host '按 Enter 退出'

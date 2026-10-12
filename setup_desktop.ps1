$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv/Scripts/pythonw.exe'
$launcherPath = Join-Path $projectPath 'launcher.py'
$iconPath = Join-Path $projectPath 'assets/app.ico'
foreach ($requiredPath in @($pythonPath, $launcherPath, $iconPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) { throw "找不到启动所需文件：$requiredPath" }
}
$shortcutShell = New-Object -ComObject WScript.Shell
$dataPath = Join-Path $projectPath 'data'
New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
$shortcutPaths = @()
foreach ($folderPath in @([Environment]::GetFolderPath('Desktop'), $projectPath)) {
    $shortcutPath = Join-Path $folderPath '安心病历.lnk'
    if (Test-Path -LiteralPath $shortcutPath) {
        $existingShortcut = $shortcutShell.CreateShortcut($shortcutPath)
        if ($existingShortcut.TargetPath -ne $pythonPath -or $existingShortcut.Arguments -ne ('"' + $launcherPath + '"')) {
            $shortcutPath = Join-Path $folderPath ('安心病历-' + [guid]::NewGuid().ToString().Substring(0, 8) + '.lnk')
        }
    }
    $shortcut = $shortcutShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonPath
    $shortcut.Arguments = '"' + $launcherPath + '"'
    $shortcut.WorkingDirectory = $projectPath
    $shortcut.IconLocation = $iconPath + ',0'
    $shortcut.Description = '母亲病历与复查管理 · 右下角托盘可打开或退出'
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    $shortcutPaths += $shortcutPath
}
$shortcutPaths | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectPath 'data/desktop-shortcuts.json') -Encoding UTF8
Write-Host '已建立桌面及项目文件夹中的 安心病历 图标。'

param([Parameter(Mandatory)][string]$Installer)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# This changes the current user's installer registry, PATH, and Startup folder.
# Run only on the disposable GitHub-hosted Windows packaging runner.
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'Installer lifecycle checks require a disposable GitHub-hosted Windows runner.'
}
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$root = Join-Path $env:RUNNER_TEMP ('cogstash-installer-' + [guid]::NewGuid().ToString('N'))
$app = Join-Path $root 'Installed app'
$bin = Join-Path $app 'bin'
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'CogStash.bat'
$ownership = 'HKCU:\Software\CogStash\Installer'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{A8B61FA0-C1C4-4C8A-8A2E-B9972DB78547}_is1'
if ((Test-Path -LiteralPath $startup) -or (Test-Path -LiteralPath $ownership) -or (Test-Path -LiteralPath $uninstallKey)) {
    throw 'Refusing to run over an existing CogStash installation.'
}
$reportDir = Join-Path $PWD 'build/qt-candidate/installer-lifecycle'
New-Item -ItemType Directory -Path $root, $reportDir -Force | Out-Null
$originalPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$checks = [System.Collections.Generic.List[string]]::new()
function Assert-Check([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
    $checks.Add($Message)
}
function Run-Setup([string]$Exe, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Exe -ArgumentList $Arguments -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(120000)) {
        $process.Kill()
        throw "Installer timed out: $Exe"
    }
    if ($process.ExitCode -ne 0) { throw "Installer exited with $($process.ExitCode): $Exe" }
}
function User-Path { [Environment]::GetEnvironmentVariable('Path', 'User') }
function Assert-Installed {
    foreach ($name in @('CogStash.exe', 'CogStash-CLI.exe', 'bin/cogstash.cmd', '.cogstash-installed', 'unins000.exe')) {
        Assert-Check (Test-Path -LiteralPath (Join-Path $app $name)) "Installed $name exists"
    }
    Assert-Check ((Get-Content -LiteralPath $startup -Raw).Contains($app + '\CogStash.exe')) 'Startup command targets the installed UI'
    $segments = @((User-Path) -split ';' | Where-Object { $_ -ieq $bin })
    Assert-Check ($segments.Count -eq 1) 'User PATH contains the CLI directory exactly once'
    Assert-Check ((Get-ItemPropertyValue -LiteralPath $ownership -Name ManagedPath) -eq $bin) 'Installer records PATH ownership'
    # A fresh child resolves the registered shim with no Python directories in PATH.
    $oldProcessPath = $env:Path
    try {
        $env:Path = "$bin;$env:SystemRoot\System32;$env:SystemRoot"
        $output = & "$env:SystemRoot\System32\cmd.exe" /d /c 'cogstash --version' 2>&1
        Assert-Check ($LASTEXITCODE -eq 0 -and ($output -join "`n") -match 'cogstash') 'Installed CLI resolves and runs through PATH without Python on PATH'
    } finally { $env:Path = $oldProcessPath }
}
$uninstaller = Join-Path $app 'unins000.exe'
$success = $false
try {
    $notes = Join-Path $root 'notes.md'
    $config = Join-Path $root 'config.json'
    [IO.File]::WriteAllText($notes, '# Preserved notes' + "`n" + 'Unicode: café 日本語')
    [IO.File]::WriteAllText($config, (@{notes_file=$notes; hotkey='ctrl+alt+shift+j'} | ConvertTo-Json))
    $beforeNotes = (Get-FileHash -LiteralPath $notes).Hash
    $beforeConfig = (Get-FileHash -LiteralPath $config).Hash
    foreach ($phase in @('install', 'reinstall')) {
        Run-Setup $Installer @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER', ('/DIR="' + $app + '"'), '/TASKS="startup,addtopath"', ('/LOG="' + (Join-Path $reportDir ($phase + '.log')) + '"'))
        Assert-Installed
        Assert-Check ((Get-FileHash -LiteralPath $notes).Hash -eq $beforeNotes -and (Get-FileHash -LiteralPath $config).Hash -eq $beforeConfig) "$phase preserves external notes and config"
    }
    # Unknown files inside the installation must also survive uninstall.
    $localNote = Join-Path $app 'user-note.md'
    [IO.File]::WriteAllText($localNote, 'User-owned note')
    Run-Setup $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/LOG="' + (Join-Path $reportDir 'uninstall.log') + '"'))
    Assert-Check (-not (Test-Path -LiteralPath (Join-Path $app 'CogStash.exe'))) 'Uninstall removes the application'
    Assert-Check (-not (Test-Path -LiteralPath $startup)) 'Uninstall removes startup registration'
    Assert-Check (-not (Test-Path -LiteralPath $uninstallKey)) 'Uninstall removes its registration'
    Assert-Check ((User-Path) -ceq $originalPath) 'Uninstall restores the original user PATH'
    Assert-Check ((Get-Content -LiteralPath $localNote -Raw) -ceq 'User-owned note') 'Uninstall preserves unknown files inside the application directory'
    Assert-Check ((Get-FileHash -LiteralPath $notes).Hash -eq $beforeNotes -and (Get-FileHash -LiteralPath $config).Hash -eq $beforeConfig) 'Uninstall preserves external notes and config'
    $success = $true
} finally {
    @{ success=$success; checks=$checks.ToArray(); cross_version_upgrade_verified=$false; interactive_desktop_verified=$false; python_free_machine_verified=$false } |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $reportDir 'report.json') -Encoding utf8
    if (-not $success -and (Test-Path -LiteralPath $uninstallKey) -and (Test-Path -LiteralPath $uninstaller)) {
        try { Run-Setup $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') } catch { Write-Warning $_ }
    }
}

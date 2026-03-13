<#
.SYNOPSIS
    ローカルの変更を GitHub にプッシュし、Raspberry Pi でデプロイ・実行・検証を行うスクリプト。

.PARAMETER CommitMessage
    コミットメッセージ (デフォルト: "update: auto deploy")

.PARAMETER TimeoutSec
    スクリプトの実行タイムアウト秒数 (デフォルト: 30, 0 = タイムアウトなし)

.PARAMETER RunTests
    テストを実行するかどうか (スイッチ)

.PARAMETER Script
    app/ 以下で実行する Python スクリプト名 (省略時は main.py)

.EXAMPLE
    # テストを実行してデプロイ
    .\deploy_and_run.ps1 -RunTests -CommitMessage "fix: バグ修正"

    # main.py を 60 秒だけ起動して確認
    .\deploy_and_run.ps1 -TimeoutSec 60 -CommitMessage "feat: 新機能追加"

    # 特定スクリプトを実行
    .\deploy_and_run.ps1 -Script dummy_sitl.py -TimeoutSec 30
#>
param(
    [Parameter()]
    [string]$CommitMessage = "update: auto deploy",

    [Parameter()]
    [int]$TimeoutSec = 30,

    [Parameter()]
    [switch]$RunTests,

    [Parameter()]
    [string]$Script = "main.py"
)

$RepoRoot   = "c:\Users\taki\Local\local\GCS-UmemotoLab"
$RaspiHost  = "taki@192.168.11.19"
$RaspiRepo  = "~/GCS-UmemotoLab"
$VenvPython = "$RaspiRepo/.venv/bin/python3"

function Write-Step {
    param([int]$Num, [string]$Message)
    Write-Host ""
    Write-Host "=== Step $Num: $Message ===" -ForegroundColor Cyan
}

function Write-Success { param([string]$Msg) Write-Host "[OK] $Msg" -ForegroundColor Green }
function Write-Fail    { param([string]$Msg) Write-Host "[NG] $Msg" -ForegroundColor Red }
function Write-Info    { param([string]$Msg) Write-Host "[..] $Msg" -ForegroundColor Yellow }

# SSH 接続確認
Write-Step 0 "SSH 接続確認"
$sshTest = ssh -o ConnectTimeout=5 -o BatchMode=yes $RaspiHost "echo OK" 2>&1
if ($sshTest -ne "OK") {
    Write-Fail "SSH 接続に失敗しました: $sshTest"
    Write-Host ""
    Write-Host "-- SSH 鍵認証をセットアップしてください --" -ForegroundColor Yellow
    Write-Host "  1. 鍵の確認: Test-Path `"`$env:USERPROFILE\.ssh\id_ed25519`""
    Write-Host "  2. 鍵の生成: ssh-keygen -t ed25519 -C 'taki-gcs'"
    Write-Host "  3. 鍵のコピー (PowerShell):"
    Write-Host "     `$pubkey = Get-Content `"`$env:USERPROFILE\.ssh\id_ed25519.pub`""
    Write-Host "     ssh taki@192.168.11.19 `"mkdir -p ~/.ssh && echo '`$pubkey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys`""
    exit 1
}
Write-Success "SSH 接続 OK ($RaspiHost)"

# ============================================================
# Step 1: ローカルの変更をコミット・プッシュ
# ============================================================
Write-Step 1 "ローカル変更を GitHub へプッシュ"

Set-Location $RepoRoot

$status = git status --porcelain
if ($status) {
    Write-Info "変更ファイルを検出。コミットします..."
    git add .
    git commit -m $CommitMessage
    if ($LASTEXITCODE -ne 0) { Write-Fail "git commit に失敗しました"; exit 1 }
} else {
    Write-Info "作業ツリーはクリーン。プッシュのみ実行します。"
}

git push
if ($LASTEXITCODE -ne 0) { Write-Fail "git push に失敗しました"; exit 1 }
Write-Success "プッシュ完了"

# ============================================================
# Step 2: Raspberry Pi で git pull
# ============================================================
Write-Step 2 "Raspberry Pi で git pull"

$pullOutput = ssh $RaspiHost "cd $RaspiRepo && git pull 2>&1"
Write-Host $pullOutput

if ($pullOutput -match "error:|fatal:") {
    Write-Fail "git pull 中にエラーが発生しました"
    exit 1
}
Write-Success "git pull 完了"

# ============================================================
# Step 3: テスト実行（-RunTests オプション指定時）
# ============================================================
if ($RunTests) {
    Write-Step 3 "pytest を実行"

    $testOutput = ssh $RaspiHost "cd $RaspiRepo && $VenvPython -m pytest tests/ -v 2>&1"
    Write-Host ""
    Write-Host "--- テスト出力 ---" -ForegroundColor Magenta
    Write-Host $testOutput
    Write-Host "--- 出力終了 ---" -ForegroundColor Magenta

    if ($testOutput -match "FAILED|ERROR") {
        Write-Fail "テストが失敗しました。コードを修正してください。"
        exit 1
    }
    Write-Success "全テスト PASSED"
}

# ============================================================
# Step 4: スクリプトを実行
# ============================================================
$stepNum = if ($RunTests) { 4 } else { 3 }
$timeoutLabel = if ($TimeoutSec -gt 0) { "timeout: ${TimeoutSec}s" } else { "タイムアウトなし" }
Write-Step $stepNum "仮想環境を有効化してスクリプトを実行 ($timeoutLabel)"

$runCmd = if ($TimeoutSec -gt 0) {
    "cd $RaspiRepo && timeout $TimeoutSec $VenvPython app/$Script 2>&1"
} else {
    "cd $RaspiRepo && $VenvPython app/$Script 2>&1"
}

Write-Info "実行: $runCmd"
$runOutput = ssh $RaspiHost $runCmd
Write-Host ""
Write-Host "--- 実行出力 ---" -ForegroundColor Magenta
Write-Host $runOutput
Write-Host "--- 出力終了 ---" -ForegroundColor Magenta

# ============================================================
# Step 5: 結果を検証
# ============================================================
$nextStep = $stepNum + 1
Write-Step $nextStep "実行結果の検証"

$hasError   = $runOutput -match "Traceback|Error:|Exception:|CRITICAL"
$hasWarning = $runOutput -match "Warning:|WARN"
$isTimeout  = ($runOutput -match "Killed") -or ($LASTEXITCODE -eq 124)

if ($isTimeout -and $TimeoutSec -gt 0) {
    Write-Info "タイムアウト (${TimeoutSec}s) で終了しました（正常）"
}

if ($hasError) {
    Write-Fail "エラーが検出されました。出力を確認してください。"
    exit 1
}

if ($hasWarning) {
    Write-Info "警告が検出されました（動作には影響しない場合があります）"
}

Write-Success "デプロイ・実行 完了"
Write-Host ""
Write-Host "次のステップ:" -ForegroundColor Cyan
Write-Host "  - 問題なければ完了"
Write-Host "  - エラーがあればコードを修正して再実行"
Write-Host "  - ラズパイのログ確認: ssh $RaspiHost `"journalctl -n 50`""

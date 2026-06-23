<#
  gimpo365-inventory DB 백업 스크립트 (pg_dump 커스텀 포맷 -Fc)

  사용 예:
    .\scripts\backup_inventory.ps1
    .\scripts\backup_inventory.ps1 -PgBin "C:\Program Files\PostgreSQL\17\bin"

  보안:
    - 실제 DB 비밀번호를 이 파일/코드에 저장하지 않는다.
    - $env:PGPASSWORD 가 설정되어 있으면 그 값을 사용하고,
      없으면 실행 시 안전 입력(SecureString)으로 받는다.
    - .env 는 절대 커밋하지 않는다.

  백업 위치(기본): OneDrive\gimpo365_inventory_backups\db
#>
[CmdletBinding()]
param(
  [string]$DbName = "gimpo365_inventory",
  [string]$DbUser = "postgres",
  [string]$DbHost = "127.0.0.1",
  [int]$DbPort = 5432,
  [string]$PgBin = "C:\Program Files\PostgreSQL\17\bin",
  [string]$BackupDir
)

$ErrorActionPreference = "Stop"

# 백업 폴더 결정: OneDrive\gimpo365_inventory_backups\db
if (-not $BackupDir) {
  $oneDrive = if ($env:OneDrive) { $env:OneDrive } else { Join-Path $env:USERPROFILE "OneDrive" }
  $BackupDir = Join-Path $oneDrive "gimpo365_inventory_backups\db"
}
if (-not (Test-Path $BackupDir)) {
  New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$pgDump = Join-Path $PgBin "pg_dump.exe"
$pgRestore = Join-Path $PgBin "pg_restore.exe"
if (-not (Test-Path $pgDump)) {
  throw "pg_dump 를 찾을 수 없습니다: $pgDump  (-PgBin 경로를 확인하세요)"
}

# 비밀번호: 환경변수에 없으면 안전 입력 (파일/코드에 저장하지 않음)
if (-not $env:PGPASSWORD) {
  $sec = Read-Host "PostgreSQL 비밀번호 ($DbUser)" -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$file = Join-Path $BackupDir "gimpo365_inventory_$stamp.dump"

Write-Host "백업 시작: $DbName ($DbHost`:$DbPort) -> $file"
& $pgDump -h $DbHost -p $DbPort -U $DbUser -Fc -f $file $DbName
if ($LASTEXITCODE -ne 0) { throw "pg_dump 실패 (exit $LASTEXITCODE)" }

# 4) 파일 크기 확인
$item = Get-Item $file
$sizeMB = [math]::Round($item.Length / 1MB, 2)
Write-Host ("백업 성공. 크기: {0} MB ({1:N0} bytes)" -f $sizeMB, $item.Length)
if ($item.Length -eq 0) { throw "백업 파일 크기가 0 입니다. 확인이 필요합니다." }

# 5) pg_restore -l 로 백업 파일 읽기 검증 (실제 복구는 하지 않음)
if (Test-Path $pgRestore) {
  Write-Host "백업 파일 읽기 검증 (pg_restore -l):"
  $toc = & $pgRestore -l $file
  if ($LASTEXITCODE -ne 0) { throw "pg_restore -l 실패: 백업 파일을 읽을 수 없습니다." }
  $entries = ($toc | Where-Object { $_.Trim() -ne "" -and $_ -notmatch '^\s*;' }).Count
  Write-Host ("읽기 검증 성공. TOC 항목 약 {0}개." -f $entries)
} else {
  Write-Host "pg_restore 를 찾을 수 없어 읽기 검증은 건너뜁니다: $pgRestore"
}

Write-Host "완료: $file"

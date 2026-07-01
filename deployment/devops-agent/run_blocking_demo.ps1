<#
.SYNOPSIS
  Simulate a blocking incident to trigger a DevOps Agent investigation (DEMO ONLY).

.DESCRIPTION
  Creates a 15-deep blocking chain and pushes connections past the alarm threshold
  so that the dbops-demo-HighConnections CloudWatch alarm trips and triggers an
  autonomous DevOps Agent investigation via the webhook executor Lambda.

  Run from the Windows bastion host. Requires the loadtest database and dbo.Orders
  table (run setup first — see below).

  Prerequisites — set these environment variables:
    $env:RDS_ENDPOINT   = "<your-rds-endpoint>"
    $env:DB_USER        = "<sql-login>"
    $env:DB_PASSWORD    = "<sql-password>"

  Setup (run once):
    Invoke-Sqlcmd -ServerInstance $env:RDS_ENDPOINT -Username $env:DB_USER -Password $env:DB_PASSWORD `
      -Database master -TrustServerCertificate -Query "IF DB_ID('loadtest') IS NULL CREATE DATABASE loadtest;"
    Invoke-Sqlcmd -ServerInstance $env:RDS_ENDPOINT -Username $env:DB_USER -Password $env:DB_PASSWORD `
      -Database loadtest -TrustServerCertificate -Query @"
        IF OBJECT_ID('dbo.Orders','U') IS NULL
        BEGIN
            CREATE TABLE dbo.Orders (OrderID INT PRIMARY KEY, Status NVARCHAR(50), Amount DECIMAL(10,2), CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME());
            INSERT INTO dbo.Orders (OrderID, Status, Amount) SELECT TOP 1000 ROW_NUMBER() OVER (ORDER BY a.object_id), 'OPEN', CAST(RAND(CHECKSUM(NEWID())) * 1000 AS DECIMAL(10,2)) FROM sys.all_objects a CROSS JOIN sys.all_objects b;
        END
"@

.PARAMETER DurationSeconds
  How long to hold the incident (default 600 = 10 minutes).

.EXAMPLE
  .\run_blocking_demo.ps1
  .\run_blocking_demo.ps1 -DurationSeconds 300
#>
param(
    [int]$DurationSeconds = 600
)

$ErrorActionPreference = "Stop"

foreach ($v in "RDS_ENDPOINT", "DB_USER", "DB_PASSWORD") {
    if (-not (Test-Path "Env:$v")) { throw "Set environment variable $v" }
}

$server   = $env:RDS_ENDPOINT
$user     = $env:DB_USER
$password = $env:DB_PASSWORD

$connStr = "Server=$server;Database=loadtest;User Id=$user;Password=$password;TrustServerCertificate=True;Connect Timeout=30"

$holdSeconds = $DurationSeconds + 60
$hms = '{0:00}:{1:00}:{2:00}' -f [int]($holdSeconds/3600), [int](($holdSeconds%3600)/60), [int]($holdSeconds%60)

$headSql    = "BEGIN TRAN; UPDATE dbo.Orders SET Status = 'PROCESSING' WHERE OrderID = 1; WAITFOR DELAY '$hms'; COMMIT;"
$waiterSql  = "UPDATE dbo.Orders SET Amount = Amount + 1 WHERE OrderID = 1;"
$paddingSql = "WAITFOR DELAY '$hms';"

$pool = [runspacefactory]::CreateRunspacePool(1, 25)
$pool.Open()
$handles = @()

$worker = {
    param($connStr, $sql, $timeout)
    $conn = New-Object System.Data.SqlClient.SqlConnection $connStr
    $conn.Open()
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = $sql
    $cmd.CommandTimeout = $timeout
    try { [void]$cmd.ExecuteScalar() } catch { } finally { $conn.Close() }
}

function Start-Worker($sql) {
    $ps = [powershell]::Create()
    $ps.RunspacePool = $pool
    [void]$ps.AddScript($worker).AddArgument($connStr).AddArgument($sql).AddArgument($holdSeconds + 120)
    $script:handles += [pscustomobject]@{ PS = $ps; Handle = $ps.BeginInvoke() }
}

Write-Host "Starting head blocker..."
Start-Worker $headSql
Start-Sleep -Seconds 5

Write-Host "Starting 14 waiters (will be blocked)..."
for ($i = 1; $i -le 14; $i++) { Start-Worker $waiterSql }

Write-Host "Starting 5 padding connections..."
for ($i = 1; $i -le 5; $i++) { Start-Worker $paddingSql }

Write-Host ""
Write-Host "INCIDENT LIVE: 20 connections, 15-deep blocking chain." -ForegroundColor Green
Write-Host "HighConnections alarm will trip in ~1-2 minutes." -ForegroundColor Green
Write-Host "DevOps Agent will start investigation via webhook." -ForegroundColor Green
Write-Host ""
Write-Host "Hold for $DurationSeconds seconds, then sessions auto-release."
Write-Host "Press Ctrl+C to release early."

Start-Sleep -Seconds $DurationSeconds

foreach ($h in $handles) { try { $h.PS.Stop() } catch { }; try { $h.PS.Dispose() } catch { } }
$pool.Close(); $pool.Dispose()
Write-Host "Incident cleared." -ForegroundColor Yellow

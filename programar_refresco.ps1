[CmdletBinding()]
param([switch]$Quitar)

$ErrorActionPreference = 'Stop'
$nombreTarea = 'TableroDiegoRefresco'

if ($Quitar) {
    $existente = Get-ScheduledTask -TaskName $nombreTarea -ErrorAction SilentlyContinue
    if ($existente) {
        Unregister-ScheduledTask -TaskName $nombreTarea -Confirm:$false
        Write-Output "OK: tarea $nombreTarea eliminada."
    } else {
        Write-Output "OK: la tarea $nombreTarea no existe."
    }
    return
}

$publicar = Join-Path $PSScriptRoot 'publicar.bat'
if (-not (Test-Path -LiteralPath $publicar -PathType Leaf)) {
    throw "No se encontro publicar.bat en $PSScriptRoot."
}

# Seis disparadores diarios: el siguiente intervalo tras las 21:00 seria 00:00.
$disparadores = @(6, 9, 12, 15, 18, 21 | ForEach-Object {
    New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($_))
})
$identidad = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$principal = New-ScheduledTaskPrincipal -UserId $identidad -LogonType Interactive -RunLevel Limited
$accion = New-ScheduledTaskAction -Execute $env:ComSpec `
    -Argument ('/d /c ""{0}""' -f $publicar) -WorkingDirectory $PSScriptRoot
$ajustes = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $nombreTarea -Action $accion `
    -Trigger $disparadores -Principal $principal -Settings $ajustes `
    -Description 'Publica el tablero cada 3 horas de 06:00 a 21:00, con sesion iniciada.' `
    -Force | Out-Null
Write-Output "OK: tarea $nombreTarea programada a las 06, 09, 12, 15, 18 y 21 horas."

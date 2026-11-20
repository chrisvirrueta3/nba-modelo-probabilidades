# Programa las tareas automáticas (no necesita permisos de administrador):
#  - rutina.bat a las 12:00 y 17:30
#  - revisión de lesiones cada 30 minutos de 11:30 a 22:00 (sin ventana; solo avisa si hay que cancelar)
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
           -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew

$accion = New-ScheduledTaskAction -Execute "$dir\rutina_auto.bat" -WorkingDirectory $dir
$tareas = @(
  @{ Nombre = "NBA rutina mediodia"; Hora = "12:00" },
  @{ Nombre = "NBA rutina tarde";    Hora = "17:30" }
)
foreach ($t in $tareas) {
  $disparador = New-ScheduledTaskTrigger -Daily -At $t.Hora
  Register-ScheduledTask -TaskName $t.Nombre -Action $accion -Trigger $disparador -Settings $ajustes -Force | Out-Null
  Write-Host ("  Programada: " + $t.Nombre + " a las " + $t.Hora)
}

# Revisión de lesiones: pythonw no abre ninguna ventana
$pyw = Join-Path (Split-Path -Parent $dir) ".venv\Scripts\pythonw.exe"
if (Test-Path $pyw) {
  $accionL = New-ScheduledTaskAction -Execute $pyw -Argument "src\revisar_lesiones.py" -WorkingDirectory $dir
  $dispL = New-ScheduledTaskTrigger -Daily -At "11:30"
  $dispL.Repetition = (New-ScheduledTaskTrigger -Once -At "11:30" -RepetitionInterval (New-TimeSpan -Minutes 30) `
                       -RepetitionDuration (New-TimeSpan -Hours 10 -Minutes 30)).Repetition
  $ajustesL = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew
  Register-ScheduledTask -TaskName "NBA revisar lesiones" -Action $accionL -Trigger $dispL -Settings $ajustesL -Force | Out-Null
  Write-Host "  Programada: NBA revisar lesiones (cada 30 min, 11:30 a 22:00)"
} else {
  Write-Host "  (No encontre $pyw: la revision de lesiones no se programo)"
}

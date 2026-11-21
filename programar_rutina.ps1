# Programa las tareas automáticas (no necesita permisos de administrador):
#  - rutina.bat a las 9:00 (momios recién salidos) y 17:30 (cierre)
#  - resumen semanal al teléfono los domingos a las 10:00
#  - revisión de lesiones cada 30 minutos de 11:30 a 22:00 (sin ventana; solo avisa si hay que cancelar)
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
# -WakeToRun: despierta la computadora si está dormida (no si está apagada)
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun `
           -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew

Unregister-ScheduledTask -TaskName "NBA rutina mediodia" -Confirm:$false -ErrorAction SilentlyContinue
$accion = New-ScheduledTaskAction -Execute "$dir\rutina_auto.bat" -WorkingDirectory $dir
$tareas = @(
  @{ Nombre = "NBA rutina manana";   Hora = "09:00" },
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
  $accionS = New-ScheduledTaskAction -Execute $pyw -Argument "src\resumen_semanal.py" -WorkingDirectory $dir
  $dispS = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "10:00"
  Register-ScheduledTask -TaskName "NBA resumen semanal" -Action $accionS -Trigger $dispS -Settings $ajustesL -Force | Out-Null
  Write-Host "  Programada: NBA resumen semanal (domingos 10:00)"
} else {
  Write-Host ("  (No encontre " + $pyw + "; la revision de lesiones no se programo)")
}

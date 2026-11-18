# Programa rutina.bat para que corra solo todos los días (12:00 y 17:30).
# Lo corre programar_rutina.bat; no necesita permisos de administrador.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$accion = New-ScheduledTaskAction -Execute "$dir\rutina_auto.bat" -WorkingDirectory $dir
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
           -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$tareas = @(
  @{ Nombre = "NBA rutina mediodia"; Hora = "12:00" },
  @{ Nombre = "NBA rutina tarde";    Hora = "17:30" }
)
foreach ($t in $tareas) {
  $disparador = New-ScheduledTaskTrigger -Daily -At $t.Hora
  Register-ScheduledTask -TaskName $t.Nombre -Action $accion -Trigger $disparador -Settings $ajustes -Force | Out-Null
  Write-Host ("  Programada: " + $t.Nombre + " a las " + $t.Hora)
}

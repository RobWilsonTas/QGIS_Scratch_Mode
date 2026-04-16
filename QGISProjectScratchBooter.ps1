#This script is designed to be triggered by ScratchMode.lnk
#The shortcut ScratchMode.lnk points to this .ps1,
#and when the user drags a .qgz onto the shortcut then it will be passed as a parameter

try {

    #Get the .qgz as it is passed in from the shortcut
    $projectFile = $args | Where-Object { Test-Path $_ } | Select-Object -First 1

	#The user needs to know that they're not supposed to double click on the shortcut
	#But instead drag a qgis project onto the shortcut
    if ($null -eq $projectFile -or [System.IO.Path]::GetExtension($projectFile) -ne ".qgz") {
		Write-Host "No valid QGIS project detected."
		Write-Host "Please drag and drop a QGIS project file onto the green arrow icon."
		Write-Host "Press Enter to close..."
		Read-Host
		return
	} else {
		Write-Host "Creating scratch project from $projectFile"
	}

    #Paths to QGIS launcher and the headless Python script
	$latestQgisFolder = Get-ChildItem "C:\Program Files" -Directory | Where-Object { $_.Name -like "QGIS *" } | Sort-Object Name -Descending | Select-Object -First 1
	$qgisLauncher = Join-Path $latestQgisFolder.FullName "bin\python-qgis-ltr.bat"
	$qgsExe = Join-Path $latestQgisFolder.FullName "bin\qgis-ltr-bin.exe"
    $headlessPythonScript = "M:\QGIS Tools and Models\QGIS Project Scratch Mode\QGISProjectScratch_Headless.py"

    #Launch QGIS in headless mode, with the script, project file, and qgis executable as parameters
    $argumentsForQgis = "`"$headlessPythonScript`" `"$projectFile`" `"$qgsExe`""
    Start-Process -FilePath $qgisLauncher -ArgumentList $argumentsForQgis -NoNewWindow

} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    Write-Host "Press Enter to close..."
    Read-Host
}
If you want the ability for others to open up a qgis project and screw around with the layers, but don't want them to accidentally save changes, this is helpful

This copies a QGIS project file to a temp AppData path, and takes all of the relative pathed data along with it

It works by you setting up 3 files

1. The headless scratch .py
2. The scratch booter powershell script
3. A windows shortcut (not provided) that points to the booter .ps1

The shortcut should have the Target as <b>C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\YOURFOLDER\QGISProjectScratchBooter.ps1"</b>

And the Start In as <b>"C:\YOURFOLDER"

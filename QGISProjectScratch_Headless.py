import os, sys, stat, shutil, tempfile, zipfile, subprocess, traceback, warnings
import xml.etree.ElementTree as xmlTree
from datetime import datetime
import urllib.parse

try:

    """
    ########################################################################
    Set up a temp path to house the copied project and files
    """

    #Bring in the parameters from the .ps1
    projectFilePath = sys.argv[1]
    qgisExecutablePath = sys.argv[2]

    #Define the temp directory in the user's app data to hold the project and its files
    sourceProjectFolder = os.path.dirname(projectFilePath)
    projectBaseName = os.path.splitext(os.path.basename(projectFilePath))[0].replace("_", "")
    temporaryProjectFolder = os.path.join(tempfile.gettempdir(), "NB")
    maximumFileSizeBytes = 50 * 1024 * 1024

    #Clear old temporary files from the app data folder
    for folderPath, subFolders, fileNames in os.walk(temporaryProjectFolder):
        for fileName in fileNames:
            fullFilePath = r"\\?\\" + os.path.join(folderPath, fileName)
            os.chmod(fullFilePath, stat.S_IWRITE)
    shutil.rmtree(temporaryProjectFolder, ignore_errors=True)

    #Create new temporary folder for this project
    temporaryProjectPath = os.path.join(temporaryProjectFolder, projectBaseName)
    os.makedirs(temporaryProjectPath, exist_ok=True)
    print("Project being created under " + temporaryProjectPath)

    #Define where the temp copy of the qgis project will live and copy the project there
    temporaryProjectFilePath = os.path.join(temporaryProjectPath, os.path.splitext(os.path.basename(projectFilePath))[0] + "_scratch" + os.path.splitext(projectFilePath)[1])
    shutil.copy2(projectFilePath, temporaryProjectFilePath)

    """
    ########################################################################
    Look inside the temp QGIS project and edit it
    """

    #Open the copied project file like a zip folder so we can peek inside; QGIS projects are really zip files with one main .qgs file that has all the layer info
    with zipfile.ZipFile(temporaryProjectFilePath, "r") as projectZip:
        #Read every file inside the zip into memory
        allFiles = {fileName: projectZip.read(fileName) for fileName in projectZip.namelist()}
        #Find the main .qgs file because that's where QGIS stores layer paths and settings, and get the content
        qgsFileName, qgsContent = next(
            (name, allFiles[name].decode("utf-8"))
            for name in allFiles if name.lower().endswith(".qgs"))

    #Turn the XML into something Python can navigate to find map layers
    projectXml = xmlTree.fromstring(qgsContent)
    usesNamespace = projectXml.tag.startswith("{")
    namespaceUri = projectXml.tag.split("}")[0][1:] if usesNamespace else None
    layerTagPath = ".//qgs:maplayer" if usesNamespace else ".//maplayer"

    windowsFilesForCopy = []
    #Loop through every layer in the project XML to process its datasource paths
    for layer in projectXml.findall(layerTagPath, {"qgs": namespaceUri} if usesNamespace else None):
        
        #Get the paths of the layers in the project
        datasourceTag = layer.find("qgs:datasource", {"qgs": namespaceUri}) if usesNamespace else layer.find("datasource")
        if datasourceTag is None or not datasourceTag.text:
            continue
        oldPath = datasourceTag.text.strip()

        #Strip 'file:' prefix for csvs
        pathText = oldPath[5:] if oldPath.lower().startswith("file:") else oldPath

        #Split up the string given that there are files that are like whatever.gpkg|layername=bruh
        if "|" in pathText:
            filePathWithExt, layerQueryString = pathText.split("|", 1)
            layerQueryString = "|" + layerQueryString
        elif "?" in pathText:
            filePathWithExt, layerQueryString = pathText.split("?", 1)
            layerQueryString = "?" + layerQueryString
        else:
            filePathWithExt, layerQueryString = pathText, ""
        
        #Get rid of the space is %20 bs
        filePathWithExt = urllib.parse.unquote(filePathWithExt)

        #If the path of the layer is relative
        if filePathWithExt.startswith("./") or filePathWithExt.startswith("../"):
            absPath = os.path.normpath(os.path.join(sourceProjectFolder, filePathWithExt))
            
            #Redirect './' paths to temporary folder and update datasource
            #The './' paths are ones that point to subfolders where the project sits
            if filePathWithExt.startswith("./"):
                absPathTemp = absPath.replace(sourceProjectFolder, temporaryProjectPath)
                datasourceTag.text = absPathTemp.replace("\\", "/") + layerQueryString

                #Prepend TEMP_ to the layer name to indicate it’s editable but in temp
                layerNameTag = layer.find("qgs:layername", {"qgs": namespaceUri}) if usesNamespace else layer.find("layername")
                if layerNameTag is not None and layerNameTag.text:
                    layerNameTag.text = "TEMP_" + layerNameTag.text

                #Keep track of files that need to be copied to temp
                windowsFilesForCopy.append(absPathTemp)
            
            #'../' relative paths become absolute but stay outside temp, so that way we can point to layers in other folders
            else:
                datasourceTag.text = absPath.replace("\\", "/") + layerQueryString
                layer.set("readOnly", "1")

        #Absolute Windows path: keep as-is and mark layer read-only
        elif len(filePathWithExt) > 2 and filePathWithExt[1] == ":":
            absPath = os.path.normpath(filePathWithExt)
            datasourceTag.text = absPath.replace("\\", "/") + layerQueryString
            layer.set("readOnly", "1")
            windowsFilesForCopy.append(absPath)

        #Set db layers to readOnly
        else:
            layer.set("readOnly", "1")
            
    #Turn the XML tree back into bytes so we can write it back into the zip
    updatedQgsBytes = xmlTree.tostring(projectXml, encoding="utf-8", method="xml")

    #Rewrite the zip file: put the updated .qgs back, keep everything else the same
    with zipfile.ZipFile(temporaryProjectFilePath, "w") as projectZip:
        for fileName, fileBytes in allFiles.items():
            if fileName == qgsFileName:
                projectZip.writestr(fileName, updatedQgsBytes)
            else:
                projectZip.writestr(fileName, fileBytes)

    """
    ########################################################################
    Copy the relevant files across then boot up the copied project
    """

    #Remove duplicate files, then strip extensions so that we can deal with auxilliary files
    windowsFilesForCopy = list(dict.fromkeys(windowsFilesForCopy))
    windowsFilesForCopyBaseNames = [os.path.splitext(os.path.basename(f))[0] for f in windowsFilesForCopy]

    #Walk through every file in the source project folder
    for folderPath, subFolders, fileNames in os.walk(sourceProjectFolder):
        for fileName in fileNames:
            baseName = os.path.splitext(fileName)[0]
            if baseName in windowsFilesForCopyBaseNames:
                sourceFilePath = os.path.join(folderPath, fileName)
                
                #Determine the path relative to the source project, use the r"\\?\\" thing to deal with long paths
                relativePath = os.path.relpath(sourceFilePath, sourceProjectFolder)
                tempFilePath = os.path.join(temporaryProjectPath, relativePath)
                
                #Copy the file to the temp folder only if it’s under 60 MB
                if os.path.getsize(sourceFilePath) <= 60 * 1024 * 1024:
                    os.makedirs(os.path.dirname(tempFilePath), exist_ok=True)
                    shutil.copy2(r"\\?\\" + sourceFilePath, r"\\?\\" + tempFilePath)
                else:
                    print("Did not copy " + sourceFilePath + " due to file size of " + str(int(os.path.getsize(sourceFilePath)/(1024*1024))) + "MB")

    #Now boot up the project in qgis
    subprocess.Popen([qgisExecutablePath, temporaryProjectFilePath], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)

except Exception:
    traceback.print_exc()
    input("Press Enter to exit...")
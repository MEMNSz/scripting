; Instalador de Scripting (Inno Setup 7). Se arma con instalador\armar.ps1,
; que pasa AppVer (archivo VERSION), RepoDir (esta carpeta del código) y BuildDir
; (carpeta con python\ y exe\ ya preparados, fuera del repositorio).

#ifndef AppVer
  #define AppVer "0.0.0"
#endif

[Setup]
AppId={{6B3F2C1E-5A7D-4E8B-9C21-8F4D2A6B7C30}
AppName=Scripting
AppVersion={#AppVer}
AppVerName=Scripting {#AppVer}
AppPublisher=MEMNSz
AppPublisherURL=https://github.com/MEMNSz/scripting
DefaultDirName={autopf}\Scripting
DefaultGroupName=Scripting
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#BuildDir}\salida
OutputBaseFilename=Scripting-{#AppVer}-instalador
SetupIconFile={#RepoDir}\ventana\Scripting.ico
UninstallDisplayIcon={app}\ventana\Scripting.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
; el programa (lo mismo que está en GitHub; las actualizaciones reemplazan estos archivos)
Source: "{#RepoDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; \
  Excludes: ".git,.gitignore,DESARROLLO.md,Trelby.bat,Scripting.bat,ventana\*.cs,ventana\*.csproj,sync\*.json,sync\*.jsonc,sync\*.mjs,.venv,*.bak*,__pycache__,.actualizaciones,*.upd-tmp,voces\*,instalador,sync\node_modules,sync\.wrangler,sync\.dev.vars*,ventana\obj,ventana\bin,ventana\out,ventana\scripting"
; la ventana translúcida (necesita .NET 8 Escritorio; si no está, Scripting.pyw abre Edge)
Source: "{#BuildDir}\exe\*"; DestDir: "{app}\ventana\scripting"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "*.pdb,*.xml"
; Python con las librerías de lectura en voz alta
Source: "{#BuildDir}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "__pycache__"

[Dirs]
Name: "{app}\voces"

[Icons]
Name: "{autoprograms}\Scripting"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\Scripting.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\ventana\Scripting.ico"
Name: "{autodesktop}\Scripting"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\Scripting.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\ventana\Scripting.ico"; Tasks: escritorio

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\Scripting.pyw"""; WorkingDir: "{app}"; Description: "Abrir Scripting"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; lo que se generó al usarlo (copias de actualizaciones, cachés de Python, voces bajadas).
; Los guiones viven en Documentos\Guiones y no se tocan.
Type: filesandordirs; Name: "{app}\.actualizaciones"
Type: filesandordirs; Name: "{app}\voces"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\python"

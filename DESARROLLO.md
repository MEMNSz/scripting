# Notas de desarrollo

## Abrir desde el código

Doble clic en `Scripting.bat`: usa `ventana\scripting\Scripting.exe` si está compilado y, si no, `server.py` con una ventana de Edge. Necesita Python 3.

Una copia con carpeta `.git` no se actualiza sola: se actualiza con `git pull`.

## Publicar una versión

1. Cambiar el número en `VERSION` (por ejemplo `1.1.0`), hacer commit y push.
2. En GitHub: *Releases* › *Draft a new release*.
3. En *Choose a tag*, el mismo número con `v` adelante (`v1.1.0`) › *Create new tag*.
4. Título y novedades en la descripción (es lo que muestra el aviso de la app).
5. Adjuntar el instalador (`Scripting-<versión>-instalador.exe`) y tocar *Publish release*.

Si `VERSION` no coincide con la etiqueta, la app no instala la actualización.

La app actualiza los archivos de este repositorio. No toca `python\`, `voces\` ni `ventana\scripting\`: si cambia `Scripting.exe` o el Python, hay que publicar un instalador nuevo.

## Armar el instalador

`instalador\armar.ps1` arma `Scripting-<versión>-instalador.exe` con Inno Setup 7. Necesita una carpeta de armado fuera del repositorio (por defecto `..\..\instalador-build`) con:

- `python\`: Python 3.13 embebible con `edge-tts` y `piper-tts` en `Lib\site-packages` (y `Lib\site-packages` + `import site` en `python313._pth`);
- `exe\`: Scripting compilado (`dotnet build -c Release -o <armado>\exe` en `ventana\`);
- `herramientas\InnoSetup\ISCC.exe`.

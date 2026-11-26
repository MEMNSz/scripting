
#VIBECODEADO XD

# Scripting

Editor de guiones y novelas para Windows.

## Qué hace

- **Guion** con formato estilo Final Draft: escena, acción, personaje, paréntesis, diálogo y transición, con Enter y Tab como en Final Draft, autocompletado de personajes y escenas, y paginado carta en Courier 12.
- **Story Map y Beat Board**: carriles de beats sobre las páginas, tableros de tarjetas, plantillas de estructura y líneas de flujo.
- **Biblia**: fichas de personajes, lugares y temas, con texto con formato e imágenes.
- **Storyboard**: cuadros por escena con plano, movimiento, imagen y descripción.
- **Modo novela**: capítulos y escenas con estado y punto de vista, metas de palabras, modo sugerencia y revisión de estilo.
- **Lectura en voz alta**, con una voz por personaje.
- **Colaboración en vivo**: salas online con cuentas, versiones e historial.
- **Exportar**:
  - guion: PDF, Final Draft (.fdx), Fountain y Word
  - novela: Word (.docx), PDF de libro, PDF manuscrito y EPUB
  - en los dos casos, con ajustes de hoja, márgenes, numeración y más

## Requisitos

- Windows 10 u 11 con Microsoft Edge (WebView2).
- Python 3.

## Cómo se abre

Doble clic en `Scripting.bat`. Abre la ventana de Scripting; si no está compilada, abre el servidor local en el navegador.

Los guiones se guardan en `Documentos\Guiones`, fuera de la carpeta del programa, así que actualizar Scripting no los toca.

## Voces

Las voces de lectura local (Piper, archivos `.onnx`) no están en el repositorio porque pesan mucho. Van en la carpeta `voces\`.

## Actualizaciones

Al abrir, Scripting consulta la última versión publicada en este repositorio (sección *Releases*). Si hay una más nueva, aparece abajo a la izquierda el aviso **⬆ Actualizar a X**. También se puede buscar a mano con ☰ › *Buscar actualizaciones*.

Al actualizar:

1. Se descarga el código de esa versión desde GitHub.
2. Se guarda una copia de lo que se reemplaza en `.actualizaciones\`.
3. Se instalan los archivos nuevos.
4. La app se recarga sola.

No se tocan los guiones, las voces ni la configuración.

Una copia que tenga carpeta `.git` (la de desarrollo) no se actualiza sola: se actualiza con `git pull`.

### Cómo publicar una versión

1. Cambiar el número en el archivo `VERSION`, por ejemplo `1.1.0`, y subirlo con commit y push.
2. En GitHub, entrar a *Releases* › *Draft a new release*.
3. En *Choose a tag*, escribir **el mismo número con una `v` adelante**, por ejemplo `v1.1.0`, y elegir *Create new tag*.
4. Poner un título y, en la descripción, las novedades: es lo que se muestra en el aviso.
5. Tocar *Publish release*.

Si el número de `VERSION` no coincide con la etiqueta, la app no instala la actualización.

## Instalador

`instalador\scripting.iss` (Inno Setup 7) arma un `Scripting-X-instalador.exe` que:

- se instala solo para el usuario, sin pedir permisos de administrador, en `%LOCALAPPDATA%\Programs\Scripting`;
- trae su propio Python 3.13 con las librerías de lectura (no hace falta instalar Python);
- crea los accesos directos.

Al abrir, usa la ventana translúcida si la PC tiene .NET 8 (Escritorio) y, si no, una ventana de Edge.

Para armarlo se ejecuta `instalador\armar.ps1`. Necesita una carpeta de armado fuera del repositorio (por defecto `..\..\instalador-build`) con:

- `python\`: Python embebible con `edge-tts` y `piper-tts`;
- `exe\`: `Scripting.exe` compilado;
- `herramientas\InnoSetup\`.

## Licencia

Todos los derechos reservados. Ver [LICENSE](LICENSE).

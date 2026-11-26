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

## Licencia

Todos los derechos reservados. Ver [LICENSE](LICENSE).

# data/

Los dos Excel de origen van acá, **no se commitean** (están en
`.gitignore`): tienen cifras reales de presupuesto municipal y el repo es
público. Solo entran a la base de datos local vía los scripts de
`scripts/`.

## `Libro1.xlsx`

Hoja `Hoja2`, 4 columnas: `Jur.` | `Secretaría` | `Categoría` | `Libre`.
`Libre` es el techo por Categoría programática dentro de cada Secretaría
(fuente 110). El techo total por Secretaría no viene en un archivo aparte
-- se deriva como la suma de sus categorías (ver el docstring de
`scripts/build_cuota_data.py` para la justificación).

## `formulario 7 2027.xlsx`

El Excel que hoy completa cada área a mano. Solo se usa la hoja
**"Listado de bienes"**: `Denominación` | `Código` | `Unidad de medida` |
`Unidad de medida N°` | ... | `Precios 2026` (columna G, el precio que se
usa como estimación 2027). Las hojas `Instructivo`, `Carga`, `F7 común` y
`F7 especial` son el formulario en sí -- la web las reemplaza, no se leen.

## Actualizar

Reemplazar el archivo correspondiente acá y correr de nuevo el script de
`scripts/` que lo importa (mismo `--anio`). Es idempotente: lo que sigue
igual no cambia de id, lo que ya no aparece en el Excel se marca
`vigente=0` en vez de borrarse (una carga de Formulario 7 ya enviada puede
seguir apuntando a esa fila).

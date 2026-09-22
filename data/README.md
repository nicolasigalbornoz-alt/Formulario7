# data/

Los Excel de origen van acá, **no se commitean** (están en `.gitignore`):
tienen cifras reales de presupuesto municipal y el repo es público. Solo
entran a la base de datos local vía los scripts de `scripts/`.

## `Libro2.xlsx` (fuente de la cuota, reemplaza a `Libro1.xlsx`)

Hoja `Techos`, columnas `Jur.` | `Secretaría` | `Categoría` | `Techo fuente
110 (F7 + F11)` | `Obras de construcción (F9)` | `Estimación fondo de 131
(total)`. Trae el techo por Categoría programática para **ambas fuentes**
(110 en la columna D, 131 en la F) en un solo archivo -- `Libro1.xlsx`
quedó obsoleto (solo traía 110) y ya no se usa. La columna E "Obras de
construcción" queda fuera de alcance, igual que antes. El techo total por
Secretaría no viene en un archivo aparte -- se deriva como la suma de sus
categorías, por fuente (ver el docstring de `scripts/build_cuota_data.py`).

**Regla de negocio, tal cual la trae el propio Excel** (columna H de la
hoja): el techo por Categoría es **sugerido**, no bloqueante -- se puede
compensar una categoría con menos gasto contra otra con más. Lo que **sí
es un máximo bloqueante es la suma de techos de toda la Secretaría**, por
fuente. `backend/validations.py` implementa exactamente esto.

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

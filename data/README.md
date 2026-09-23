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
`F7 especial` son el formulario en sí, no se leen para importar datos --
pero ver el punto siguiente, la web sí usa esa misma estructura para
generar el Excel que se descarga.

## `formulario7_modelo.xlsx`

Copia de `formulario 7 2027.xlsx` (mismas hojas y fórmulas) que usa
`backend/excel_export.py` como plantilla: cuando un área descarga el Excel
de una carga ya enviada, el backend abre una copia de este archivo y
escribe ahí Fuente/Denominación/Cantidad en la hoja "F7 común" (filas 11
en adelante) -- Código/Unidad/Precio/Total los resuelve la propia fórmula
`VLOOKUP` de la plantilla contra "Listado de bienes", igual que si alguien
lo completara a mano. La web no reemplaza este Excel: lo sigue generando,
solo que ahora la carga de datos es por la página en vez de tipeando en la
planilla. La hoja "F7 especial" queda siempre vacía (ya no se cargan
ítems especiales en esta versión).

## Excels a Drive

`scripts/exportar_todos_los_excel.py` baja a `exports/` (gitignored) el
Excel de todas las cargas ya enviadas, pegando contra la API del backend
-- es el primer paso para subirlas a una carpeta de Drive. El script en sí
no tiene credenciales de Google ni sube nada: el backend Flask tampoco
tiene credenciales propias de Google Drive (eso requeriría una cuenta de
servicio de Google Cloud, que nadie configuró todavía). Por ahora la
subida a Drive la hace Claude a pedido, con su propio acceso a Drive del
usuario, tomando los archivos que deja este script. Si en algún momento
hace falta que quede automático (sin que alguien lo pida), ahí sí hay que
dar de alta una cuenta de servicio de Google Cloud con acceso a la
carpeta y cablear `backend/excel_export.py` para que suba directo.

## Actualizar

Reemplazar el archivo correspondiente acá y correr de nuevo el script de
`scripts/` que lo importa (mismo `--anio`). Es idempotente: lo que sigue
igual no cambia de id, lo que ya no aparece en el Excel se marca
`vigente=0` en vez de borrarse (una carga de Formulario 7 ya enviada puede
seguir apuntando a esa fila).

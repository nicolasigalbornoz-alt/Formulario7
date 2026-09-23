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

**Regla de negocio**: las notas del propio Excel (columna H de la hoja)
dicen que el techo por Categoría es "sugerido" y que el máximo es la suma
de la Secretaría. La regla vigente es más estricta: **los dos techos
bloquean** -- el de cada Categoría y el total de la Secretaría, por fuente
(`backend/validations.py`).

## `formulario 7 2027.xlsx`

La planilla oficial que completa cada área y **sube a la página**, una por
Categoría programática. De este archivo se importa a la base solo la hoja
**"Listado de bienes"**: `Denominación` | `Código` | `Unidad de medida` |
`Unidad de medida N°` | ... | `Precios 2026` (columna G, el precio de
Presupuesto que se usa como estimación 2027). Un bien sin precio ahí solo
puede ir en "F7 especial".

Lo que espera `backend/excel_import.py` de cada Excel subido (la
estructura de esta misma planilla):

- Hojas **"F7 común"** y/o **"F7 especial"**, con los encabezados en la
  fila 10 (Fuente | Código | Denominación | Unidad | Cantidad | Precio |
  Costo total, columnas A a G) y los ítems desde la fila 11 hasta la fila
  "Subtotal".
- "F7 común": el área completa Fuente (A), Denominación (C) y Cantidad (E);
  Código, Unidad y Precio los completa el `VLOOKUP` de la planilla. El
  precio que vale es el de la base (el Listado oficial): si el archivo
  muestra otro, es un error.
- "F7 especial": el área completa de A a F, incluido el precio.
- Subjurisdicción en C6 y "Programa o Actividades centrales" en A7 (se
  guardan como referencia).

Se leen los valores que el archivo trae guardados (lo que Excel calculó al
guardarlo): no se ejecuta nada del archivo.

`formulario7_modelo.xlsx` (la plantilla que usaba la descarga de Excel)
ya no se usa: la página no genera archivos.

## Excels a Drive

El backend sube a Drive cada Excel **aprobado**, con una cuenta de servicio
de Google Cloud (variables `GOOGLE_DRIVE_*`, ver README de la raíz y
`backend/integrations.py`): un archivo por Categoría,
`F7_Subjurisdicción_Categoría.xlsx`, que se reemplaza (con historial de
versiones en Drive) cada vez que se aprueba un Excel nuevo de esa
Categoría. Además queda una copia en `cargas/` en el servidor (gitignored).
Los rechazados no van a Drive.

## Actualizar

Reemplazar el archivo correspondiente acá y correr de nuevo el script de
`scripts/` que lo importa (mismo `--anio`). Es idempotente: lo que sigue
igual no cambia de id, lo que ya no aparece en el Excel se marca
`vigente=0` en vez de borrarse (una carga de Formulario 7 ya enviada puede
seguir apuntando a esa fila).

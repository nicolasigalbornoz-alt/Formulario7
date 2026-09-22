# db/

`schema.sql` define toda la base (`formulario7.db`, SQLite, gitignored).
Crearla desde cero:

```bash
python -c "import sqlite3,pathlib; c=sqlite3.connect('db/formulario7.db'); c.executescript(pathlib.Path('db/schema.sql').read_text(encoding='utf-8')); c.commit()"
```

Después importar los datos de referencia (`scripts/build_cuota_data.py` y
`scripts/build_catalogo_data.py`) y crear el admin (`scripts/seed_admin.py`)
-- ver el README de la raíz para la secuencia completa.

## Tablas

- `secretaria`: las 14 Secretarías, resueltas por nombre desde
  `Libro1.xlsx` al importar la cuota.
- `fuente_financiamiento`: catálogo fijo (110 activa, 131 no todavía).
- `usuario`: login real. `rol` `area` (atado a una `secretaria_id`) o
  `admin` (sin Secretaría, ve todo).
- `secretaria_cuota_total` / `cuota_categoria`: el techo, por Secretaría y
  por Secretaría+Categoría respectivamente. Tienen `vigente` en vez de
  borrarse en cada reimportación -- una carga ya enviada no puede quedar
  apuntando a una fila que desapareció.
- `catalogo_bienes`: el "Listado de bienes" del Excel del formulario.
  `precio IS NULL` es un bien real (sirve para autocompletar código/unidad
  al cargarlo como "especial"), simplemente no tiene precio de catálogo.
- `f7_submission` / `f7_item`: una carga de Formulario 7 (única por
  Secretaría+Categoría+Fuente+año, por el `UNIQUE`) y sus ítems. `f7_item`
  guarda una foto de denominación/unidad/precio al momento de guardar, no
  un link en vivo al catálogo -- una carga ya enviada no cambia de valor si
  el catálogo se reimporta después con otros precios.

## Por qué no hay un total cacheado en `f7_submission`

Con el volumen esperado (unas pocas centenas de cargas por año, pocos
ítems cada una) un `SUM(subtotal)` en el momento es instantáneo, y evita
que un total cacheado se desincronice de sus propias filas -- se calcula
así en todos lados donde hace falta (`backend/db.py`), nunca se guarda.

## Editar un techo a mano vs. reimportar el Excel

`PATCH /api/admin/cuota-categoria/<id>` y `.../cuota-total/<id>` (el panel
"Reporte de cuota" del admin) actualizan `techo`/`monto_total` directo en la
base, para correcciones puntuales. Esos valores **no vuelven** a
`Libro1.xlsx`: si alguien corre `build_cuota_data.py` de nuevo, pisa
cualquier edición manual con lo que diga el Excel en ese momento. Una
corrección que tiene que durar hay que hacerla en el Excel también, no solo
acá.

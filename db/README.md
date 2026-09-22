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
  `Libro2.xlsx` al importar la cuota.
- `fuente_financiamiento`: catálogo fijo. Se activa sola (`activa=1`) al
  correr `build_cuota_data.py`, si esa fuente tiene datos en el Excel.
- `usuario`: login real. `rol` `area` (atado a una `secretaria_id`) o
  `admin` (sin Secretaría, ve todo).
- `secretaria_cuota_total` / `cuota_categoria`: el techo, por Secretaría y
  por Secretaría+Categoría respectivamente, con una fila por cada fuente
  que corresponda (una categoría puede tener techo en 110, en 131, en
  ambas o en ninguna -- si no tiene, no se crea la fila). Tienen `vigente`
  en vez de borrarse en cada reimportación -- una carga ya enviada no
  puede quedar apuntando a una fila que desapareció. **El techo de
  `cuota_categoria` es informativo** (el Excel lo llama "sugerido"); el
  que de verdad bloquea el envío es `secretaria_cuota_total.monto_total`
  -- ver `backend/validations.py`.
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
`Libro2.xlsx`: si alguien corre `build_cuota_data.py` de nuevo, pisa
cualquier edición manual con lo que diga el Excel en ese momento. Una
corrección que tiene que durar hay que hacerla en el Excel también, no solo
acá.

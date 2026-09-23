# Formulario7

Carga online del **Formulario N° 7** (Programación Anual de Compras de
Bienes y Contrataciones de Servicios) para las Secretarías de la
Municipalidad de Morón, con el techo presupuestario por categoría validado
en el momento en vez de conciliarse después contra el Excel.

No reemplaza al Excel: cada área carga por la web (con el techo
presupuestario validado en el momento), y en cualquier momento puede
descargar el mismo Excel de siempre (`formulario 7 2027.xlsx`, misma hoja
"F7 común", mismas fórmulas) ya completado con lo que cargó -- para
mandarlo por mail a `dir.presupuesto@moron.gob.ar` o para lo que haga
falta después (el bot de carga a RAFAM de Pagv2 lee ese mismo formato).

## Cómo está armado

- **Backend**: Flask + SQLite (`backend/`, `db/formulario7.db`) -- un solo
  proceso, sin build step. Auth real (usuario/contraseña con hash,
  sesión de servidor), no la clave compartida que usa el sitio hermano
  Pagv2.
- **Frontend**: HTML/CSS/JS plano (`frontend/`), sin framework.
- **Datos de referencia** (`data/`, no se commitean -- ver `data/README.md`):
  `Libro2.xlsx` (techo presupuestario, ambas fuentes) y `formulario 7
  2027.xlsx` (catálogo de bienes), importados a la base con los scripts de
  `scripts/`. `formulario7_modelo.xlsx` es la plantilla que usa
  `backend/excel_export.py` para generar la descarga.

Fuentes de financiamiento **110 y 131 están activas**, ambas con techo
propio por Categoría y por Secretaría (`Libro2.xlsx` las trae juntas).
Regla de negocio (tal cual la trae el propio Excel, ver `data/README.md`):
el techo **por Categoría es sugerido** -- se puede compensar gastando de
más en una y de menos en otra dentro de la misma Secretaría -- y el que
**sí bloquea el envío es el total por Secretaría** (y por fuente).

## Levantar todo localmente

1. `pip install -r requirements.txt`
2. Copiar `Libro2.xlsx`, `formulario 7 2027.xlsx` y `formulario7_modelo.xlsx` a `data/` (ver `data/README.md`)
3. Crear la base:
   ```bash
   python -c "import sqlite3,pathlib; c=sqlite3.connect('db/formulario7.db'); c.executescript(pathlib.Path('db/schema.sql').read_text(encoding='utf-8')); c.commit()"
   ```
4. Importar los datos de referencia:
   ```bash
   python scripts/build_cuota_data.py --anio 2027
   python scripts/build_catalogo_data.py --anio 2027
   ```
5. Crear el usuario administrador:
   ```bash
   python scripts/seed_admin.py --username admin
   ```
6. Correr el backend y el frontend (o usar los dos configs de `.claude/launch.json`):
   ```bash
   SECRET_KEY="una-clave-larga-random" python backend/app.py
   python -m http.server 8890 --directory frontend
   ```
7. Abrir http://localhost:8890 -- ingresar con el admin, crear ahí un
   usuario por cada Secretaría que vaya a cargar (Usuarios → Crear usuario).

`SECRET_KEY` es obligatoria fuera de una prueba local rápida (firma la
cookie de sesión); sin ella el servidor arranca con una clave de desarrollo
fija y lo avisa por log.

## Qué hace cada parte

- `GET/POST /api/formularios`: un área carga o reemplaza el Formulario 7 de
  una (Categoría × Fuente) suya. El servidor recalcula el total, revalida
  que cada fila esté completa, avisa (sin bloquear) si se supera el techo
  sugerido de la categoría, y bloquea el envío solo si se supera el total
  permitido de la Secretaría en esa fuente (devuelve cuánto hay disponible
  y cuánto se pidió).
- `PATCH /api/admin/cuota-categoria/<id>` y `.../cuota-total/<id>`: el admin
  corrige un techo a mano sin tener que volver a subir el Excel. **Ojo**: la
  próxima vez que se corra `build_cuota_data.py` con `Libro2.xlsx`, ese
  Excel vuelve a pisar el valor -- es la fuente de verdad de origen. Una
  edición manual pensada para durar tiene que reflejarse también ahí.
- `GET /api/admin/seguimiento`: panel de avance -- por Secretaría y fuente,
  cuántas de sus categorías ya tienen una carga enviada y cuáles faltan.
- `GET /api/admin/reporte`: techo presupuestario/cargado/disponible por
  categoría y por Secretaría (por fuente), con export a CSV.
- `GET /api/formularios/<id>/excel`: descarga el Excel de una carga ya
  enviada, generado a partir de `data/formulario7_modelo.xlsx` (ver
  `backend/excel_export.py` y `data/README.md`).
- `PATCH /api/admin/secretarias/<id>`: el admin carga la Subjurisdicción
  (código RAFAM fijo) de una Secretaría -- el área la ve de solo lectura,
  no la puede escribir.

Ver `db/README.md` para el detalle del esquema y `data/README.md` para el
formato esperado de los Excel de origen.

## Pendiente (fuera de alcance de esta primera versión)

- Ítems "especiales" (bienes fuera del catálogo o sin precio asignado) --
  se sacaron de esta versión, solo se cargan bienes del catálogo con
  precio. Si hace falta volver a admitirlos, hay que reabrir esa rama en
  `backend/validations.py` (ya no existe) y el flujo de carga manual en
  `frontend/js/formulario.js`.
- Que un usuario de área pueda cambiar su propia contraseña (hoy solo el
  admin la resetea).
- Selector de año fiscal (hoy `ANIO_FISCAL` es una constante en `backend/app.py`, 2027).
- Deploy real (hoy es todo local; para llevarlo a algo como Render hace
  falta un `Procfile`/similar y mover `SECRET_KEY`/`FRONTEND_ORIGIN` a
  variables de entorno del servicio -- ya están leídas así, falta el
  hosting en sí).

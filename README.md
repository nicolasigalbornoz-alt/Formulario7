# Formulario7

Carga online del **Formulario N° 7** (Programación Anual de Compras de
Bienes y Contrataciones de Servicios) para las Secretarías de la
Municipalidad de Morón, con la cuota por categoría validada en el momento
en vez de conciliarse después contra el Excel.

Reemplaza el flujo actual: cada área completaba `formulario 7 2027.xlsx` a
mano y lo mandaba por mail a `dir.presupuesto@moron.gob.ar`, y recién ahí se
chequeaba contra la cuota asignada (`Libro1.xlsx`).

## Cómo está armado

- **Backend**: Flask + SQLite (`backend/`, `db/formulario7.db`) -- un solo
  proceso, sin build step. Auth real (usuario/contraseña con hash,
  sesión de servidor), no la clave compartida que usa el sitio hermano
  Pagv2.
- **Frontend**: HTML/CSS/JS plano (`frontend/`), sin framework.
- **Datos de referencia** (`data/`, no se commitean -- ver `data/README.md`):
  `Libro1.xlsx` (cuota/techo) y `formulario 7 2027.xlsx` (catálogo de
  bienes), importados a la base con los scripts de `scripts/`.

Fuente de financiamiento: solo **110** está activa (es todo lo que trae
`Libro1.xlsx` hoy). La **131** ya tiene su lugar en el modelo de datos y en
la interfaz (aparece deshabilitada, "próximamente") -- para activarla el día
que haya un archivo de cuota propio: agregar sus filas a la tabla
`fuente_financiamiento` (`activa=1`) y correr `build_cuota_data.py` con los
datos de esa fuente.

## Levantar todo localmente

1. `pip install -r requirements.txt`
2. Copiar `Libro1.xlsx` y `formulario 7 2027.xlsx` a `data/` (ver `data/README.md`)
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
  que cada fila esté completa, y bloquea el envío si se supera el techo de
  la categoría o el total de la Secretaría (devuelve cuánto hay disponible
  y cuánto se pidió).
- `PATCH /api/admin/cuota-categoria/<id>` y `.../cuota-total/<id>`: el admin
  corrige un techo a mano sin tener que volver a subir el Excel. **Ojo**: la
  próxima vez que se corra `build_cuota_data.py` con `Libro1.xlsx`, ese
  Excel vuelve a pisar el valor -- es la fuente de verdad de origen. Una
  edición manual pensada para durar tiene que reflejarse también ahí.
- `GET /api/admin/seguimiento`: panel de avance -- por Secretaría, cuántas
  de sus categorías ya tienen una carga enviada y cuáles faltan.
- `GET /api/admin/reporte`: cuota usada/disponible por categoría y por
  Secretaría, con export a CSV.

Ver `db/README.md` para el detalle del esquema y `data/README.md` para el
formato esperado de los dos Excel de origen.

## Pendiente (fuera de alcance de esta primera versión)

- Integrar la fuente 131 cuando exista su archivo de cuota.
- Que un usuario de área pueda cambiar su propia contraseña (hoy solo el
  admin la resetea).
- Selector de año fiscal (hoy `ANIO_FISCAL` es una constante en `backend/app.py`, 2027).
- Deploy real (hoy es todo local; para llevarlo a algo como Render hace
  falta un `Procfile`/similar y mover `SECRET_KEY`/`FRONTEND_ORIGIN` a
  variables de entorno del servicio -- ya están leídas así, falta el
  hosting en sí).

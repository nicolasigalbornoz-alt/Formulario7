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

## Deploy

**Frontend**: publicado en GitHub Pages (`.github/workflows/deploy-pages.yml`,
se dispara solo con cada push a `main`) -- https://nicolasigalbornoz-alt.github.io/Formulario7/.
Solo sirve archivos estáticos; llama a lo que diga `API_BASE` en
`frontend/js/api.js`.

**Backend**: corriendo hoy dentro de un **GitHub Codespace** de este mismo
repo (codespace `legendary-fishstick-jjx7q79v7497h7j5`), con el puerto 5190
reenviado en modo público (`gh codespace ports visibility 5190:public`) --
sin necesitar cuenta de hosting nueva, usa la cuenta de GitHub que ya existe
para el repo. `API_BASE` en `frontend/js/api.js` apunta a la URL pública que
da ese reenvío (`https://<nombre-del-codespace>-5190.app.github.dev`).

Esto es un parche funcional, no un deploy "de manual": el codespace se
autodetiene tras un rato de inactividad (`--idle-timeout`, hoy 4hs) y ahí se
cae el backend hasta que alguien lo reinicie a mano (`gh codespace ssh` +
volver a levantar `backend/app.py` + volver a poner el puerto en público --
la IP pública cambia si se borra el codespace, pero **no** solo por
detenerse y reiniciarse). A favor: a diferencia del plan gratis de Render,
acá el disco **sí es persistente** entre reinicios -- la base con los
Formularios 7 cargados no se pierde, salvo que se borre el codespace.
Los minutos de cómputo de Codespaces no son ilimitados (cuota gratis
mensual por cuenta de GitHub); para un uso sostenido en el tiempo conviene
migrar a un hosting pensado para eso -- quedan los pasos con Render más
abajo para cuando haga falta.

<details>
<summary>Alternativa: Render (requiere que alguien cree la cuenta)</summary>

1. En [render.com](https://render.com) → New → Web Service → conectar este
   repo de GitHub.
2. Root Directory: (vacío/raíz). Build Command: `pip install -r requirements.txt`.
   Start Command: `python backend/app.py`. Plan: Free o Starter (ver ⚠️).
3. Variables de entorno: `SECRET_KEY` (Generate en el propio Render) y
   `FRONTEND_ORIGIN=https://nicolasigalbornoz-alt.github.io`.
4. Los datos de referencia (`Libro2.xlsx`, `formulario 7 2027.xlsx`,
   `formulario7_modelo.xlsx`) no están en el repo (cifras reales, no se
   commitean) -- subirlos como *Secret Files* de Render (Environment →
   Secret Files) y correr, desde el Shell de Render, los mismos comandos de
   "Levantar todo localmente" (pasos 3 a 5) apuntando `--archivo` a donde
   Render deja los secret files (`/etc/secrets/...`).
5. Actualizar `API_BASE` en `frontend/js/api.js` con la URL que dé Render.

⚠️ El plan Free de Render **no tiene disco persistente**: cada redeploy (o
cada vez que el servicio se "duerme" y despierta) borra `db/formulario7.db`
-- se pierden los Formularios 7 ya cargados. Para eso hace falta el plan
Starter con disco (~USD 7/mes) o mover a Postgres.
</details>

Como red de respaldo en cualquiera de los dos casos,
`scripts/exportar_todos_los_excel.py` + la carpeta de Drive (ver
`data/README.md`, "Excels a Drive") guardan una copia de lo ya enviado
aparte de la base.

## Pendiente (fuera de alcance de esta primera versión)

- Ítems "especiales" (bienes fuera del catálogo o sin precio asignado) --
  se sacaron de esta versión, solo se cargan bienes del catálogo con
  precio. Si hace falta volver a admitirlos, hay que reabrir esa rama en
  `backend/validations.py` (ya no existe) y el flujo de carga manual en
  `frontend/js/formulario.js`.
- Que un usuario de área pueda cambiar su propia contraseña (hoy solo el
  admin la resetea).
- Selector de año fiscal (hoy `ANIO_FISCAL` es una constante en `backend/app.py`, 2027).
- Deploy del backend en un hosting pensado para eso, no un Codespace (ver "Deploy" arriba).

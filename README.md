# Formulario7

Carga del **Formulario N° 7** (Programación Anual de Compras de Bienes y
Contrataciones de Servicios) para las Secretarías de la Municipalidad de
Morón: cada área **sube el Excel oficial** del Formulario 7 de cada
categoría programática y el sistema lo revisa entero antes de aceptarlo.

- Solo se carga si el Excel cumple lo que pide el instructivo de la propia
  planilla: denominaciones copiadas del Listado de bienes, **todas las
  celdas pintadas de cada fila completas** y cantidades enteras. Los bienes
  de "F7 común" usan el precio de Presupuesto y los de "F7 especial" el que
  pone el área. El archivo puede llamarse de cualquier manera, y el
  encabezado (Subjurisdicción, Fecha, Programa) no se valida.
- No puede pasarse del **techo presupuestario de la categoría ni del total
  de la Secretaría** (por fuente de financiamiento).
- **Aprobado**: se guarda en la carpeta de Google Drive de Presupuesto, en
  una subcarpeta por jurisdicción (`04 - Salud`) y con el nombre de la
  categoría (`22.01.00.xlsx`), y se registran sus ítems.
- **Rechazado**: no se carga nada. El área ve en la página cada error con
  su hoja y celda para corregirlo y volver a subirlo.
- No se manda ningún mail. Las direcciones de Presupuesto
  (dir.presupuesto@moron.gob.ar, bessega.tadeo@moron.gob.ar) figuran en la
  página para que las áreas escriban con dudas sobre el techo o la carga.

La página no genera ni devuelve ningún archivo.

## Cómo está armado

- **Backend**: Flask + SQLite (`backend/`, `db/formulario7.db`) -- un solo
  proceso, sin build step. Auth real (usuario/contraseña con hash, sesión
  por token), no la clave compartida que usa el sitio hermano Pagv2.
  `excel_import.py` lee y valida el Excel, `validations.py` los techos,
  `integrations.py` lo guarda en Drive.
- **Frontend**: HTML/CSS/JS plano (`frontend/`), sin framework.
- **Datos de referencia** (`data/`, no se commitean -- ver `data/README.md`):
  `Libro2.xlsx` (techo presupuestario, ambas fuentes) y `formulario 7
  2027.xlsx` (catálogo de bienes con los precios de Presupuesto),
  importados a la base con los scripts de `scripts/`.

Fuentes de financiamiento: `Libro2.xlsx` trae techo para la 110 y la 131,
pero **solo se muestra y se acepta la 110**. Lo define la variable
`FUENTES_HABILITADAS` del backend (por defecto `110`; con `110,131` vuelve
la 131). El backend la aplica al arrancar, y los techos y cargas de una
fuente oculta quedan en la base sin tocar. Un
Excel es el Formulario 7 completo de una categoría y trae la fuente fila
por fila: sus totales se validan por fuente. Los dos techos bloquean: el
**de la categoría** y el **total de la Secretaría** (la suma de sus
categorías). Ojo: las notas de `Libro2.xlsx` todavía dicen que el techo por
categoría es "sugerido"; la regla vigente es que también es un máximo.

## Levantar todo localmente

1. `pip install -r requirements.txt`
2. Copiar `Libro2.xlsx` y `formulario 7 2027.xlsx` a `data/` (ver `data/README.md`)
3. Crear la base (el backend la actualiza solo al arrancar si le falta alguna tabla nueva):
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

Sin Drive configurado todo funciona igual, pero los aprobados quedan solo
en el servidor (`cargas/`). Ver "Drive" más abajo.

Pruebas: `python -m unittest discover -s tests -v` (arman sus propias
planillas y una base temporal; no necesitan los Excel de `data/`).

## Qué hace cada parte

- `POST /api/formularios/excel` (multipart: `categoria` + `archivo`): un
  área sube el Excel de una de sus categorías. Se valida entero
  (`backend/excel_import.py` + `backend/validations.py`) y:
  - si está todo bien (201): se sube a Drive y se guardan sus ítems -- un
    Excel reemplaza la carga anterior de esa categoría, incluida la de una
    fuente habilitada que ya no traiga;
  - si hay algún error (422): no se guarda nada y se devuelve la lista
    completa (`errores`, cada uno con `hoja`/`celda`/`mensaje`, o
    `tipo: "techo"` con techo/solicitado/excedente).
  Cada intento queda registrado en `f7_carga_excel`.
- `GET /api/mis-categorias`: las categorías del área (por fuente) con techo
  y cargado, el total de la Secretaría por fuente y el último Excel subido
  de cada categoría.
- `GET /api/admin/cargas-excel`: los últimos Excel subidos por todas las
  áreas, aprobados y rechazados (panel "Seguimiento" del admin).
- `PATCH /api/admin/cuota-categoria/<id>` y `.../cuota-total/<id>`: el admin
  corrige un techo a mano sin tener que volver a subir el Excel. **Ojo**: la
  próxima vez que se corra `build_cuota_data.py` con `Libro2.xlsx`, ese
  Excel vuelve a pisar el valor -- es la fuente de verdad de origen. Una
  edición manual pensada para durar tiene que reflejarse también ahí.
- `GET /api/admin/seguimiento`: panel de avance -- por Secretaría y fuente,
  cuántas de sus categorías ya tienen una carga enviada y cuáles faltan.
- `GET /api/admin/reporte`: techo presupuestario/cargado/disponible por
  categoría y por Secretaría (por fuente), con export a CSV.
- `PATCH /api/admin/secretarias/<id>`: el admin carga la Subjurisdicción
  (código RAFAM fijo) de una Secretaría, como dato de referencia.

Ver `db/README.md` para el detalle del esquema y `data/README.md` para el
formato esperado de los Excel de origen.

## Deploy

**Backend**: corriendo en **Render** (Web Service, plan Free), conectado a
este repo -- cada push a `main` lo redeploya solo. URL:
`https://formulario7.onrender.com`. `API_BASE` en `frontend/js/api.js`
apunta ahí.

⚠️ El plan Free de Render **no tiene disco persistente**: cada redeploy (o
cada vez que el servicio se "duerme" por inactividad y despierta) borra
`db/formulario7.db` entero -- se pierden los usuarios, los techos y los
Formularios 7 ya cargados (los Excel aprobados sobreviven aparte, en Drive,
si está configurado -- ver "Drive" abajo). Para que el servicio no arranque
completamente vacío en cada reset:

- **Admin**: variables de entorno `ADMIN_USERNAME` y `ADMIN_PASSWORD` en
  Render (Settings → Environment) -- el backend crea (o reactiva y resetea
  la contraseña de) ese admin solo al arrancar, sin necesitar shell
  (`backend/app.py:_sembrar_admin`).
- **Techos presupuestarios**: no hay shell en el plan Free para correr
  `scripts/build_cuota_data.py`, así que se suben por API una vez logueado
  como admin -- `POST /api/admin/importar-techos` (multipart, campo
  `archivo` con el Excel de techos, mismo formato que `Libro2.xlsx`/hoja
  "Techos"; opcional `fuentes` en el form, default `"110"`). Ejemplo:
  ```bash
  curl -X POST https://formulario7.onrender.com/api/admin/importar-techos \
    -H "Authorization: Bearer $TOKEN" \
    -F "archivo=@Libro2.xlsx"
  ```
- El **catálogo de bienes** (`formulario 7 2027.xlsx`) no tiene un endpoint
  equivalente todavía -- hoy solo se importa localmente
  (`scripts/build_catalogo_data.py`) contra un archivo de base con disco
  persistente, o manualmente vía el Shell de un plan pago de Render.

Para uso sostenido sin perder datos en cada sleep, migrar al plan Starter de
Render (~USD 7/mes, con disco persistente) o mover a Postgres.

Como red de respaldo, cada Excel aprobado queda en Drive y además en
`cargas/` en el servidor (`FORMULARIO7_CARGAS_DIR`) -- esto último tampoco
sobrevive un reset en el plan Free.

**Frontend**: publicado en GitHub Pages (`.github/workflows/deploy-pages.yml`,
se dispara solo con cada push a `main`) -- https://nicolasigalbornoz-alt.github.io/Formulario7/.
Solo sirve archivos estáticos; llama a lo que diga `API_BASE` en
`frontend/js/api.js`.

También está publicado en Cloudflare (Worker de solo archivos estáticos,
`wrangler.toml`, sirve `frontend/` vía Workers Static Assets):
https://formulario7.moron-presupuesto.workers.dev/. Con "Workers Builds"
conectado al repo en el dashboard de Cloudflare, se actualiza solo en cada
push (antes había que subir el contenido de `frontend/` a mano -- sin
`wrangler.toml` esa build no tenía forma de saber qué desplegar). El backend
acepta los dos orígenes (`FRONTEND_ORIGIN` con los dos, separados por coma).

### Drive

Los Excel aprobados se guardan en la carpeta de Drive de Presupuesto
(https://drive.google.com/drive/folders/13tEsPkFBoMysSdxdqQtC2s0LwuAqsGec).
La subida pasa por un Apps Script (`scripts/drive_apps_script.gs`) que
publica la **persona dueña de la carpeta**: corre con su cuenta, así que
guarda en una carpeta común de "Mi unidad" sin proyecto de Google Cloud.
Se configura una sola vez:

1. Con la cuenta dueña de la carpeta, entrar a https://script.google.com →
   **Nuevo proyecto**, borrar lo que trae y pegar `scripts/drive_apps_script.gs`.
2. En `TOKEN` poner una clave larga inventada (no subirla al repo).
3. **Implementar → Nueva implementación → Aplicación web**, con "Ejecutar
   como: **Yo**" y "Quién tiene acceso: **Cualquier usuario**". Autorizar
   el acceso a Drive cuando lo pida y copiar la URL (termina en `/exec`).
4. En el backend, las variables `DRIVE_APPS_SCRIPT_URL` (esa URL) y
   `DRIVE_TOKEN` (la misma clave), y reiniciarlo. En Render se cargan en
   Settings → Environment, igual que las demás.
5. Subir lo que se aprobó antes de configurar Drive:
   `python scripts/subir_pendientes_a_drive.py --anio 2027`.

Dentro de la carpeta, el script crea una subcarpeta por jurisdicción
(`04 - Salud`) y guarda cada Excel aprobado con el nombre de su categoría
(`22.01.00.xlsx`). Cada categoría tiene un solo archivo: al aprobarse un
Excel nuevo, el anterior va a la papelera de Drive (se recupera de ahí
durante 30 días). Si se cambia el código del script, hay que publicar una
versión nueva (Implementar → Gestionar implementaciones → editar → Versión:
nueva versión) para que la URL siga siendo la misma.
Con `REQUIRE_DRIVE_UPLOAD=1` no se aprueba ninguna carga si Drive no está
configurado o falla.

## Pendiente (fuera de alcance de esta versión)

- Configurar Drive en el servidor (ver "Drive"): hasta entonces los
  aprobados quedan solo en `cargas/`; el admin ve todos los intentos en
  "Seguimiento".
- Que un usuario de área pueda cambiar su propia contraseña (hoy solo el
  admin la resetea).
- Selector de año fiscal (hoy `ANIO_FISCAL` es una constante en `backend/app.py`, 2027).
- Migrar a un plan de Render con disco persistente (o Postgres): en el plan
  Free actual, cada sleep/redeploy borra la base entera (ver "Deploy" arriba).
- Endpoint para importar el catálogo de bienes (`formulario 7 2027.xlsx`) sin
  shell, igual que ya existe para los techos (`POST /api/admin/importar-techos`).

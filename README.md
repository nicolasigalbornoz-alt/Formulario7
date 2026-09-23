# Formulario7

Carga del **Formulario N° 7** (Programación Anual de Compras de Bienes y
Contrataciones de Servicios) para las Secretarías de la Municipalidad de
Morón: cada área **sube el Excel oficial** del Formulario 7 de cada
categoría programática y el sistema lo revisa entero antes de aceptarlo.

- Solo se carga si el Excel está **bien completo**: toda fila con datos
  tiene todas sus columnas, los bienes de "F7 común" usan el precio de
  Presupuesto (el del Listado de bienes oficial) y los de "F7 especial"
  traen el precio que pone el área.
- No puede pasarse del **techo presupuestario de la categoría ni del total
  de la Secretaría** (por fuente de financiamiento).
- **Aprobado**: se guarda en una carpeta de Google Drive (un archivo por
  categoría, `F7_Subjurisdicción_Categoría.xlsx`), se registran sus ítems y
  se avisa por mail a Presupuesto con el Excel adjunto.
- **Rechazado**: no se carga nada. El área ve en la página cada error con
  su hoja y celda, y el mismo detalle va por mail, con una copia del Excel
  con cada celda con error marcada y comentada.

La página no genera ni devuelve ningún archivo.

## Cómo está armado

- **Backend**: Flask + SQLite (`backend/`, `db/formulario7.db`) -- un solo
  proceso, sin build step. Auth real (usuario/contraseña con hash, sesión
  por token), no la clave compartida que usa el sitio hermano Pagv2.
  `excel_import.py` lee y valida el Excel, `validations.py` los techos,
  `integrations.py` Drive y mail.
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

Sin Drive ni SMTP configurados todo funciona igual: los aprobados quedan
solo en el servidor (`cargas/`) y los mails no salen (queda en el log). Ver
"Drive y mail" más abajo para activarlos.

Pruebas: `python -m unittest discover -s tests -v` (arman sus propias
planillas y una base temporal; no necesitan los Excel de `data/`).

## Qué hace cada parte

- `POST /api/formularios/excel` (multipart: `categoria` + `archivo`): un
  área sube el Excel de una de sus categorías. Se valida entero
  (`backend/excel_import.py` + `backend/validations.py`) y:
  - si está todo bien (201): se sube a Drive, se guardan sus ítems -- un
    Excel reemplaza la carga anterior de esa categoría, incluida la de una
    fuente que ya no traiga -- y se avisa por mail con el Excel adjunto;
  - si hay algún error (422): no se guarda nada y se devuelve la lista
    completa (`errores`, cada uno con `hoja`/`celda`/`mensaje`, o
    `tipo: "techo"` con techo/solicitado/excedente). El mismo detalle va por
    mail, con el Excel marcado.
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
  (código RAFAM fijo) de una Secretaría. Se usa para nombrar el Excel
  aprobado (`F7_Subjurisdicción_Categoría`); si falta, se toma la celda C6
  del propio Excel.

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
4. Los datos de referencia (`Libro2.xlsx`, `formulario 7 2027.xlsx`) no
   están en el repo (cifras reales, no se commitean) -- subirlos como
   *Secret Files* de Render (Environment →
   Secret Files) y correr, desde el Shell de Render, los mismos comandos de
   "Levantar todo localmente" (pasos 3 a 5) apuntando `--archivo` a donde
   Render deja los secret files (`/etc/secrets/...`).
5. Actualizar `API_BASE` en `frontend/js/api.js` con la URL que dé Render.

⚠️ El plan Free de Render **no tiene disco persistente**: cada redeploy (o
cada vez que el servicio se "duerme" y despierta) borra `db/formulario7.db`
-- se pierden los Formularios 7 ya cargados. Para eso hace falta el plan
Starter con disco (~USD 7/mes) o mover a Postgres.
</details>

Como red de respaldo en cualquiera de los dos casos, cada Excel aprobado
queda en Drive y además en `cargas/` en el servidor (`FORMULARIO7_CARGAS_DIR`).

### Drive y mail

Variables de entorno del backend (detalle en `backend/integrations.py`):

- **Drive**: `GOOGLE_DRIVE_FOLDER_ID` (la carpeta destino) y las
  credenciales de una **cuenta de servicio** de Google Cloud con la API de
  Drive habilitada: `GOOGLE_DRIVE_CREDENTIALS_FILE` (ruta al JSON) o
  `GOOGLE_DRIVE_CREDENTIALS_JSON` (el contenido, cómodo como secreto del
  Codespace). Una cuenta de servicio no tiene espacio propio en "Mi unidad":
  la carpeta tiene que estar en una **Unidad compartida** con la cuenta de
  servicio como miembro (Administrador de contenido). Con
  `REQUIRE_DRIVE_UPLOAD=1` no se aprueba ninguna carga si Drive no está
  configurado o falla.
- **Mail**: `SMTP_HOST`, `SMTP_PORT` (587 con STARTTLS, 465 SSL),
  `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`. Destinatarios: `MAIL_TO`
  (separados por coma; por defecto `dir.presupuesto@moron.gob.ar` y
  `bessega.tadeo@moron.gob.ar`). Sale un mail por cada Excel aprobado (con
  el archivo) y por cada rechazado (con la lista de errores y el Excel
  marcado).

## Pendiente (fuera de alcance de esta versión)

- Configurar en el servidor la cuenta de servicio de Drive y el SMTP (ver
  "Drive y mail"): hasta entonces los aprobados quedan solo en `cargas/` y
  no sale ningún mail -- el admin ve todos los intentos en "Seguimiento".
- Mandar el aviso de rechazo también al mail del área (hoy los usuarios no
  tienen mail cargado; solo va a Presupuesto).
- Que un usuario de área pueda cambiar su propia contraseña (hoy solo el
  admin la resetea).
- Selector de año fiscal (hoy `ANIO_FISCAL` es una constante en `backend/app.py`, 2027).
- Deploy del backend en un hosting pensado para eso, no un Codespace (ver "Deploy" arriba).

"""
Backend de Formulario7: Flask + SQLite (db/formulario7.db), sin build step,
mismo espiritu que Pagv2/backend-local/app.py. Login real (auth.py). Cada
area carga su Formulario 7 subiendo el Excel oficial de cada Categoria:
se valida entero (excel_import.py: filas completas y precios;
validations.py: techo de la Categoria y total de la Secretaria) y solo si
pasa todo se registra y se guarda en Drive (integrations.py); si no, se
rechaza con la lista de errores.

Uso:
    python backend/app.py
Por defecto escucha en http://localhost:5190

Variables de entorno:
    PORT              puerto (default 5190)
    SECRET_KEY        no se usa para la sesion (ver auth.py), pero Flask la pide igual; cualquier valor sirve
    FRONTEND_ORIGIN   origenes exactos permitidos por CORS, separados por coma (default http://localhost:8890;
                      p. ej. "https://nicolasigalbornoz-alt.github.io,https://formulario7.moron-presupuesto.workers.dev")
    FORMULARIO7_DB_PATH    ubicacion de la base SQLite (default db/formulario7.db)
    FORMULARIO7_CARGAS_DIR donde se guarda una copia de cada Excel aprobado (default cargas/)
    FUENTES_HABILITADAS    fuentes de financiamiento que se muestran y se aceptan en el Excel,
                           separadas por coma (default 110 -- la 131 queda oculta; "110,131" la vuelve a mostrar)
    ADMIN_USERNAME, ADMIN_PASSWORD  si vienen las dos, crea (o reactiva y resetea la contraseña de)
                           ese admin al arrancar -- para hosts sin shell (Render) donde no se puede
                           correr scripts/seed_admin.py a mano
    Drive: ver el docstring de integrations.py (DRIVE_APPS_SCRIPT_URL, DRIVE_TOKEN, REQUIRE_DRIVE_UPLOAD)
"""
import hashlib
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from flask import Flask, jsonify, request

import auth
import db
import excel_import
import integrations
import validations

ANIO_FISCAL = int(os.environ.get("ANIO_FISCAL", 2027))
FRONTEND_ORIGINS = tuple(
    origen.strip().rstrip("/")
    for origen in (os.environ.get("FRONTEND_ORIGIN") or "http://localhost:8890").split(",") if origen.strip()
)
CARGAS_DIR = Path(os.environ.get("FORMULARIO7_CARGAS_DIR", db.RAIZ / "cargas"))
FUENTES_HABILITADAS = tuple(
    int(fuente) for fuente in (os.environ.get("FUENTES_HABILITADAS") or "110").split(",") if fuente.strip()
)
MAX_MB_EXCEL = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("formulario7")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "no-se-usa-la-sesion-de-flask-ver-auth.py")
# La planilla oficial pesa ~250 KB; esto es solo un tope contra archivos que no son el Formulario 7.
app.config["MAX_CONTENT_LENGTH"] = MAX_MB_EXCEL * 1024 * 1024


def _preparar_base():
    """Al arrancar: crea el archivo de la base si todavia no existe (hosts
    sin shell, como Render), lo que le falte a una base hecha con una
    version anterior de db/schema.sql (p. ej. la tabla `sesion` del login
    por token, sin la cual el login falla), deja habilitadas solo
    FUENTES_HABILITADAS y, si vienen ADMIN_USERNAME/ADMIN_PASSWORD y/o
    SEED_USUARIOS_AREA, crea o reactiva esos usuarios -- necesario en un
    host sin disco persistente, donde cada reinicio arranca con la base
    vacia y nadie puede loguearse para crearlos a mano."""
    db.asegurar_archivo()
    try:
        with db.conexion() as conn:
            db.asegurar_esquema(conn)
            db.habilitar_fuentes(conn, FUENTES_HABILITADAS)
            _sembrar_admin(conn)
            _sembrar_areas(conn)
    except db.DbError as exc:
        log.warning("No se pudo preparar la base: %s", exc)


def _sembrar_admin(conn):
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        return
    password_hash = auth.hashear_password(password)
    existente = db.obtener_usuario_por_username(conn, username)
    if existente and existente["rol"] == "admin":
        db.actualizar_usuario(conn, existente["id"], activo=True, password_hash=password_hash)
    elif not existente:
        db.crear_usuario(conn, username=username, password_hash=password_hash, rol="admin")


# Usuarios de area fijos: en un host sin disco persistente (Render Free)
# es lo unico que evita que una Secretaria se quede sin poder loguear
# despues de cada reset -- _sembrar_areas los recrea solos en cada arranque.
USUARIOS_AREA_FIJOS = {
    "HCD": ("hcd", "zZsjBBhdSP"),
    "Economía y Finanzas": ("economia_finanzas", "9qc7wg9XrE"),
    "Salud": ("salud", "gvzrMSEEvs"),
    "Obras y Serv. Púb.": ("obras_serv_pub", "nPXnpXSU2o"),
    "Control Comunal": ("control_comunal", "w3UP9kQeiq"),
    "Educación y Des. De la Com.": ("educacion", "L3eZ2SA8Sy"),
    "Legal y Técnica": ("legal_tecnica", "DAxfEjxTmH"),
    "Planificación Estratégica": ("planificacion_estrategica", "sVd3Svunrs"),
    "Mujeres, GyD": ("mujeres_gyd", "uakP44v2XX"),
    "Jefatura de Gabinete": ("jefatura_gabinete", "dgB54ki7So"),
    "Seguridad Ciudadana": ("seguridad_ciudadana", "BKL3YNfkx4"),
    "Desarrollo Local, Empleo y E.S.": ("desarrollo_local", "iEhY3pYsZi"),
    "Desarrollo Productivo": ("desarrollo_productivo", "4iSZbJzgin"),
    "Tránsito y Transporte": ("transito_transporte", "4xqEM7JDk7"),
}


def _sembrar_areas(conn):
    """Igual que _sembrar_admin, para USUARIOS_AREA_FIJOS. La Secretaria se
    resuelve por nombre (se crea si todavia no existe; importar-techos la
    completa despues con su jur)."""
    for nombre_secretaria, (username, password) in USUARIOS_AREA_FIJOS.items():
        secretaria_id = db.resolver_secretaria(conn, nombre_secretaria)
        password_hash = auth.hashear_password(password)
        existente = db.obtener_usuario_por_username(conn, username)
        if existente and existente["rol"] == "area":
            db.actualizar_usuario(conn, existente["id"], activo=True, password_hash=password_hash)
        elif not existente:
            db.crear_usuario(conn, username=username, password_hash=password_hash,
                              rol="area", secretaria_id=secretaria_id)


_preparar_base()


@app.before_request
def _preflight():
    if request.method == "OPTIONS":
        return "", 204


@app.after_request
def _cors(response):
    # Solo los origenes de FRONTEND_ORIGIN (no "*"): se devuelve el que hizo
    # el pedido si esta en la lista -- la pagina puede estar publicada en mas
    # de un lugar (GitHub Pages, Cloudflare). La sesion viaja por header
    # Authorization (ver auth.py), no por cookie: no hace falta
    # Access-Control-Allow-Credentials.
    origen = request.headers.get("Origin", "").rstrip("/")
    response.headers["Access-Control-Allow-Origin"] = origen if origen in FRONTEND_ORIGINS else FRONTEND_ORIGINS[0]
    response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return response


@app.errorhandler(413)
def _archivo_muy_grande(_exc):
    return jsonify({"ok": False, "error": f"El archivo supera el máximo de {MAX_MB_EXCEL} MB."}), 413


def _usuario_publico(usuario):
    return {
        "id": usuario["id"],
        "username": usuario["username"],
        "rol": usuario["rol"],
        "secretaria_id": usuario["secretaria_id"],
        "secretaria_nombre": usuario["secretaria_nombre"],
        "secretaria_subjurisdiccion": usuario.get("secretaria_subjurisdiccion"),
        "nombre_completo": usuario["nombre_completo"],
    }


# ================= Auth =================

@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return jsonify({"ok": False, "error": "Usuario y contraseña son obligatorios."}), 400

    try:
        with db.conexion() as conn:
            usuario = db.obtener_usuario_por_username(conn, username)
            if (usuario is None or not usuario["activo"]
                    or not auth.verificar_password(usuario["password_hash"], password)):
                return jsonify({"ok": False, "error": "Usuario o contraseña incorrectos."}), 401

            token = auth.generar_token()
            db.crear_sesion(conn, usuario["id"], token)
    except db.DbError as exc:
        log.error("Error de base en login: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True, "token": token, "usuario": _usuario_publico(usuario)}), 200


@app.route("/api/logout", methods=["POST"])
def logout():
    token = auth._token_de_la_request()
    if token is not None:
        with db.conexion() as conn:
            db.borrar_sesion(conn, token)
    return jsonify({"ok": True}), 200


@app.route("/api/sesion", methods=["GET"])
@auth.login_required
def sesion(usuario):
    return jsonify({"ok": True, "usuario": _usuario_publico(usuario)}), 200


# ================= Referencia =================

@app.route("/api/secretarias", methods=["GET"])
@auth.login_required
def secretarias(usuario):
    with db.conexion() as conn:
        return jsonify({"ok": True, "secretarias": db.listar_secretarias(conn)}), 200


@app.route("/api/fuentes", methods=["GET"])
@auth.login_required
def fuentes_endpoint(usuario):
    """Las fuentes habilitadas (FUENTES_HABILITADAS): las unicas que ofrecen
    los selectores del admin."""
    with db.conexion() as conn:
        fuentes = [f for f in db.listar_fuentes(conn) if f["activa"]]
    return jsonify({"ok": True, "fuentes": fuentes}), 200


@app.route("/api/admin/secretarias/<int:secretaria_id>", methods=["PATCH"])
@auth.admin_required
def actualizar_secretaria_endpoint(usuario, secretaria_id):
    """Carga la Subjurisdiccion (codigo RAFAM fijo) de una Secretaria --
    el area nunca la escribe a mano, la ve de solo lectura en el formulario."""
    body = request.get_json(silent=True) or {}
    subjurisdiccion = (body.get("subjurisdiccion") or "").strip() or None
    with db.conexion() as conn:
        db.actualizar_subjurisdiccion_secretaria(conn, secretaria_id, subjurisdiccion)
    log.info("Subjurisdiccion de secretaria_id=%s actualizada por admin=%s", secretaria_id, usuario["username"])
    return jsonify({"ok": True, "subjurisdiccion": subjurisdiccion}), 200


@app.route("/api/mis-categorias", methods=["GET"])
@auth.login_required
def mis_categorias(usuario):
    """Lo que ve el area en su pagina: sus categorias (una fila por
    Categoria+Fuente, con techo y lo ya cargado), el total de la Secretaria
    por fuente y el ultimo Excel que subio de cada Categoria."""
    if usuario["rol"] == "admin":
        secretaria_id = request.args.get("secretaria_id", type=int)
        if not secretaria_id:
            return jsonify({"ok": False, "error": "secretaria_id es requerido para el admin."}), 400
    else:
        secretaria_id = usuario["secretaria_id"]

    with db.conexion() as conn:
        fuentes = db.listar_fuentes(conn)
        categorias = db.listar_categorias_de_secretaria(conn, secretaria_id, ANIO_FISCAL)
        totales = [
            total
            for fuente in fuentes if fuente["activa"]
            for total in db.reporte_totales_secretaria(conn, ANIO_FISCAL, fuente["id"], secretaria_id=secretaria_id)
        ]
        ultimas_cargas = db.ultimas_cargas_por_categoria(conn, secretaria_id, ANIO_FISCAL)

    return jsonify({
        "ok": True,
        "categorias": categorias,
        "totales": totales,
        "ultimas_cargas": ultimas_cargas,
        "fuentes": fuentes,
        "anio_fiscal": ANIO_FISCAL,
    }), 200


# ================= Formularios =================

def _guardar_copia_local(contenido, secretaria_id, nombre_destino):
    """Copia del Excel aprobado en el servidor (FORMULARIO7_CARGAS_DIR): el
    respaldo mientras Drive no este configurado, o si algun dia se pierde
    el archivo de alla. Un error aca no frena la carga."""
    try:
        carpeta = CARGAS_DIR / str(ANIO_FISCAL) / f"secretaria_{secretaria_id}"
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"{datetime.now():%Y%m%d-%H%M%S}_{nombre_destino}"
        ruta.write_bytes(contenido)
        return str(ruta)
    except OSError:
        log.exception("No se pudo guardar la copia local de %s", nombre_destino)
        return None


@app.route("/api/formularios/excel", methods=["POST"])
@auth.login_required
def cargar_excel_endpoint(usuario):
    """El area carga el Formulario 7 de una Categoria subiendo su Excel (la
    planilla oficial, un archivo por Categoria). Se acepta solo si pasa
    TODAS las validaciones -- filas completas, precios, techo de la
    Categoria y techo total de la Secretaria --: ahi se guarda en Drive y
    se registran sus items (reemplazando la carga anterior de la Categoria).
    Si algo falla se rechaza entero, no se guarda nada y se devuelve la
    lista completa de errores. Nunca devuelve un archivo."""
    if usuario["rol"] != "area":
        return jsonify({"ok": False, "error": "Solo un usuario de área puede cargar un Formulario 7."}), 403

    categoria = (request.form.get("categoria") or "").strip()
    archivo = request.files.get("archivo")
    if not categoria:
        return jsonify({"ok": False, "error": "Elegí la categoría programática."}), 400
    if archivo is None or not archivo.filename:
        return jsonify({"ok": False, "error": "Seleccioná el Excel del Formulario 7."}), 400
    nombre_archivo = Path(archivo.filename.replace("\\", "/")).name
    if not nombre_archivo.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "error": "El archivo tiene que ser un Excel .xlsx (la planilla oficial "
                                              "del Formulario 7)."}), 400
    contenido = archivo.read()
    if not contenido:
        return jsonify({"ok": False, "error": "El archivo está vacío."}), 400

    secretaria_id = usuario["secretaria_id"]
    with db.conexion() as conn:
        cuotas = {c["fuente"]: c for c in db.listar_cuotas_de_categoria(conn, secretaria_id, categoria, ANIO_FISCAL)}
        if not cuotas:
            return jsonify({"ok": False, "error": "Esa categoría no tiene techo asignado para tu Secretaría."}), 400
        fuentes_activas = {f["id"] for f in db.listar_fuentes(conn) if f["activa"]}
        catalogo = db.listar_catalogo(conn, ANIO_FISCAL)

    lectura = excel_import.leer_formulario(
        contenido, categoria=categoria, catalogo=catalogo,
        fuentes_categoria=set(cuotas), fuentes_activas=fuentes_activas, anio_fiscal=ANIO_FISCAL,
    )
    totales_por_fuente = dict(lectura["totales_por_fuente"])
    with db.conexion() as conn:
        errores_techo = validations.validar_techos(
            conn, secretaria_id=secretaria_id, categoria=categoria, anio_fiscal=ANIO_FISCAL,
            totales_por_fuente=totales_por_fuente,
        )
    errores = errores_techo + lectura["errores"]

    totales = [
        {"fuente": fuente, "total": float(total), "techo_categoria": float(cuotas[fuente]["techo"])}
        for fuente, total in sorted(totales_por_fuente.items())
    ]
    total_general = float(sum(totales_por_fuente.values(), Decimal(0)))
    subjurisdiccion = usuario.get("secretaria_subjurisdiccion") or lectura["subjurisdiccion"]
    registro = {
        "secretaria_id": secretaria_id, "categoria": categoria, "anio_fiscal": ANIO_FISCAL,
        "nombre_archivo": nombre_archivo, "sha256": hashlib.sha256(contenido).hexdigest(),
        "total": total_general, "subido_por": usuario["id"],
    }

    if errores:
        with db.conexion() as conn:
            carga_id = db.registrar_carga_excel(conn, estado="rechazado", errores=errores, **registro)
        log.info("Excel rechazado: secretaria=%s categoria=%s archivo=%s errores=%s (carga id=%s)",
                 secretaria_id, categoria, nombre_archivo, len(errores), carga_id)
        return jsonify({
            "ok": False, "estado": "rechazado", "id": carga_id,
            "error": f"El Excel no se cargó: tiene {len(errores)} error(es). Corregilos en el archivo y volvé a subirlo.",
            "errores": errores, "totales": totales,
        }), 422

    # En Drive: una carpeta por jurisdiccion, el archivo con el nombre de la categoria.
    nombre_destino = integrations.nombre_archivo(categoria)
    carpeta = integrations.nombre_carpeta(usuario.get("secretaria_jur"), usuario["secretaria_nombre"])
    try:
        drive = integrations.subir_a_drive(nombre_destino, contenido, carpeta)
    except integrations.IntegracionError as exc:
        log.error("Excel valido pero no se pudo guardar en Drive (secretaria=%s categoria=%s): %s",
                  secretaria_id, categoria, exc)
        return jsonify({"ok": False, "error": f"El Excel está bien, pero no se pudo guardar en Drive, así que "
                                              f"no se registró la carga. Probá de nuevo en unos minutos. ({exc})"}), 502
    drive = drive or {}
    archivo_local = _guardar_copia_local(contenido, secretaria_id, nombre_destino)

    items_por_fuente = defaultdict(list)
    for item in lectura["items"]:
        items_por_fuente[item["fuente"]].append(item)
    with db.conexion() as conn:
        db.reemplazar_formularios_de_categoria(
            conn, secretaria_id=secretaria_id, categoria=categoria, anio_fiscal=ANIO_FISCAL,
            items_por_fuente=items_por_fuente, fuentes_activas=fuentes_activas,
            subjurisdiccion=subjurisdiccion, programa=lectura["programa"], submitted_by=usuario["id"],
        )
        carga_id = db.registrar_carga_excel(
            conn, estado="aprobado", errores=None, drive_file_id=drive.get("id"),
            drive_link=drive.get("webViewLink"), archivo_local=archivo_local, **registro)

    log.info("Excel aprobado: secretaria=%s categoria=%s total=%s items=%s drive=%s (carga id=%s)",
             secretaria_id, categoria, total_general, len(lectura["items"]), drive.get("id"), carga_id)
    return jsonify({
        "ok": True, "estado": "aprobado", "id": carga_id, "total": total_general, "totales": totales,
        "items": len(lectura["items"]), "drive": bool(drive),
    }), 201


@app.route("/api/formularios", methods=["GET"])
@auth.login_required
def listar_formularios_endpoint(usuario):
    if usuario["rol"] == "admin":
        secretaria_id = request.args.get("secretaria_id", type=int)
    else:
        secretaria_id = usuario["secretaria_id"]
    fuente = request.args.get("fuente", 110, type=int)

    with db.conexion() as conn:
        formularios = db.listar_formularios(conn, secretaria_id=secretaria_id, fuente=fuente, anio_fiscal=ANIO_FISCAL)
    return jsonify({"ok": True, "formularios": formularios}), 200


@app.route("/api/formularios/<int:submission_id>", methods=["GET"])
@auth.login_required
def obtener_formulario_endpoint(usuario, submission_id):
    with db.conexion() as conn:
        formulario = db.obtener_formulario(conn, submission_id)
    if formulario is None:
        return jsonify({"ok": False, "error": "No encontrado."}), 404
    if usuario["rol"] != "admin" and formulario["secretaria_id"] != usuario["secretaria_id"]:
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    return jsonify({"ok": True, "formulario": formulario}), 200


# ================= Admin =================

@app.route("/api/admin/usuarios", methods=["POST"])
@auth.admin_required
def crear_usuario_endpoint(usuario):
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    rol = body.get("rol")
    secretaria_id = body.get("secretaria_id")

    campos_requeridos = {"username": username, "password": password, "rol": rol}
    faltantes = [c for c, v in campos_requeridos.items() if not v]
    if faltantes:
        return jsonify({"ok": False, "error": f"Faltan campos: {faltantes}"}), 400
    if rol not in ("area", "admin"):
        return jsonify({"ok": False, "error": "rol debe ser 'area' o 'admin'."}), 400
    if rol == "area" and not secretaria_id:
        return jsonify({"ok": False, "error": "Un usuario de area necesita secretaria_id."}), 400
    if len(password) < 8:
        return jsonify({"ok": False, "error": "La contraseña debe tener al menos 8 caracteres."}), 400

    try:
        with db.conexion() as conn:
            nuevo_id = db.crear_usuario(
                conn, username=username, password_hash=auth.hashear_password(password),
                rol=rol, secretaria_id=secretaria_id, nombre_completo=body.get("nombre_completo"),
            )
    except db.DbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409

    log.info("Usuario creado: %s (rol=%s) por admin=%s", username, rol, usuario["username"])
    return jsonify({"ok": True, "id": nuevo_id}), 201


@app.route("/api/admin/usuarios", methods=["GET"])
@auth.admin_required
def listar_usuarios_endpoint(usuario):
    with db.conexion() as conn:
        return jsonify({"ok": True, "usuarios": db.listar_usuarios(conn)}), 200


@app.route("/api/admin/usuarios/<int:usuario_id>", methods=["PATCH"])
@auth.admin_required
def actualizar_usuario_endpoint(usuario, usuario_id):
    body = request.get_json(silent=True) or {}
    password_hash = auth.hashear_password(body["password"]) if body.get("password") else None
    if password_hash and len(body["password"]) < 8:
        return jsonify({"ok": False, "error": "La contraseña debe tener al menos 8 caracteres."}), 400
    with db.conexion() as conn:
        db.actualizar_usuario(conn, usuario_id, activo=body.get("activo"), password_hash=password_hash)
    log.info("Usuario id=%s actualizado por admin=%s", usuario_id, usuario["username"])
    return jsonify({"ok": True}), 200


@app.route("/api/admin/formularios/<int:submission_id>/anular", methods=["PATCH"])
@auth.admin_required
def anular_formulario_endpoint(usuario, submission_id):
    with db.conexion() as conn:
        if db.obtener_formulario(conn, submission_id) is None:
            return jsonify({"ok": False, "error": "No encontrado."}), 404
        db.anular_formulario(conn, submission_id)
    log.info("Formulario id=%s anulado por admin=%s", submission_id, usuario["username"])
    return jsonify({"ok": True}), 200


@app.route("/api/admin/reporte", methods=["GET"])
@auth.admin_required
def reporte_endpoint(usuario):
    secretaria_id = request.args.get("secretaria_id", type=int)
    fuente = request.args.get("fuente", 110, type=int)
    formato = request.args.get("formato", "json")

    with db.conexion() as conn:
        categorias = db.reporte_cuota(conn, ANIO_FISCAL, fuente, secretaria_id=secretaria_id)
        totales = db.reporte_totales_secretaria(conn, ANIO_FISCAL, fuente, secretaria_id=secretaria_id)

    if formato == "csv":
        import csv
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Secretaria", "Categoria", "Fuente", "Techo presupuestario", "Cargado", "Disponible"])
        for fila in categorias:
            writer.writerow([fila["secretaria"], fila["categoria"], fuente, fila["techo"], fila["cargado"], fila["disponible"]])
        respuesta = app.response_class(buf.getvalue(), mimetype="text/csv")
        respuesta.headers["Content-Disposition"] = f"attachment; filename=reporte_techo_presupuestario_{fuente}_{ANIO_FISCAL}.csv"
        return respuesta

    return jsonify({
        "ok": True, "categorias": categorias, "totales_secretaria": totales,
        "anio_fiscal": ANIO_FISCAL, "fuente": fuente,
    }), 200


@app.route("/api/admin/cuota-categoria/<int:cuota_categoria_id>", methods=["PATCH"])
@auth.admin_required
def actualizar_techo_categoria_endpoint(usuario, cuota_categoria_id):
    """Edicion manual del techo por categoria -- para correcciones puntuales
    sin tener que volver a subir Libro2.xlsx (que igual las pisaria en la
    proxima reimportacion, eso es esperable y se documenta en db/README.md).
    Este techo bloquea (ver validations.validar_techos): el proximo Excel de
    esa categoria se valida contra el valor nuevo. Las cargas ya aprobadas
    no se revalidan."""
    body = request.get_json(silent=True) or {}
    try:
        techo = float(body.get("techo"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "El techo debe ser un numero."}), 400
    if techo < 0:
        return jsonify({"ok": False, "error": "El techo no puede ser negativo."}), 400

    with db.conexion() as conn:
        actual = db.obtener_cuota_categoria_por_id(conn, cuota_categoria_id)
        if actual is None:
            return jsonify({"ok": False, "error": "No encontrado."}), 404
        db.actualizar_techo_categoria(conn, cuota_categoria_id, techo)

    log.info("Techo editado por admin=%s: secretaria_id=%s categoria=%s %s -> %s",
              usuario["username"], actual["secretaria_id"], actual["categoria"], actual["techo"], techo)
    return jsonify({"ok": True, "techo": techo}), 200


@app.route("/api/admin/cuota-total/<int:secretaria_cuota_total_id>", methods=["PATCH"])
@auth.admin_required
def actualizar_monto_total_endpoint(usuario, secretaria_cuota_total_id):
    body = request.get_json(silent=True) or {}
    try:
        monto_total = float(body.get("monto_total"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "El monto debe ser un numero."}), 400
    if monto_total < 0:
        return jsonify({"ok": False, "error": "El monto no puede ser negativo."}), 400

    with db.conexion() as conn:
        actual = db.obtener_secretaria_cuota_total_por_id(conn, secretaria_cuota_total_id)
        if actual is None:
            return jsonify({"ok": False, "error": "No encontrado."}), 404
        db.actualizar_monto_total_secretaria(conn, secretaria_cuota_total_id, monto_total)

    log.info("Monto total editado por admin=%s: secretaria_id=%s %s -> %s",
              usuario["username"], actual["secretaria_id"], actual["monto_total"], monto_total)
    return jsonify({"ok": True, "monto_total": monto_total}), 200


@app.route("/api/admin/importar-techos", methods=["POST"])
@auth.admin_required
def importar_techos_endpoint(usuario):
    """Sube el Excel de techos presupuestarios (misma estructura de
    Libro2.xlsx, hoja "Techos") y lo importa directo a la base -- para hosts
    sin shell (Render) donde no se puede correr scripts/build_cuota_data.py
    a mano. Por default importa solo la fuente 110 (la unica habilitada);
    mandar "fuentes":"110,131" en el form para traer tambien la 131."""
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        return jsonify({"ok": False, "error": "Seleccioná el Excel de techos presupuestarios."}), 400
    if not archivo.filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "error": "El archivo tiene que ser un Excel .xlsx."}), 400
    contenido = archivo.read()
    if not contenido:
        return jsonify({"ok": False, "error": "El archivo está vacío."}), 400

    fuentes = tuple(
        int(f) for f in (request.form.get("fuentes") or "110").split(",") if f.strip()
    )

    try:
        with db.conexion() as conn:
            resumen = db.importar_techos(conn, contenido, ANIO_FISCAL, fuentes=fuentes)
    except db.DbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    log.info("Techos importados por admin=%s: %s", usuario["username"], resumen)
    return jsonify({"ok": True, **resumen}), 200


@app.route("/api/admin/importar-catalogo", methods=["POST"])
@auth.admin_required
def importar_catalogo_endpoint(usuario):
    """Sube el Excel del catalogo de bienes (misma estructura de
    "formulario 7 2027.xlsx", hoja "Listado de bienes") y lo importa directo
    a la base -- para hosts sin shell (Render) donde no se puede correr
    scripts/build_catalogo_data.py a mano. Sin este catalogo cargado, todo
    Excel de "F7 común" se rechaza (no hay con que verificar la
    denominación ni el precio de Presupuesto de cada bien)."""
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        return jsonify({"ok": False, "error": "Seleccioná el Excel del catálogo de bienes."}), 400
    if not archivo.filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "error": "El archivo tiene que ser un Excel .xlsx."}), 400
    contenido = archivo.read()
    if not contenido:
        return jsonify({"ok": False, "error": "El archivo está vacío."}), 400

    try:
        with db.conexion() as conn:
            resumen = db.importar_catalogo(conn, contenido, ANIO_FISCAL)
    except db.DbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    log.info("Catálogo importado por admin=%s: %s", usuario["username"], resumen)
    return jsonify({"ok": True, **resumen}), 200


@app.route("/api/admin/seguimiento", methods=["GET"])
@auth.admin_required
def seguimiento_endpoint(usuario):
    """Panel de avance: por Secretaria, cuantas de sus categorias ya tienen
    una carga 'enviada' y cuales faltan -- para saber a quien hay que
    recordarle, sin tener que revisar el reporte de montos categoria por
    categoria."""
    fuente = request.args.get("fuente", 110, type=int)
    with db.conexion() as conn:
        filas = db.seguimiento_categorias(conn, fuente, ANIO_FISCAL)

    por_secretaria = {}
    for f in filas:
        s = por_secretaria.setdefault(f["secretaria_id"], {
            "secretaria_id": f["secretaria_id"],
            "secretaria": f["secretaria"],
            "total_categorias": 0,
            "cargadas": 0,
            "ultima_carga": None,
            "pendientes": [],
        })
        s["total_categorias"] += 1
        if f["submission_id"] is not None:
            s["cargadas"] += 1
            if s["ultima_carga"] is None or f["submitted_at"] > s["ultima_carga"]:
                s["ultima_carga"] = f["submitted_at"]
        else:
            s["pendientes"].append(f["categoria"])

    resumen = sorted(por_secretaria.values(), key=lambda s: s["secretaria"])
    for s in resumen:
        s["porcentaje"] = round(100 * s["cargadas"] / s["total_categorias"], 1) if s["total_categorias"] else 0.0

    total_categorias = sum(s["total_categorias"] for s in resumen)
    total_cargadas = sum(s["cargadas"] for s in resumen)

    return jsonify({
        "ok": True,
        "secretarias": resumen,
        "totales": {
            "total_categorias": total_categorias,
            "cargadas": total_cargadas,
            "porcentaje": round(100 * total_cargadas / total_categorias, 1) if total_categorias else 0.0,
        },
        "anio_fiscal": ANIO_FISCAL,
        "fuente": fuente,
    }), 200


@app.route("/api/admin/cargas-excel", methods=["GET"])
@auth.admin_required
def cargas_excel_endpoint(usuario):
    """Ultimos Excel subidos por las areas, aprobados y rechazados, con el
    link al archivo de Drive de los aprobados."""
    limite = max(1, min(request.args.get("limite", 100, type=int), 500))
    with db.conexion() as conn:
        cargas = db.listar_cargas_excel(conn, ANIO_FISCAL, limite=limite)
    return jsonify({
        "ok": True, "cargas": cargas, "anio_fiscal": ANIO_FISCAL,
        "drive_configurado": integrations.drive_configurado(),
    }), 200


# ================= Salud =================

@app.route("/api/salud", methods=["GET"])
def salud():
    try:
        with db.conexion() as conn:
            conn.execute("SELECT 1").fetchone()
    except db.DbError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "db": str(db._db_path()), "anio_fiscal": ANIO_FISCAL}), 200


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 5190))
    print(f"Formulario7 backend escuchando en http://localhost:{puerto}")
    print(f"Base de datos: {db._db_path()}")
    print(f"Origenes frontend permitidos (CORS): {', '.join(FRONTEND_ORIGINS)}")
    # threaded=True: a diferencia de Pagv2/backend-local (uso tipicamente de
    # una sola persona a la vez), aca varias Secretarias pueden cargar al
    # mismo tiempo -- el servidor de desarrollo de Werkzeug sin threading
    # sirve una conexion a la vez y se cuelga con requests concurrentes del
    # browser (se detecto en la prueba manual: una segunda pestana/fetch
    # quedaba esperando indefinidamente). db.py ya protege la unica seccion
    # de escritura sensible (guardar_formulario) con un Lock propio.
    #
    # host "::", no "127.0.0.1" ni "0.0.0.0": bindear solo a 127.0.0.1 (IPv4)
    # causaba que el login fallara en el navegador real cuando el sistema
    # resuelve "localhost" a ::1 (IPv6) primero -- el frontend (python -m
    # http.server, que escucha en "::") cargaba bien, pero el fetch al
    # backend se caia con "No se pudo conectar" (se detecto asi: puerto 8890
    # escuchando en "::", puerto 5190 solo en "127.0.0.1", via
    # Get-NetTCPConnection). "0.0.0.0" tampoco alcanza: en Windows es
    # IPv4-only, "::1" seguia sin responder incluso con ese bind (probado).
    # "::" es dual-stack en Windows por default (IPV6_V6ONLY=0) y cubre
    # IPv4 + IPv6 en todas las interfaces con un solo bind -- mismo
    # comportamiento que ya tenia el server estatico del frontend.
    host = os.environ.get("HOST", "::")
    app.run(host=host, port=puerto, debug=False, threaded=True)

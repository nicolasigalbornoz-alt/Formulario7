"""
Backend de Formulario7: Flask + SQLite (db/formulario7.db), sin build step,
mismo espiritu que Pagv2/backend-local/app.py. Login real (auth.py),
cuota validada server-side en dos niveles -- categoria y Secretaria
(validations.py) -- con bloqueo duro si se supera el techo.

Uso:
    python backend/app.py
Por defecto escucha en http://localhost:5190

Variables de entorno:
    PORT              puerto (default 5190)
    SECRET_KEY        clave para firmar la cookie de sesion (OBLIGATORIA fuera de desarrollo)
    FRONTEND_ORIGIN   origen exacto permitido por CORS (default http://localhost:8890)
    FORMULARIO7_DB_PATH  ubicacion de la base SQLite (default db/formulario7.db)
"""
import logging
import os
import sys

from flask import Flask, jsonify, request, session

import auth
import db
import validations

ANIO_FISCAL = int(os.environ.get("ANIO_FISCAL", 2027))
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:8890")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("formulario7")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    app.secret_key = "dev-secret-cambiar-en-produccion"
    log.warning("SECRET_KEY no seteada -- usando una clave de desarrollo. No usar asi en produccion.")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


@app.before_request
def _preflight():
    if request.method == "OPTIONS":
        return "", 204


@app.after_request
def _cors(response):
    # Origen fijo (no "*"): con Allow-Credentials=true el browser rechaza
    # un origen comodin, y aca la cookie de sesion es necesaria en cada
    # request autenticado.
    response.headers["Access-Control-Allow-Origin"] = FRONTEND_ORIGIN
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return response


def _usuario_publico(usuario):
    return {
        "id": usuario["id"],
        "username": usuario["username"],
        "rol": usuario["rol"],
        "secretaria_id": usuario["secretaria_id"],
        "secretaria_nombre": usuario["secretaria_nombre"],
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
    except db.DbError as exc:
        log.error("Error de base en login: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500

    if (usuario is None or not usuario["activo"]
            or not auth.verificar_password(usuario["password_hash"], password)):
        return jsonify({"ok": False, "error": "Usuario o contraseña incorrectos."}), 401

    session.clear()
    session["usuario_id"] = usuario["id"]
    return jsonify({"ok": True, "usuario": _usuario_publico(usuario)}), 200


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
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


@app.route("/api/catalogo", methods=["GET"])
@auth.login_required
def catalogo(usuario):
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"ok": True, "bienes": []}), 200
    con_precio = request.args.get("con_precio") in ("1", "true", "True")
    with db.conexion() as conn:
        bienes = db.buscar_catalogo(conn, q, ANIO_FISCAL, con_precio=con_precio)
    return jsonify({"ok": True, "bienes": bienes}), 200


@app.route("/api/mis-categorias", methods=["GET"])
@auth.login_required
def mis_categorias(usuario):
    if usuario["rol"] == "admin":
        secretaria_id = request.args.get("secretaria_id", type=int)
        if not secretaria_id:
            return jsonify({"ok": False, "error": "secretaria_id es requerido para el admin."}), 400
    else:
        secretaria_id = usuario["secretaria_id"]
    fuente = request.args.get("fuente", 110, type=int)

    with db.conexion() as conn:
        categorias = db.listar_categorias_de_secretaria(conn, secretaria_id, fuente, ANIO_FISCAL)
        cuota_total = db.obtener_secretaria_cuota_total(conn, secretaria_id, fuente, ANIO_FISCAL)
        fuentes = db.listar_fuentes(conn)

    return jsonify({
        "ok": True,
        "categorias": categorias,
        "cuota_total": cuota_total,
        "fuentes": fuentes,
        "anio_fiscal": ANIO_FISCAL,
    }), 200


# ================= Formularios =================

@app.route("/api/formularios", methods=["POST"])
@auth.login_required
def crear_formulario(usuario):
    if usuario["rol"] != "area":
        return jsonify({"ok": False, "error": "Solo un usuario de area puede cargar un Formulario 7."}), 403

    body = request.get_json(silent=True) or {}
    categoria = (body.get("categoria") or "").strip()
    fuente = body.get("fuente")
    items_body = body.get("items") or []

    if not categoria:
        return jsonify({"ok": False, "error": "Falta la categoria."}), 400
    try:
        fuente = int(fuente)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Fuente de financiamiento invalida."}), 400

    secretaria_id = usuario["secretaria_id"]

    try:
        with db.conexion() as conn:
            fuente_row = db.obtener_fuente(conn, fuente)
            if fuente_row is None or not fuente_row["activa"]:
                return jsonify({"ok": False, "error": f"La fuente {fuente} todavia no esta habilitada."}), 400

            existente = db.obtener_submission_por_combinacion(conn, secretaria_id, categoria, fuente, ANIO_FISCAL)
            excluir_id = existente["id"] if existente else None

            items = validations.resolver_y_validar_items(conn, items_body, ANIO_FISCAL)
            nuevo_total = round(sum(i["subtotal"] for i in items), 2)

            aviso_categoria = validations.validar_techos(
                conn, secretaria_id=secretaria_id, categoria=categoria, fuente=fuente,
                anio_fiscal=ANIO_FISCAL, nuevo_total=nuevo_total, excluir_submission_id=excluir_id,
            )

            submission_id = db.guardar_formulario(
                conn, secretaria_id=secretaria_id, categoria=categoria, fuente=fuente,
                anio_fiscal=ANIO_FISCAL, subjurisdiccion=body.get("subjurisdiccion"),
                programa=body.get("programa"), submitted_by=usuario["id"], items=items,
                submission_id_existente=excluir_id,
            )
    except validations.ValidacionError as exc:
        return jsonify({"ok": False, **exc.to_dict()}), 400
    except validations.TechoExcedidoError as exc:
        return jsonify({"ok": False, **exc.to_dict()}), 409
    except db.DbError as exc:
        log.error("Error de base creando formulario: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
    except Exception:
        log.exception("Error inesperado creando formulario")
        return jsonify({"ok": False, "error": "Error inesperado. Revisar la consola del servidor."}), 500

    log.info("Formulario guardado: secretaria=%s categoria=%s fuente=%s total=%s (id=%s)%s",
              secretaria_id, categoria, fuente, nuevo_total, submission_id,
              " [supera techo sugerido de categoria]" if aviso_categoria else "")
    return jsonify({
        "ok": True, "id": submission_id, "total": nuevo_total, "aviso_categoria": aviso_categoria,
    }), 201


@app.route("/api/formularios", methods=["GET"])
@auth.login_required
def listar_formularios_endpoint(usuario):
    if usuario["rol"] == "admin":
        secretaria_id = request.args.get("secretaria_id", type=int)
    else:
        secretaria_id = usuario["secretaria_id"]

    with db.conexion() as conn:
        formularios = db.listar_formularios(conn, secretaria_id=secretaria_id, fuente=110, anio_fiscal=ANIO_FISCAL)
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
        writer.writerow(["Secretaria", "Categoria", "Fuente", "Techo", "Usado", "Disponible"])
        for fila in categorias:
            writer.writerow([fila["secretaria"], fila["categoria"], fuente, fila["techo"], fila["usado"], fila["disponible"]])
        respuesta = app.response_class(buf.getvalue(), mimetype="text/csv")
        respuesta.headers["Content-Disposition"] = f"attachment; filename=reporte_cuota_{fuente}_{ANIO_FISCAL}.csv"
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
    Este techo es informativo (ver validations.validar_techos), asi que
    editarlo no bloquea ni desbloquea nada por si solo -- ajusta el aviso
    que se muestra, y sirve como referencia para el admin."""
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
    print(f"Origen frontend permitido (CORS): {FRONTEND_ORIGIN}")
    # threaded=True: a diferencia de Pagv2/backend-local (uso tipicamente de
    # una sola persona a la vez), aca varias Secretarias pueden cargar al
    # mismo tiempo -- el servidor de desarrollo de Werkzeug sin threading
    # sirve una conexion a la vez y se cuelga con requests concurrentes del
    # browser (se detecto en la prueba manual: una segunda pestana/fetch
    # quedaba esperando indefinidamente). db.py ya protege la unica seccion
    # de escritura sensible (guardar_formulario) con un Lock propio.
    app.run(host="127.0.0.1", port=puerto, debug=False, threaded=True)

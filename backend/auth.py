"""
Autenticacion real de Formulario7: hash de contraseñas (werkzeug) + sesion
de Flask (cookie firmada). A diferencia del "Auth" de
Pagv2/sitio-suministros/script.js (clave unica hardcodeada en el cliente,
sin verificacion en el servidor), aca el servidor es quien valida la
contraseña y quien decide, en cada request, si la sesion sigue siendo
valida -- desactivar un usuario corta el acceso al instante, no recien en
el proximo login.
"""
from functools import wraps

from flask import jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

import db


def hashear_password(password):
    return generate_password_hash(password)


def verificar_password(password_hash, password):
    return check_password_hash(password_hash, password)


def usuario_actual(conn):
    """Relee el usuario desde la base en cada llamada (no confia en lo que
    haya en la cookie mas alla del id) -- asi un admin que desactiva a
    alguien corta su acceso aunque esa persona ya tenga una sesion abierta."""
    usuario_id = session.get("usuario_id")
    if usuario_id is None:
        return None
    usuario = db.obtener_usuario_por_id(conn, usuario_id)
    if usuario is None or not usuario["activo"]:
        return None
    return usuario


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        with db.conexion() as conn:
            usuario = usuario_actual(conn)
            if usuario is None:
                return jsonify({"ok": False, "error": "No autenticado."}), 401
            return f(usuario, *args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        with db.conexion() as conn:
            usuario = usuario_actual(conn)
            if usuario is None:
                return jsonify({"ok": False, "error": "No autenticado."}), 401
            if usuario["rol"] != "admin":
                return jsonify({"ok": False, "error": "Requiere rol administrador."}), 403
            return f(usuario, *args, **kwargs)
    return wrapper

"""
Autenticacion real de Formulario7: hash de contraseñas (werkzeug) + sesion
por token (Authorization: Bearer <token>), no cookie. A diferencia del
"Auth" de Pagv2/sitio-suministros/script.js (clave unica hardcodeada en el
cliente, sin verificacion en el servidor), aca el servidor es quien valida
la contraseña y quien decide, en cada request, si la sesion sigue siendo
valida -- desactivar un usuario corta el acceso al instante, no recien en
el proximo login.

Por que token y no cookie de sesion: frontend (GitHub Pages) y backend
(Codespace, Render, etc.) viven en dominios distintos de verdad, no
"same-site" como localhost:8890 vs localhost:5190 en desarrollo. Con
cookie (aunque sea SameSite=None + Secure) varios navegadores la bloquean
igual por proteccion de cookies de terceros (Safari por default, Chrome
con las protecciones activadas, etc.) -- el login devolvia 200 pero la
sesion se perdia en el siguiente request, sin ningun error visible. Un
token en el header Authorization no depende de politicas de cookies del
navegador en absoluto.
"""
import secrets
from functools import wraps

from flask import jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

import db


def hashear_password(password):
    return generate_password_hash(password)


def verificar_password(password_hash, password):
    return check_password_hash(password_hash, password)


def generar_token():
    return secrets.token_urlsafe(32)


def _token_de_la_request():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer "):].strip()
    return None


def usuario_actual(conn):
    """Relee el usuario desde la base en cada llamada (no confia en nada
    mas alla del id que el token resuelve) -- asi un admin que desactiva a
    alguien corta su acceso aunque esa persona ya tenga un token valido."""
    token = _token_de_la_request()
    if token is None:
        return None
    usuario = db.obtener_usuario_por_token(conn, token)
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

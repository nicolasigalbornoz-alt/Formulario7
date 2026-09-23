"""
Crea el usuario administrador inicial (o le resetea la contraseña si ya
existe). Es el unico modo de crear el primer admin: la propia pantalla de
alta de usuarios (admin-usuarios.html) necesita ya estar logueado como
admin para usarse.

Uso:
    python scripts/seed_admin.py --username admin
    (pide la contraseña de forma interactiva, sin mostrarla en pantalla)

    python scripts/seed_admin.py --username admin --password "algo-largo"
    (o via variable de entorno ADMIN_PASSWORD -- util para no dejarla en el historial de la terminal)
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
import auth  # noqa: E402
import db  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", default=None, help="Si se omite, se pide de forma interactiva.")
    parser.add_argument("--nombre-completo", default=None)
    args = parser.parse_args()

    password = args.password or os.environ.get("ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass(f"Contraseña para '{args.username}': ")
        confirmacion = getpass.getpass("Repetir contraseña: ")
        if password != confirmacion:
            print("Las contraseñas no coinciden.")
            raise SystemExit(1)
    if len(password) < 8:
        print("La contraseña debe tener al menos 8 caracteres.")
        raise SystemExit(1)

    password_hash = auth.hashear_password(password)

    with db.conexion() as conn:
        existente = db.obtener_usuario_por_username(conn, args.username)
        if existente:
            if existente["rol"] != "admin":
                print(f"'{args.username}' ya existe pero con rol '{existente['rol']}', no se pisa.")
                raise SystemExit(1)
            db.actualizar_usuario(conn, existente["id"], activo=True, password_hash=password_hash)
            print(f"Contraseña actualizada para el admin '{args.username}' (id={existente['id']}).")
        else:
            nuevo_id = db.crear_usuario(
                conn, username=args.username, password_hash=password_hash,
                rol="admin", nombre_completo=args.nombre_completo,
            )
            print(f"Admin '{args.username}' creado (id={nuevo_id}).")


if __name__ == "__main__":
    main()

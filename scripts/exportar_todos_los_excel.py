"""
Descarga a una carpeta local el Excel de TODAS las cargas de Formulario 7
ya enviadas (todas las Secretarias, ambas fuentes) -- el primer paso para
subirlas a Drive.

No sube nada a Drive por si solo: este script solo sabe hablar con el
backend de Formulario7 (via su API HTTP), no tiene credenciales de Google.
La subida a Drive la hace Claude con su propio acceso a Drive del usuario,
tomando los archivos que este script deja en `exports/` -- ver
data/README.md, seccion "Excels a Drive", para el por que de este diseno
en dos pasos (el backend en si no tiene credenciales de Google propias).

Uso:
    ADMIN_USERNAME=admin ADMIN_PASSWORD="..." python scripts/exportar_todos_los_excel.py
"""
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE_URL = os.environ.get("FORMULARIO7_API", "http://localhost:5190")
SALIDA = Path(__file__).resolve().parent.parent / "exports"


def _opener():
    cj = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def _login(opener, username, password):
    import json
    data = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/api/login", data=data, method="POST",
                                  headers={"Content-Type": "application/json"})
    with opener.open(req) as resp:
        return resp.status == 200


def _get_json(opener, path):
    import json
    with opener.open(f"{BASE_URL}{path}") as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        print("Falta ADMIN_PASSWORD (contraseña del admin).")
        raise SystemExit(1)

    opener = _opener()
    if not _login(opener, username, password):
        print("No se pudo iniciar sesion como admin.")
        raise SystemExit(1)

    SALIDA.mkdir(exist_ok=True)
    descargados = 0
    for fuente in (110, 131):
        data = _get_json(opener, f"/api/formularios?fuente={fuente}")
        for formulario in data["formularios"]:
            sub_id = formulario["id"]
            nombre = f"F7_{formulario.get('subjurisdiccion') or 'SD'}_{formulario['categoria']}_f{fuente}.xlsx"
            try:
                with opener.open(f"{BASE_URL}/api/formularios/{sub_id}/excel") as resp:
                    contenido = resp.read()
            except urllib.error.HTTPError as exc:
                print(f"  aviso: no se pudo exportar formulario id={sub_id}: {exc}")
                continue
            (SALIDA / nombre).write_bytes(contenido)
            descargados += 1
            print(f"  {nombre}")

    print(f"\n{descargados} archivo(s) en {SALIDA}")


if __name__ == "__main__":
    main()

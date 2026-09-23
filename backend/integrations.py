"""
Guardado en Google Drive de los Excel aprobados.

La subida pasa por un Apps Script de Google publicado como aplicacion web
por el dueño de la carpeta (el codigo esta en scripts/drive_apps_script.gs):
corre con la cuenta de esa persona, asi que guarda en una carpeta comun de
"Mi unidad" -- una cuenta de servicio de Google Cloud no puede, y ademas no
hace falta ningun proyecto de Google Cloud ni libreria de Google. El
backend le manda el archivo por HTTPS junto con una clave compartida.

    DRIVE_APPS_SCRIPT_URL   URL de la aplicacion web publicada (termina en /exec)
    DRIVE_TOKEN             la misma clave que TOKEN en el script
    REQUIRE_DRIVE_UPLOAD=1  sin Drive configurado no se aprueba ninguna carga

Sin configurar, los aprobados quedan solo en el servidor (cargas/) y
scripts/subir_pendientes_a_drive.py los sube cuando se configure.
"""
import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request

log = logging.getLogger("formulario7")

TIMEOUT_DRIVE = 60


class IntegracionError(Exception):
    pass


def nombre_f7(subjurisdiccion, categoria):
    """El nombre que pide el instructivo de la planilla para el archivo:
    F7_Subjurisdiccion_Categoria programatica."""
    sub = re.sub(r"[^\w.-]", "", subjurisdiccion or "") or "SD"
    return f"F7_{sub}_{re.sub(r'[^\w.-]', '', categoria)}"


def drive_configurado():
    return bool(os.environ.get("DRIVE_APPS_SCRIPT_URL") and os.environ.get("DRIVE_TOKEN"))


def subir_a_drive(nombre, contenido):
    """Guarda el Excel aprobado en la carpeta de Drive. Un archivo por
    Categoria: el script manda a la papelera de Drive el anterior con el
    mismo nombre (se puede recuperar de ahi durante 30 dias).

    Devuelve {"id", "webViewLink"}, o None si Drive no esta configurado (y
    no se exige). Si esta configurado y falla levanta IntegracionError: la
    carga NO se aprueba (aprobado == guardado en Drive)."""
    if not drive_configurado():
        if os.environ.get("REQUIRE_DRIVE_UPLOAD", "0") == "1":
            raise IntegracionError("Drive no está configurado (falta DRIVE_APPS_SCRIPT_URL o DRIVE_TOKEN).")
        log.warning("Drive no configurado: el Excel aprobado '%s' queda solo en el servidor.", nombre)
        return None

    cuerpo = json.dumps({
        "token": os.environ["DRIVE_TOKEN"],
        "nombre": nombre,
        "contenido": base64.b64encode(contenido).decode("ascii"),
    }).encode("utf-8")
    pedido = urllib.request.Request(
        os.environ["DRIVE_APPS_SCRIPT_URL"], data=cuerpo, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        # Apps Script contesta con una redireccion a la respuesta: urllib la
        # sigue solo (como GET, que es lo que espera Google).
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_DRIVE) as respuesta:
            texto = respuesta.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise IntegracionError(f"No se pudo guardar el Excel en Drive: {exc}") from exc
    try:
        datos = json.loads(texto)
    except ValueError:
        raise IntegracionError(
            "Drive contestó algo que no es la respuesta del script (¿está publicado como aplicación web con "
            "acceso para cualquier usuario?)."
        ) from None
    if not datos.get("ok"):
        raise IntegracionError(f"Drive no guardó el Excel: {datos.get('error', 'sin detalle')}")
    return {"id": datos["id"], "webViewLink": datos.get("url")}

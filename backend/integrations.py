"""
Integraciones externas de una carga de Excel: Google Drive (donde se guarda
el Excel aprobado) y mail (aviso de cada aprobacion y de cada rechazo).
Las dos son opcionales en desarrollo: sin configurar no hacen nada (y lo
dicen en el log), para poder probar la carga sin credenciales.

Drive -- cuenta de servicio de Google Cloud con la API de Drive habilitada:
    GOOGLE_DRIVE_FOLDER_ID          id de la carpeta destino (lo que sigue a /folders/ en su URL)
    GOOGLE_DRIVE_CREDENTIALS_FILE   ruta al JSON de la cuenta de servicio, o bien
    GOOGLE_DRIVE_CREDENTIALS_JSON   el contenido de ese JSON (comodo como secreto del Codespace)
    GOOGLE_DRIVE_IMPERSONATE        (opcional) usuario del dominio a impersonar, si la cuenta de
                                    servicio tiene delegacion de dominio
    REQUIRE_DRIVE_UPLOAD=1          en produccion: sin Drive configurado no se aprueba ninguna carga
  Ojo: una cuenta de servicio no tiene espacio propio en "Mi unidad". La
  carpeta tiene que estar en una Unidad compartida con la cuenta de
  servicio como miembro (Administrador de contenido), o usar impersonacion.

Mail -- SMTP:
    SMTP_HOST, SMTP_PORT (587 por defecto, con STARTTLS; 465 = SSL directo),
    SMTP_USER, SMTP_PASSWORD, SMTP_FROM (por defecto SMTP_USER),
    SMTP_STARTTLS=0 para un relay interno sin TLS,
    MAIL_TO   destinatarios separados por coma (por defecto DESTINATARIOS_DEFECTO)
"""
import io
import json
import logging
import os
import re
import smtplib
import threading
from email.message import EmailMessage

from formato import ahora_argentina, pesos

log = logging.getLogger("formulario7")

DESTINATARIOS_DEFECTO = ("dir.presupuesto@moron.gob.ar", "bessega.tadeo@moron.gob.ar")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
MAX_ERRORES_EN_MAIL = 200


class IntegracionError(Exception):
    pass


def nombre_f7(subjurisdiccion, categoria):
    """El nombre que pide el instructivo de la planilla para el archivo (y
    para el asunto del mail): F7_Subjurisdiccion_Categoria programatica."""
    sub = re.sub(r"[^\w.-]", "", subjurisdiccion or "") or "SD"
    return f"F7_{sub}_{re.sub(r'[^\w.-]', '', categoria)}"


def en_segundo_plano(funcion, *args, **kwargs):
    """Corre `funcion` en un hilo aparte: el area no tiene que esperar al
    servidor de mail (hasta 30 s si anda lento) para ver el resultado de
    su carga. Si falla, queda en el log."""
    def correr():
        try:
            funcion(*args, **kwargs)
        except Exception:
            log.exception("Fallo una tarea en segundo plano (%s)", getattr(funcion, "__name__", funcion))
    threading.Thread(target=correr, daemon=True).start()


# ================= Google Drive =================

def drive_configurado():
    return bool(os.environ.get("GOOGLE_DRIVE_FOLDER_ID") and (
        os.environ.get("GOOGLE_DRIVE_CREDENTIALS_FILE") or os.environ.get("GOOGLE_DRIVE_CREDENTIALS_JSON")))


def _servicio_drive():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise IntegracionError("Faltan las librerías de Google Drive (pip install -r requirements.txt).") from exc
    if os.environ.get("GOOGLE_DRIVE_CREDENTIALS_JSON"):
        credenciales = service_account.Credentials.from_service_account_info(
            json.loads(os.environ["GOOGLE_DRIVE_CREDENTIALS_JSON"]), scopes=DRIVE_SCOPES)
    else:
        credenciales = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_DRIVE_CREDENTIALS_FILE"], scopes=DRIVE_SCOPES)
    if os.environ.get("GOOGLE_DRIVE_IMPERSONATE"):
        credenciales = credenciales.with_subject(os.environ["GOOGLE_DRIVE_IMPERSONATE"])
    return build("drive", "v3", credentials=credenciales, cache_discovery=False)


def subir_a_drive(nombre, contenido, file_id_anterior=None):
    """Guarda el Excel aprobado en la carpeta de Drive. Un archivo por
    Categoria: si ya tenia uno aprobado (file_id_anterior) se reemplaza su
    contenido -- Drive guarda la version anterior en su historial -- en vez
    de juntar copias con el mismo nombre.

    Devuelve {"id", "webViewLink"}, o None si Drive no esta configurado (y
    no se exige). Si esta configurado y falla levanta IntegracionError: la
    carga NO se aprueba (aprobado == guardado en Drive)."""
    if not drive_configurado():
        if os.environ.get("REQUIRE_DRIVE_UPLOAD", "0") == "1":
            raise IntegracionError("Drive no está configurado (faltan credenciales o carpeta de destino).")
        log.warning("Drive no configurado: el Excel aprobado '%s' queda solo en el servidor.", nombre)
        return None
    try:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaIoBaseUpload

        servicio = _servicio_drive()
        if file_id_anterior:
            try:
                return servicio.files().update(
                    fileId=file_id_anterior, body={"name": nombre},
                    media_body=MediaIoBaseUpload(io.BytesIO(contenido), mimetype=XLSX_MIME),
                    fields="id,webViewLink", supportsAllDrives=True,
                ).execute()
            except HttpError as exc:
                if getattr(exc.resp, "status", None) != 404:
                    raise
                log.warning("El archivo anterior de Drive (%s) ya no existe: se crea uno nuevo.", file_id_anterior)
        return servicio.files().create(
            body={"name": nombre, "parents": [os.environ["GOOGLE_DRIVE_FOLDER_ID"]]},
            media_body=MediaIoBaseUpload(io.BytesIO(contenido), mimetype=XLSX_MIME),
            fields="id,webViewLink", supportsAllDrives=True,
        ).execute()
    except IntegracionError:
        raise
    except Exception as exc:
        raise IntegracionError(f"No se pudo guardar el Excel en Drive: {exc}") from exc


# ================= Mail =================

def mail_configurado():
    return bool(os.environ.get("SMTP_HOST"))


def destinatarios():
    crudo = os.environ.get("MAIL_TO")
    if not crudo:
        return list(DESTINATARIOS_DEFECTO)
    return [d.strip() for d in crudo.split(",") if d.strip()]


def enviar_mail(asunto, cuerpo, adjuntos=()):
    """adjuntos: [(nombre, bytes de un .xlsx)]. Levanta si no se pudo enviar."""
    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "formulario7@moron.gob.ar"
    mensaje["To"] = ", ".join(destinatarios())
    mensaje.set_content(cuerpo)
    for nombre, contenido in adjuntos:
        tipo, subtipo = XLSX_MIME.split("/")
        mensaje.add_attachment(contenido, maintype=tipo, subtype=subtipo, filename=nombre)

    host = os.environ["SMTP_HOST"]
    puerto = int(os.environ.get("SMTP_PORT", "587"))
    ssl_directo = puerto == 465 or os.environ.get("SMTP_SSL") == "1"
    clase = smtplib.SMTP_SSL if ssl_directo else smtplib.SMTP
    with clase(host, puerto, timeout=30) as servidor:
        if not ssl_directo and os.environ.get("SMTP_STARTTLS", "1") != "0":
            servidor.starttls()
        if os.environ.get("SMTP_USER"):
            servidor.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        servidor.send_message(mensaje)


def _encabezado(*, secretaria, categoria, subjurisdiccion, nombre_archivo, usuario):
    return (
        f"Secretaría: {secretaria}\n"
        f"Categoría programática: {categoria}\n"
        f"Subjurisdicción: {subjurisdiccion or '(sin definir)'}\n"
        f"Archivo subido: {nombre_archivo}\n"
        f"Subido por: {usuario}\n"
        f"Fecha: {ahora_argentina()} (hora de Argentina)\n"
    )


def mail_aprobado(*, secretaria, categoria, subjurisdiccion, nombre_archivo, usuario, programa, totales,
                  drive_link):
    """totales: [{"fuente", "total", "techo_categoria"}]. Devuelve (asunto, cuerpo)."""
    lineas = [f"  Fuente {t['fuente']}: {pesos(t['total'])} (techo de la categoría: {pesos(t['techo_categoria'])})"
              for t in totales]
    total = sum(t["total"] for t in totales)
    cuerpo = (
        "Formulario 7 aprobado: el Excel pasó todas las validaciones y quedó cargado.\n\n"
        + _encabezado(secretaria=secretaria, categoria=categoria, subjurisdiccion=subjurisdiccion,
                      nombre_archivo=nombre_archivo, usuario=usuario)
        + (f"Programa o Actividades centrales: {programa}\n" if programa else "")
        + "\nTotales validados:\n" + "\n".join(lineas) + f"\n  Total: {pesos(total)}\n\n"
        + (f"Guardado en Drive: {drive_link}\n" if drive_link
           else "Drive no está configurado: el Excel quedó guardado solo en el servidor.\n")
        + "Va adjunto el Excel aprobado.\n"
    )
    return f"{nombre_f7(subjurisdiccion, categoria)} - aprobado - {secretaria}", cuerpo


def mail_rechazado(*, secretaria, categoria, subjurisdiccion, nombre_archivo, usuario, errores, con_adjunto):
    """Devuelve (asunto, cuerpo)."""
    lineas = []
    for error in errores[:MAX_ERRORES_EN_MAIL]:
        donde = ""
        if error.get("celda"):
            donde = f"{error['hoja']}, celda {error['celda']}"
            if error.get("campo"):
                donde += f" ({error['campo']})"
            donde += ": "
        elif error.get("hoja"):
            donde = f"{error['hoja']}: "
        lineas.append(f"  - {donde}{error['mensaje']}")
    if len(errores) > MAX_ERRORES_EN_MAIL:
        lineas.append(f"  ... y {len(errores) - MAX_ERRORES_EN_MAIL} error(es) más.")
    cuerpo = (
        "Formulario 7 RECHAZADO: el Excel no se cargó.\n\n"
        + _encabezado(secretaria=secretaria, categoria=categoria, subjurisdiccion=subjurisdiccion,
                      nombre_archivo=nombre_archivo, usuario=usuario)
        + f"\nErrores encontrados ({len(errores)}):\n" + "\n".join(lineas) + "\n\n"
        + ("Va adjunta una copia del Excel con cada error pintado en rojo y explicado en un comentario de su celda.\n"
           if con_adjunto else "")
        + "El área ve este mismo detalle en la página: tiene que corregir el archivo y volver a subirlo.\n"
    )
    asunto = f"{nombre_f7(subjurisdiccion, categoria)} - RECHAZADO ({len(errores)} error(es)) - {secretaria}"
    return asunto, cuerpo

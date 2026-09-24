"""
Conexion a db/formulario7.db (SQLite) y todas las consultas del backend.

Mismo patron que Pagv2/backend-local/db_sqlite.py: conexion() como context
manager (PRAGMA foreign_keys, commit/rollback automatico), un _lock de
threading como segunda red de seguridad para escrituras concurrentes, y
DbError para distinguir errores de configuracion/datos de errores de
programacion.

Se puede pisar la ubicacion de la base con la variable de entorno
FORMULARIO7_DB_PATH (usado por los tests).
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH_DEFECTO = RAIZ / "db" / "formulario7.db"
SCHEMA_PATH = RAIZ / "db" / "schema.sql"

_lock = threading.Lock()


class DbError(Exception):
    pass


def _db_path():
    return Path(os.environ.get("FORMULARIO7_DB_PATH", DB_PATH_DEFECTO))


def asegurar_archivo():
    """Crea el archivo de la base (vacio) y su carpeta si todavia no existen
    -- para que el primer arranque en un host sin acceso a shell (Render,
    etc.) no dependa de correr sqlite3 a mano. conexion() sigue exigiendo
    que el archivo ya exista; este es el unico lugar que lo crea."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        sqlite3.connect(path).close()


@contextmanager
def conexion():
    path = _db_path()
    if not path.exists():
        raise DbError(
            f"No existe {path}. Correr primero: sqlite3 \"{path}\" < db/schema.sql "
            "(ver db/README.md)."
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def asegurar_esquema(conn):
    """Vuelve a correr db/schema.sql sobre una base ya existente: como todo
    ahi es IF NOT EXISTS / OR IGNORE, solo crea lo que falte (por ejemplo
    las tablas `sesion` o `f7_carga_excel` en una base creada antes de que
    existieran) sin tocar ningun dato. Lo llama app.py al arrancar."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


# ================= Fuentes de financiamiento =================

def habilitar_fuentes(conn, fuentes):
    """Deja activas solo estas fuentes y oculta el resto (activa=0): una
    fuente oculta no aparece en ninguna pagina ni se acepta en el Excel,
    pero sus techos y cargas siguen en la base por si se vuelve a habilitar.
    La llama app.py al arrancar, con FUENTES_HABILITADAS."""
    marcadores = ",".join("?" * len(fuentes))
    conn.execute(
        f"UPDATE fuente_financiamiento SET activa = CASE WHEN id IN ({marcadores}) THEN 1 ELSE 0 END",
        tuple(fuentes),
    )


def listar_fuentes(conn):
    filas = conn.execute("SELECT * FROM fuente_financiamiento ORDER BY id").fetchall()
    return [dict(f) for f in filas]


# ================= Secretarias =================

def listar_secretarias(conn):
    filas = conn.execute("SELECT id, nombre, jur, subjurisdiccion FROM secretaria ORDER BY nombre").fetchall()
    return [dict(f) for f in filas]


def resolver_secretaria(conn, nombre, jur=None):
    """Devuelve el id de la Secretaria, creandola si todavia no existe.
    Usado por scripts/build_cuota_data.py -- Libro2.xlsx es la fuente de
    verdad de que Secretarias existen."""
    fila = conn.execute("SELECT id FROM secretaria WHERE nombre = ?", (nombre,)).fetchone()
    if fila:
        if jur is not None:
            conn.execute("UPDATE secretaria SET jur = ? WHERE id = ?", (jur, fila["id"]))
        return fila["id"]
    cur = conn.execute("INSERT INTO secretaria (nombre, jur) VALUES (?, ?)", (nombre, jur))
    return cur.lastrowid


def actualizar_subjurisdiccion_secretaria(conn, secretaria_id, subjurisdiccion):
    """Solo el admin la carga (PATCH /api/admin/secretarias/<id>) -- es un
    codigo RAFAM fijo por Secretaria, el area nunca lo escribe a mano."""
    conn.execute("UPDATE secretaria SET subjurisdiccion = ? WHERE id = ?", (subjurisdiccion, secretaria_id))


# ================= Usuarios =================

def crear_usuario(conn, *, username, password_hash, rol, secretaria_id=None, nombre_completo=None):
    if rol not in ("area", "admin"):
        raise DbError(f"Rol invalido: {rol!r}")
    if rol == "area" and secretaria_id is None:
        raise DbError("Un usuario de area necesita secretaria_id.")
    if rol == "admin":
        secretaria_id = None
    try:
        cur = conn.execute(
            """
            INSERT INTO usuario (username, password_hash, rol, secretaria_id, nombre_completo)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, password_hash, rol, secretaria_id, nombre_completo),
        )
    except sqlite3.IntegrityError as exc:
        raise DbError(f"Ya existe un usuario '{username}'.") from exc
    return cur.lastrowid


def obtener_usuario_por_username(conn, username):
    fila = conn.execute(
        """
        SELECT u.*, s.nombre AS secretaria_nombre, s.subjurisdiccion AS secretaria_subjurisdiccion,
               s.jur AS secretaria_jur
        FROM usuario u LEFT JOIN secretaria s ON s.id = u.secretaria_id
        WHERE u.username = ?
        """,
        (username,),
    ).fetchone()
    return dict(fila) if fila else None


def obtener_usuario_por_id(conn, usuario_id):
    fila = conn.execute(
        """
        SELECT u.*, s.nombre AS secretaria_nombre, s.subjurisdiccion AS secretaria_subjurisdiccion,
               s.jur AS secretaria_jur
        FROM usuario u LEFT JOIN secretaria s ON s.id = u.secretaria_id
        WHERE u.id = ?
        """,
        (usuario_id,),
    ).fetchone()
    return dict(fila) if fila else None


# ================= Sesion (token, no cookie) =================

def crear_sesion(conn, usuario_id, token):
    conn.execute("INSERT INTO sesion (token, usuario_id) VALUES (?, ?)", (token, usuario_id))


def borrar_sesion(conn, token):
    conn.execute("DELETE FROM sesion WHERE token = ?", (token,))


def obtener_usuario_por_token(conn, token):
    """Relee el usuario desde la base a partir del token -- no confia en
    nada mas alla del id que el token resuelve, asi que desactivar a
    alguien corta el acceso al instante aunque tenga un token todavia
    valido (mismo criterio que tenia la sesion de cookie)."""
    fila = conn.execute(
        """
        SELECT u.*, s.nombre AS secretaria_nombre, s.subjurisdiccion AS secretaria_subjurisdiccion,
               s.jur AS secretaria_jur
        FROM sesion se
        JOIN usuario u ON u.id = se.usuario_id
        LEFT JOIN secretaria s ON s.id = u.secretaria_id
        WHERE se.token = ?
        """,
        (token,),
    ).fetchone()
    return dict(fila) if fila else None


def listar_usuarios(conn):
    filas = conn.execute(
        """
        SELECT u.id, u.username, u.rol, u.secretaria_id, s.nombre AS secretaria_nombre,
               u.nombre_completo, u.activo, u.creado_en
        FROM usuario u LEFT JOIN secretaria s ON s.id = u.secretaria_id
        ORDER BY u.rol, s.nombre, u.username
        """
    ).fetchall()
    return [dict(f) for f in filas]


def actualizar_usuario(conn, usuario_id, *, activo=None, password_hash=None):
    campos, valores = [], []
    if activo is not None:
        campos.append("activo = ?")
        valores.append(1 if activo else 0)
    if password_hash is not None:
        campos.append("password_hash = ?")
        valores.append(password_hash)
    if not campos:
        return
    valores.append(usuario_id)
    conn.execute(f"UPDATE usuario SET {', '.join(campos)} WHERE id = ?", valores)


# ================= Cuota (Libro1.xlsx) =================

def marcar_cuota_no_vigente(conn, fuente, anio_fiscal):
    """Primera fase del reimport idempotente: todo lo de este fuente/anio
    pasa a no vigente; el upsert que sigue vuelve a poner vigente=1 en lo
    que todavia aparece en el Excel. Lo que no reaparece queda marcado (no
    se borra) -- una carga ya enviada que apunta a esa fila no se rompe."""
    conn.execute(
        "UPDATE cuota_categoria SET vigente = 0 WHERE fuente = ? AND anio_fiscal = ?",
        (fuente, anio_fiscal),
    )
    conn.execute(
        "UPDATE secretaria_cuota_total SET vigente = 0 WHERE fuente = ? AND anio_fiscal = ?",
        (fuente, anio_fiscal),
    )


def upsert_secretaria_cuota_total(conn, *, secretaria_id, fuente, anio_fiscal, monto_total):
    conn.execute(
        """
        INSERT INTO secretaria_cuota_total (secretaria_id, fuente, anio_fiscal, monto_total, vigente, actualizado_en)
        VALUES (:secretaria_id, :fuente, :anio_fiscal, :monto_total, 1, datetime('now'))
        ON CONFLICT(secretaria_id, fuente, anio_fiscal) DO UPDATE SET
            monto_total = excluded.monto_total,
            vigente = 1,
            actualizado_en = datetime('now')
        """,
        {"secretaria_id": secretaria_id, "fuente": fuente, "anio_fiscal": anio_fiscal, "monto_total": monto_total},
    )


def upsert_cuota_categoria(conn, *, secretaria_id, categoria, fuente, anio_fiscal,
                            suma_compromiso, porcentaje, techo, pauta=0,
                            eventos_culturales=0, obras_construccion=0):
    conn.execute(
        """
        INSERT INTO cuota_categoria (
            secretaria_id, categoria, fuente, anio_fiscal, suma_compromiso,
            porcentaje, techo, pauta, eventos_culturales, obras_construccion,
            vigente, actualizado_en
        ) VALUES (
            :secretaria_id, :categoria, :fuente, :anio_fiscal, :suma_compromiso,
            :porcentaje, :techo, :pauta, :eventos_culturales, :obras_construccion,
            1, datetime('now')
        )
        ON CONFLICT(secretaria_id, categoria, fuente, anio_fiscal) DO UPDATE SET
            suma_compromiso = excluded.suma_compromiso,
            porcentaje = excluded.porcentaje,
            techo = excluded.techo,
            pauta = excluded.pauta,
            eventos_culturales = excluded.eventos_culturales,
            obras_construccion = excluded.obras_construccion,
            vigente = 1,
            actualizado_en = datetime('now')
        """,
        {
            "secretaria_id": secretaria_id, "categoria": categoria, "fuente": fuente,
            "anio_fiscal": anio_fiscal, "suma_compromiso": suma_compromiso,
            "porcentaje": porcentaje, "techo": techo, "pauta": pauta,
            "eventos_culturales": eventos_culturales, "obras_construccion": obras_construccion,
        },
    )


def importar_techos(conn, contenido_excel, anio_fiscal, fuentes=(110,)):
    """Importa la hoja "Techos" de un Excel con la misma estructura de
    Libro2.xlsx (Jur. | Secretaria | Categoria | Techo fuente 110 | Obras de
    construccion | Estimacion fondo de 131) directo desde bytes, para hosts
    sin shell (Render) donde no se puede correr scripts/build_cuota_data.py
    a mano. `fuentes` filtra que fuentes se importan (default solo 110);
    misma logica idempotente que el script: marca no vigente lo de esa
    fuente/anio y el upsert que sigue vuelve a poner vigente=1 en lo que
    aparece en el Excel."""
    import io as _io
    import openpyxl as _openpyxl

    COL_JUR, COL_SECRETARIA, COL_CATEGORIA = 1, 2, 3
    COL_TECHO_POR_FUENTE = {110: 4, 131: 6}
    FILA_INICIO = 2

    wb = _openpyxl.load_workbook(_io.BytesIO(contenido_excel), data_only=True)
    if "Techos" not in wb.sheetnames:
        raise DbError('El Excel no tiene una hoja "Techos".')
    ws = wb["Techos"]

    filas = []
    r = FILA_INICIO
    while True:
        jur = ws.cell(row=r, column=COL_JUR).value
        if jur is None or str(jur).strip() == "":
            break
        filas.append({
            "jur": str(jur).strip(),
            "secretaria": str(ws.cell(row=r, column=COL_SECRETARIA).value or "").strip(),
            "categoria": str(ws.cell(row=r, column=COL_CATEGORIA).value or "").strip(),
            "techo_por_fuente": {
                fuente: round(float(ws.cell(row=r, column=col).value or 0), 2)
                for fuente, col in COL_TECHO_POR_FUENTE.items()
            },
        })
        r += 1

    for fuente in fuentes:
        marcar_cuota_no_vigente(conn, fuente, anio_fiscal)

    secretarias_vistas = set()
    total_por_secretaria = {fuente: {} for fuente in fuentes}
    categorias_por_fuente = {fuente: 0 for fuente in fuentes}

    for f in filas:
        secretaria_id = resolver_secretaria(conn, f["secretaria"], jur=f["jur"])
        secretarias_vistas.add(f["secretaria"])
        for fuente in fuentes:
            techo = f["techo_por_fuente"].get(fuente, 0)
            if techo <= 0:
                continue
            total_por_secretaria[fuente][secretaria_id] = total_por_secretaria[fuente].get(secretaria_id, 0) + techo
            categorias_por_fuente[fuente] += 1
            upsert_cuota_categoria(
                conn, secretaria_id=secretaria_id, categoria=f["categoria"], fuente=fuente,
                anio_fiscal=anio_fiscal, suma_compromiso=None, porcentaje=None, techo=techo,
            )

    for fuente in fuentes:
        for secretaria_id, monto_total in total_por_secretaria[fuente].items():
            upsert_secretaria_cuota_total(
                conn, secretaria_id=secretaria_id, fuente=fuente, anio_fiscal=anio_fiscal,
                monto_total=round(monto_total, 2),
            )

    return {
        "secretarias": len(secretarias_vistas),
        "categorias_por_fuente": categorias_por_fuente,
        "totales_por_fuente": {f: len(total_por_secretaria[f]) for f in fuentes},
    }


def actualizar_techo_categoria(conn, cuota_categoria_id, techo):
    """Edicion manual del techo por el admin -- por fuera del reimport
    desde Libro1.xlsx, para correcciones puntuales sin tener que tocar el
    Excel fuente. actualizado_en registra cuando fue el ultimo cambio; el
    detalle de quien lo hizo queda en el log del servidor (ver app.py)."""
    conn.execute(
        "UPDATE cuota_categoria SET techo = ?, actualizado_en = datetime('now') WHERE id = ?",
        (techo, cuota_categoria_id),
    )


def actualizar_monto_total_secretaria(conn, secretaria_cuota_total_id, monto_total):
    conn.execute(
        "UPDATE secretaria_cuota_total SET monto_total = ?, actualizado_en = datetime('now') WHERE id = ?",
        (monto_total, secretaria_cuota_total_id),
    )


def obtener_cuota_categoria_por_id(conn, cuota_categoria_id):
    fila = conn.execute("SELECT * FROM cuota_categoria WHERE id = ?", (cuota_categoria_id,)).fetchone()
    return dict(fila) if fila else None


def obtener_secretaria_cuota_total_por_id(conn, secretaria_cuota_total_id):
    fila = conn.execute(
        "SELECT * FROM secretaria_cuota_total WHERE id = ?", (secretaria_cuota_total_id,)
    ).fetchone()
    return dict(fila) if fila else None


def obtener_cuota_categoria(conn, secretaria_id, categoria, fuente, anio_fiscal):
    fila = conn.execute(
        """
        SELECT * FROM cuota_categoria
        WHERE secretaria_id = ? AND categoria = ? AND fuente = ? AND anio_fiscal = ?
        """,
        (secretaria_id, categoria, fuente, anio_fiscal),
    ).fetchone()
    # Se busca sin filtrar por vigente a proposito: una carga ya enviada
    # tiene que poder seguir editandose con su ultimo techo conocido aunque
    # Presupuesto haya sacado esa categoria del picker en una reimportacion.
    return dict(fila) if fila else None


def obtener_secretaria_cuota_total(conn, secretaria_id, fuente, anio_fiscal):
    fila = conn.execute(
        """
        SELECT * FROM secretaria_cuota_total
        WHERE secretaria_id = ? AND fuente = ? AND anio_fiscal = ?
        """,
        (secretaria_id, fuente, anio_fiscal),
    ).fetchone()
    return dict(fila) if fila else None


def listar_categorias_de_secretaria(conn, secretaria_id, anio_fiscal):
    """Categorias vigentes de una Secretaria, una fila por Categoria+Fuente
    (solo fuentes habilitadas), con su techo y lo ya cargado (via la carga
    'enviada' de esa combinacion, si existe) -- lo que alimenta el selector
    de categoria y la tabla "Mis cargas" del area."""
    filas = conn.execute(
        """
        SELECT cc.categoria, cc.fuente, cc.techo,
               s.id AS submission_id, s.submitted_at,
               COALESCE((SELECT SUM(i.subtotal) FROM f7_item i WHERE i.submission_id = s.id), 0) AS cargado
        FROM cuota_categoria cc
        JOIN fuente_financiamiento ff ON ff.id = cc.fuente AND ff.activa = 1
        LEFT JOIN f7_submission s
               ON s.secretaria_id = cc.secretaria_id AND s.categoria = cc.categoria
              AND s.fuente = cc.fuente AND s.anio_fiscal = cc.anio_fiscal AND s.estado = 'enviado'
        WHERE cc.secretaria_id = ? AND cc.anio_fiscal = ? AND cc.vigente = 1
        ORDER BY cc.categoria, cc.fuente
        """,
        (secretaria_id, anio_fiscal),
    ).fetchall()
    return [dict(f) for f in filas]


def listar_cuotas_de_categoria(conn, secretaria_id, categoria, anio_fiscal):
    """El techo vigente de UNA Categoria de la Secretaria en cada fuente
    habilitada (una fila por fuente) -- define con que fuentes se puede
    cargar un Excel de esa Categoria. Lista vacia = la Categoria no es de
    esta Secretaria (o no tiene techo en ninguna fuente)."""
    filas = conn.execute(
        """
        SELECT cc.* FROM cuota_categoria cc
        JOIN fuente_financiamiento ff ON ff.id = cc.fuente AND ff.activa = 1
        WHERE cc.secretaria_id = ? AND cc.categoria = ? AND cc.anio_fiscal = ? AND cc.vigente = 1
        ORDER BY cc.fuente
        """,
        (secretaria_id, categoria, anio_fiscal),
    ).fetchall()
    return [dict(f) for f in filas]


# ================= Catalogo de bienes =================

def marcar_catalogo_no_vigente(conn, anio_fiscal):
    conn.execute("UPDATE catalogo_bienes SET vigente = 0 WHERE anio_fiscal = ?", (anio_fiscal,))


def upsert_catalogo_bien(conn, *, codigo, denominacion, unidad_texto, unidad_num, precio, anio_fiscal):
    conn.execute(
        """
        INSERT INTO catalogo_bienes (codigo, denominacion, unidad_texto, unidad_num, precio, anio_fiscal, vigente, actualizado_en)
        VALUES (:codigo, :denominacion, :unidad_texto, :unidad_num, :precio, :anio_fiscal, 1, datetime('now'))
        ON CONFLICT(codigo, anio_fiscal) DO UPDATE SET
            denominacion = excluded.denominacion,
            unidad_texto = excluded.unidad_texto,
            unidad_num = excluded.unidad_num,
            precio = excluded.precio,
            vigente = 1,
            actualizado_en = datetime('now')
        """,
        {
            "codigo": codigo, "denominacion": denominacion, "unidad_texto": unidad_texto,
            "unidad_num": unidad_num, "precio": precio, "anio_fiscal": anio_fiscal,
        },
    )


def importar_catalogo(conn, contenido_excel, anio_fiscal):
    """Importa la hoja "Listado de bienes" de un Excel con la misma
    estructura de "formulario 7 2027.xlsx" directo desde bytes, para hosts
    sin shell (Render) donde no se puede correr
    scripts/build_catalogo_data.py a mano. Misma logica que ese script:
    bienes sin precio se importan igual (solo cargables como "especial"),
    codigo duplicado se queda con la primera fila (como el VLOOKUP del
    Excel original), e idempotente por (codigo, anio_fiscal)."""
    import io as _io
    import openpyxl as _openpyxl

    COL_DENOMINACION, COL_CODIGO, COL_UNIDAD_TEXTO, COL_UNIDAD_NUM, COL_PRECIO = 1, 2, 3, 4, 7
    FILA_INICIO = 2

    wb = _openpyxl.load_workbook(_io.BytesIO(contenido_excel), data_only=True)
    if "Listado de bienes" not in wb.sheetnames:
        raise DbError('El Excel no tiene una hoja "Listado de bienes".')
    ws = wb["Listado de bienes"]

    bienes = []
    r = FILA_INICIO
    while True:
        denominacion = ws.cell(row=r, column=COL_DENOMINACION).value
        if denominacion is None or str(denominacion).strip() == "":
            break
        codigo = ws.cell(row=r, column=COL_CODIGO).value
        precio = ws.cell(row=r, column=COL_PRECIO).value
        bienes.append({
            "denominacion": str(denominacion).strip(),
            "codigo": str(codigo).strip() if codigo is not None else None,
            "unidad_texto": str(ws.cell(row=r, column=COL_UNIDAD_TEXTO).value or "").strip(),
            "unidad_num": ws.cell(row=r, column=COL_UNIDAD_NUM).value,
            "precio": round(float(precio), 2) if isinstance(precio, (int, float)) else None,
        })
        r += 1

    marcar_catalogo_no_vigente(conn, anio_fiscal)

    vistos = set()
    duplicados = []
    sin_precio = 0
    for b in bienes:
        if not b["codigo"]:
            continue
        if b["codigo"] in vistos:
            duplicados.append(b["codigo"])
            continue
        vistos.add(b["codigo"])
        if b["precio"] is None:
            sin_precio += 1
        upsert_catalogo_bien(
            conn, codigo=b["codigo"], denominacion=b["denominacion"], unidad_texto=b["unidad_texto"],
            unidad_num=b["unidad_num"], precio=b["precio"], anio_fiscal=anio_fiscal,
        )

    return {"total": len(vistos), "sin_precio": sin_precio, "duplicados": sorted(set(duplicados))}


def listar_catalogo(conn, anio_fiscal):
    """Todo el "Listado de bienes" vigente del anio (~1500 filas), en el
    orden del Excel original -- excel_import lo indexa en memoria una vez
    por Excel subido en vez de hacer una consulta por fila."""
    filas = conn.execute(
        """
        SELECT id, codigo, denominacion, unidad_texto, precio FROM catalogo_bienes
        WHERE anio_fiscal = ? AND vigente = 1 ORDER BY id
        """,
        (anio_fiscal,),
    ).fetchall()
    return [dict(f) for f in filas]


# ================= Formulario 7 =================

def calcular_usado_secretaria(conn, secretaria_id, fuente, anio_fiscal, excluir_categoria=None):
    """Lo ya cargado (cargas 'enviadas') por la Secretaria en una fuente.
    excluir_categoria deja afuera esa Categoria: es la que se esta por
    reemplazar con un Excel nuevo, no hay que sumarla dos veces."""
    sql = """
        SELECT COALESCE(SUM(i.subtotal), 0) AS usado
        FROM f7_submission s JOIN f7_item i ON i.submission_id = s.id
        WHERE s.secretaria_id = ? AND s.fuente = ? AND s.anio_fiscal = ? AND s.estado = 'enviado'
    """
    params = [secretaria_id, fuente, anio_fiscal]
    if excluir_categoria is not None:
        sql += " AND s.categoria != ?"
        params.append(excluir_categoria)
    fila = conn.execute(sql, params).fetchone()
    return fila["usado"]


def reemplazar_formularios_de_categoria(conn, *, secretaria_id, categoria, anio_fiscal, items_por_fuente,
                                          fuentes_activas, subjurisdiccion, programa, submitted_by):
    """Un Excel aprobado es el Formulario 7 COMPLETO de la Categoria (el
    archivo es uno por Categoria, con la fuente fila por fila): reemplaza
    la carga de cada fuente que trae y anula la de las fuentes habilitadas
    que ya no trae -- si no, un segundo Excel que saco todos los bienes de
    una fuente dejaria viva la carga de esa fuente del Excel anterior. Las
    cargas de una fuente oculta no se tocan: el Excel no la puede traer.
    Devuelve {fuente: id}."""
    existentes = {
        fila["fuente"]: dict(fila)
        for fila in conn.execute(
            "SELECT * FROM f7_submission WHERE secretaria_id = ? AND categoria = ? AND anio_fiscal = ?",
            (secretaria_id, categoria, anio_fiscal),
        ).fetchall()
    }
    ids = {}
    for fuente, items in sorted(items_por_fuente.items()):
        existente = existentes.get(fuente)
        ids[fuente] = guardar_formulario(
            conn, secretaria_id=secretaria_id, categoria=categoria, fuente=fuente, anio_fiscal=anio_fiscal,
            subjurisdiccion=subjurisdiccion, programa=programa, submitted_by=submitted_by, items=items,
            submission_id_existente=existente["id"] if existente else None,
        )
    for fuente, existente in existentes.items():
        if fuente in fuentes_activas and fuente not in items_por_fuente and existente["estado"] == "enviado":
            anular_formulario(conn, existente["id"])
    return ids


def guardar_formulario(conn, *, secretaria_id, categoria, fuente, anio_fiscal,
                        subjurisdiccion, programa, submitted_by, items, submission_id_existente=None):
    """Crea la carga o, si ya existia esa combinacion (Secretaria+Categoria+
    Fuente+anio -- UNIQUE de f7_submission), reemplaza sus items. No hay
    caso de 'crear duplicado': el UNIQUE de la tabla lo impide."""
    with _lock:
        if submission_id_existente is not None:
            submission_id = submission_id_existente
            # submitted_at se renueva: es "cuando se envio esta version",
            # lo que muestran "Mis cargas" y el panel de seguimiento.
            conn.execute(
                """
                UPDATE f7_submission
                SET subjurisdiccion = ?, programa = ?, submitted_by = ?, estado = 'enviado',
                    submitted_at = datetime('now')
                WHERE id = ?
                """,
                (subjurisdiccion, programa, submitted_by, submission_id),
            )
            conn.execute("DELETE FROM f7_item WHERE submission_id = ?", (submission_id,))
        else:
            cur = conn.execute(
                """
                INSERT INTO f7_submission (secretaria_id, categoria, fuente, anio_fiscal, subjurisdiccion, programa, submitted_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (secretaria_id, categoria, fuente, anio_fiscal, subjurisdiccion, programa, submitted_by),
            )
            submission_id = cur.lastrowid

        for orden, item in enumerate(items):
            conn.execute(
                """
                INSERT INTO f7_item (
                    submission_id, tipo, catalogo_id, codigo, denominacion,
                    unidad_medida, cantidad, precio_unitario, subtotal, orden
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id, item["tipo"], item.get("catalogo_id"), item.get("codigo"),
                    item["denominacion"], item["unidad_medida"], item["cantidad"],
                    item["precio_unitario"], item["subtotal"], orden,
                ),
            )
        return submission_id


def listar_formularios(conn, *, secretaria_id=None, fuente=None, anio_fiscal=None):
    sql = """
        SELECT f.*, s.nombre AS secretaria_nombre, u.username AS submitted_by_username,
               COALESCE((SELECT SUM(i.subtotal) FROM f7_item i WHERE i.submission_id = f.id), 0) AS total
        FROM f7_submission f
        JOIN secretaria s ON s.id = f.secretaria_id
        JOIN usuario u ON u.id = f.submitted_by
        WHERE 1=1
    """
    params = []
    if secretaria_id is not None:
        sql += " AND f.secretaria_id = ?"
        params.append(secretaria_id)
    if fuente is not None:
        sql += " AND f.fuente = ?"
        params.append(fuente)
    if anio_fiscal is not None:
        sql += " AND f.anio_fiscal = ?"
        params.append(anio_fiscal)
    sql += " ORDER BY f.submitted_at DESC"
    filas = conn.execute(sql, params).fetchall()
    return [dict(f) for f in filas]


def obtener_formulario(conn, submission_id):
    fila = conn.execute(
        """
        SELECT f.*, s.nombre AS secretaria_nombre, u.username AS submitted_by_username
        FROM f7_submission f
        JOIN secretaria s ON s.id = f.secretaria_id
        JOIN usuario u ON u.id = f.submitted_by
        WHERE f.id = ?
        """,
        (submission_id,),
    ).fetchone()
    if not fila:
        return None
    formulario = dict(fila)
    items = conn.execute(
        "SELECT * FROM f7_item WHERE submission_id = ? ORDER BY orden", (submission_id,)
    ).fetchall()
    formulario["items"] = [dict(i) for i in items]
    return formulario


def anular_formulario(conn, submission_id):
    conn.execute("UPDATE f7_submission SET estado = 'anulado' WHERE id = ?", (submission_id,))


def reporte_cuota(conn, anio_fiscal, fuente, secretaria_id=None):
    sql = """
        SELECT cc.id AS cuota_categoria_id, sc.id AS secretaria_id, sc.nombre AS secretaria,
               cc.categoria, cc.techo,
               COALESCE(u.usado, 0) AS cargado, cc.techo - COALESCE(u.usado, 0) AS disponible
        FROM cuota_categoria cc
        JOIN secretaria sc ON sc.id = cc.secretaria_id
        LEFT JOIN (
            SELECT s.secretaria_id, s.categoria, s.fuente, s.anio_fiscal, SUM(i.subtotal) AS usado
            FROM f7_submission s JOIN f7_item i ON i.submission_id = s.id
            WHERE s.estado = 'enviado'
            GROUP BY s.secretaria_id, s.categoria, s.fuente, s.anio_fiscal
        ) u ON u.secretaria_id = cc.secretaria_id AND u.categoria = cc.categoria
           AND u.fuente = cc.fuente AND u.anio_fiscal = cc.anio_fiscal
        WHERE cc.anio_fiscal = ? AND cc.fuente = ? AND cc.vigente = 1
    """
    params = [anio_fiscal, fuente]
    if secretaria_id is not None:
        sql += " AND cc.secretaria_id = ?"
        params.append(secretaria_id)
    sql += " ORDER BY sc.nombre, cc.categoria"
    filas = conn.execute(sql, params).fetchall()
    return [dict(f) for f in filas]


def reporte_totales_secretaria(conn, anio_fiscal, fuente, secretaria_id=None):
    sql = """
        SELECT sct.id AS secretaria_cuota_total_id, sct.secretaria_id, sc.nombre AS secretaria,
               sct.fuente, sct.monto_total,
               COALESCE((
                   SELECT SUM(i.subtotal)
                   FROM f7_submission s JOIN f7_item i ON i.submission_id = s.id
                   WHERE s.secretaria_id = sct.secretaria_id AND s.fuente = sct.fuente
                     AND s.anio_fiscal = sct.anio_fiscal AND s.estado = 'enviado'
               ), 0) AS cargado
        FROM secretaria_cuota_total sct
        JOIN secretaria sc ON sc.id = sct.secretaria_id
        WHERE sct.anio_fiscal = ? AND sct.fuente = ? AND sct.vigente = 1
    """
    params = [anio_fiscal, fuente]
    if secretaria_id is not None:
        sql += " AND sct.secretaria_id = ?"
        params.append(secretaria_id)
    sql += " ORDER BY sc.nombre"
    filas = conn.execute(sql, params).fetchall()
    return [dict(f) for f in filas]


# ================= Cargas de Excel (registro de cada intento) =================

def registrar_carga_excel(conn, *, secretaria_id, categoria, anio_fiscal, nombre_archivo, sha256, estado,
                          total, errores, subido_por, drive_file_id=None, drive_link=None, archivo_local=None):
    cur = conn.execute(
        """
        INSERT INTO f7_carga_excel (
            secretaria_id, categoria, anio_fiscal, nombre_archivo, sha256, estado, total,
            errores, drive_file_id, drive_link, archivo_local, subido_por
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            secretaria_id, categoria, anio_fiscal, nombre_archivo, sha256, estado, total,
            json.dumps(errores, ensure_ascii=False) if errores else None,
            drive_file_id, drive_link, archivo_local, subido_por,
        ),
    )
    return cur.lastrowid


def aprobadas_sin_drive(conn, anio_fiscal):
    """El ultimo Excel aprobado de cada Categoria que todavia no esta en
    Drive (se aprobo con Drive sin configurar) -- lo que sube
    scripts/subir_pendientes_a_drive.py. Los aprobados anteriores de la
    misma Categoria ya quedaron reemplazados, no hace falta subirlos."""
    filas = conn.execute(
        """
        SELECT c.*, s.jur AS secretaria_jur, s.nombre AS secretaria_nombre
        FROM f7_carga_excel c JOIN secretaria s ON s.id = c.secretaria_id
        WHERE c.id IN (
            SELECT MAX(id) FROM f7_carga_excel
            WHERE anio_fiscal = ? AND estado = 'aprobado'
            GROUP BY secretaria_id, categoria
        ) AND c.drive_file_id IS NULL
        ORDER BY c.id
        """,
        (anio_fiscal,),
    ).fetchall()
    return [dict(f) for f in filas]


def marcar_en_drive(conn, carga_id, drive_file_id, drive_link):
    conn.execute(
        "UPDATE f7_carga_excel SET drive_file_id = ?, drive_link = ? WHERE id = ?",
        (drive_file_id, drive_link, carga_id),
    )


def _carga_publica(fila):
    carga = dict(fila)
    errores = json.loads(carga.pop("errores") or "[]")
    carga["cantidad_errores"] = len(errores)
    return carga


def ultimas_cargas_por_categoria(conn, secretaria_id, anio_fiscal):
    """El ultimo Excel subido (aprobado o rechazado) de cada Categoria de la
    Secretaria, para la columna "Ultimo Excel" de "Mis cargas"."""
    filas = conn.execute(
        """
        SELECT id, categoria, nombre_archivo, estado, total, errores, subido_en
        FROM f7_carga_excel
        WHERE id IN (
            SELECT MAX(id) FROM f7_carga_excel
            WHERE secretaria_id = ? AND anio_fiscal = ?
            GROUP BY categoria
        )
        """,
        (secretaria_id, anio_fiscal),
    ).fetchall()
    return {fila["categoria"]: _carga_publica(fila) for fila in filas}


def listar_cargas_excel(conn, anio_fiscal, limite=100):
    """Ultimos Excel subidos por todas las areas (panel del admin)."""
    filas = conn.execute(
        """
        SELECT c.id, c.categoria, c.nombre_archivo, c.estado, c.total, c.errores,
               c.drive_link, c.subido_en,
               s.nombre AS secretaria, u.username AS subido_por_username
        FROM f7_carga_excel c
        JOIN secretaria s ON s.id = c.secretaria_id
        JOIN usuario u ON u.id = c.subido_por
        WHERE c.anio_fiscal = ?
        ORDER BY c.id DESC
        LIMIT ?
        """,
        (anio_fiscal, limite),
    ).fetchall()
    return [_carga_publica(f) for f in filas]


# ================= Seguimiento de avance =================

def seguimiento_categorias(conn, fuente, anio_fiscal):
    """Una fila por Secretaria+Categoria vigente, con la carga 'enviada'
    correspondiente si ya existe (o NULL si esa combinacion todavia no se
    cargo). Base del panel de seguimiento -- la agregacion por Secretaria
    (total/cargadas/pendientes) se arma en app.py a partir de esto, son
    pocas filas (~65) y no vale la pena una segunda consulta agregada."""
    filas = conn.execute(
        """
        SELECT sc.id AS secretaria_id, sc.nombre AS secretaria,
               cc.categoria, cc.techo,
               s.id AS submission_id, s.submitted_at, us.username AS submitted_by_username
        FROM cuota_categoria cc
        JOIN secretaria sc ON sc.id = cc.secretaria_id
        LEFT JOIN f7_submission s
               ON s.secretaria_id = cc.secretaria_id AND s.categoria = cc.categoria
              AND s.fuente = cc.fuente AND s.anio_fiscal = cc.anio_fiscal AND s.estado = 'enviado'
        LEFT JOIN usuario us ON us.id = s.submitted_by
        WHERE cc.fuente = ? AND cc.anio_fiscal = ? AND cc.vigente = 1
        ORDER BY sc.nombre, cc.categoria
        """,
        (fuente, anio_fiscal),
    ).fetchall()
    return [dict(f) for f in filas]

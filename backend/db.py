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
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH_DEFECTO = RAIZ / "db" / "formulario7.db"

_lock = threading.Lock()


class DbError(Exception):
    pass


def _db_path():
    return Path(os.environ.get("FORMULARIO7_DB_PATH", DB_PATH_DEFECTO))


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


# ================= Fuentes de financiamiento =================

def obtener_fuente(conn, fuente_id):
    fila = conn.execute("SELECT * FROM fuente_financiamiento WHERE id = ?", (fuente_id,)).fetchone()
    return dict(fila) if fila else None


def listar_fuentes(conn):
    filas = conn.execute("SELECT * FROM fuente_financiamiento ORDER BY id").fetchall()
    return [dict(f) for f in filas]


# ================= Secretarias =================

def listar_secretarias(conn):
    filas = conn.execute("SELECT id, nombre, jur FROM secretaria ORDER BY nombre").fetchall()
    return [dict(f) for f in filas]


def resolver_secretaria(conn, nombre, jur=None):
    """Devuelve el id de la Secretaria, creandola si todavia no existe.
    Usado por scripts/build_cuota_data.py -- Libro1.xlsx es la fuente de
    verdad de que Secretarias existen."""
    fila = conn.execute("SELECT id FROM secretaria WHERE nombre = ?", (nombre,)).fetchone()
    if fila:
        if jur is not None:
            conn.execute("UPDATE secretaria SET jur = ? WHERE id = ?", (jur, fila["id"]))
        return fila["id"]
    cur = conn.execute("INSERT INTO secretaria (nombre, jur) VALUES (?, ?)", (nombre, jur))
    return cur.lastrowid


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
        SELECT u.*, s.nombre AS secretaria_nombre
        FROM usuario u LEFT JOIN secretaria s ON s.id = u.secretaria_id
        WHERE u.username = ?
        """,
        (username,),
    ).fetchone()
    return dict(fila) if fila else None


def obtener_usuario_por_id(conn, usuario_id):
    fila = conn.execute(
        """
        SELECT u.*, s.nombre AS secretaria_nombre
        FROM usuario u LEFT JOIN secretaria s ON s.id = u.secretaria_id
        WHERE u.id = ?
        """,
        (usuario_id,),
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


def listar_categorias_de_secretaria(conn, secretaria_id, fuente, anio_fiscal):
    """Categorias vigentes de una Secretaria con su techo y lo ya usado (via
    la carga 'enviada' de esa combinacion, si existe) -- lo que alimenta el
    picker de categoria del area."""
    filas = conn.execute(
        """
        SELECT cc.categoria, cc.techo,
               s.id AS submission_id, s.submitted_at,
               COALESCE((SELECT SUM(i.subtotal) FROM f7_item i WHERE i.submission_id = s.id), 0) AS usado
        FROM cuota_categoria cc
        LEFT JOIN f7_submission s
               ON s.secretaria_id = cc.secretaria_id AND s.categoria = cc.categoria
              AND s.fuente = cc.fuente AND s.anio_fiscal = cc.anio_fiscal AND s.estado = 'enviado'
        WHERE cc.secretaria_id = ? AND cc.fuente = ? AND cc.anio_fiscal = ? AND cc.vigente = 1
        ORDER BY cc.categoria
        """,
        (secretaria_id, fuente, anio_fiscal),
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


def obtener_catalogo_por_id(conn, catalogo_id):
    fila = conn.execute("SELECT * FROM catalogo_bienes WHERE id = ?", (catalogo_id,)).fetchone()
    return dict(fila) if fila else None


def buscar_catalogo(conn, q, anio_fiscal, con_precio=False, limite=25):
    sql = "SELECT * FROM catalogo_bienes WHERE anio_fiscal = ? AND vigente = 1 AND denominacion LIKE ?"
    params = [anio_fiscal, f"%{q}%"]
    if con_precio:
        sql += " AND precio IS NOT NULL"
    sql += " ORDER BY denominacion LIMIT ?"
    params.append(limite)
    filas = conn.execute(sql, params).fetchall()
    return [dict(f) for f in filas]


# ================= Formulario 7 =================

def obtener_submission_por_combinacion(conn, secretaria_id, categoria, fuente, anio_fiscal):
    fila = conn.execute(
        """
        SELECT * FROM f7_submission
        WHERE secretaria_id = ? AND categoria = ? AND fuente = ? AND anio_fiscal = ?
        """,
        (secretaria_id, categoria, fuente, anio_fiscal),
    ).fetchone()
    return dict(fila) if fila else None


def calcular_usado_secretaria(conn, secretaria_id, fuente, anio_fiscal, excluir_submission_id=None):
    sql = """
        SELECT COALESCE(SUM(i.subtotal), 0) AS usado
        FROM f7_submission s JOIN f7_item i ON i.submission_id = s.id
        WHERE s.secretaria_id = ? AND s.fuente = ? AND s.anio_fiscal = ? AND s.estado = 'enviado'
    """
    params = [secretaria_id, fuente, anio_fiscal]
    if excluir_submission_id is not None:
        sql += " AND s.id != ?"
        params.append(excluir_submission_id)
    fila = conn.execute(sql, params).fetchone()
    return fila["usado"]


def guardar_formulario(conn, *, secretaria_id, categoria, fuente, anio_fiscal,
                        subjurisdiccion, programa, submitted_by, items, submission_id_existente=None):
    """Crea la carga o, si ya existia esa combinacion (Secretaria+Categoria+
    Fuente+anio -- UNIQUE de f7_submission), reemplaza sus items. No hay
    caso de 'crear duplicado': el UNIQUE de la tabla lo impide."""
    with _lock:
        if submission_id_existente is not None:
            submission_id = submission_id_existente
            conn.execute(
                """
                UPDATE f7_submission
                SET subjurisdiccion = ?, programa = ?, submitted_by = ?, estado = 'enviado'
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
               COALESCE(u.usado, 0) AS usado, cc.techo - COALESCE(u.usado, 0) AS disponible
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
        SELECT sct.id AS secretaria_cuota_total_id, sct.secretaria_id, sc.nombre AS secretaria, sct.monto_total,
               COALESCE((
                   SELECT SUM(i.subtotal)
                   FROM f7_submission s JOIN f7_item i ON i.submission_id = s.id
                   WHERE s.secretaria_id = sct.secretaria_id AND s.fuente = sct.fuente
                     AND s.anio_fiscal = sct.anio_fiscal AND s.estado = 'enviado'
               ), 0) AS usado
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

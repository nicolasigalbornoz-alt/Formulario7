-- Esquema de Formulario7 (SQLite). Ver db/README.md para como (re)generar
-- la base a partir de este archivo y de los scripts de importacion.
--
-- Todo es "IF NOT EXISTS" / "OR IGNORE" a proposito: el backend vuelve a
-- correr este mismo archivo al arrancar (db.asegurar_esquema) para crear lo
-- que le falte a una base hecha con una version anterior -- solo agrega
-- tablas/indices nuevos, nunca toca ni borra datos existentes.

PRAGMA foreign_keys = ON;

-- ================= Catalogos / dimensiones =================

CREATE TABLE IF NOT EXISTS secretaria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL UNIQUE,   -- "Salud", "Jefatura de Gabinete", etc. (viene de Libro2.xlsx)
    jur             TEXT,                    -- codigo "Jur." de 2 digitos (ej. "04") -- referencia, no se usa para validar
    subjurisdiccion TEXT,                    -- codigo RAFAM de 10 digitos (ej. "1110111000") -- fijo por Secretaria,
                                              -- lo carga el admin; se usa para nombrar el Excel aprobado (F7_Subjurisdiccion_Categoria)
    creado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fuente_financiamiento (
    id      INTEGER PRIMARY KEY,            -- 110, 131 (valores explicitos, no autoincrement)
    nombre  TEXT NOT NULL,
    activa  INTEGER NOT NULL DEFAULT 1       -- 1 = se acepta en el Excel; 131 arranca en 0
);

CREATE TABLE IF NOT EXISTS usuario (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    rol             TEXT NOT NULL CHECK (rol IN ('area','admin')),
    secretaria_id   INTEGER REFERENCES secretaria(id),
    nombre_completo TEXT,
    activo          INTEGER NOT NULL DEFAULT 1,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en  TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ( (rol = 'admin' AND secretaria_id IS NULL) OR (rol = 'area' AND secretaria_id IS NOT NULL) )
);
CREATE INDEX IF NOT EXISTS idx_usuario_secretaria ON usuario(secretaria_id);

CREATE TRIGGER IF NOT EXISTS trg_usuario_actualizado_en
AFTER UPDATE ON usuario FOR EACH ROW
BEGIN UPDATE usuario SET actualizado_en = datetime('now') WHERE id = NEW.id; END;

-- Sesion por token (Authorization: Bearer <token>), no cookie -- frontend
-- (GitHub Pages) y backend (Codespace/Render/etc.) viven en dominios
-- distintos de verdad, y varios navegadores (Safari, Chrome con
-- proteccion de cookies de terceros, etc.) bloquean la cookie de sesion
-- entre sitios aunque el resto del flujo este bien. Un token en el header
-- Authorization no depende de politicas de cookies del navegador.
CREATE TABLE IF NOT EXISTS sesion (
    token       TEXT PRIMARY KEY,
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id),
    creado_en   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sesion_usuario ON sesion(usuario_id);

-- ================= Cuota / techos (Libro2.xlsx, hoja "Techos") =================

-- Techo total por Secretaria y fuente (suma de sus categorias)
CREATE TABLE IF NOT EXISTS secretaria_cuota_total (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    secretaria_id   INTEGER NOT NULL REFERENCES secretaria(id),
    fuente          INTEGER NOT NULL DEFAULT 110 REFERENCES fuente_financiamiento(id),
    anio_fiscal     INTEGER NOT NULL,
    monto_total     NUMERIC(16,2) NOT NULL,
    vigente         INTEGER NOT NULL DEFAULT 1,   -- 0 = no aparecio en la ultima importacion de ese anio (no se borra)
    actualizado_en  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (secretaria_id, fuente, anio_fiscal)
);

-- Techo por Categoria programatica dentro de cada Secretaria, por fuente
CREATE TABLE IF NOT EXISTS cuota_categoria (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    secretaria_id       INTEGER NOT NULL REFERENCES secretaria(id),
    categoria           TEXT NOT NULL,              -- "Categoria programatica", ej. "01.41.00"
    fuente              INTEGER NOT NULL DEFAULT 110 REFERENCES fuente_financiamiento(id),
    anio_fiscal         INTEGER NOT NULL,
    suma_compromiso     NUMERIC(16,2),               -- referencia/auditoria, no se usa para validar
    porcentaje          REAL,                        -- referencia/auditoria, no se usa para validar
    techo               NUMERIC(16,2) NOT NULL,       -- el techo que valida el servidor (bloqueante)
    pauta               NUMERIC(16,2) DEFAULT 0,      -- fuera de alcance V1
    eventos_culturales  NUMERIC(16,2) DEFAULT 0,      -- fuera de alcance V1
    obras_construccion  NUMERIC(16,2) DEFAULT 0,      -- fuera de alcance V1
    vigente             INTEGER NOT NULL DEFAULT 1,
    actualizado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (secretaria_id, categoria, fuente, anio_fiscal)
);
CREATE INDEX IF NOT EXISTS idx_cuota_categoria_secretaria ON cuota_categoria(secretaria_id, fuente, anio_fiscal);

-- ================= Catalogo de bienes ("Listado de bienes") =================

CREATE TABLE IF NOT EXISTS catalogo_bienes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT NOT NULL,              -- col B, ej. "2.1.1.00435"
    denominacion    TEXT NOT NULL,               -- col A
    unidad_texto    TEXT NOT NULL,               -- col C, ej. "KILOGRAMO" (tal cual viene, ver db/README.md)
    unidad_num      INTEGER,                     -- col D -- referencia
    precio          NUMERIC(14,2),                -- col G "Precios 2026"; NULL = sin precio -> va en "F7 especial"
    anio_fiscal     INTEGER NOT NULL,
    vigente         INTEGER NOT NULL DEFAULT 1,
    actualizado_en  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (codigo, anio_fiscal)
);
CREATE INDEX IF NOT EXISTS idx_catalogo_denominacion ON catalogo_bienes(anio_fiscal, denominacion);

-- ================= Formulario 7 =================

-- Una carga aprobada por Secretaria+Categoria+Fuente+anio. Un Excel
-- aprobado de una Categoria genera/reemplaza una fila por cada fuente que
-- trae (ver db.reemplazar_formularios_de_categoria).
CREATE TABLE IF NOT EXISTS f7_submission (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    secretaria_id    INTEGER NOT NULL REFERENCES secretaria(id),
    categoria        TEXT NOT NULL,
    fuente           INTEGER NOT NULL DEFAULT 110 REFERENCES fuente_financiamiento(id),
    anio_fiscal      INTEGER NOT NULL,
    subjurisdiccion  TEXT,                -- codigo de 10 digitos -- texto libre/referencia, NO se valida
    programa         TEXT,                -- "Programa o Actividades centrales" (celda A7 del Excel) -- referencia
    estado           TEXT NOT NULL DEFAULT 'enviado' CHECK (estado IN ('enviado','anulado')),
    submitted_by     INTEGER NOT NULL REFERENCES usuario(id),
    submitted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (secretaria_id, categoria, fuente, anio_fiscal)
);
CREATE INDEX IF NOT EXISTS idx_f7_submission_secretaria ON f7_submission(secretaria_id, fuente, anio_fiscal);

CREATE TRIGGER IF NOT EXISTS trg_f7_submission_actualizado_en
AFTER UPDATE ON f7_submission FOR EACH ROW
BEGIN UPDATE f7_submission SET actualizado_en = datetime('now') WHERE id = NEW.id; END;

CREATE TABLE IF NOT EXISTS f7_item (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id    INTEGER NOT NULL REFERENCES f7_submission(id) ON DELETE CASCADE,
    tipo             TEXT NOT NULL CHECK (tipo IN ('comun','especial')),
    catalogo_id      INTEGER REFERENCES catalogo_bienes(id),   -- NULL si no corresponde a ningun item del catalogo
    codigo           TEXT,                  -- foto al momento de guardar, no se vuelve a resolver despues
    denominacion     TEXT NOT NULL,
    unidad_medida    TEXT NOT NULL,
    cantidad         INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario  NUMERIC(14,2) NOT NULL CHECK (precio_unitario >= 0),
    subtotal         NUMERIC(16,2) NOT NULL,  -- cantidad * precio_unitario, calculado server-side al insertar
    orden            INTEGER,
    creado_en        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_f7_item_submission ON f7_item(submission_id);

-- Un registro por cada Excel que sube un area, aprobado o rechazado: que
-- archivo, quien, cuando y, si se rechazo, por que. Los items de un Excel
-- aprobado quedan en f7_submission/f7_item.
CREATE TABLE IF NOT EXISTS f7_carga_excel (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    secretaria_id    INTEGER NOT NULL REFERENCES secretaria(id),
    categoria        TEXT NOT NULL,
    anio_fiscal      INTEGER NOT NULL,
    nombre_archivo   TEXT NOT NULL,              -- tal cual lo subio el area
    sha256           TEXT NOT NULL,
    estado           TEXT NOT NULL CHECK (estado IN ('aprobado','rechazado')),
    total            NUMERIC(16,2),              -- suma de las filas que se pudieron calcular, todas las fuentes
    errores          TEXT,                        -- JSON con la lista de errores (solo si se rechazo)
    drive_file_id    TEXT,                        -- NULL = todavia no esta en Drive (scripts/subir_pendientes_a_drive.py)
    drive_link       TEXT,
    archivo_local    TEXT,                        -- copia del aprobado en el servidor (ver FORMULARIO7_CARGAS_DIR)
    subido_por       INTEGER NOT NULL REFERENCES usuario(id),
    subido_en        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_f7_carga_excel_categoria ON f7_carga_excel(secretaria_id, categoria, anio_fiscal);

-- ================= Semilla minima =================
INSERT OR IGNORE INTO fuente_financiamiento (id, nombre, activa) VALUES
    (110, 'Fuente 110', 1),
    (131, 'Fuente 131', 0);

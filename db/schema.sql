-- Esquema de Formulario7 (SQLite). Ver db/README.md para como (re)generar
-- la base a partir de este archivo y de los scripts de importacion.

PRAGMA foreign_keys = ON;

-- ================= Catalogos / dimensiones =================

CREATE TABLE secretaria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL UNIQUE,   -- "Salud", "Jefatura de Gabinete", etc. (viene de Libro2.xlsx)
    jur             TEXT,                    -- codigo "Jur." de 2 digitos (ej. "04") -- referencia, no se usa para validar
    subjurisdiccion TEXT,                    -- codigo RAFAM de 10 digitos (ej. "1110111000") -- fijo por Secretaria,
                                              -- lo carga el admin, el area no lo puede escribir (ver backend/app.py)
    creado_en       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE fuente_financiamiento (
    id      INTEGER PRIMARY KEY,            -- 110, 131 (valores explicitos, no autoincrement)
    nombre  TEXT NOT NULL,
    activa  INTEGER NOT NULL DEFAULT 1       -- 1 = seleccionable en el form; 131 arranca en 0
);

CREATE TABLE usuario (
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
CREATE INDEX idx_usuario_secretaria ON usuario(secretaria_id);

CREATE TRIGGER trg_usuario_actualizado_en
AFTER UPDATE ON usuario FOR EACH ROW
BEGIN UPDATE usuario SET actualizado_en = datetime('now') WHERE id = NEW.id; END;

-- ================= Cuota / techos (Libro1.xlsx, hoja "Hoja2") =================

-- Techo total por Secretaria (columnas M:N del Excel)
CREATE TABLE secretaria_cuota_total (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    secretaria_id   INTEGER NOT NULL REFERENCES secretaria(id),
    fuente          INTEGER NOT NULL DEFAULT 110 REFERENCES fuente_financiamiento(id),
    anio_fiscal     INTEGER NOT NULL,
    monto_total     NUMERIC(16,2) NOT NULL,
    vigente         INTEGER NOT NULL DEFAULT 1,   -- 0 = no aparecio en la ultima importacion de ese anio (no se borra)
    actualizado_en  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (secretaria_id, fuente, anio_fiscal)
);

-- Techo por Categoria programatica dentro de cada Secretaria (columnas B,C,D,H)
CREATE TABLE cuota_categoria (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    secretaria_id       INTEGER NOT NULL REFERENCES secretaria(id),
    categoria           TEXT NOT NULL,              -- "Categoria programatica", ej. "01.41.00"
    fuente              INTEGER NOT NULL DEFAULT 110 REFERENCES fuente_financiamiento(id),
    anio_fiscal         INTEGER NOT NULL,
    suma_compromiso     NUMERIC(16,2),               -- col E -- referencia/auditoria, no se usa para validar
    porcentaje          REAL,                        -- col F -- referencia/auditoria, no se usa para validar
    techo               NUMERIC(16,2) NOT NULL,       -- col H "Libre" -- el techo que valida el servidor
    pauta               NUMERIC(16,2) DEFAULT 0,      -- col I -- fuera de alcance V1
    eventos_culturales  NUMERIC(16,2) DEFAULT 0,      -- col J -- fuera de alcance V1
    obras_construccion  NUMERIC(16,2) DEFAULT 0,      -- col K -- fuera de alcance V1
    vigente             INTEGER NOT NULL DEFAULT 1,
    actualizado_en      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (secretaria_id, categoria, fuente, anio_fiscal)
);
CREATE INDEX idx_cuota_categoria_secretaria ON cuota_categoria(secretaria_id, fuente, anio_fiscal);

-- ================= Catalogo de bienes ("Listado de bienes") =================

CREATE TABLE catalogo_bienes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT NOT NULL,              -- col B, ej. "2.1.1.00435"
    denominacion    TEXT NOT NULL,               -- col A
    unidad_texto    TEXT NOT NULL,               -- col C, ej. "KILOGRAMO" (tal cual viene, ver db/README.md)
    unidad_num      INTEGER,                     -- col D -- referencia
    precio          NUMERIC(14,2),                -- col G "Precios 2026"; NULL = sin precio -> va como "especial"
    anio_fiscal     INTEGER NOT NULL,
    vigente         INTEGER NOT NULL DEFAULT 1,
    actualizado_en  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (codigo, anio_fiscal)
);
CREATE INDEX idx_catalogo_denominacion ON catalogo_bienes(anio_fiscal, denominacion);

-- ================= Formulario 7 =================

CREATE TABLE f7_submission (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    secretaria_id    INTEGER NOT NULL REFERENCES secretaria(id),
    categoria        TEXT NOT NULL,
    fuente           INTEGER NOT NULL DEFAULT 110 REFERENCES fuente_financiamiento(id),
    anio_fiscal      INTEGER NOT NULL,
    subjurisdiccion  TEXT,                -- codigo de 10 digitos -- texto libre/referencia, NO se valida
    programa         TEXT,                -- "Programa o Actividades centrales" -- texto libre/referencia
    estado           TEXT NOT NULL DEFAULT 'enviado' CHECK (estado IN ('enviado','anulado')),
    submitted_by     INTEGER NOT NULL REFERENCES usuario(id),
    submitted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (secretaria_id, categoria, fuente, anio_fiscal)
);
CREATE INDEX idx_f7_submission_secretaria ON f7_submission(secretaria_id, fuente, anio_fiscal);

CREATE TRIGGER trg_f7_submission_actualizado_en
AFTER UPDATE ON f7_submission FOR EACH ROW
BEGIN UPDATE f7_submission SET actualizado_en = datetime('now') WHERE id = NEW.id; END;

CREATE TABLE f7_item (
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
CREATE INDEX idx_f7_item_submission ON f7_item(submission_id);

-- ================= Semilla minima =================
INSERT INTO fuente_financiamiento (id, nombre, activa) VALUES
    (110, 'Fuente 110', 1),
    (131, 'Fuente 131', 0);

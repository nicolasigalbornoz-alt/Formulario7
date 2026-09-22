"""
Importa la cuota/techo de Libro1.xlsx (hoja "Hoja2") a la base SQLite:
secretaria, cuota_categoria (columnas Jur./Secretaria/Categoria/Libre -- el
techo por Categoria programatica dentro de cada Secretaria) y
secretaria_cuota_total (el techo total por Secretaria, DERIVADO como la
suma de sus categorias -- ver nota mas abajo, "Por que no hay una tabla de
totales separada").

Libro1.xlsx no trae columna de Fuente: representa la fuente 110 unicamente
(la 131 todavia no tiene archivo propio -- se integra mas adelante, ver
README.md).

Formato esperado (4 columnas, una fila por Secretaria x Categoria):

    Jur. | Secretaria | Categoria | Libre
    00   | HCD        | 01.41.00  | 221292804.37

Por que no hay una tabla de totales separada:
El archivo trajo en un primer momento una tabla aparte (Jur -> monto total)
de la que "Libre" salia calculado (Libre = % del rubro x monto total de esa
Jurisdiccion). La version actual del archivo ya viene solo con el resultado
("Libre") y sin esa tabla ni las columnas intermedias. Como los % de cada
Secretaria suman ~1 sobre su propio total, sumar los "Libre" de todas las
categorias de una Secretaria reconstruye ese mismo monto total (verificado
contra la version anterior del archivo, que si traia ambos: coinciden salvo
redondeo). Por eso el techo total de Secretaria se guarda como un valor
propio en la base (secretaria_cuota_total), sembrado con esa suma pero
editable aparte por el admin despues (PATCH /api/admin/cuota-total/<id>) --
no se recalcula on-the-fly en cada consulta, para que una correccion manual
del admin no se pierda en la proxima reimportacion de este mismo archivo
(ver db/README.md).

Idempotente: se puede correr las veces que haga falta con el mismo --anio.
Hace upsert por clave natural (Secretaria+Categoria+Fuente+anio) en vez de
borrar y recrear, porque a diferencia de cuota-110-data.js (que no tiene
nada apuntandole por id) aca cuota_categoria.id puede estar referenciado
por una carga de Formulario 7 ya enviada. Lo que desaparece del Excel en una
reimportacion se marca vigente=0, nunca se borra.

Uso:
    python scripts/build_cuota_data.py --anio 2027
    python scripts/build_cuota_data.py --anio 2027 --archivo "data/Libro1.xlsx"
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
import db  # noqa: E402

ARCHIVO_DEFECTO = RAIZ / "data" / "Libro1.xlsx"
HOJA = "Hoja2"
FUENTE = 110

COL_JUR, COL_SECRETARIA, COL_CATEGORIA, COL_TECHO = 1, 2, 3, 4  # A, B, C, D
FILA_INICIO = 2


def num(v):
    return round(float(v), 2) if v is not None else 0.0


def leer_categorias(ws):
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
            "techo": num(ws.cell(row=r, column=COL_TECHO).value),
        })
        r += 1
    return filas


def importar(anio_fiscal, archivo, conn):
    wb = openpyxl.load_workbook(archivo, data_only=True)
    ws = wb[HOJA]

    categorias = leer_categorias(ws)

    db.marcar_cuota_no_vigente(conn, FUENTE, anio_fiscal)

    secretarias_vistas = set()
    total_por_secretaria = defaultdict(float)
    for c in categorias:
        secretaria_id = db.resolver_secretaria(conn, c["secretaria"], jur=c["jur"])
        secretarias_vistas.add(c["secretaria"])
        total_por_secretaria[secretaria_id] += c["techo"]
        db.upsert_cuota_categoria(
            conn, secretaria_id=secretaria_id, categoria=c["categoria"], fuente=FUENTE,
            anio_fiscal=anio_fiscal, suma_compromiso=None, porcentaje=None, techo=c["techo"],
        )

    for secretaria_id, monto_total in total_por_secretaria.items():
        db.upsert_secretaria_cuota_total(
            conn, secretaria_id=secretaria_id, fuente=FUENTE, anio_fiscal=anio_fiscal,
            monto_total=round(monto_total, 2),
        )

    return {
        "secretarias": len(secretarias_vistas),
        "categorias": len(categorias),
        "totales": len(total_por_secretaria),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anio", type=int, required=True, help="Anio fiscal presupuestado (ej. 2027)")
    parser.add_argument("--archivo", type=Path, default=ARCHIVO_DEFECTO)
    args = parser.parse_args()

    if not args.archivo.exists():
        print(f"No se encontro {args.archivo}. Copiar ahi el Excel de cuota (ver data/README.md).")
        raise SystemExit(1)

    with db.conexion() as conn:
        resumen = importar(args.anio, args.archivo, conn)

    print(f"Fuente {FUENTE}, anio {args.anio}: "
          f"{resumen['secretarias']} secretarias, {resumen['categorias']} categorias, "
          f"{resumen['totales']} totales de secretaria (derivados como suma de sus categorias).")


if __name__ == "__main__":
    main()

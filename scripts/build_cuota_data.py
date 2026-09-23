"""
Importa la cuota/techo de Libro2.xlsx (hoja "Techos") a la base SQLite,
para AMBAS fuentes de financiamiento (110 y 131) en una sola pasada:
secretaria, cuota_categoria (columna D = techo fuente 110 "F7 + F11",
columna F = estimación fondo 131) y secretaria_cuota_total (derivado como
la suma de las categorías de cada Secretaría, por fuente).

Reemplaza a Libro1.xlsx (que solo traía fuente 110 y no tenía la 131 en
absoluto) -- ver data/README.md. La columna E "Obras de construcción (F9)"
queda fuera de alcance, mismo criterio que las columnas Pauta/Eventos
culturales/Obras de la versión anterior del archivo -- no se lee.

Regla de negocio confirmada en las propias notas de la hoja (columna H del
Excel, filas 3 a 5):
  "Los techos por categoría son SUGERIDOS en función de la ejecución de 2026."
  "La suma de los techos por secretaría son el MONTO MÁXIMO PERMITIDO."
  "Pueden compensarse categorías de menos con categorías de más, pero la
   suma de las subjurisdicciones NO PUEDE SUPERAR la suma de los techos
   aquí expuestos."
Es decir: el techo por Categoría es una sugerencia (el backend la usa para
avisar, no para bloquear); lo que sí bloquea es la suma por Secretaría y
Fuente. Ver backend/validations.py.

Una categoría sin techo en una fuente (columna en 0) simplemente no genera
fila en cuota_categoria para esa fuente -- por ejemplo HCD no tiene ninguna
categoría financiada por 131 en los datos actuales, y no aparecerá en el
selector de categorías de un usuario de HCD cuando elija fuente 131.

Al importar, esta corrida también activa la fuente 131
(`fuente_financiamiento.activa = 1`) -- hasta ahora quedaba deshabilitada
en la interfaz por no haber de dónde sacar su techo.

Idempotente, mismo criterio que siempre: upsert por clave natural
(Secretaría+Categoría+Fuente+año), lo que desaparece del Excel en una
reimportación se marca vigente=0, nunca se borra.

Uso:
    python scripts/build_cuota_data.py --anio 2027
    python scripts/build_cuota_data.py --anio 2027 --archivo "data/Libro2.xlsx"
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
import db  # noqa: E402

ARCHIVO_DEFECTO = RAIZ / "data" / "Libro2.xlsx"
HOJA = "Techos"

COL_JUR, COL_SECRETARIA, COL_CATEGORIA = 1, 2, 3     # A, B, C
COL_TECHO_110, COL_TECHO_131 = 4, 6                   # D, F  (E = Obras de construcción, fuera de alcance)
FILA_INICIO = 2

FUENTES = (110, 131)


def num(v):
    return round(float(v), 2) if v is not None else 0.0


def leer_filas(ws):
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
            "techo_110": num(ws.cell(row=r, column=COL_TECHO_110).value),
            "techo_131": num(ws.cell(row=r, column=COL_TECHO_131).value),
        })
        r += 1
    return filas


def importar(anio_fiscal, archivo, conn):
    wb = openpyxl.load_workbook(archivo, data_only=True)
    ws = wb[HOJA]
    filas = leer_filas(ws)

    for fuente in FUENTES:
        db.marcar_cuota_no_vigente(conn, fuente, anio_fiscal)

    secretarias_vistas = set()
    total_por_secretaria = {110: defaultdict(float), 131: defaultdict(float)}
    categorias_por_fuente = {110: 0, 131: 0}

    for f in filas:
        secretaria_id = db.resolver_secretaria(conn, f["secretaria"], jur=f["jur"])
        secretarias_vistas.add(f["secretaria"])

        for fuente, techo in ((110, f["techo_110"]), (131, f["techo_131"])):
            if techo <= 0:
                continue  # sin cuota en esta fuente -- no se crea fila (ver docstring)
            total_por_secretaria[fuente][secretaria_id] += techo
            categorias_por_fuente[fuente] += 1
            db.upsert_cuota_categoria(
                conn, secretaria_id=secretaria_id, categoria=f["categoria"], fuente=fuente,
                anio_fiscal=anio_fiscal, suma_compromiso=None, porcentaje=None, techo=techo,
            )

    for fuente in FUENTES:
        for secretaria_id, monto_total in total_por_secretaria[fuente].items():
            db.upsert_secretaria_cuota_total(
                conn, secretaria_id=secretaria_id, fuente=fuente, anio_fiscal=anio_fiscal,
                monto_total=round(monto_total, 2),
            )

    conn.execute("UPDATE fuente_financiamiento SET activa = 1 WHERE id = 131")

    return {
        "secretarias": len(secretarias_vistas),
        "categorias_110": categorias_por_fuente[110],
        "categorias_131": categorias_por_fuente[131],
        "totales_110": len(total_por_secretaria[110]),
        "totales_131": len(total_por_secretaria[131]),
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

    print(f"Año {args.anio}: {resumen['secretarias']} secretarías -- "
          f"fuente 110: {resumen['categorias_110']} categorías / {resumen['totales_110']} totales de secretaría; "
          f"fuente 131: {resumen['categorias_131']} categorías / {resumen['totales_131']} totales de secretaría. "
          f"Fuente 131 activada.")


if __name__ == "__main__":
    main()

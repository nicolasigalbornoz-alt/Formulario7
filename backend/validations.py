"""
Techos presupuestarios de una carga de Formulario 7 (los de Libro2.xlsx,
importados a cuota_categoria y secretaria_cuota_total). Las filas del Excel
se validan en excel_import.py; aca solo se comparan los totales, por
fuente, contra los dos techos -- y los dos bloquean la carga:

- el techo de la Categoria (cuota_categoria.techo), y
- el techo total de la Secretaria (secretaria_cuota_total.monto_total),
  sumando lo ya cargado en sus otras Categorias.

(Libro2.xlsx describe el techo por Categoria como "sugerido"; la regla
vigente es que tambien es un maximo -- ver README.)
"""
from decimal import Decimal

import db
from formato import pesos


def _error_techo(nivel, fuente, techo, solicitado, mensaje, **extra):
    return {
        "tipo": "techo",
        "nivel": nivel,
        "fuente": fuente,
        "techo": float(techo),
        "solicitado": float(solicitado),
        "excedente": float(solicitado - techo),
        "hoja": None, "fila": None, "columna": None, "celda": None, "campo": None,
        "mensaje": mensaje,
        **extra,
    }


def validar_techos(conn, *, secretaria_id, categoria, anio_fiscal, totales_por_fuente):
    """totales_por_fuente: {fuente: Decimal} de lo que trae el Excel de la
    Categoria. Devuelve la lista de errores (vacia si no supera nada).

    El total de la Categoria se compara entero contra su techo: el Excel
    reemplaza lo que hubiera cargado antes para esa Categoria, no se suma."""
    errores = []
    for fuente, total in sorted(totales_por_fuente.items()):
        total = Decimal(total)
        cuota = db.obtener_cuota_categoria(conn, secretaria_id, categoria, fuente, anio_fiscal)
        if cuota is None:
            continue  # excel_import ya marco fila por fila que la categoria no tiene techo en esa fuente
        techo = Decimal(str(cuota["techo"]))
        if total > techo:
            errores.append(_error_techo(
                "categoria", fuente, techo, total,
                f"Fuente {fuente}: el total de la categoría {categoria} es {pesos(total)} y su techo "
                f"presupuestario es {pesos(techo)} -- se pasa por {pesos(total - techo)}.",
            ))

        cuota_total = db.obtener_secretaria_cuota_total(conn, secretaria_id, fuente, anio_fiscal)
        if cuota_total is None:
            errores.append(_error_techo(
                "secretaria", fuente, Decimal(0), total,
                f"Fuente {fuente}: la Secretaría no tiene techo presupuestario total asignado en esta fuente.",
                disponible=0.0,
            ))
            continue
        monto_total = Decimal(str(cuota_total["monto_total"]))
        usado_otras = Decimal(str(db.calcular_usado_secretaria(
            conn, secretaria_id, fuente, anio_fiscal, excluir_categoria=categoria,
        )))
        if usado_otras + total > monto_total:
            disponible = monto_total - usado_otras
            errores.append(_error_techo(
                "secretaria", fuente, monto_total, usado_otras + total,
                f"Fuente {fuente}: con esta carga la Secretaría llega a {pesos(usado_otras + total)} y su techo "
                f"total es {pesos(monto_total)} -- se pasa por {pesos(usado_otras + total - monto_total)} "
                f"(ya cargado en otras categorías: {pesos(usado_otras)}; disponible para esta: "
                f"{pesos(max(disponible, Decimal(0)))}).",
                disponible=float(disponible),
            ))
    return errores

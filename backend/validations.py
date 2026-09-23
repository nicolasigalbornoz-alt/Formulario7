"""
Reglas de validacion de una carga de Formulario 7. El servidor es la fuente
de verdad -- nunca confia en precio/codigo/unidad que mande el cliente para
un item "comun" (eso siempre se vuelve a resolver contra el catalogo), y
revalida completitud de filas aunque el frontend ya lo haya hecho.
"""
import db


class ValidacionError(Exception):
    """Error de datos de entrada (filas incompletas, item comun inexistente,
    etc.) -- se traduce a 400. Distinto de un error de techo, que es 409."""
    def __init__(self, mensaje, fila=None, campo=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.fila = fila
        self.campo = campo

    def to_dict(self):
        d = {"error": self.mensaje}
        if self.fila is not None:
            d["fila"] = self.fila
        if self.campo is not None:
            d["campo"] = self.campo
        return d


class TechoExcedidoError(Exception):
    """Se traduce a 409. `nivel` siempre es 'secretaria' -- el techo por
    categoria es sugerido, no bloqueante (ver validar_techos)."""
    def __init__(self, nivel, disponible, solicitado):
        super().__init__(f"Supera el techo de {nivel}: disponible {disponible}, solicitado {solicitado}")
        self.nivel = nivel
        self.disponible = disponible
        self.solicitado = solicitado

    def to_dict(self):
        return {
            "error": str(self),
            "nivel": self.nivel,
            "disponible": self.disponible,
            "solicitado": self.solicitado,
        }


CAMPOS_ITEM = ("catalogo_id", "cantidad")


def _vacio(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def resolver_y_validar_items(conn, items_body, anio_fiscal):
    """Recorre las filas que mando el cliente, descarta las totalmente
    vacias, y para cada una vuelve a resolver denominacion/codigo/unidad/
    precio contra catalogo_bienes (ignora cualquier otro dato que haya
    mandado el cliente para esos campos -- el catalogo es la unica fuente
    de verdad). Solo existen items "comunes": no hay carga manual de
    bienes/precios fuera del catalogo en esta version. Levanta
    ValidacionError en la primera fila invalida -- se corrige una por vez,
    igual que completar un Excel."""
    resueltos = []
    for idx, raw in enumerate(items_body):
        catalogo_id = raw.get("catalogo_id")
        cantidad = raw.get("cantidad")

        fila_vacia = _vacio(catalogo_id) and _vacio(cantidad)
        if fila_vacia:
            continue

        if _vacio(catalogo_id):
            raise ValidacionError("Falta elegir el bien de la lista.", fila=idx, campo="catalogo_id")
        if _vacio(cantidad):
            raise ValidacionError("Falta la cantidad.", fila=idx, campo="cantidad")
        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            raise ValidacionError("La cantidad debe ser un numero entero.", fila=idx, campo="cantidad")
        if cantidad <= 0:
            raise ValidacionError("La cantidad debe ser mayor a cero.", fila=idx, campo="cantidad")

        bien = db.obtener_catalogo_por_id(conn, catalogo_id)
        if bien is None:
            raise ValidacionError("El bien elegido no existe en el catalogo.", fila=idx, campo="catalogo_id")
        if bien["precio"] is None:
            raise ValidacionError(
                f"'{bien['denominacion']}' no tiene precio de catalogo asignado.",
                fila=idx, campo="catalogo_id",
            )

        resueltos.append({
            "tipo": "comun",
            "catalogo_id": catalogo_id,
            "codigo": bien["codigo"],
            "denominacion": bien["denominacion"],
            "unidad_medida": bien["unidad_texto"],
            "cantidad": cantidad,
            "precio_unitario": float(bien["precio"]),
            "subtotal": round(cantidad * float(bien["precio"]), 2),
        })

    if not resueltos:
        raise ValidacionError("El formulario no tiene ningun item cargado.")

    return resueltos


def validar_techos(conn, *, secretaria_id, categoria, fuente, anio_fiscal, nuevo_total, excluir_submission_id):
    """El techo por Categoria es SUGERIDO, no bloqueante -- son las propias
    notas de Libro2.xlsx (hoja "Techos"): "Los techos por categoria son
    SUGERIDOS... Pueden compensarse categorias de menos con categorias de
    mas". Lo unico que bloquea es la suma por Secretaria y Fuente ("LA
    SUMA... ES EL MONTO MAXIMO PERMITIDO"). Por eso esta funcion nunca
    lanza TechoExcedidoError por categoria -- devuelve un aviso informativo
    (o None) para que el llamador lo pueda mostrar igual, y solo lanza
    (bloquea) cuando se supera el techo de Secretaria.

    El total de categoria a comparar es solo el de ESTA carga porque el
    UNIQUE de f7_submission garantiza que nunca hay mas de una carga
    enviada para la misma combinacion Secretaria+Categoria+Fuente+anio."""
    cuota_cat = db.obtener_cuota_categoria(conn, secretaria_id, categoria, fuente, anio_fiscal)
    if cuota_cat is None:
        raise ValidacionError("Esa categoria no tiene cuota asignada para esta Secretaria en esta fuente.")
    techo_categoria = float(cuota_cat["techo"])
    aviso_categoria = None
    if nuevo_total > techo_categoria:
        aviso_categoria = {"techo_categoria": techo_categoria, "solicitado": nuevo_total}

    cuota_total = db.obtener_secretaria_cuota_total(conn, secretaria_id, fuente, anio_fiscal)
    if cuota_total is None:
        raise ValidacionError("Esta Secretaria no tiene cuota total asignada en esta fuente.")
    usado_otras = float(db.calcular_usado_secretaria(
        conn, secretaria_id, fuente, anio_fiscal, excluir_submission_id=excluir_submission_id
    ))
    monto_total = float(cuota_total["monto_total"])
    if usado_otras + nuevo_total > monto_total:
        raise TechoExcedidoError("secretaria", monto_total - usado_otras, nuevo_total)

    return aviso_categoria

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
    """Se traduce a 409. `nivel` es 'categoria' o 'secretaria'."""
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


CAMPOS_ITEM = ("denominacion", "unidad_medida", "cantidad", "precio_unitario")


def _vacio(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def resolver_y_validar_items(conn, items_body, anio_fiscal):
    """Recorre las filas que mando el cliente, descarta las totalmente
    vacias, valida que las que tienen algun dato tengan todos los campos
    requeridos, y para las de tipo 'comun' vuelve a resolver denominacion/
    codigo/unidad/precio contra catalogo_bienes (ignora lo que haya mandado
    el cliente en esos campos). Levanta ValidacionError en la primera fila
    invalida -- se corrige una por vez, igual que completar un Excel."""
    resueltos = []
    for idx, raw in enumerate(items_body):
        tipo = raw.get("tipo")
        catalogo_id = raw.get("catalogo_id")

        fila_vacia = tipo is None and catalogo_id is None and all(_vacio(raw.get(c)) for c in CAMPOS_ITEM)
        if fila_vacia:
            continue

        if tipo not in ("comun", "especial"):
            raise ValidacionError("Tipo de item invalido (debe ser 'comun' o 'especial').", fila=idx, campo="tipo")

        cantidad = raw.get("cantidad")
        if _vacio(cantidad):
            raise ValidacionError("Falta la cantidad.", fila=idx, campo="cantidad")
        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            raise ValidacionError("La cantidad debe ser un numero entero.", fila=idx, campo="cantidad")
        if cantidad <= 0:
            raise ValidacionError("La cantidad debe ser mayor a cero.", fila=idx, campo="cantidad")

        if tipo == "comun":
            if _vacio(catalogo_id):
                raise ValidacionError("Falta elegir el bien de la lista.", fila=idx, campo="catalogo_id")
            bien = db.obtener_catalogo_por_id(conn, catalogo_id)
            if bien is None:
                raise ValidacionError("El bien elegido no existe en el catalogo.", fila=idx, campo="catalogo_id")
            if bien["precio"] is None:
                raise ValidacionError(
                    f"'{bien['denominacion']}' no tiene precio de catalogo -- cargarlo como especial.",
                    fila=idx, campo="catalogo_id",
                )
            denominacion = bien["denominacion"]
            codigo = bien["codigo"]
            unidad_medida = bien["unidad_texto"]
            precio_unitario = float(bien["precio"])
        else:
            faltantes = [c for c in ("denominacion", "unidad_medida", "precio_unitario") if _vacio(raw.get(c))]
            if faltantes:
                raise ValidacionError(f"Faltan campos: {', '.join(faltantes)}.", fila=idx, campo=faltantes[0])
            denominacion = raw["denominacion"]
            unidad_medida = raw["unidad_medida"]
            try:
                precio_unitario = float(raw["precio_unitario"])
            except (TypeError, ValueError):
                raise ValidacionError("El precio debe ser un numero.", fila=idx, campo="precio_unitario")
            if precio_unitario < 0:
                raise ValidacionError("El precio no puede ser negativo.", fila=idx, campo="precio_unitario")
            codigo = None
            if not _vacio(catalogo_id):
                bien = db.obtener_catalogo_por_id(conn, catalogo_id)
                if bien is not None:
                    codigo = bien["codigo"]

        resueltos.append({
            "tipo": tipo,
            "catalogo_id": catalogo_id if not _vacio(catalogo_id) else None,
            "codigo": codigo,
            "denominacion": denominacion,
            "unidad_medida": unidad_medida,
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "subtotal": round(cantidad * precio_unitario, 2),
        })

    if not resueltos:
        raise ValidacionError("El formulario no tiene ningun item cargado.")

    return resueltos


def validar_techos(conn, *, secretaria_id, categoria, fuente, anio_fiscal, nuevo_total, excluir_submission_id):
    """Nivel 1 (categoria) y nivel 2 (Secretaria), en ese orden -- corta en
    el primero que falle. Ver plan: el techo de categoria solo mira el total
    de ESTA carga porque el UNIQUE de f7_submission garantiza que nunca hay
    mas de una carga enviada para la misma combinacion Secretaria+Categoria+
    Fuente+anio."""
    cuota_cat = db.obtener_cuota_categoria(conn, secretaria_id, categoria, fuente, anio_fiscal)
    if cuota_cat is None:
        raise ValidacionError("Esa categoria no tiene cuota asignada para esta Secretaria.")
    techo_categoria = float(cuota_cat["techo"])
    if nuevo_total > techo_categoria:
        raise TechoExcedidoError("categoria", techo_categoria, nuevo_total)

    cuota_total = db.obtener_secretaria_cuota_total(conn, secretaria_id, fuente, anio_fiscal)
    if cuota_total is None:
        raise ValidacionError("Esta Secretaria no tiene cuota total asignada.")
    usado_otras = float(db.calcular_usado_secretaria(
        conn, secretaria_id, fuente, anio_fiscal, excluir_submission_id=excluir_submission_id
    ))
    monto_total = float(cuota_total["monto_total"])
    if usado_otras + nuevo_total > monto_total:
        raise TechoExcedidoError("secretaria", monto_total - usado_otras, nuevo_total)

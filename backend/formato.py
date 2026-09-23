"""
Formato de montos y fechas para los mensajes que ve una persona (errores de
validacion, mails) -- en criollo: $ 1.234.567,89 y hora de Argentina.
"""
from datetime import datetime, timedelta, timezone

# Argentina no tiene horario de verano: UTC-3 fijo, sin depender de que el
# servidor tenga la base de zonas horarias instalada (en Windows no viene).
HORA_ARGENTINA = timezone(timedelta(hours=-3))


def pesos(monto):
    """2 decimales a proposito: un techo puede superarse por centavos y
    "$ 1.000 supera $ 1.000" no le serviria a nadie."""
    texto = f"{float(monto):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"$ {texto}"


def ahora_argentina():
    return datetime.now(HORA_ARGENTINA).strftime("%d/%m/%Y %H:%M")

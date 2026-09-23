"""
Sube a Drive los Excel aprobados que todavia no estan ahi -- los que se
aprobaron mientras Drive no estaba configurado y quedaron solo en el
servidor (cargas/). Sube solo el ultimo aprobado de cada Categoria: los
anteriores ya fueron reemplazados. Se puede correr las veces que haga falta.

Uso (con las mismas variables que el backend, ver backend/integrations.py):
    DRIVE_APPS_SCRIPT_URL=... DRIVE_TOKEN=... python scripts/subir_pendientes_a_drive.py --anio 2027
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))
import db  # noqa: E402
import integrations  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anio", type=int, required=True, help="Anio fiscal (ej. 2027)")
    args = parser.parse_args()

    if not integrations.drive_configurado():
        print("Drive no esta configurado: faltan DRIVE_APPS_SCRIPT_URL y/o DRIVE_TOKEN.")
        raise SystemExit(1)

    with db.conexion() as conn:
        pendientes = db.aprobadas_sin_drive(conn, args.anio)
    if not pendientes:
        print("No hay Excel aprobados pendientes de subir a Drive.")
        return

    subidos = 0
    for carga in pendientes:
        ruta = Path(carga["archivo_local"] or "")
        if not ruta.is_file():
            print(f"  aviso: no esta la copia local de la carga id={carga['id']} ({carga['archivo_local']})")
            continue
        # Igual que al aprobar: carpeta de la jurisdiccion, nombre de la categoria.
        nombre = integrations.nombre_archivo(carga["categoria"])
        carpeta = integrations.nombre_carpeta(carga["secretaria_jur"], carga["secretaria_nombre"])
        try:
            drive = integrations.subir_a_drive(nombre, ruta.read_bytes(), carpeta)
        except integrations.IntegracionError as exc:
            print(f"  error subiendo {nombre}: {exc}")
            continue
        with db.conexion() as conn:
            db.marcar_en_drive(conn, carga["id"], drive["id"], drive.get("webViewLink"))
        subidos += 1
        print(f"  {carpeta}/{nombre} -> {drive.get('webViewLink')}")

    print(f"\n{subidos} de {len(pendientes)} archivo(s) subidos a Drive.")


if __name__ == "__main__":
    main()

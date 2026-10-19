/**
 * Formulario 7 -- guarda en Google Drive los Excel que aprueba el backend.
 *
 * Se publica como aplicacion web desde la cuenta de Google duena de la
 * carpeta (pasos en el README, seccion "Drive"): corre con esa cuenta, asi
 * que puede guardar en una carpeta comun de "Mi unidad". El backend le manda
 * cada Excel aprobado con la clave TOKEN (su variable DRIVE_TOKEN).
 *
 * Dentro de la carpeta hay una subcarpeta por jurisdiccion ("04 - Salud"),
 * que se crea sola la primera vez, y en ella un archivo por categoria con
 * el nombre de la categoria ("22.01.00.xlsx"). Si ya habia uno, el anterior
 * va a la papelera de Drive -- se puede recuperar de ahi durante 30 dias.
 */
const CARPETA_ID = "13tEsPkFBoMysSdxdqQtC2s0LwuAqsGec";
const TOKEN = "CAMBIAR-POR-UNA-CLAVE-LARGA";  // la misma que DRIVE_TOKEN en el backend; no la subas al repo
const MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const VERSION = 4;  // el backend la ve en cada respuesta

function doPost(e) {
  try {
    const datos = JSON.parse(e.postData.contents);
    if (datos.token !== TOKEN) {
      return responder({ ok: false, error: "clave inválida" });
    }
    if (datos.accion === "listar") {
      return listarArchivos();
    }
    if (datos.accion === "descargar") {
      return descargarArchivo(String(datos.id || ""));
    }
    const nombre = String(datos.nombre || "");
    const subcarpeta = String(datos.carpeta || "").trim();
    if (!/^[\w.-]+\.xlsx$/.test(nombre)) {
      return responder({ ok: false, error: "nombre de archivo inválido: " + nombre });
    }
    if (!subcarpeta || subcarpeta.length > 100 || /[\/\\]/.test(subcarpeta)) {
      return responder({ ok: false, error: "carpeta inválida: " + subcarpeta });
    }

    // Una sola subida a la vez: dos areas de la misma jurisdiccion no crean
    // dos carpetas con el mismo nombre.
    const candado = LockService.getScriptLock();
    candado.waitLock(30000);
    try {
      const raiz = DriveApp.getFolderById(CARPETA_ID);
      const existentes = raiz.getFoldersByName(subcarpeta);
      const carpeta = existentes.hasNext() ? existentes.next() : raiz.createFolder(subcarpeta);

      const blob = Utilities.newBlob(Utilities.base64Decode(datos.contenido), MIME_XLSX, nombre);
      const nuevo = carpeta.createFile(blob);
      // Recien con el nuevo guardado, el anterior de la misma categoria va a la papelera.
      const anteriores = carpeta.getFilesByName(nombre);
      while (anteriores.hasNext()) {
        const archivo = anteriores.next();
        if (archivo.getId() !== nuevo.getId()) archivo.setTrashed(true);
      }
      return responder({ ok: true, id: nuevo.getId(), url: nuevo.getUrl() });
    } finally {
      candado.releaseLock();
    }
  } catch (err) {
    return responder({ ok: false, error: String(err) });
  }
}

// Lista todos los Excel aprobados (una subcarpeta por jurisdiccion, un
// archivo por categoria) -- SIN su contenido, a proposito: el backend la
// usa al arrancar para reconstruir que cargo cada area (eso NO tiene ningun
// otro respaldo, a diferencia del catalogo/techos, y se pierde entero en
// cada reset de Render), y los Excel reales pueden pesar varios cientos de
// KB cada uno -- mandar el contenido en base64 de TODOS juntos en una sola
// respuesta puede superar el limite de tamaño de una respuesta de Apps
// Script a medida que se suman mas Secretarias y categorias, cortando la
// restauracion entera sin aviso. Por eso el contenido se trae aparte, un
// archivo a la vez, con descargarArchivo().
function listarArchivos() {
  const raiz = DriveApp.getFolderById(CARPETA_ID);
  const archivos = [];
  const carpetas = raiz.getFolders();
  while (carpetas.hasNext()) {
    const carpeta = carpetas.next();
    const nombreCarpeta = carpeta.getName();
    const files = carpeta.getFilesByType(MIME_XLSX);
    while (files.hasNext()) {
      const archivo = files.next();
      archivos.push({
        carpeta: nombreCarpeta,
        nombre: archivo.getName(),
        id: archivo.getId(),
        url: archivo.getUrl(),
      });
    }
  }
  return responder({ ok: true, archivos: archivos });
}

// Contenido en base64 de un solo archivo, por id -- la contraparte liviana
// de listarArchivos(). Un archivo a la vez: si uno falla o pesa demasiado,
// no se pierden los demas.
function descargarArchivo(id) {
  if (!id) {
    return responder({ ok: false, error: "falta el id del archivo" });
  }
  try {
    const archivo = DriveApp.getFileById(id);
    return responder({ ok: true, contenido: Utilities.base64Encode(archivo.getBlob().getBytes()) });
  } catch (err) {
    return responder({ ok: false, error: String(err) });
  }
}

function responder(datos) {
  datos.version = VERSION;
  return ContentService.createTextOutput(JSON.stringify(datos)).setMimeType(ContentService.MimeType.JSON);
}

/**
 * Formulario 7 -- guarda en Google Drive los Excel que aprueba el backend.
 *
 * Se publica como aplicacion web desde la cuenta de Google duena de la
 * carpeta (pasos en el README, seccion "Drive"): corre con esa cuenta, asi
 * que puede guardar en una carpeta comun de "Mi unidad". El backend le manda
 * cada Excel aprobado con la clave TOKEN (su variable DRIVE_TOKEN).
 *
 * Un archivo por categoria: si ya hay uno con el mismo nombre
 * (F7_Subjurisdiccion_Categoria.xlsx), el anterior va a la papelera de
 * Drive -- se puede recuperar de ahi durante 30 dias.
 */
const CARPETA_ID = "13tEsPkFBoMysSdxdqQtC2s0LwuAqsGec";
const TOKEN = "CAMBIAR-POR-UNA-CLAVE-LARGA";  // la misma que DRIVE_TOKEN en el backend; no la subas al repo
const MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function doPost(e) {
  try {
    const datos = JSON.parse(e.postData.contents);
    if (datos.token !== TOKEN) {
      return responder({ ok: false, error: "clave inválida" });
    }
    if (!/^F7_[\w.-]+\.xlsx$/.test(datos.nombre)) {
      return responder({ ok: false, error: "nombre de archivo inválido: " + datos.nombre });
    }
    const carpeta = DriveApp.getFolderById(CARPETA_ID);
    const blob = Utilities.newBlob(Utilities.base64Decode(datos.contenido), MIME_XLSX, datos.nombre);
    const nuevo = carpeta.createFile(blob);
    // Recien con el nuevo guardado, el anterior de la misma categoria va a la papelera.
    const anteriores = carpeta.getFilesByName(datos.nombre);
    while (anteriores.hasNext()) {
      const archivo = anteriores.next();
      if (archivo.getId() !== nuevo.getId()) archivo.setTrashed(true);
    }
    return responder({ ok: true, id: nuevo.getId(), url: nuevo.getUrl() });
  } catch (err) {
    return responder({ ok: false, error: String(err) });
  }
}

function responder(datos) {
  return ContentService.createTextOutput(JSON.stringify(datos)).setMimeType(ContentService.MimeType.JSON);
}

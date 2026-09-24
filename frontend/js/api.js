// Unica linea a cambiar para apuntar al backend ya desplegado (ver README.md).
// Backend corriendo en Render (ver README.md, seccion "Deploy") -- plan
// Free: sin disco persistente, la base se resetea en cada redeploy o
// cuando el servicio se duerme y despierta.
// Abriendo el frontend en localhost (desarrollo) se usa el backend local.
const API_BASE = ["localhost", "127.0.0.1"].includes(window.location.hostname)
  ? "http://localhost:5190"
  : "https://formulario7.onrender.com";

const SOPORTE_EMAILS = ["dir.presupuesto@moron.gob.ar", "bessega.tadeo@moron.gob.ar"];
const SOPORTE_TEXTO = `Si el problema persiste, escribí a ${SOPORTE_EMAILS.join(" o ")}.`;

class ApiError extends Error {
  constructor(status, message, payload) {
    super(message);
    this.status = status;
    this.payload = payload || {};
  }
}

// Sesion por token (Authorization: Bearer <token>), no cookie -- ver
// backend/auth.py para el por que. Se guarda en localStorage: sobrevive a
// un F5 pero no viaja solo entre sitios como haria una cookie.
const TOKEN_KEY = "formulario7_token";
const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (token) => localStorage.setItem(TOKEN_KEY, token);
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch(path, options = {}) {
  // Con FormData (subida de archivos) el navegador pone solo el
  // Content-Type multipart con su boundary: no hay que pisarlo.
  const contentType = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  let resp;
  try {
    resp = await fetch(API_BASE + path, {
      ...options,
      headers: { ...contentType, ...authHeaders(), ...(options.headers || {}) },
    });
  } catch (err) {
    // Fallo de red (backend caido, CORS, sin conexion) -- no es un error de
    // validacion, es un problema tecnico: ahi es donde tiene sentido mandar
    // a soporte, no en un 400/409 con un mensaje de negocio ya claro.
    throw new ApiError(0, `No se pudo conectar con el servidor. ${SOPORTE_TEXTO}`);
  }

  let payload = null;
  const tipo = resp.headers.get("Content-Type") || "";
  if (tipo.includes("application/json")) {
    payload = await resp.json().catch(() => null);
  }

  if (!resp.ok) {
    const mensajeNegocio = payload && payload.error;
    const mensaje = resp.status >= 500 || !mensajeNegocio
      ? `Error inesperado (${resp.status}). ${SOPORTE_TEXTO}`
      : mensajeNegocio;
    throw new ApiError(resp.status, mensaje, payload || {});
  }
  return payload;
}

// Descarga de archivos (Excel, CSV): no puede ser un <a href> plano porque
// la sesion viaja por header Authorization, no por cookie, y el navegador
// no manda headers custom en una navegacion/descarga de <a>. Se pide con
// fetch (con el header), se arma un blob y se dispara la descarga a mano.
async function descargarArchivo(path) {
  let resp;
  try {
    resp = await fetch(API_BASE + path, { headers: authHeaders() });
  } catch (err) {
    throw new ApiError(0, `No se pudo conectar con el servidor. ${SOPORTE_TEXTO}`);
  }

  if (!resp.ok) {
    let payload = null;
    const tipo = resp.headers.get("Content-Type") || "";
    if (tipo.includes("application/json")) payload = await resp.json().catch(() => null);
    const mensajeNegocio = payload && payload.error;
    const mensaje = resp.status >= 500 || !mensajeNegocio
      ? `Error inesperado (${resp.status}). ${SOPORTE_TEXTO}`
      : mensajeNegocio;
    throw new ApiError(resp.status, mensaje, payload || {});
  }

  const disposicion = resp.headers.get("Content-Disposition") || "";
  const match = disposicion.match(/filename="?([^";]+)"?/);
  const nombre = match ? match[1] : "descarga";

  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function qs(params) {
  const partes = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`);
  return partes.length ? `?${partes.join("&")}` : "";
}

const Api = {
  login: async (username, password) => {
    const data = await apiFetch("/api/login", { method: "POST", body: JSON.stringify({ username, password }) });
    if (data && data.token) setToken(data.token);
    return data;
  },
  logout: async () => {
    try {
      await apiFetch("/api/logout", { method: "POST" });
    } finally {
      clearToken();
    }
  },
  sesion: () => apiFetch("/api/sesion"),

  secretarias: () => apiFetch("/api/secretarias"),
  fuentes: () => apiFetch("/api/fuentes"),
  misCategorias: (secretariaId) =>
    apiFetch(`/api/mis-categorias${qs({ secretaria_id: secretariaId })}`),

  // Rechazado (422): el ApiError trae en payload.errores la lista completa.
  cargarExcel: (categoria, archivo) => {
    const datos = new FormData();
    datos.append("categoria", categoria);
    datos.append("archivo", archivo);
    return apiFetch("/api/formularios/excel", { method: "POST", body: datos });
  },

  crearUsuario: (body) =>
    apiFetch("/api/admin/usuarios", { method: "POST", body: JSON.stringify(body) }),
  listarUsuarios: () => apiFetch("/api/admin/usuarios"),
  actualizarUsuario: (id, body) =>
    apiFetch(`/api/admin/usuarios/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  actualizarSecretaria: (id, subjurisdiccion) =>
    apiFetch(`/api/admin/secretarias/${id}`, { method: "PATCH", body: JSON.stringify({ subjurisdiccion }) }),

  anularFormulario: (id) =>
    apiFetch(`/api/admin/formularios/${id}/anular`, { method: "PATCH" }),
  reporte: (fuente, secretariaId) =>
    apiFetch(`/api/admin/reporte${qs({ fuente, secretaria_id: secretariaId })}`),
  descargarReporteCsv: (fuente, secretariaId) =>
    descargarArchivo(`/api/admin/reporte${qs({ formato: "csv", fuente, secretaria_id: secretariaId })}`),
  actualizarTechoCategoria: (id, techo) =>
    apiFetch(`/api/admin/cuota-categoria/${id}`, { method: "PATCH", body: JSON.stringify({ techo }) }),
  actualizarMontoTotal: (id, monto_total) =>
    apiFetch(`/api/admin/cuota-total/${id}`, { method: "PATCH", body: JSON.stringify({ monto_total }) }),
  seguimiento: (fuente) => apiFetch(`/api/admin/seguimiento${qs({ fuente })}`),
  cargasExcel: (limite) => apiFetch(`/api/admin/cargas-excel${qs({ limite })}`),
};

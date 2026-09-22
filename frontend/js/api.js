// Unica linea a cambiar para apuntar al backend ya desplegado (ver README.md).
const API_BASE = "http://localhost:5190";

const SOPORTE_EMAILS = ["dir.presupuesto@moron.gob.ar", "bessega.tadeo@moron.gob.ar"];
const SOPORTE_TEXTO = `Si el problema persiste, escribí a ${SOPORTE_EMAILS.join(" o ")}.`;

class ApiError extends Error {
  constructor(status, message, payload) {
    super(message);
    this.status = status;
    this.payload = payload || {};
  }
}

async function apiFetch(path, options = {}) {
  let resp;
  try {
    resp = await fetch(API_BASE + path, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
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

function qs(params) {
  const partes = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`);
  return partes.length ? `?${partes.join("&")}` : "";
}

const Api = {
  login: (username, password) =>
    apiFetch("/api/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => apiFetch("/api/logout", { method: "POST" }),
  sesion: () => apiFetch("/api/sesion"),

  secretarias: () => apiFetch("/api/secretarias"),
  catalogo: (q, conPrecio) =>
    apiFetch(`/api/catalogo${qs({ q, con_precio: conPrecio ? 1 : undefined })}`),
  misCategorias: (fuente, secretariaId) =>
    apiFetch(`/api/mis-categorias${qs({ fuente, secretaria_id: secretariaId })}`),

  crearFormulario: (body) =>
    apiFetch("/api/formularios", { method: "POST", body: JSON.stringify(body) }),
  listarFormularios: (secretariaId) =>
    apiFetch(`/api/formularios${qs({ secretaria_id: secretariaId })}`),
  obtenerFormulario: (id) => apiFetch(`/api/formularios/${id}`),

  crearUsuario: (body) =>
    apiFetch("/api/admin/usuarios", { method: "POST", body: JSON.stringify(body) }),
  listarUsuarios: () => apiFetch("/api/admin/usuarios"),
  actualizarUsuario: (id, body) =>
    apiFetch(`/api/admin/usuarios/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  anularFormulario: (id) =>
    apiFetch(`/api/admin/formularios/${id}/anular`, { method: "PATCH" }),
  reporte: (fuente, secretariaId) =>
    apiFetch(`/api/admin/reporte${qs({ fuente, secretaria_id: secretariaId })}`),
  reporteCsvUrl: (fuente, secretariaId) =>
    `${API_BASE}/api/admin/reporte${qs({ formato: "csv", fuente, secretaria_id: secretariaId })}`,
  actualizarTechoCategoria: (id, techo) =>
    apiFetch(`/api/admin/cuota-categoria/${id}`, { method: "PATCH", body: JSON.stringify({ techo }) }),
  actualizarMontoTotal: (id, monto_total) =>
    apiFetch(`/api/admin/cuota-total/${id}`, { method: "PATCH", body: JSON.stringify({ monto_total }) }),
  seguimiento: (fuente) => apiFetch(`/api/admin/seguimiento${qs({ fuente })}`),
};

function formatoPesos(monto) {
  return new Intl.NumberFormat("es-AR", {
    style: "currency", currency: "ARS", maximumFractionDigits: 0,
  }).format(monto || 0);
}

function formatoFecha(iso) {
  if (!iso) return "--";
  // Las fechas de la base vienen "YYYY-MM-DD HH:MM:SS" en hora del servidor.
  const [fecha, hora] = iso.split(" ");
  const [anio, mes, dia] = fecha.split("-");
  return `${dia}/${mes}/${anio}${hora ? " " + hora.slice(0, 5) : ""}`;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s == null ? "" : String(s);
  return div.innerHTML;
}

function mostrarAlerta(contenedor, mensaje, tipo = "error") {
  contenedor.innerHTML = `<div class="alerta alerta-${tipo}">${mensaje}</div>`;
}

function limpiarAlerta(contenedor) {
  contenedor.innerHTML = "";
}

/** Redirige a index.html si no hay sesion, o si el rol no esta en
 * rolesPermitidos (por ejemplo un usuario de area entrando a una pagina de
 * admin a mano por URL). Devuelve el usuario logueado o null (ya redirigio). */
async function requerirSesion(rolesPermitidos) {
  let usuario;
  try {
    ({ usuario } = await Api.sesion());
  } catch (e) {
    window.location.href = "index.html";
    return null;
  }
  if (rolesPermitidos && !rolesPermitidos.includes(usuario.rol)) {
    window.location.href = usuario.rol === "admin" ? "admin-seguimiento.html" : "formulario.html";
    return null;
  }
  return usuario;
}

const NAV_ADMIN = [
  { href: "admin-seguimiento.html", texto: "Seguimiento" },
  { href: "admin-reporte.html", texto: "Reporte de cuota" },
  { href: "admin-usuarios.html", texto: "Usuarios" },
];

function montarHeader(usuario, paginaActiva) {
  const topbar = document.getElementById("topbar");
  if (!topbar) return;

  const nav = usuario.rol === "admin"
    ? NAV_ADMIN.map(item =>
        `<a href="${item.href}" class="${item.href === paginaActiva ? "activo" : ""}">${item.texto}</a>`
      ).join("")
    : "";

  const quien = usuario.rol === "admin"
    ? `${usuario.nombre_completo || usuario.username} (admin)`
    : `${usuario.secretaria_nombre} -- ${usuario.nombre_completo || usuario.username}`;

  topbar.innerHTML = `
    <div>
      <h1>Formulario 7 -- Presupuesto 2027</h1>
      <div class="subtitulo">Municipalidad de Morón</div>
    </div>
    <nav class="topbar-nav">${nav}</nav>
    <div class="topbar-usuario">
      <span>${escapeHtml(quien)}</span>
      <button class="btn-logout" id="btn-logout">Salir</button>
    </div>
  `;
  document.getElementById("btn-logout").addEventListener("click", async () => {
    await Api.logout().catch(() => {});
    window.location.href = "index.html";
  });
}

function montarFooterSoporte() {
  const el = document.getElementById("footer-soporte");
  if (!el) return;
  const links = SOPORTE_EMAILS.map(e => `<a href="mailto:${e}">${e}</a>`).join(" o ");
  el.innerHTML = `¿Problemas para cargar el formulario? Escribinos a ${links}.`;
}

document.addEventListener("DOMContentLoaded", montarFooterSoporte);

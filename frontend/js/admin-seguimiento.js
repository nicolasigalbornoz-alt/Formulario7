(async function () {
  const usuario = await requerirSesion(["admin"]);
  if (!usuario) return;
  montarHeader(usuario, "admin-seguimiento.html");

  const selFuente = document.getElementById("sel-fuente");
  const resumenEl = document.getElementById("resumen-general");
  const alertaEl = document.getElementById("alerta");
  const tbody = document.getElementById("tbody-seguimiento");

  async function cargar() {
    limpiarAlerta(alertaEl);
    try {
      const { secretarias, totales } = await Api.seguimiento(Number(selFuente.value));

      resumenEl.innerHTML = `
        <div class="resumen-total">
          <div>
            <div style="font-size:12.5px;color:var(--text-muted);">Categorías cargadas</div>
            <div class="monto">${totales.cargadas} / ${totales.total_categorias}</div>
          </div>
          <div style="flex:1; margin:0 24px;">
            <div class="barra"><div class="barra-relleno ${totales.porcentaje >= 100 ? "completo" : ""}" style="width:${totales.porcentaje}%"></div></div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:12.5px;color:var(--text-muted);">Avance</div>
            <div class="monto">${totales.porcentaje}%</div>
          </div>
        </div>
      `;

      if (secretarias.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="card-desc">Ninguna Secretaría tiene categorías asignadas en esta fuente.</td></tr>`;
        return;
      }

      tbody.innerHTML = secretarias.map(s => `
        <tr>
          <td>${escapeHtml(s.secretaria)}</td>
          <td>
            <div class="barra"><div class="barra-relleno ${s.porcentaje >= 100 ? "completo" : ""}" style="width:${s.porcentaje}%"></div></div>
            <div style="font-size:11.5px;color:var(--text-muted);margin-top:3px;">${s.porcentaje}%</div>
          </td>
          <td class="num">${s.cargadas} / ${s.total_categorias}</td>
          <td>${s.ultima_carga ? formatoFecha(s.ultima_carga) : "--"}</td>
          <td>${s.pendientes.length === 0
            ? '<span class="badge badge-ok">Completo</span>'
            : s.pendientes.map(p => `<span class="badge badge-pendiente" style="margin:1px;">${p}</span>`).join("")}
          </td>
        </tr>
      `).join("");
    } catch (err) {
      mostrarAlerta(alertaEl, err.message);
    }
  }

  const alertaCargas = document.getElementById("alerta-cargas");
  const tbodyCargas = document.getElementById("tbody-cargas");
  const estadoIntegraciones = document.getElementById("estado-integraciones");

  async function cargarExcels() {
    limpiarAlerta(alertaCargas);
    try {
      const { cargas, drive_configurado } = await Api.cargasExcel(50);
      estadoIntegraciones.textContent = drive_configurado
        ? ""
        : "Drive no está configurado: los aprobados quedan solo en el servidor hasta que se configure.";

      if (cargas.length === 0) {
        tbodyCargas.innerHTML = `<tr><td colspan="7" class="card-desc">Todavía no se subió ningún Excel.</td></tr>`;
        return;
      }
      tbodyCargas.innerHTML = cargas.map(c => `
        <tr>
          <td>${formatoFecha(c.subido_en)}</td>
          <td>${escapeHtml(c.secretaria)}<div class="dato-chico">${escapeHtml(c.subido_por_username)}</div></td>
          <td>${escapeHtml(c.categoria)}</td>
          <td>${escapeHtml(c.nombre_archivo)}</td>
          <td>${c.estado === "aprobado"
            ? '<span class="badge badge-ok">Aprobado</span>'
            : `<span class="badge badge-error">Rechazado</span> <span class="dato-chico">${c.cantidad_errores} error(es)</span>`}</td>
          <td class="num">${c.total != null ? formatoPesos(c.total) : "--"}</td>
          <td>${c.drive_link && c.drive_link.startsWith("https://")
            ? `<a href="${escapeHtml(c.drive_link)}" target="_blank" rel="noopener">Abrir</a>`
            : (c.estado === "aprobado" ? '<span class="dato-chico">Pendiente</span>' : "--")}</td>
        </tr>
      `).join("");
    } catch (err) {
      mostrarAlerta(alertaCargas, escapeHtml(err.message));
    }
  }

  selFuente.addEventListener("change", cargar);
  await cargarSelectorFuentes(selFuente);
  await Promise.all([cargar(), cargarExcels()]);
})();

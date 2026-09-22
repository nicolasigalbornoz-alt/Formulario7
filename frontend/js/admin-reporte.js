(async function () {
  const usuario = await requerirSesion(["admin"]);
  if (!usuario) return;
  montarHeader(usuario, "admin-reporte.html");

  const alertaTotales = document.getElementById("alerta-totales");
  const alertaCategorias = document.getElementById("alerta-categorias");
  const tbodyTotales = document.getElementById("tbody-totales");
  const tbodyCategorias = document.getElementById("tbody-categorias");
  const selSecretaria = document.getElementById("sel-secretaria");
  const linkCsv = document.getElementById("link-csv");

  let secretariaFiltro = "";

  async function cargarSecretarias() {
    const { secretarias } = await Api.secretarias();
    selSecretaria.innerHTML = `<option value="">Todas las Secretarías</option>` +
      secretarias.map(s => `<option value="${s.id}">${escapeHtml(s.nombre)}</option>`).join("");
  }

  async function cargarReporte() {
    limpiarAlerta(alertaTotales);
    limpiarAlerta(alertaCategorias);
    const { categorias, totales_secretaria } = await Api.reporte(secretariaFiltro || undefined);

    tbodyTotales.innerHTML = totales_secretaria.map(t => `
      <tr>
        <td>${escapeHtml(t.secretaria)}</td>
        <td class="num editable" data-tipo="total" data-id="${t.secretaria_cuota_total_id}">${formatoPesos(t.monto_total)}</td>
        <td class="num">${formatoPesos(t.usado)}</td>
        <td class="num">${formatoPesos(t.monto_total - t.usado)}</td>
      </tr>
    `).join("");

    tbodyCategorias.innerHTML = categorias.map(c => `
      <tr>
        <td>${escapeHtml(c.secretaria)}</td>
        <td>${c.categoria}</td>
        <td class="num editable" data-tipo="categoria" data-id="${c.cuota_categoria_id}">${formatoPesos(c.techo)}</td>
        <td class="num">${formatoPesos(c.usado)}</td>
        <td class="num">${formatoPesos(c.disponible)}</td>
      </tr>
    `).join("");

    linkCsv.href = Api.reporteCsvUrl(secretariaFiltro || undefined);
  }

  function empezarEdicion(celda) {
    if (celda.querySelector("input")) return;
    const valorActual = celda.dataset.tipo === "total" || celda.dataset.tipo === "categoria"
      ? celda.textContent.replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(",", ".")
      : "";
    const original = celda.textContent;
    celda.innerHTML = `<input type="number" step="0.01" min="0" style="text-align:right;">`;
    const input = celda.querySelector("input");
    input.value = valorActual;
    input.focus();
    input.select();

    let resuelto = false;
    const guardar = async () => {
      if (resuelto) return;
      resuelto = true;
      const nuevoValor = Number(input.value);
      if (!Number.isFinite(nuevoValor) || nuevoValor < 0) {
        celda.textContent = original;
        return;
      }
      try {
        if (celda.dataset.tipo === "categoria") {
          await Api.actualizarTechoCategoria(celda.dataset.id, nuevoValor);
        } else {
          await Api.actualizarMontoTotal(celda.dataset.id, nuevoValor);
        }
        await cargarReporte();
      } catch (err) {
        mostrarAlerta(celda.dataset.tipo === "categoria" ? alertaCategorias : alertaTotales, err.message);
        celda.textContent = original;
      }
    };
    const cancelar = () => {
      if (resuelto) return;
      resuelto = true;
      celda.textContent = original;
    };

    input.addEventListener("blur", guardar);
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); input.blur(); }
      if (ev.key === "Escape") { ev.preventDefault(); cancelar(); }
    });
  }

  document.addEventListener("click", (ev) => {
    const celda = ev.target.closest("td.editable");
    if (celda) empezarEdicion(celda);
  });

  selSecretaria.addEventListener("change", () => {
    secretariaFiltro = selSecretaria.value;
    cargarReporte();
  });

  await cargarSecretarias();
  await cargarReporte();
})();

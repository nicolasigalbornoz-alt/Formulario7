(async function () {
  const usuario = await requerirSesion(["admin"]);
  if (!usuario) return;
  montarHeader(usuario, "admin-reporte.html");

  const alertaSecretarias = document.getElementById("alerta-secretarias");
  const alertaTotales = document.getElementById("alerta-totales");
  const alertaCategorias = document.getElementById("alerta-categorias");
  const tbodySecretarias = document.getElementById("tbody-secretarias");
  const tbodyTotales = document.getElementById("tbody-totales");
  const tbodyCategorias = document.getElementById("tbody-categorias");
  const selSecretaria = document.getElementById("sel-secretaria");
  const selFuente = document.getElementById("sel-fuente");
  const linkCsv = document.getElementById("link-csv");

  let secretariaFiltro = "";

  async function cargarSecretarias() {
    limpiarAlerta(alertaSecretarias);
    const { secretarias } = await Api.secretarias();
    selSecretaria.innerHTML = `<option value="">Todas las Secretarías</option>` +
      secretarias.map(s => `<option value="${s.id}">${escapeHtml(s.nombre)}</option>`).join("");

    tbodySecretarias.innerHTML = secretarias.map(s => `
      <tr>
        <td>${escapeHtml(s.nombre)}</td>
        <td class="editable" data-tipo="subjurisdiccion" data-id="${s.id}">${escapeHtml(s.subjurisdiccion || "(sin definir)")}</td>
      </tr>
    `).join("");
  }

  async function cargarReporte() {
    limpiarAlerta(alertaTotales);
    limpiarAlerta(alertaCategorias);
    const fuente = Number(selFuente.value);
    const { categorias, totales_secretaria } = await Api.reporte(fuente, secretariaFiltro || undefined);

    tbodyTotales.innerHTML = totales_secretaria.map(t => `
      <tr>
        <td>${escapeHtml(t.secretaria)}</td>
        <td class="num editable" data-tipo="total" data-id="${t.secretaria_cuota_total_id}">${formatoPesos(t.monto_total)}</td>
        <td class="num">${formatoPesos(t.cargado)}</td>
        <td class="num">${formatoPesos(t.monto_total - t.cargado)}</td>
      </tr>
    `).join("");

    tbodyCategorias.innerHTML = categorias.length === 0
      ? `<tr><td colspan="5" class="card-desc">Sin categorías en esta fuente.</td></tr>`
      : categorias.map(c => `
      <tr>
        <td>${escapeHtml(c.secretaria)}</td>
        <td>${c.categoria}</td>
        <td class="num editable" data-tipo="categoria" data-id="${c.cuota_categoria_id}">${formatoPesos(c.techo)}</td>
        <td class="num">${formatoPesos(c.cargado)}</td>
        <td class="num">${formatoPesos(c.disponible)}</td>
      </tr>
    `).join("");

    linkCsv.href = Api.reporteCsvUrl(fuente, secretariaFiltro || undefined);
  }

  function empezarEdicion(celda) {
    if (celda.querySelector("input")) return;
    const esTexto = celda.dataset.tipo === "subjurisdiccion";
    const original = celda.textContent;
    const valorActual = esTexto
      ? (original === "(sin definir)" ? "" : original)
      : original.replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(",", ".");

    celda.innerHTML = esTexto
      ? `<input type="text" placeholder="Ej. 1110111000">`
      : `<input type="number" step="0.01" min="0" style="text-align:right;">`;
    const input = celda.querySelector("input");
    input.value = valorActual;
    input.focus();
    input.select();

    const alertaDestino = celda.dataset.tipo === "categoria" ? alertaCategorias
      : celda.dataset.tipo === "subjurisdiccion" ? alertaSecretarias
      : alertaTotales;

    let resuelto = false;
    const guardar = async () => {
      if (resuelto) return;
      resuelto = true;
      try {
        if (esTexto) {
          await Api.actualizarSecretaria(celda.dataset.id, input.value.trim() || null);
          await cargarSecretarias();
        } else {
          const nuevoValor = Number(input.value);
          if (!Number.isFinite(nuevoValor) || nuevoValor < 0) {
            celda.textContent = original;
            return;
          }
          if (celda.dataset.tipo === "categoria") {
            await Api.actualizarTechoCategoria(celda.dataset.id, nuevoValor);
          } else {
            await Api.actualizarMontoTotal(celda.dataset.id, nuevoValor);
          }
          await cargarReporte();
        }
      } catch (err) {
        mostrarAlerta(alertaDestino, err.message);
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
  selFuente.addEventListener("change", cargarReporte);

  await cargarSecretarias();
  await cargarReporte();
})();

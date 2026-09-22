(async function () {
  const usuario = await requerirSesion(["area"]);
  if (!usuario) return;
  montarHeader(usuario, "");

  let fuenteActual = 110;
  let categorias = [];          // [{categoria, techo, submission_id, usado, submitted_at}]
  let cuotaTotalSecretaria = null; // {monto_total, ...} o null si esta fuente no tiene nada asignado
  let categoriaSeleccionada = null;
  let items = [];               // [{tipo, catalogo_id, codigo, denominacion, unidad_medida, cantidad, precio_unitario}]

  const selFuente = document.getElementById("sel-fuente");
  const selCategoria = document.getElementById("sel-categoria");
  const infoCategoria = document.getElementById("info-categoria");
  const cardItems = document.getElementById("card-items");
  const alertaForm = document.getElementById("alerta-form");
  const filasContenedor = document.getElementById("filas-items");
  const montoTotalEl = document.getElementById("monto-total");
  const montoDisponibleEl = document.getElementById("monto-disponible");
  const catActualEl = document.getElementById("cat-actual");
  const buscarBienInput = document.getElementById("buscar-bien");
  const listaSugerencias = document.getElementById("lista-sugerencias");
  const btnAgregarEspecial = document.getElementById("btn-agregar-especial");
  const btnEnviar = document.getElementById("btn-enviar");
  const tbodyMisCargas = document.getElementById("tbody-mis-cargas");
  const resumenSecretaria = document.getElementById("resumen-secretaria");

  function actualizarEtiquetasFuente() {
    document.querySelectorAll("#fuente-actual-label, #fuente-actual-label-2").forEach(el => {
      el.textContent = `-- Fuente ${fuenteActual}`;
    });
  }

  async function cargarCategorias() {
    fuenteActual = Number(selFuente.value);
    actualizarEtiquetasFuente();
    categoriaSeleccionada = null;
    cardItems.hidden = true;
    selCategoria.innerHTML = "";

    const data = await Api.misCategorias(fuenteActual);
    categorias = data.categorias;
    cuotaTotalSecretaria = data.cuota_total;

    if (categorias.length === 0) {
      selCategoria.innerHTML = `<option value="">-- Tu Secretaría no tiene categorías en esta fuente --</option>`;
    } else {
      // El numero que se muestra es siempre el techo (el tope sugerido),
      // no techo-usado: una categoria "ya cargada" se REEMPLAZA al
      // reenviar, no se le suma.
      selCategoria.innerHTML = `<option value="">-- Elegir categoría --</option>` + categorias.map(c =>
        `<option value="${c.categoria}">${c.categoria} -- techo sugerido ${formatoPesos(c.techo)}${c.submission_id ? " (ya cargada)" : ""}</option>`
      ).join("");
    }
    renderMisCargas();
    renderResumenSecretaria();
  }

  function renderResumenSecretaria() {
    if (!cuotaTotalSecretaria) {
      resumenSecretaria.innerHTML = `<div class="alerta alerta-warn">Tu Secretaría no tiene un total asignado en la fuente ${fuenteActual}.</div>`;
      return;
    }
    const usado = categorias.reduce((acc, c) => acc + c.usado, 0);
    const techo = cuotaTotalSecretaria.monto_total;
    const porcentaje = techo > 0 ? Math.min(100, Math.round((usado / techo) * 1000) / 10) : 0;
    resumenSecretaria.innerHTML = `
      <div class="resumen-total">
        <div>
          <div style="font-size:12.5px;color:var(--text-muted);">Usado</div>
          <div class="monto ${usado > techo ? "excedido" : ""}">${formatoPesos(usado)}</div>
        </div>
        <div style="flex:1; margin:0 24px;">
          <div class="barra"><div class="barra-relleno ${porcentaje >= 100 ? "completo" : ""}" style="width:${porcentaje}%"></div></div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:12.5px;color:var(--text-muted);">Total permitido</div>
          <div class="monto">${formatoPesos(techo)}</div>
        </div>
      </div>
    `;
  }

  function renderMisCargas() {
    if (categorias.length === 0) {
      tbodyMisCargas.innerHTML = `<tr><td colspan="5" class="card-desc">Sin categorías en esta fuente.</td></tr>`;
      return;
    }
    tbodyMisCargas.innerHTML = categorias.map(c => `
      <tr>
        <td>${c.categoria}</td>
        <td class="num">${formatoPesos(c.techo)}</td>
        <td class="num">${formatoPesos(c.usado)}</td>
        <td>${c.submission_id
          ? '<span class="badge badge-ok">Cargado</span>'
          : '<span class="badge badge-pendiente">Pendiente</span>'}</td>
        <td>${c.submitted_at ? formatoFecha(c.submitted_at) : "--"}</td>
      </tr>
    `).join("");
  }

  async function alSeleccionarCategoria() {
    const codigo = selCategoria.value;
    limpiarAlerta(alertaForm);
    if (!codigo) {
      cardItems.hidden = true;
      return;
    }
    categoriaSeleccionada = categorias.find(c => c.categoria === codigo);
    catActualEl.textContent = codigo;
    infoCategoria.innerHTML = "";
    cardItems.hidden = false;

    if (categoriaSeleccionada.submission_id) {
      infoCategoria.innerHTML = `<div class="alerta alerta-warn">Esta categoría ya tiene una carga enviada. Si volvés a enviar, se reemplazan sus ítems por los que dejes acá.</div>`;
      const { formulario } = await Api.obtenerFormulario(categoriaSeleccionada.submission_id);
      document.getElementById("in-subjurisdiccion").value = formulario.subjurisdiccion || "";
      document.getElementById("in-programa").value = formulario.programa || "";
      items = formulario.items.map(i => ({
        tipo: i.tipo, catalogo_id: i.catalogo_id, codigo: i.codigo,
        denominacion: i.denominacion, unidad_medida: i.unidad_medida,
        cantidad: i.cantidad, precio_unitario: i.precio_unitario,
      }));
    } else {
      items = [];
    }
    renderFilas();
  }

  function subtotal(item) {
    const cant = Number(item.cantidad) || 0;
    const precio = Number(item.precio_unitario) || 0;
    return Math.round(cant * precio * 100) / 100;
  }

  function renderFilas() {
    if (items.length === 0) {
      filasContenedor.innerHTML = `<p class="card-desc">Todavía no agregaste ningún ítem.</p>`;
    } else {
      filasContenedor.innerHTML = items.map((item, idx) => {
        const st = subtotal(item);
        if (item.tipo === "comun") {
          return `
            <div class="fila-item" data-idx="${idx}">
              <div class="solo-lectura">${escapeHtml(item.codigo || "")}</div>
              <div class="solo-lectura">${escapeHtml(item.denominacion)}</div>
              <div class="solo-lectura">${escapeHtml(item.unidad_medida)}</div>
              <input type="number" min="1" step="1" class="in-cantidad" data-campo="cantidad" value="${item.cantidad ?? ""}" placeholder="Cant.">
              <div class="solo-lectura">${formatoPesos(item.precio_unitario)}</div>
              <div class="solo-lectura">${formatoPesos(st)}</div>
              <button type="button" class="btn-quitar-fila" data-quitar="${idx}" title="Quitar">×</button>
            </div>`;
        }
        return `
          <div class="fila-item" data-idx="${idx}">
            <div class="solo-lectura">especial</div>
            <input type="text" class="in-denominacion" data-campo="denominacion" value="${escapeHtml(item.denominacion || "")}" placeholder="Nombre del bien/servicio">
            <input type="text" class="in-unidad" data-campo="unidad_medida" value="${escapeHtml(item.unidad_medida || "")}" placeholder="Unidad">
            <input type="number" min="1" step="1" class="in-cantidad" data-campo="cantidad" value="${item.cantidad ?? ""}" placeholder="Cant.">
            <input type="number" min="0" step="0.01" class="in-precio" data-campo="precio_unitario" value="${item.precio_unitario ?? ""}" placeholder="Precio">
            <div class="solo-lectura">${formatoPesos(st)}</div>
            <button type="button" class="btn-quitar-fila" data-quitar="${idx}" title="Quitar">×</button>
          </div>`;
      }).join("");
    }
    actualizarTotales();
  }

  function actualizarTotales() {
    const total = items.reduce((acc, it) => acc + subtotal(it), 0);
    montoTotalEl.textContent = formatoPesos(total);
    if (categoriaSeleccionada) {
      // El techo por categoria es SUGERIDO (no bloquea) -- el color rojo es
      // solo una senal visual, el servidor solo rechaza si se supera el
      // total de la Secretaria (ver resumen-secretaria mas arriba).
      montoDisponibleEl.textContent = formatoPesos(categoriaSeleccionada.techo);
      montoTotalEl.classList.toggle("excedido", total > categoriaSeleccionada.techo);
    }
  }

  filasContenedor.addEventListener("input", (ev) => {
    const fila = ev.target.closest(".fila-item");
    if (!fila) return;
    const idx = Number(fila.dataset.idx);
    const campo = ev.target.dataset.campo;
    if (!campo) return;
    items[idx][campo] = ev.target.value;
    // Solo se re-renderiza el subtotal/total, no toda la fila -- si no,
    // el input pierde el foco en cada tecla.
    const st = subtotal(items[idx]);
    fila.querySelectorAll(".solo-lectura")[fila.querySelectorAll(".solo-lectura").length - 1].textContent = formatoPesos(st);
    actualizarTotales();
  });

  filasContenedor.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-quitar]");
    if (!btn) return;
    items.splice(Number(btn.dataset.quitar), 1);
    renderFilas();
  });

  // ---- Autocomplete "comun" ----
  let timeoutBusqueda = null;
  buscarBienInput.addEventListener("input", () => {
    clearTimeout(timeoutBusqueda);
    const q = buscarBienInput.value.trim();
    if (q.length < 2) {
      listaSugerencias.hidden = true;
      return;
    }
    timeoutBusqueda = setTimeout(async () => {
      const { bienes } = await Api.catalogo(q, true);
      if (bienes.length === 0) {
        listaSugerencias.innerHTML = `<div class="autocomplete-opcion">Sin resultados con precio. Probá «Agregar ítem especial».</div>`;
      } else {
        listaSugerencias.innerHTML = bienes.map(b => `
          <div class="autocomplete-opcion" data-id="${b.id}">
            ${escapeHtml(b.denominacion)}
            <div class="precio">${escapeHtml(b.codigo)} -- ${escapeHtml(b.unidad_texto)} -- ${formatoPesos(b.precio)}</div>
          </div>
        `).join("");
      }
      listaSugerencias.hidden = false;
      listaSugerencias._bienes = bienes;
    }, 250);
  });

  listaSugerencias.addEventListener("click", (ev) => {
    const opcion = ev.target.closest("[data-id]");
    if (!opcion) return;
    const bien = listaSugerencias._bienes.find(b => String(b.id) === opcion.dataset.id);
    items.push({
      tipo: "comun", catalogo_id: bien.id, codigo: bien.codigo,
      denominacion: bien.denominacion, unidad_medida: bien.unidad_texto,
      cantidad: "", precio_unitario: bien.precio,
    });
    buscarBienInput.value = "";
    listaSugerencias.hidden = true;
    renderFilas();
  });

  document.addEventListener("click", (ev) => {
    if (!ev.target.closest(".autocomplete")) listaSugerencias.hidden = true;
  });

  btnAgregarEspecial.addEventListener("click", () => {
    items.push({
      tipo: "especial", catalogo_id: null, codigo: null,
      denominacion: "", unidad_medida: "", cantidad: "", precio_unitario: "",
    });
    renderFilas();
  });

  btnEnviar.addEventListener("click", async () => {
    limpiarAlerta(alertaForm);
    if (!categoriaSeleccionada) return;
    btnEnviar.disabled = true;
    btnEnviar.textContent = "Enviando...";
    try {
      const body = {
        categoria: categoriaSeleccionada.categoria,
        fuente: fuenteActual,
        subjurisdiccion: document.getElementById("in-subjurisdiccion").value.trim() || null,
        programa: document.getElementById("in-programa").value.trim() || null,
        items: items.map(it => ({
          tipo: it.tipo, catalogo_id: it.catalogo_id,
          denominacion: it.denominacion, unidad_medida: it.unidad_medida,
          cantidad: it.cantidad, precio_unitario: it.precio_unitario,
        })),
      };
      const resultado = await Api.crearFormulario(body);
      if (resultado.aviso_categoria) {
        mostrarAlerta(alertaForm,
          `Formulario enviado. Total: ${formatoPesos(resultado.total)}. `
          + `Atención: superaste el techo sugerido de esta categoría (sugerido ${formatoPesos(resultado.aviso_categoria.techo_categoria)}) -- `
          + `se guardó igual porque el total de tu Secretaría sigue dentro de lo permitido.`, "warn");
      } else {
        mostrarAlerta(alertaForm, `Formulario enviado. Total: ${formatoPesos(resultado.total)}.`, "ok");
      }
      const categoriaEnviada = categoriaSeleccionada.categoria;
      await cargarCategorias();
      selCategoria.value = categoriaEnviada;
      await alSeleccionarCategoria();
    } catch (err) {
      if (err.status === 409) {
        mostrarAlerta(alertaForm,
          `Esta carga supera el total permitido de tu Secretaría: disponible ${formatoPesos(err.payload.disponible)}, `
          + `solicitado ${formatoPesos(err.payload.solicitado)}. Ajustá las cantidades e intentá de nuevo.`, "error");
      } else if (err.status === 400 && err.payload.fila !== undefined) {
        mostrarAlerta(alertaForm, `Fila ${err.payload.fila + 1}: ${err.message}`, "error");
      } else {
        mostrarAlerta(alertaForm, err.message, "error");
      }
    } finally {
      btnEnviar.disabled = false;
      btnEnviar.textContent = "Enviar Formulario 7";
    }
  });

  selCategoria.addEventListener("change", alSeleccionarCategoria);
  selFuente.addEventListener("change", cargarCategorias);

  await cargarCategorias();
})();

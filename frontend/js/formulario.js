(async function () {
  const usuario = await requerirSesion(["area"]);
  if (!usuario) return;
  montarHeader(usuario, "");

  let fuenteActual = 110;
  let categorias = [];          // [{categoria, techo, submission_id, cargado, submitted_at}]
  let techoTotalSecretaria = null; // {monto_total, ...} o null si esta fuente no tiene nada asignado
  let categoriaSeleccionada = null;
  let items = [];               // [{catalogo_id, codigo, denominacion, unidad_medida, cantidad, precio_unitario}]

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
  const btnEnviar = document.getElementById("btn-enviar");
  const linkDescargarExcel = document.getElementById("link-descargar-excel");
  const tbodyMisCargas = document.getElementById("tbody-mis-cargas");
  const resumenSecretaria = document.getElementById("resumen-secretaria");
  const inSubjurisdiccion = document.getElementById("in-subjurisdiccion");

  // Subjurisdiccion es un dato fijo de la Secretaria (lo carga el admin),
  // no algo que el area escriba -- se muestra de solo lectura.
  inSubjurisdiccion.value = usuario.secretaria_subjurisdiccion || "(sin definir -- pedile al admin que la cargue)";

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
    techoTotalSecretaria = data.cuota_total;

    if (categorias.length === 0) {
      selCategoria.innerHTML = `<option value="">-- Tu Secretaría no tiene categorías en esta fuente --</option>`;
    } else {
      // El numero que se muestra es siempre el techo (el tope sugerido),
      // no techo-cargado: una categoria "ya cargada" se REEMPLAZA al
      // reenviar, no se le suma.
      selCategoria.innerHTML = `<option value="">-- Elegir categoría --</option>` + categorias.map(c =>
        `<option value="${c.categoria}">${c.categoria} -- techo presupuestario ${formatoPesos(c.techo)}${c.submission_id ? " (ya cargada)" : ""}</option>`
      ).join("");
    }
    renderMisCargas();
    renderResumenSecretaria();
  }

  function renderResumenSecretaria() {
    if (!techoTotalSecretaria) {
      resumenSecretaria.innerHTML = `<div class="alerta alerta-warn">Tu Secretaría no tiene un techo presupuestario asignado en la fuente ${fuenteActual}.</div>`;
      return;
    }
    const cargado = categorias.reduce((acc, c) => acc + c.cargado, 0);
    const techo = techoTotalSecretaria.monto_total;
    const porcentaje = techo > 0 ? Math.min(100, Math.round((cargado / techo) * 1000) / 10) : 0;
    resumenSecretaria.innerHTML = `
      <div class="resumen-total">
        <div>
          <div style="font-size:12.5px;color:var(--text-muted);">Cargado</div>
          <div class="monto ${cargado > techo ? "excedido" : ""}">${formatoPesos(cargado)}</div>
        </div>
        <div style="flex:1; margin:0 24px;">
          <div class="barra"><div class="barra-relleno ${porcentaje >= 100 ? "completo" : ""}" style="width:${porcentaje}%"></div></div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:12.5px;color:var(--text-muted);">Techo presupuestario</div>
          <div class="monto">${formatoPesos(techo)}</div>
        </div>
      </div>
    `;
  }

  function renderMisCargas() {
    if (categorias.length === 0) {
      tbodyMisCargas.innerHTML = `<tr><td colspan="6" class="card-desc">Sin categorías en esta fuente.</td></tr>`;
      return;
    }
    tbodyMisCargas.innerHTML = categorias.map(c => `
      <tr>
        <td>${c.categoria}</td>
        <td class="num">${formatoPesos(c.techo)}</td>
        <td class="num">${formatoPesos(c.cargado)}</td>
        <td>${c.submission_id
          ? '<span class="badge badge-ok">Cargado</span>'
          : '<span class="badge badge-pendiente">Pendiente</span>'}</td>
        <td>${c.submitted_at ? formatoFecha(c.submitted_at) : "--"}</td>
        <td>${c.submission_id
          ? `<a class="btn btn-secundario btn-chico" href="${Api.excelUrl(c.submission_id)}" download>Excel</a>`
          : ""}</td>
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
    linkDescargarExcel.hidden = true;

    if (categoriaSeleccionada.submission_id) {
      infoCategoria.innerHTML = `<div class="alerta alerta-warn">Esta categoría ya tiene una carga enviada. Si volvés a enviar, se reemplazan sus ítems por los que dejes acá.</div>`;
      const { formulario } = await Api.obtenerFormulario(categoriaSeleccionada.submission_id);
      document.getElementById("in-programa").value = formulario.programa || "";
      items = formulario.items.map(i => ({
        catalogo_id: i.catalogo_id, codigo: i.codigo,
        denominacion: i.denominacion, unidad_medida: i.unidad_medida,
        cantidad: i.cantidad, precio_unitario: i.precio_unitario,
      }));
      linkDescargarExcel.href = Api.excelUrl(categoriaSeleccionada.submission_id);
      linkDescargarExcel.hidden = false;
    } else {
      items = [];
      document.getElementById("in-programa").value = "";
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
      }).join("");
    }
    actualizarTotales();
  }

  function actualizarTotales() {
    // El total mostrado es siempre la suma de las filas de detalle -- no
    // hay un numero de total aparte que se pueda desincronizar de la lista.
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

  // ---- Autocomplete (unico modo de cargar un bien: siempre del catalogo) ----
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
        listaSugerencias.innerHTML = `<div class="autocomplete-opcion">Sin resultados con precio de catálogo.</div>`;
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
      catalogo_id: bien.id, codigo: bien.codigo,
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

  btnEnviar.addEventListener("click", async () => {
    limpiarAlerta(alertaForm);
    if (!categoriaSeleccionada) return;
    btnEnviar.disabled = true;
    btnEnviar.textContent = "Enviando...";
    try {
      const body = {
        categoria: categoriaSeleccionada.categoria,
        fuente: fuenteActual,
        programa: document.getElementById("in-programa").value.trim() || null,
        items: items.map(it => ({ catalogo_id: it.catalogo_id, cantidad: it.cantidad })),
      };
      const resultado = await Api.crearFormulario(body);
      if (resultado.aviso_categoria) {
        mostrarAlerta(alertaForm,
          `Formulario enviado. Total: ${formatoPesos(resultado.total)}. `
          + `Atención: superaste el techo presupuestario sugerido de esta categoría (sugerido ${formatoPesos(resultado.aviso_categoria.techo_categoria)}) -- `
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

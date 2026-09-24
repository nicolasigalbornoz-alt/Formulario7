(async function () {
  const usuario = await requerirSesion(["area"]);
  if (!usuario) return;
  montarHeader(usuario, "");

  const MAX_MB = 10;
  let categorias = [];     // [{categoria, fuente, techo, cargado, submission_id, submitted_at}] -- una por Categoria+Fuente
  let totales = [];        // [{fuente, monto_total, cargado}] -- total de la Secretaria por fuente
  let ultimasCargas = {};  // {categoria: {estado, subido_en, nombre_archivo, cantidad_errores}}

  const selCategoria = document.getElementById("sel-categoria");
  const inArchivo = document.getElementById("in-archivo");
  const btnSubir = document.getElementById("btn-subir");
  const infoCategoria = document.getElementById("info-categoria");
  const resultado = document.getElementById("resultado");
  const resumenSecretaria = document.getElementById("resumen-secretaria");
  const tbodyMisCargas = document.getElementById("tbody-mis-cargas");
  const dropzone = document.getElementById("dropzone");
  const dropzoneContenido = document.getElementById("dropzone-contenido");

  const ICONO_SUBIR = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="M7 8l5-5 5 5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>`;
  const ICONO_ARCHIVO = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h6"/></svg>`;
  const ICONO_QUITAR = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>`;

  function renderDropzone() {
    const archivo = inArchivo.files[0];
    if (!archivo) {
      dropzoneContenido.innerHTML = `
        <div class="dropzone-prompt">
          <div class="dropzone-icono">${ICONO_SUBIR}</div>
          <div class="dropzone-texto">
            <strong>Arrastrá el Excel acá</strong>
            <span class="dato-chico">o hacé clic para elegirlo -- hasta ${MAX_MB}&nbsp;MB</span>
          </div>
        </div>`;
      return;
    }
    dropzoneContenido.innerHTML = `
      <div class="dropzone-archivo">
        <div class="dropzone-archivo-icono">${ICONO_ARCHIVO}</div>
        <div class="dropzone-archivo-info">
          <strong>${escapeHtml(archivo.name)}</strong>
          <span class="dato-chico">${formatoTamano(archivo.size)}</span>
        </div>
        <button type="button" class="dropzone-quitar" id="dropzone-quitar" title="Quitar archivo" aria-label="Quitar archivo">${ICONO_QUITAR}</button>
      </div>`;
    document.getElementById("dropzone-quitar").addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      inArchivo.value = "";
      actualizarBoton();
    });
  }

  ["dragenter", "dragover"].forEach(evento => dropzone.addEventListener(evento, (e) => {
    e.preventDefault();
    dropzone.classList.add("arrastrando");
  }));
  ["dragleave", "dragend"].forEach(evento => dropzone.addEventListener(evento, (e) => {
    e.preventDefault();
    dropzone.classList.remove("arrastrando");
  }));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("arrastrando");
    if (e.dataTransfer.files.length) {
      inArchivo.files = e.dataTransfer.files;
      inArchivo.dispatchEvent(new Event("change"));
    }
  });

  // {categoria: [filas, una por fuente]}, en el orden en que vienen.
  function porCategoria() {
    const grupos = new Map();
    for (const c of categorias) {
      if (!grupos.has(c.categoria)) grupos.set(c.categoria, []);
      grupos.get(c.categoria).push(c);
    }
    return grupos;
  }

  async function cargarDatos() {
    const data = await Api.misCategorias();
    categorias = data.categorias;
    totales = data.totales;
    ultimasCargas = data.ultimas_cargas || {};
    renderSelector();
    renderResumenSecretaria();
    renderMisCargas();
  }

  function renderSelector() {
    const elegida = selCategoria.value;
    const grupos = porCategoria();
    if (grupos.size === 0) {
      selCategoria.innerHTML = `<option value="">-- Tu Secretaría no tiene categorías con techo asignado --</option>`;
    } else {
      selCategoria.innerHTML = `<option value="">-- Elegir categoría --</option>` + [...grupos].map(([codigo, filas]) => {
        const techos = filas.map(f => `F${f.fuente} ${formatoPesos(f.techo)}`).join(" · ");
        const cargada = filas.some(f => f.submission_id);
        return `<option value="${escapeHtml(codigo)}">${escapeHtml(codigo)} -- techo ${techos}${cargada ? " (ya cargada)" : ""}</option>`;
      }).join("");
    }
    if (grupos.has(elegida)) selCategoria.value = elegida;
    renderInfoCategoria();
    actualizarBoton();
  }

  function renderInfoCategoria() {
    const filas = porCategoria().get(selCategoria.value);
    if (!filas) {
      infoCategoria.innerHTML = "";
      return;
    }
    const techos = filas.map(f =>
      `<li>Fuente <strong>${f.fuente}</strong>: techo ${formatoPesos(f.techo)}${f.submission_id ? ` -- cargado ${formatoPesos(f.cargado)}` : ""}</li>`
    ).join("");
    const fuentes = filas.map(f => f.fuente).join(" o ");
    const aviso = filas.some(f => f.submission_id)
      ? `<div class="alerta alerta-warn">Esta categoría ya tiene un Excel aprobado. Si subís otro, <strong>reemplaza al anterior</strong> entero.</div>`
      : "";
    infoCategoria.innerHTML = `
      <p class="card-desc">Techo de la categoría ${escapeHtml(selCategoria.value)} -- sus filas solo pueden tener fuente ${fuentes}:</p>
      <ul class="lista-techos">${techos}</ul>${aviso}`;
  }

  function renderResumenSecretaria() {
    if (totales.length === 0) {
      resumenSecretaria.innerHTML = `<div class="alerta alerta-warn">Tu Secretaría no tiene un techo presupuestario asignado.</div>`;
      return;
    }
    resumenSecretaria.innerHTML = totales.map(t => {
      const techo = t.monto_total;
      const porcentaje = techo > 0 ? Math.min(100, Math.round((t.cargado / techo) * 1000) / 10) : 0;
      return `
        <div class="resumen-total">
          <div>
            <div style="font-size:12.5px;color:var(--text-muted);">Fuente ${t.fuente} -- cargado</div>
            <div class="monto ${t.cargado > techo ? "excedido" : ""}">${formatoPesos(t.cargado)}</div>
          </div>
          <div style="flex:1; margin:0 24px;">
            <div class="barra"><div class="barra-relleno ${porcentaje >= 100 ? "completo" : ""}" style="width:${porcentaje}%"></div></div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:12.5px;color:var(--text-muted);">Techo presupuestario</div>
            <div class="monto">${formatoPesos(techo)}</div>
          </div>
        </div>`;
    }).join("");
  }

  function ultimoExcel(carga) {
    if (!carga) return "--";
    const fecha = `<span class="dato-chico">${formatoFecha(carga.subido_en)}</span>`;
    return carga.estado === "aprobado"
      ? `<span class="badge badge-ok">Aprobado</span> ${fecha}`
      : `<span class="badge badge-error">Rechazado</span> ${fecha} <span class="dato-chico">· ${carga.cantidad_errores} error(es)</span>`;
  }

  function renderMisCargas() {
    const grupos = porCategoria();
    if (grupos.size === 0) {
      tbodyMisCargas.innerHTML = `<tr><td colspan="6" class="card-desc">Sin categorías asignadas.</td></tr>`;
      return;
    }
    tbodyMisCargas.innerHTML = [...grupos].map(([codigo, filas]) => filas.map((f, i) => `
      <tr>
        ${i === 0 ? `<td rowspan="${filas.length}">${escapeHtml(codigo)}</td>` : ""}
        <td>${f.fuente}</td>
        <td class="num">${formatoPesos(f.techo)}</td>
        <td class="num">${formatoPesos(f.cargado)}</td>
        <td>${f.submission_id
          ? '<span class="badge badge-ok">Cargado</span>'
          : '<span class="badge badge-pendiente">Pendiente</span>'}</td>
        ${i === 0 ? `<td rowspan="${filas.length}">${ultimoExcel(ultimasCargas[codigo])}</td>` : ""}
      </tr>`).join("")).join("");
  }

  function actualizarBoton() {
    btnSubir.disabled = !(selCategoria.value && inArchivo.files.length);
    renderDropzone();
  }

  function renderAprobado(categoria) {
    resultado.innerHTML = `
      <div class="alerta alerta-ok">
        <strong>El Formulario 7 de la categoría ${escapeHtml(categoria)} se cargó exitosamente.</strong>
      </div>`;
  }

  function listaDeErrores(titulo, errores) {
    return `
      <h3 class="titulo-errores">${titulo}</h3>
      <ul class="lista-errores">${errores.map(e => `<li>${escapeHtml(e.mensaje)}</li>`).join("")}</ul>`;
  }

  // "Marcar el error y comentarlo": cada error con su hoja y celda, en el
  // orden de la planilla -- lo mismo que va marcado en el Excel del mail.
  function renderRechazado(p, nombre) {
    const techos = p.errores.filter(e => e.tipo === "techo");
    const generales = p.errores.filter(e => e.tipo !== "techo" && !e.celda);
    const deCelda = p.errores.filter(e => e.celda);
    let html = `
      <div class="alerta alerta-error">
        <strong>El Excel no se cargó.</strong> ${escapeHtml(nombre)} tiene ${p.errores.length} error(es):
        corregilos en el archivo y volvé a subirlo. Si tenés dudas sobre el techo o la carga, escribí a
        ${SOPORTE_EMAILS.map(e => `<a href="mailto:${e}">${e}</a>`).join(" o ")}.
      </div>`;
    if (techos.length) html += listaDeErrores("Techo presupuestario superado", techos);
    if (generales.length) html += listaDeErrores("Problemas con el archivo", generales);
    if (deCelda.length) {
      html += `
        <h3 class="titulo-errores">Errores en las filas (${deCelda.length})</h3>
        <div class="tabla-scroll tabla-errores">
          <table>
            <thead><tr><th>Hoja</th><th>Celda</th><th>Columna</th><th>Qué hay que corregir</th></tr></thead>
            <tbody>${deCelda.map(e => `
              <tr>
                <td>${escapeHtml(e.hoja)}</td>
                <td><span class="celda">${escapeHtml(e.celda)}</span></td>
                <td>${escapeHtml(e.campo || "")}</td>
                <td>${escapeHtml(e.mensaje)}</td>
              </tr>`).join("")}
            </tbody>
          </table>
        </div>`;
    }
    resultado.innerHTML = html;
  }

  btnSubir.addEventListener("click", async () => {
    const categoria = selCategoria.value;
    const archivo = inArchivo.files[0];
    if (!categoria || !archivo) return;
    limpiarAlerta(resultado);
    if (archivo.size > MAX_MB * 1024 * 1024) {
      mostrarAlerta(resultado, `El archivo pesa más de ${MAX_MB} MB: no parece la planilla del Formulario 7.`);
      return;
    }
    btnSubir.disabled = true;
    btnSubir.textContent = "Validando...";
    try {
      await Api.cargarExcel(categoria, archivo);
      renderAprobado(categoria);
    } catch (err) {
      if (err.status === 422 && Array.isArray(err.payload.errores)) {
        renderRechazado(err.payload, archivo.name);
      } else {
        mostrarAlerta(resultado, escapeHtml(err.message));
      }
    } finally {
      // Para volver a subir hay que elegir de nuevo el archivo ya corregido
      // (el navegador no relee un archivo que cambio despues de elegirlo).
      inArchivo.value = "";
      btnSubir.textContent = "Validar y cargar";
      await cargarDatos().catch(() => {});
      actualizarBoton();
    }
  });

  selCategoria.addEventListener("change", () => {
    limpiarAlerta(resultado);
    renderInfoCategoria();
    actualizarBoton();
  });
  inArchivo.addEventListener("change", actualizarBoton);

  await cargarDatos();
})();

(async function () {
  const usuario = await requerirSesion(["admin"]);
  if (!usuario) return;
  montarHeader(usuario, "admin-usuarios.html");

  const alertaCrear = document.getElementById("alerta-crear");
  const alertaLista = document.getElementById("alerta-lista");
  const form = document.getElementById("form-crear");
  const selRol = document.getElementById("sel-rol");
  const campoSecretaria = document.getElementById("campo-secretaria");
  const selSecretariaNueva = document.getElementById("sel-secretaria-nueva");
  const tbody = document.getElementById("tbody-usuarios");

  async function cargarSecretarias() {
    const { secretarias } = await Api.secretarias();
    selSecretariaNueva.innerHTML = secretarias.map(s => `<option value="${s.id}">${escapeHtml(s.nombre)}</option>`).join("");
  }

  async function cargarUsuarios() {
    limpiarAlerta(alertaLista);
    const { usuarios } = await Api.listarUsuarios();
    tbody.innerHTML = usuarios.map(u => `
      <tr data-id="${u.id}">
        <td>${escapeHtml(u.username)}</td>
        <td>${escapeHtml(u.nombre_completo || "--")}</td>
        <td>${u.rol === "admin" ? "Administrador" : "Área"}</td>
        <td>${escapeHtml(u.secretaria_nombre || "--")}</td>
        <td>${u.activo
          ? '<span class="badge badge-ok">Activo</span>'
          : '<span class="badge badge-pendiente">Desactivado</span>'}</td>
        <td>
          <button type="button" class="btn btn-secundario btn-chico" data-accion="toggle">${u.activo ? "Desactivar" : "Activar"}</button>
          <button type="button" class="btn btn-secundario btn-chico" data-accion="resetear">Resetear contraseña</button>
        </td>
      </tr>
    `).join("");
  }

  selRol.addEventListener("change", () => {
    campoSecretaria.hidden = selRol.value === "admin";
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    limpiarAlerta(alertaCrear);
    const body = {
      username: document.getElementById("in-username").value.trim(),
      password: document.getElementById("in-password").value,
      nombre_completo: document.getElementById("in-nombre").value.trim() || null,
      rol: selRol.value,
      secretaria_id: selRol.value === "area" ? Number(selSecretariaNueva.value) : null,
    };
    try {
      await Api.crearUsuario(body);
      form.reset();
      campoSecretaria.hidden = false;
      mostrarAlerta(alertaCrear, "Usuario creado.", "ok");
      await cargarUsuarios();
    } catch (err) {
      mostrarAlerta(alertaCrear, err.message);
    }
  });

  tbody.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-accion]");
    if (!btn) return;
    const fila = btn.closest("tr");
    const id = fila.dataset.id;
    limpiarAlerta(alertaLista);
    try {
      if (btn.dataset.accion === "toggle") {
        const estaActivo = fila.querySelector(".badge-ok") !== null;
        await Api.actualizarUsuario(id, { activo: !estaActivo });
      } else if (btn.dataset.accion === "resetear") {
        const nueva = prompt("Nueva contraseña (mínimo 8 caracteres):");
        if (!nueva) return;
        if (nueva.length < 8) {
          mostrarAlerta(alertaLista, "La contraseña debe tener al menos 8 caracteres.");
          return;
        }
        await Api.actualizarUsuario(id, { password: nueva });
        mostrarAlerta(alertaLista, "Contraseña actualizada.", "ok");
      }
      await cargarUsuarios();
    } catch (err) {
      mostrarAlerta(alertaLista, err.message);
    }
  });

  await cargarSecretarias();
  await cargarUsuarios();
})();

(async function () {
  // Si ya hay sesion activa, no mostrar el login de nuevo.
  try {
    const { usuario } = await Api.sesion();
    window.location.href = usuario.rol === "admin" ? "admin-seguimiento.html" : "formulario.html";
    return;
  } catch (e) {
    // No autenticado -- se queda en el login, es lo esperado.
  }

  const form = document.getElementById("form-login");
  const alertaEl = document.getElementById("alerta");
  const btn = document.getElementById("btn-entrar");

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    limpiarAlerta(alertaEl);
    btn.disabled = true;
    btn.textContent = "Ingresando...";
    try {
      const { usuario } = await Api.login(
        document.getElementById("username").value.trim(),
        document.getElementById("password").value,
      );
      window.location.href = usuario.rol === "admin" ? "admin-seguimiento.html" : "formulario.html";
    } catch (err) {
      mostrarAlerta(alertaEl, err.message);
      btn.disabled = false;
      btn.textContent = "Ingresar";
    }
  });
})();

(async function () {
  // Render (plan Free) duerme el backend tras un rato sin trafico y despertarlo
  // tarda 1-2 minutos: este ping al abrir el login ya lo va despertando
  // mientras la persona escribe usuario y contraseña.
  fetch(API_BASE + "/api/sesion").catch(() => {});

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
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value;
      // Un fallo de red o 502/503/504 es el servidor despertando, no una
      // clave mala: se reintenta solo (hasta ~2,5 min) con un aviso claro.
      let usuario;
      for (let intento = 0; ; intento++) {
        try {
          ({ usuario } = await Api.login(username, password));
          break;
        } catch (err) {
          const dormido = err.status === 0 || [502, 503, 504].includes(err.status);
          if (!dormido || intento >= 8) throw err;
          mostrarAlerta(alertaEl, "El servidor estaba dormido y se está despertando (puede tardar 1-2 minutos). Reintentando solo, no cierres la página...", "ok");
          await new Promise((r) => setTimeout(r, 15000));
        }
      }
      window.location.href = usuario.rol === "admin" ? "admin-seguimiento.html" : "formulario.html";
    } catch (err) {
      mostrarAlerta(alertaEl, err.message);
      btn.disabled = false;
      btn.textContent = "Ingresar";
    }
  });
})();

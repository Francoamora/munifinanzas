document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("movimiento-filter-form");
  if (!form) return;

  const desdeInput = form.querySelector('input[name="desde"]');
  const hastaInput = form.querySelector('input[name="hasta"]');
  const quickButtons = form.querySelectorAll("[data-quick-range]");

  if (!desdeInput || !hastaInput || quickButtons.length === 0) {
    return;
  }

  function formatDateLocal(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + d;
  }

  function parseISODate(value) {
    if (!value) return null;
    const parts = value.split("-");
    if (parts.length !== 3) return null;
    const y = Number(parts[0]);
    const m = Number(parts[1]);
    const d = Number(parts[2]);
    if (!y || !m || !d) return null;
    return new Date(y, m - 1, d);
  }

  function sameDay(a, b) {
    return (
      a &&
      b &&
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()
    );
  }

  function setActiveButton(activeRange) {
    quickButtons.forEach(function (btn) {
      const r = btn.getAttribute("data-quick-range");
      btn.classList.toggle("btn-quick-active", r === activeRange);
    });
  }

  // Marcar todos los botones como "btn-quick" para el CSS
  quickButtons.forEach(function (btn) {
    btn.classList.add("btn-quick");
  });

  // Detectar si al cargar la página los rangos coinciden con alguno de los atajos
  function detectInitialRange() {
    const desde = parseISODate(desdeInput.value);
    const hasta = parseISODate(hastaInput.value);
    if (!desde || !hasta) return null;

    // Tomamos "hasta" como hoy lógico del filtro
    const today = new Date(hasta.getFullYear(), hasta.getMonth(), hasta.getDate());

    // Este año: desde 1/1 hasta hoy
    const firstOfYear = new Date(today.getFullYear(), 0, 1);
    if (sameDay(desde, firstOfYear) && sameDay(hasta, today)) {
      return "this_year";
    }

    // Este mes: desde 1 del mes hasta hoy
    const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    if (sameDay(desde, firstOfMonth) && sameDay(hasta, today)) {
      return "this_month";
    }

    // Últimos 30 días (incluyendo hoy): hoy y los 29 días anteriores
    const start30 = new Date(today);
    start30.setDate(start30.getDate() - 29);
    if (sameDay(desde, start30) && sameDay(hasta, today)) {
      return "last30";
    }

    return null;
  }

  const initialRange = detectInitialRange();
  if (initialRange) {
    setActiveButton(initialRange);
  }

  // Si el usuario toca a mano las fechas, limpiamos la selección de atajos
  function clearQuickSelectionOnManualChange() {
    setActiveButton(null);
  }
  desdeInput.addEventListener("change", clearQuickSelectionOnManualChange);
  hastaInput.addEventListener("change", clearQuickSelectionOnManualChange);

  // Comportamiento de los atajos
  quickButtons.forEach(function (btn) {
    btn.addEventListener("click", function (event) {
      event.preventDefault();

      const range = btn.getAttribute("data-quick-range");
      const today = new Date();
      let desde = null;
      let hasta = null;

      // Hasta siempre hoy (inclusive)
      hasta = new Date(
        today.getFullYear(),
        today.getMonth(),
        today.getDate()
      );

      if (range === "last30") {
        // Hoy + 29 días hacia atrás = 30 días en total
        const desdeDate = new Date(hasta);
        desdeDate.setDate(desdeDate.getDate() - 29);
        desde = desdeDate;
      } else if (range === "this_month") {
        desde = new Date(hasta.getFullYear(), hasta.getMonth(), 1);
      } else if (range === "this_year") {
        desde = new Date(hasta.getFullYear(), 0, 1);
      }

      if (desde) {
        desdeInput.value = formatDateLocal(desde);
      }
      if (hasta) {
        hastaInput.value = formatDateLocal(hasta);
      }

      setActiveButton(range);

      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.submit();
      }
    });
  });
});

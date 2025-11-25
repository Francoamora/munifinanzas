document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("movimiento-filter-form");
  if (!form) return;

  const desdeInput = form.querySelector('input[name="desde"]');
  const hastaInput = form.querySelector('input[name="hasta"]');
  const quickButtons = document.querySelectorAll("[data-quick-range]");

  if (!desdeInput || !hastaInput || quickButtons.length === 0) {
    return;
  }

  function formatDateLocal(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + d;
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
        const desdeDate = new Date(hasta);
        desdeDate.setDate(desdeDate.getDate() - 30);
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
      form.submit();
    });
  });
});

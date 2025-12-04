// Mejora de UX para ViajeVehiculo:
// - Autocompletado local de chofer (usa las opciones del select oculto)
// - Selector de beneficiarios con buscador + chips sobre el select multiple oculto

(function () {
  function normalizar(texto) {
    return (texto || "").toString().toLowerCase();
  }

  // Deja solo dígitos (para comparar DNI con o sin puntos/espacios)
  function soloDigitos(texto) {
    return (texto || "").toString().replace(/\D+/g, "");
  }

  // =======================
  //   CHOFER (autocomplete)
  // =======================
  function initChoferAutocomplete(wrapper) {
    const select = wrapper.querySelector("select");
    const input = wrapper.querySelector(".js-chofer-search");
    const resultados = wrapper.querySelector(".js-chofer-results");
    const preview = wrapper.querySelector(".js-chofer-preview");

    if (!select || !input || !resultados || !preview) return;

    const opciones = Array.from(select.options).filter((opt) => opt.value);

    function limpiarResultados() {
      resultados.innerHTML = "";
    }

    function setPreview(optionOrNull) {
      preview.innerHTML = "";

      if (!optionOrNull) {
        select.value = "";
        const span = document.createElement("span");
        span.className = "text-muted";
        span.textContent = "Ningún chofer seleccionado todavía.";
        preview.appendChild(span);
        return;
      }

      const opt = optionOrNull;
      select.value = opt.value;

      const cont = document.createElement("div");
      cont.textContent = opt.text;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-link btn-sm p-0 ms-2 text-decoration-none";
      btn.textContent = "Quitar";
      btn.addEventListener("click", function () {
        setPreview(null);
      });

      cont.appendChild(btn);
      preview.appendChild(cont);
    }

    function renderResultados(termino) {
      limpiarResultados();

      const raw = termino.trim();
      const tNorm = normalizar(raw);
      const tDigits = soloDigitos(raw);

      if (!tNorm && !tDigits) return;

      const matches = opciones
        .filter((opt) => {
          const label = opt.text || "";
          const labelNorm = normalizar(label);
          const labelDigits = soloDigitos(label);

          const coincideTexto =
            tNorm && labelNorm.includes(tNorm);

          const coincideDni =
            tDigits && labelDigits && labelDigits.includes(tDigits);

          return coincideTexto || coincideDni;
        })
        .slice(0, 25);

      if (!matches.length) {
        const vacio = document.createElement("div");
        vacio.className = "list-group-item small text-muted";
        vacio.textContent = `Sin resultados para "${termino}"`;
        resultados.appendChild(vacio);
        return;
      }

      matches.forEach((opt) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "list-group-item list-group-item-action";
        item.textContent = opt.text;

        item.addEventListener("click", function () {
          setPreview(opt);
          limpiarResultados();
        });

        resultados.appendChild(item);
      });
    }

    input.addEventListener("input", function () {
      renderResultados(input.value);
    });

    // Si ya hay un chofer seleccionado (modo edición), lo mostramos
    const selectedOpt =
      opciones.find((opt) => opt.selected) ||
      (select.value ? select.options[select.selectedIndex] : null);

    if (selectedOpt && selectedOpt.value) {
      setPreview(selectedOpt);
    } else {
      setPreview(null);
    }
  }

  // =========================================
  //   BENEFICIARIOS (chips + buscador local)
  // =========================================
  function initBeneficiariosSelector(wrapper) {
    const select = wrapper.querySelector("select");
    const input = wrapper.querySelector(".js-benef-search");
    const resultados = wrapper.querySelector(".js-benef-results");
    const chips = wrapper.querySelector(".js-benef-chips");

    if (!select || !input || !resultados || !chips) return;

    const opciones = Array.from(select.options).filter((opt) => opt.value);

    function limpiarResultados() {
      resultados.innerHTML = "";
    }

    function refrescarChips() {
      chips.innerHTML = "";

      const seleccionados = opciones.filter((opt) => opt.selected);

      if (!seleccionados.length) {
        const span = document.createElement("span");
        span.className = "text-muted small";
        span.textContent = "Todavía no agregaste personas.";
        chips.appendChild(span);
        return;
      }

      seleccionados.forEach((opt) => {
        const chip = document.createElement("span");
        chip.className =
          "badge rounded-pill bg-primary-subtle text-primary border border-primary-subtle d-flex align-items-center gap-1";

        const texto = document.createElement("span");
        texto.textContent = opt.text;

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-link btn-sm p-0 ms-1 text-decoration-none";
        btn.innerHTML = "&times;";
        btn.setAttribute("aria-label", "Quitar beneficiario");

        btn.addEventListener("click", function () {
          opt.selected = false;
          refrescarChips();
        });

        chip.appendChild(texto);
        chip.appendChild(btn);
        chips.appendChild(chip);
      });
    }

    function renderResultados(termino) {
      limpiarResultados();

      const raw = termino.trim();
      const tNorm = normalizar(raw);
      const tDigits = soloDigitos(raw);

      if (!tNorm && !tDigits) return;

      const seleccionadosIds = new Set(
        opciones.filter((o) => o.selected).map((o) => o.value)
      );

      const matches = opciones
        .filter((opt) => {
          if (seleccionadosIds.has(opt.value)) {
            return false;
          }

          const label = opt.text || "";
          const labelNorm = normalizar(label);
          const labelDigits = soloDigitos(label);

          const coincideTexto =
            tNorm && labelNorm.includes(tNorm);

          const coincideDni =
            tDigits && labelDigits && labelDigits.includes(tDigits);

          return coincideTexto || coincideDni;
        })
        .slice(0, 25);

      if (!matches.length) {
        const vacio = document.createElement("div");
        vacio.className = "list-group-item small text-muted";
        vacio.textContent = `Sin resultados para "${termino}"`;
        resultados.appendChild(vacio);
        return;
      }

      matches.forEach((opt) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "list-group-item list-group-item-action";
        item.textContent = opt.text;

        item.addEventListener("click", function () {
          opt.selected = true;
          refrescarChips();
          limpiarResultados();
          input.value = "";
        });

        resultados.appendChild(item);
      });
    }

    input.addEventListener("input", function () {
      renderResultados(input.value);
    });

    // Inicial: si ya vienen beneficiarios cargados (edición), armamos los chips
    refrescarChips();
  }

  document.addEventListener("DOMContentLoaded", function () {
    const choferWrapper = document.querySelector("[data-chofer-enhanced='1']");
    if (choferWrapper) {
      initChoferAutocomplete(choferWrapper);
    }

    const benefWrapper = document.querySelector("[data-benef-enhanced='1']");
    if (benefWrapper) {
      initBeneficiariosSelector(benefWrapper);
    }
  });
})();

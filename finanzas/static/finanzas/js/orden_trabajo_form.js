// =========================================================
// Buscador de solicitante para Orden de Trabajo
// - Usa API persona_suggest (texto: apellido, nombre o DNI)
// - Completa el <select id="id_solicitante">
// - Muestra ficha a la derecha
// =========================================================
(function () {
  const wrapper  = document.getElementById("solicitante-wrapper");
  const selectEl = document.getElementById("id_solicitante");
  const queryEl  = document.getElementById("solicitante-query");
  const resultsEl = document.getElementById("solicitante-results");
  const previewEl = document.getElementById("solicitante-preview");
  const textoEl   = document.getElementById("id_solicitante_texto");

  if (!wrapper || !selectEl || !queryEl || !resultsEl || !previewEl) {
    // No estamos en el form de OT, salimos silenciosamente
    return;
  }

  const suggestUrl =
    wrapper.getAttribute("data-persona-suggest-url") ||
    window.PERSONA_SUGGEST_URL ||
    "";

  if (!suggestUrl) {
    console.warn("[finanzas] No se encontró URL para persona_suggest");
    return;
  }

  let debounceId = null;

  function limpiarResultados() {
    resultsEl.innerHTML = "";
  }

  function renderPreview(persona) {
    if (!persona) {
      previewEl.innerHTML =
        '<span class="text-muted">Ninguna persona seleccionada todavía.</span>';
      return;
    }

    const partes = [];
    if (persona.nombre) {
      partes.push("<strong>" + persona.nombre + "</strong>");
    }
    if (persona.dni) {
      partes.push("DNI: " + persona.dni);
    }
    if (persona.direccion) {
      partes.push("Domicilio: " + persona.direccion);
    }
    if (persona.barrio) {
      partes.push("Barrio: " + persona.barrio);
    }

    previewEl.innerHTML = '<div class="d-flex flex-column gap-1 small">'
      + '<div>' + partes.join(" · ") + "</div>"
      + '<button type="button" class="btn btn-sm btn-outline-secondary mt-1" id="btn-limpiar-solicitante">'
      + 'Quitar selección'
      + "</button>"
      + "</div>";

    const btnLimpiar = document.getElementById("btn-limpiar-solicitante");
    if (btnLimpiar) {
      btnLimpiar.addEventListener("click", function () {
        selectEl.value = "";
        if (textoEl) {
          // Dejamos que el usuario cargue texto libre si quiere
          // (no lo pisamos)
        }
        renderPreview(null);
      });
    }
  }

  function seleccionarPersona(persona) {
    if (!persona || !persona.id) return;

    selectEl.value = String(persona.id);

    // Si estaba cargado solicitante_texto, lo limpiamos para no mezclar
    if (textoEl && textoEl.value) {
      textoEl.value = "";
    }

    renderPreview(persona);
  }

  function renderResultados(lista) {
    limpiarResultados();

    if (!lista || !lista.length) {
      return;
    }

    lista.forEach(function (p) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "list-group-item list-group-item-action";
      item.innerHTML =
        "<div class='fw-semibold'>" + (p.nombre || "(sin nombre)") + "</div>"
        + "<div class='small text-muted'>"
        + (p.dni ? "DNI: " + p.dni + " · " : "")
        + (p.direccion || "")
        + (p.barrio ? " – " + p.barrio : "")
        + "</div>";

      item.addEventListener("click", function () {
        seleccionarPersona(p);
      });

      resultsEl.appendChild(item);
    });
  }

  function buscarPersonas(q) {
    q = (q || "").trim();
    if (!q || q.length < 2) {
      limpiarResultados();
      return;
    }

    fetch(suggestUrl + "?q=" + encodeURIComponent(q))
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        renderResultados(data.results || []);
      })
      .catch(function (err) {
        console.error("[finanzas] Error en persona_suggest:", err);
        limpiarResultados();
      });
  }

  // Input con debounce
  queryEl.addEventListener("input", function () {
    const q = queryEl.value;
    if (debounceId) {
      clearTimeout(debounceId);
    }
    debounceId = setTimeout(function () {
      buscarPersonas(q);
    }, 300);
  });

  // Si ya hay un solicitante elegido (ej. en edición), mostramos algo básico
  (function initPreviewDesdeSelect() {
    const value = selectEl.value;
    if (!value) {
      renderPreview(null);
      return;
    }
    const option = selectEl.options[selectEl.selectedIndex];
    if (!option) {
      renderPreview(null);
      return;
    }
    renderPreview({
      id: value,
      nombre: option.text,
      dni: "",
      direccion: "",
      barrio: "",
    });
  })();
})();

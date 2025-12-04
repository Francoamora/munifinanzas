document.addEventListener("DOMContentLoaded", function () {
  /* =========================================================
   * 0) Autofocus inicial
   * ========================================================= */
  (function () {
    const fechaOp = document.getElementById("id_fecha_operacion");
    if (fechaOp && !fechaOp.value) {
      try {
        fechaOp.focus();
      } catch (e) {
        // silencioso
      }
    }
  })();

  /* =========================================================
   * 1) BLOQUES OPCIONALES (PROVEEDOR / BENEFICIARIO / COMBUSTIBLE)
   * ========================================================= */
  function setupSectionToggle(toggleId, sectionId, fieldIds) {
    const toggle = document.getElementById(toggleId);
    const section = document.getElementById(sectionId);

    if (!toggle || !section) return;

    function hasAnyValue() {
      return fieldIds.some(function (id) {
        const field = document.getElementById(id);
        return field && field.value && field.value.trim() !== "";
      });
    }

    function clearField(id) {
      const field = document.getElementById(id);
      const hidden = document.getElementById(id + "_hidden");

      if (field) {
        field.value = "";
      }
      if (hidden) {
        hidden.value = "";
      }
    }

    function applyState() {
      const active = toggle.checked;

      if (active) {
        section.classList.remove("d-none");
        section.classList.add("mv-section-active");
        fieldIds.forEach(function (id) {
          const field = document.getElementById(id);
          if (field) {
            field.removeAttribute("disabled");
          }
        });
      } else {
        section.classList.remove("mv-section-active");
        section.classList.add("d-none");
        fieldIds.forEach(function (id) {
          const field = document.getElementById(id);
          if (field) {
            field.setAttribute("disabled", "disabled");
          }
          clearField(id);
        });
      }
    }

    // Si ya hay valores cargados (editar), mantenemos el bloque activo
    if (hasAnyValue()) {
      toggle.checked = true;
    }

    applyState();
    toggle.addEventListener("change", applyState);
  }

  // Proveedor
  setupSectionToggle("toggle-proveedor", "proveedor-section", [
    "id_proveedor_cuit",
    "id_proveedor_nombre",
  ]);

  // Beneficiario
  setupSectionToggle("toggle-beneficiario", "beneficiario-section", [
    "id_beneficiario_dni",
    "id_beneficiario_nombre",
    "id_beneficiario_direccion",
    "id_beneficiario_barrio",
  ]);

  // Combustible / vehículo
  // 👉 ahora incluye también id_vehiculo (FK) para abrir/cerrar bien el bloque
  setupSectionToggle("toggle-combustible", "combustible-section", [
    "id_vehiculo_texto",
    "id_vehiculo",
    "id_litros",
    "id_precio_unitario",
    "id_tipo_combustible",
  ]);

  /* =========================================================
   * 2) AUTOCOMPLETE DNI (usa URL desde data-persona-dni-url)
   * ========================================================= */
  (function () {
    const dniInput = document.getElementById("id_beneficiario_dni");
    const nombreInput = document.getElementById("id_beneficiario_nombre");
    const direccionInput = document.getElementById("id_beneficiario_direccion");
    const barrioInput = document.getElementById("id_beneficiario_barrio");
    const alertBox = document.getElementById("beneficiario-alert");
    const beneficiarioToggle = document.getElementById("toggle-beneficiario");
    const beneficiarioSection = document.getElementById("beneficiario-section");

    if (!dniInput || !alertBox || !beneficiarioSection) {
      return;
    }

    // Tomamos la URL de forma robusta desde el data-atributo
    const dniLookupUrl =
      beneficiarioSection.getAttribute("data-persona-dni-url");
    if (!dniLookupUrl) {
      console.warn(
        "[finanzas] No se encontró data-persona-dni-url en #beneficiario-section"
      );
      return;
    }

    let lastDni = "";

    function mostrarMensaje(texto, tipo) {
      alertBox.textContent = texto;
      alertBox.classList.remove(
        "d-none",
        "alert-info",
        "alert-warning",
        "alert-danger"
      );
      alertBox.classList.add(tipo || "alert-info");
    }

    dniInput.addEventListener("blur", function () {
      const dni = dniInput.value.trim();

      if (!dni) {
        lastDni = "";
        alertBox.classList.add("d-none");
        return;
      }

      if (dni === lastDni) {
        return;
      }

      // Si el bloque está apagado, lo activamos automáticamente
      if (beneficiarioToggle && !beneficiarioToggle.checked) {
        beneficiarioToggle.checked = true;
        beneficiarioToggle.dispatchEvent(new Event("change"));
      }

      lastDni = dni;

      mostrarMensaje("Buscando DNI en el censo...", "alert-info");

      fetch(dniLookupUrl + "?dni=" + encodeURIComponent(dni))
        .then(function (resp) {
          if (!resp.ok) {
            throw new Error("Respuesta HTTP no OK: " + resp.status);
          }
          return resp.json();
        })
        .then(function (data) {
          if (data.found) {
            if (nombreInput && !nombreInput.value)
              nombreInput.value = data.nombre || "";
            if (direccionInput && !direccionInput.value)
              direccionInput.value = data.direccion || "";
            if (barrioInput && !barrioInput.value)
              barrioInput.value = data.barrio || "";

            mostrarMensaje("Datos cargados desde el censo.", "alert-info");
          } else {
            mostrarMensaje(
              "DNI no encontrado. Se creará una nueva persona.",
              "alert-warning"
            );
          }
        })
        .catch(function (error) {
          console.error("[finanzas] Error consultando DNI:", error);
          mostrarMensaje(
            "No se pudo consultar el censo. Verificá la conexión o avisá al administrador.",
            "alert-danger"
          );
        });
    });
  })();

  /* =========================================================
   * 3) MÁSCARA DE MONTOS / LITROS / PRECIO
   * ========================================================= */
  (function () {
    const montoInput = document.getElementById("id_monto");
    const litrosInput = document.getElementById("id_litros");
    const precioInput = document.getElementById("id_precio_unitario");

    function getNumericString(text) {
      return String(text || "").replace(/[^\d.,]/g, "");
    }

    function normalizeToEnglish(text) {
      text = getNumericString(text);
      if (text === "") return "";

      const hasComma = text.includes(",");
      const hasDot = text.includes(".");

      // Caso 1: tiene coma y punto
      if (hasComma && hasDot) {
        const lastComma = text.lastIndexOf(",");
        const lastDot = text.lastIndexOf(".");

        // es-AR: 1.234,56 => coma decimal
        if (lastComma > lastDot) {
          const cleaned = text.replace(/\./g, "");
          const parts = cleaned.split(",");
          const intRaw = parts[0] || "";
          const decRaw = parts[1] || "";
          const intPart = intRaw.replace(/\D/g, "") || "0";
          const dec = decRaw.replace(/\D/g, "").padEnd(2, "0").slice(0, 2);
          return intPart + "." + dec;
        }

        // en-US: 1,234.56 => punto decimal
        const cleaned = text.replace(/,/g, "");
        const parts = cleaned.split(".");
        const intRaw = parts[0] || "";
        const decRaw = parts[1] || "";
        const intPart = intRaw.replace(/\D/g, "") || "0";
        const dec = decRaw.replace(/\D/g, "").padEnd(2, "0").slice(0, 2);
        return intPart + "." + dec;
      }

      // Caso 2: solo coma (es-AR decimal)
      if (hasComma && !hasDot) {
        const cleaned = text.replace(/\./g, "");
        const parts = cleaned.split(",");
        const intRaw = parts[0] || "";
        const decRaw = parts[1] || "";
        const intPart = intRaw.replace(/\D/g, "") || "0";
        const dec = decRaw.replace(/\D/g, "").padEnd(2, "0").slice(0, 2);
        return intPart + "." + dec;
      }

      // Caso 3: solo punto
      if (hasDot && !hasComma) {
        const lastDot = text.lastIndexOf(".");
        const decimalsCount = text.length - lastDot - 1;

        if (decimalsCount > 0 && decimalsCount <= 2) {
          const cleaned = text.replace(/,/g, "");
          const parts = cleaned.split(".");
          const intRaw = parts[0] || "";
          const decRaw = parts[1] || "";
          const intPart = intRaw.replace(/\D/g, "") || "0";
          const dec = decRaw.replace(/\D/g, "").padEnd(2, "0").slice(0, 2);
          return intPart + "." + dec;
        }

        const intPart = text.replace(/\D/g, "") || "0";
        return intPart + ".00";
      }

      // Caso 4: sin separadores -> entero
      const intPart = text.replace(/\D/g, "") || "0";
      return intPart + ".00";
    }

    function formatEsAr(eng) {
      if (!eng) return "";
      const n = Number(eng);
      if (!isFinite(n)) return eng;

      return new Intl.NumberFormat("es-AR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(n);
    }

    function setupMoneyInput(input) {
      if (!input) return;

      const form = input.form;
      if (!form) return;

      input.type = "text";

      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = input.name;
      hidden.id = input.id + "_hidden";

      // Si ya venía con un valor (editar), lo normalizamos y lo mostramos formateado
      if (input.value) {
        const normInit = normalizeToEnglish(input.value);
        hidden.value = normInit;
        input.value = formatEsAr(normInit);
      } else {
        hidden.value = "";
      }

      const parent = input.parentNode;
      if (parent) {
        parent.insertBefore(hidden, input);
      }

      input.removeAttribute("name");
      input.setAttribute("inputmode", "decimal");
      input.setAttribute("autocomplete", "off");

      input.addEventListener("input", function () {
        const raw = input.value;
        const cleaned = raw.replace(/[^0-9.,]/g, "");
        if (cleaned !== raw) {
          const posDiff = raw.length - cleaned.length;
          let pos = input.selectionStart || cleaned.length;
          input.value = cleaned;
          try {
            input.setSelectionRange(pos - posDiff, pos - posDiff);
          } catch (e) {}
        }

        hidden.value = normalizeToEnglish(input.value);
      });

      input.addEventListener("blur", function () {
        if (!input.value) {
          hidden.value = "";
          return;
        }
        const norm = normalizeToEnglish(input.value);
        hidden.value = norm;
        input.value = formatEsAr(norm);
      });

      form.addEventListener("submit", function () {
        if (!input.value) {
          hidden.value = "";
          return;
        }
        const norm = normalizeToEnglish(input.value);
        hidden.value = norm;
      });
    }

    setupMoneyInput(montoInput);
    setupMoneyInput(litrosInput);
    setupMoneyInput(precioInput);
  })();

  /* =========================================================
   * 4) HINT SEGÚN TIPO DE MOVIMIENTO + FILTRO DE CATEGORÍAS
   * ========================================================= */
  (function () {
    const tipoSelect = document.getElementById("id_tipo");
    const hint = document.getElementById("tipo-hint");
    const categoriaSelect = document.getElementById("id_categoria");
    const dataScript = document.getElementById("categoria-tipos-data");

    let categoriaMap = null;
    let categoriaOptions = [];

    if (categoriaSelect && dataScript) {
      try {
        categoriaMap = JSON.parse(dataScript.textContent || "{}");
      } catch (e) {
        console.warn(
          "[finanzas] No se pudo parsear categoria-tipos-data:",
          e
        );
      }

      if (categoriaMap) {
        categoriaOptions = Array.from(categoriaSelect.options);
      }
    }

    function updateHint(valor) {
      const v =
        valor != null && valor !== undefined
          ? valor
          : tipoSelect
          ? tipoSelect.value
          : "";

      if (!hint) return;

      if (v === "INGRESO") {
        hint.textContent =
          "Ingreso: registrá entradas de dinero (subsidios, coparticipación, aportes, etc.).";
      } else if (v === "GASTO") {
        hint.textContent =
          "Gasto: registrá salidas de dinero (compras, ayudas sociales, combustible, servicios, etc.).";
      } else if (v === "TRANSFERENCIA") {
        hint.textContent =
          "Transferencia: mové fondos entre cuentas de la comuna (completá bien origen y destino).";
      } else {
        hint.textContent =
          "Seleccioná el tipo de movimiento y completá fecha y monto.";
      }
    }

    function aplicarFiltroCategorias() {
      if (
        !tipoSelect ||
        !categoriaSelect ||
        !categoriaMap ||
        !categoriaOptions.length
      ) {
        return;
      }

      const tipo = tipoSelect.value;
      const currentValue = categoriaSelect.value;

      // limpiamos y volvemos a armar opciones
      categoriaSelect.innerHTML = "";

      let optionsToUse = categoriaOptions;

      if (tipo) {
        optionsToUse = categoriaOptions.filter(function (opt) {
          if (!opt.value) {
            // opción vacía / placeholder
            return true;
          }
          const catTipo = categoriaMap[opt.value];
          if (!catTipo) {
            // si no tenemos mapping, no filtramos esa opción
            return true;
          }

          if (tipo === "TRANSFERENCIA") {
            return catTipo === "TRANSFERENCIA";
          }

          // Para INGRESO / GASTO filtramos directo
          return catTipo === tipo;
        });
      }

      optionsToUse.forEach(function (opt) {
        categoriaSelect.appendChild(opt);
      });

      // Si la categoría que estaba seleccionada sigue disponible, la mantenemos
      const stillExists = optionsToUse.some(function (opt) {
        return opt.value === currentValue;
      });

      if (stillExists) {
        categoriaSelect.value = currentValue;
      } else {
        // caso contrario, dejamos la primera opción
        if (categoriaSelect.options.length > 0) {
          categoriaSelect.selectedIndex = 0;
        }
      }
    }

    if (tipoSelect) {
      tipoSelect.addEventListener("change", function () {
        updateHint(tipoSelect.value);
        aplicarFiltroCategorias();
      });

      // Estado inicial
      updateHint(tipoSelect.value);
      aplicarFiltroCategorias();
    } else {
      updateHint("");
    }
  })();

  /* =========================================================
   * 5) AUTOCOMPLETE PERSONA POR APELLIDO/NOMBRE
   * ========================================================= */
  (function () {
    const section = document.getElementById("beneficiario-section");
    if (!section) return;

    const searchUrl = section.getAttribute("data-persona-search-url");
    if (!searchUrl) {
      console.warn(
        "[finanzas] Falta data-persona-search-url en #beneficiario-section"
      );
      return;
    }

    const toggle = document.getElementById("toggle-beneficiario");
    const nombreInput = document.getElementById("id_beneficiario_nombre");
    const dniInput = document.getElementById("id_beneficiario_dni");
    const direccionInput = document.getElementById(
      "id_beneficiario_direccion"
    );
    const barrioInput = document.getElementById("id_beneficiario_barrio");
    const suggestionsBox = document.getElementById(
      "beneficiario-suggestions"
    );

    if (!nombreInput || !suggestionsBox) return;

    let lastQuery = "";
    let debounceTimer = null;
    let abortController = null;

    function clearSuggestions() {
      suggestionsBox.innerHTML = "";
      suggestionsBox.classList.add("d-none");
    }

    function renderSuggestions(items) {
      suggestionsBox.innerHTML = "";

      if (!items || !items.length) {
        suggestionsBox.classList.add("d-none");
        return;
      }

      items.forEach(function (item) {
        const button = document.createElement("button");
        button.type = "button";
        button.className =
          "mv-autocomplete-item list-group-item list-group-item-action py-1 px-2";

        const partes = [];
        if (item.apellido || item.nombre) {
          partes.push(
            ((item.apellido || "") + " " + (item.nombre || "")).trim()
          );
        }
        if (item.dni) {
          partes.push("DNI " + item.dni);
        }

        button.textContent = partes.join(" – ") || "(sin nombre)";

        button.addEventListener("click", function (ev) {
          ev.preventDefault();

          // Activamos el toggle si estaba apagado
          if (toggle && !toggle.checked) {
            toggle.checked = true;
            toggle.dispatchEvent(new Event("change"));
          }

          if (dniInput && item.dni) {
            dniInput.value = item.dni;
          }

          if (nombreInput) {
            nombreInput.value = (
              (item.apellido || "") +
              " " +
              (item.nombre || "")
            ).trim();
          }

          if (direccionInput) {
            direccionInput.value = item.direccion || "";
          }

          if (barrioInput) {
            barrioInput.value = item.barrio || "";
          }

          clearSuggestions();
        });

        suggestionsBox.appendChild(button);
      });

      suggestionsBox.classList.remove("d-none");
    }

    function fetchSuggestions(q) {
      if (abortController) {
        abortController.abort();
      }
      abortController = new AbortController();

      fetch(searchUrl + "?q=" + encodeURIComponent(q), {
        signal: abortController.signal,
      })
        .then(function (resp) {
          if (!resp.ok) {
            throw new Error("HTTP " + resp.status);
          }
          return resp.json();
        })
        .then(function (data) {
          renderSuggestions(data.results || []);
        })
        .catch(function (err) {
          if (err.name === "AbortError") {
            return;
          }
          console.error("[finanzas] Error en persona_autocomplete:", err);
          clearSuggestions();
        });
    }

    nombreInput.addEventListener("input", function (ev) {
      const q = ev.target.value.trim();

      // Si no hay texto o menos de 2/3 caracteres, cerramos
      if (q.length < 2) {
        lastQuery = "";
        clearSuggestions();
        return;
      }

      if (q === lastQuery) {
        return;
      }
      lastQuery = q;

      // Activamos el bloque si estaba apagado
      if (toggle && !toggle.checked) {
        toggle.checked = true;
        toggle.dispatchEvent(new Event("change"));
      }

      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }

      debounceTimer = setTimeout(function () {
        fetchSuggestions(q);
      }, 250);
    });

    // Cerrar el dropdown si se hace click afuera
    document.addEventListener("click", function (ev) {
      if (!section.contains(ev.target)) {
        clearSuggestions();
      }
    });
  })();

  /* =========================================================
   * 6) AUTOCOMPLETE VEHÍCULO PARA COMBUSTIBLE (con FK)
   * ========================================================= */
  (function () {
    const section = document.getElementById("combustible-section");
    if (!section) return;

    const url = section.getAttribute("data-vehiculo-search-url");
    if (!url) {
      console.warn(
        "[finanzas] Falta data-vehiculo-search-url en #combustible-section"
      );
      return;
    }

    const toggle = document.getElementById("toggle-combustible");
    const input = document.getElementById("id_vehiculo_texto");
    const hidden = document.getElementById("id_vehiculo"); // 👈 FK real
    const list = document.getElementById("vehiculo-suggestions");

    if (!input || !hidden || !list) return;

    let currentController = null;

    function clearList() {
      list.classList.add("d-none");
      list.innerHTML = "";
    }

    input.addEventListener("input", function () {
      const q = this.value.trim();

      // Si el usuario toca el texto, reseteamos el FK
      hidden.value = "";

      if (!q) {
        clearList();
        return;
      }

      // Activamos el toggle si estaba apagado
      if (toggle && !toggle.checked) {
        toggle.checked = true;
        toggle.dispatchEvent(new Event("change"));
      }

      if (currentController) {
        currentController.abort();
      }
      currentController = new AbortController();

      fetch(url + "?q=" + encodeURIComponent(q), {
        signal: currentController.signal,
      })
        .then(function (res) {
          return res.ok ? res.json() : [];
        })
        .then(function (data) {
          const items = Array.isArray(data) ? data : (data.results || []);
          list.innerHTML = "";

          if (!Array.isArray(items) || !items.length) {
            clearList();
            return;
          }

          items.forEach(function (item) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "list-group-item list-group-item-action";

            btn.textContent =
              item.label ||
              item.descripcion ||
              item.patente ||
              ("Vehículo #" + item.id);

            btn.addEventListener("click", function () {
              input.value = btn.textContent;
              hidden.value = item.id || ""; // 👈 acá se setea el FK
              clearList();
            });

            list.appendChild(btn);
          });

          list.classList.remove("d-none");
        })
        .catch(function (err) {
          if (err && err.name === "AbortError") {
            return;
          }
          // silencioso para el usuario
          console.error("[finanzas] Error en vehiculo_autocomplete:", err);
        });
    });

    // Cerrar la lista si clickean afuera
    document.addEventListener("click", function (ev) {
      if (!list.contains(ev.target) && ev.target !== input) {
        clearList();
      }
    });
  })();
});

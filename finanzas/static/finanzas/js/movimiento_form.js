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
  setupSectionToggle(
    "toggle-proveedor",
    "proveedor-section",
    ["id_proveedor_cuit", "id_proveedor_nombre"]
  );

  // Beneficiario
  setupSectionToggle(
    "toggle-beneficiario",
    "beneficiario-section",
    [
      "id_beneficiario_dni",
      "id_beneficiario_nombre",
      "id_beneficiario_direccion",
      "id_beneficiario_barrio"
    ]
  );

  // Combustible / vehículo
  setupSectionToggle(
    "toggle-combustible",
    "combustible-section",
    ["id_vehiculo_texto", "id_litros", "id_precio_unitario", "id_tipo_combustible"]
  );

  /* =========================================================
   * 2) AUTOCOMPLETE DNI (usa URL desde data-persona-dni-url)
   * ========================================================= */
  (function () {
    const dniInput            = document.getElementById("id_beneficiario_dni");
    const nombreInput         = document.getElementById("id_beneficiario_nombre");
    const direccionInput      = document.getElementById("id_beneficiario_direccion");
    const barrioInput         = document.getElementById("id_beneficiario_barrio");
    const alertBox            = document.getElementById("beneficiario-alert");
    const beneficiarioToggle  = document.getElementById("toggle-beneficiario");
    const beneficiarioSection = document.getElementById("beneficiario-section");

    if (!dniInput || !alertBox || !beneficiarioSection) {
      return;
    }

    // Tomamos la URL de forma robusta desde el data-atributo
    const dniLookupUrl = beneficiarioSection.getAttribute("data-persona-dni-url");
    if (!dniLookupUrl) {
      console.warn("[finanzas] No se encontró data-persona-dni-url en #beneficiario-section");
      return;
    }

    let lastDni = "";

    function mostrarMensaje(texto, tipo) {
      alertBox.textContent = texto;
      alertBox.classList.remove("d-none", "alert-info", "alert-warning", "alert-danger");
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
            if (nombreInput && !nombreInput.value)        nombreInput.value    = data.nombre    || "";
            if (direccionInput && !direccionInput.value)  direccionInput.value = data.direccion || "";
            if (barrioInput && !barrioInput.value)        barrioInput.value    = data.barrio    || "";

            mostrarMensaje("Datos cargados desde el censo.", "alert-info");
          } else {
            mostrarMensaje("DNI no encontrado. Se creará una nueva persona.", "alert-warning");
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
    const montoInput  = document.getElementById("id_monto");
    const litrosInput = document.getElementById("id_litros");
    const precioInput = document.getElementById("id_precio_unitario");

    function getNumericString(text) {
      return String(text || "").replace(/[^\d.,]/g, "");
    }

    function normalizeToEnglish(text) {
      text = getNumericString(text);
      if (text === "") return "";

      const hasComma = text.includes(",");
      const hasDot   = text.includes(".");

      // Caso 1: tiene coma y punto
      if (hasComma && hasDot) {
        const lastComma = text.lastIndexOf(",");
        const lastDot   = text.lastIndexOf(".");

        // es-AR: 1.234,56 => coma decimal
        if (lastComma > lastDot) {
          const cleaned = text.replace(/\./g, "");
          const parts   = cleaned.split(",");
          const intRaw  = parts[0] || "";
          const decRaw  = parts[1] || "";
          const intPart = intRaw.replace(/\D/g, "") || "0";
          const dec     = decRaw.replace(/\D/g, "").padEnd(2, "0").slice(0, 2);
          return intPart + "." + dec;
        }

        // en-US: 1,234.56 => punto decimal
        const cleaned = text.replace(/,/g, "");
        const parts   = cleaned.split(".");
        const intRaw  = parts[0] || "";
        const decRaw  = parts[1] || "";
        const intPart = intRaw.replace(/\D/g, "") || "0";
        const dec     = decRaw.replace(/\D/g, "").padEnd(2, "0").slice(0, 2);
        return intPart + "." + dec;
      }

      // Caso 2: solo coma (es-AR decimal)
      if (hasComma && !hasDot) {
        const cleaned = text.replace(/\./g, "");
        const parts   = cleaned.split(",");
        const intRaw  = parts[0] || "";
        const decRaw  = parts[1] || "";
        const intPart = intRaw.replace(/\D/g, "") || "0";
        const dec     = decRaw.replace(/\D/g, "").padEnd(2, "0").slice(0, 2);
        return intPart + "." + dec;
      }

      // Caso 3: solo punto
      if (hasDot && !hasComma) {
        const lastDot       = text.lastIndexOf(".");
        const decimalsCount = text.length - lastDot - 1;

        if (decimalsCount > 0 && decimalsCount <= 2) {
          const cleaned = text.replace(/,/g, "");
          const parts   = cleaned.split(".");
          const intRaw  = parts[0] || "";
          const decRaw  = parts[1] || "";
          const intPart = intRaw.replace(/\D/g, "") || "0";
          const dec     = decRaw.replace(/\D/g, "").padEnd(2, "0").slice(0, 2);
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
        maximumFractionDigits: 2
      }).format(n);
    }

    function setupMoneyInput(input) {
      if (!input) return;

      const form = input.form;
      if (!form) return;

      input.type = "text";

      const hidden = document.createElement("input");
      hidden.type  = "hidden";
      hidden.name  = input.name;
      hidden.id    = input.id + "_hidden";

      // Si ya venía con un valor (editar), lo normalizamos y lo mostramos formateado
      if (input.value) {
        const normInit = normalizeToEnglish(input.value);
        hidden.value = normInit;
        input.value  = formatEsAr(normInit);
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
        const raw     = input.value;
        const cleaned = raw.replace(/[^0-9.,]/g, "");
        if (cleaned !== raw) {
          const posDiff = raw.length - cleaned.length;
          let pos       = input.selectionStart || cleaned.length;
          input.value   = cleaned;
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
        input.value  = formatEsAr(norm);
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
   * 4) HINT SEGÚN TIPO DE MOVIMIENTO
   * ========================================================= */
  (function () {
    const tipoSelect = document.getElementById("id_tipo");
    const hint       = document.getElementById("tipo-hint");

    if (!tipoSelect || !hint) return;

    function updateHint() {
      const v = tipoSelect.value;
      if (v === "INGRESO") {
        hint.textContent = "Ingreso: registrá entradas de dinero (subsidios, coparticipación, aportes, etc.).";
      } else if (v === "GASTO") {
        hint.textContent = "Gasto: registrá salidas de dinero (compras, ayudas sociales, combustible, servicios, etc.).";
      } else if (v === "TRANSFERENCIA") {
        hint.textContent = "Transferencia: mové fondos entre cuentas de la comuna (completá bien origen y destino).";
      } else {
        hint.textContent = "Seleccioná el tipo de movimiento y completá fecha y monto.";
      }
    }

    tipoSelect.addEventListener("change", updateHint);
    updateHint();
  })();
});

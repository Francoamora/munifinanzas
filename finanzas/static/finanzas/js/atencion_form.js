// static/finanzas/js/atencion_form.js
document.addEventListener("DOMContentLoaded", function () {
  /* =========================================================
   * 0) Autofocus inicial en persona_nombre
   * ========================================================= */
  (function () {
    const nombreInput = document.getElementById("id_persona_nombre");
    if (nombreInput && !nombreInput.value) {
      try {
        nombreInput.focus();
      } catch (e) {
        // silencioso
      }
    }
  })();

  /* =========================================================
   * 1) AUTOCOMPLETE POR DNI (usa data-persona-dni-url)
   * ========================================================= */
  (function () {
    const section = document.getElementById("persona-section");
    const dniInput = document.getElementById("id_persona_dni");
    const nombreInput = document.getElementById("id_persona_nombre");
    const barrioInput = document.getElementById("id_persona_barrio");
    const personaSelect = document.getElementById("id_persona");
    const alertBox = document.getElementById("persona-alert");

    if (!section || !dniInput || !alertBox) {
      return;
    }

    const dniLookupUrl = section.getAttribute("data-persona-dni-url");
    if (!dniLookupUrl) {
      console.warn(
        "[finanzas] No se encontró data-persona-dni-url en #persona-section"
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
      lastDni = dni;

      mostrarMensaje("Buscando DNI en el censo...", "alert-info");

      fetch(dniLookupUrl + "?dni=" + encodeURIComponent(dni))
        .then(function (resp) {
          if (!resp.ok) {
            throw new Error("HTTP " + resp.status);
          }
          return resp.json();
        })
        .then(function (data) {
          if (data.found) {
            if (nombreInput && !nombreInput.value) {
              nombreInput.value = data.nombre || "";
            }
            if (barrioInput && !barrioInput.value) {
              barrioInput.value = data.barrio || "";
            }

            // Si la API devuelve id, vinculamos la Atencion al Beneficiario
            if (personaSelect && data.id) {
              personaSelect.value = String(data.id);
            }

            mostrarMensaje("Datos cargados desde el censo.", "alert-info");
          } else {
            mostrarMensaje(
              "DNI no encontrado en el censo. Verificá el número o cargá la persona en Personas / censo.",
              "alert-warning"
            );
          }
        })
        .catch(function (error) {
          console.error("[finanzas] Error consultando DNI en censo:", error);
          mostrarMensaje(
            "No se pudo consultar el censo. Verificá la conexión o avisá al administrador.",
            "alert-danger"
          );
        });
    });
  })();

  /* =========================================================
   * 2) AUTOCOMPLETE PERSONA POR APELLIDO / NOMBRE
   *    (usa data-persona-search-url)
   * ========================================================= */
  (function () {
    const section = document.getElementById("persona-section");
    if (!section) return;

    const searchUrl = section.getAttribute("data-persona-search-url");
    if (!searchUrl) {
      console.warn(
        "[finanzas] Falta data-persona-search-url en #persona-section"
      );
      return;
    }

    const nombreInput = document.getElementById("id_persona_nombre");
    const dniInput = document.getElementById("id_persona_dni");
    const barrioInput = document.getElementById("id_persona_barrio");
    const personaSelect = document.getElementById("id_persona");
    const suggestionsBox = document.getElementById("persona-suggestions");

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

          if (barrioInput) {
            barrioInput.value = item.barrio || "";
          }

          // Vinculamos el FK persona si el endpoint devuelve id
          if (personaSelect && item.id) {
            personaSelect.value = String(item.id);
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
          // Soportamos tanto lista simple como {results: [...]}
          const items = Array.isArray(data) ? data : data.results || [];
          renderSuggestions(items);
        })
        .catch(function (err) {
          if (err.name === "AbortError") return;
          console.error("[finanzas] Error en persona_autocomplete:", err);
          clearSuggestions();
        });
    }

    nombreInput.addEventListener("input", function (ev) {
      const q = ev.target.value.trim();

      if (q.length < 2) {
        lastQuery = "";
        clearSuggestions();
        return;
      }

      if (q === lastQuery) {
        return;
      }
      lastQuery = q;

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
});

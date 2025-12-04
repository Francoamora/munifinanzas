// static/finanzas/js/movimiento_proveedor.js
(() => {
  function onReady(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn);
    }
  }

  onReady(() => {
    const section = document.getElementById("proveedor-section");
    if (!section) return;

    const cuitInput = section.querySelector('input[name$="proveedor_cuit"]');
    const nombreInput = section.querySelector('input[name$="proveedor_nombre"]');
    const alertBox = document.getElementById("proveedor-alert");
    const suggestionsEl = document.getElementById("proveedor-suggestions");
    const cuitUrl = section.dataset.proveedorCuitUrl || "";
    const searchUrl = section.dataset.proveedorSearchUrl || "";
    const toggleProveedor = document.getElementById("toggle-proveedor");

    function showAlert(message, type) {
      if (!alertBox) return;
      alertBox.textContent = message || "";
      alertBox.classList.remove(
        "d-none",
        "alert-info",
        "alert-success",
        "alert-warning",
        "alert-danger"
      );
      alertBox.classList.add("alert-" + (type || "info"));
    }

    function hideAlert() {
      if (!alertBox) return;
      alertBox.classList.add("d-none");
    }

    function normalizeCuit(raw) {
      return (raw || "").replace(/[^\d]/g, "");
    }

    // Toggle de sección proveedor
    if (toggleProveedor) {
      toggleProveedor.addEventListener("change", () => {
        const visible = toggleProveedor.checked;
        section.classList.toggle("d-none", !visible);
        if (!visible) {
          hideAlert();
        }
      });
    }

    // Lookup por CUIT
    if (cuitInput && cuitUrl) {
      cuitInput.addEventListener("blur", () => {
        const raw = normalizeCuit(cuitInput.value);
        if (!raw) {
          hideAlert();
          return;
        }
        if (raw.length < 8) {
          showAlert("El CUIT parece incompleto. Verificalo.", "warning");
          return;
        }

        showAlert("Buscando proveedor por CUIT…", "info");

        const url = cuitUrl + "?cuit=" + encodeURIComponent(raw);

        fetch(url, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
        })
          .then((resp) => (resp.ok ? resp.json() : null))
          .then((data) => {
            if (!data) {
              showAlert(
                "No se pudo consultar el proveedor. Intentá nuevamente.",
                "danger"
              );
              return;
            }

            let prov = null;

            // Soportar distintos formatos de respuesta
            if (data.proveedor) {
              prov = data.proveedor;
            } else if (Array.isArray(data.results) && data.results.length) {
              prov = data.results[0];
            } else if (data.id || data.nombre || data.razon_social) {
              prov = data;
            }

            if (!prov) {
              showAlert(
                "No se encontró proveedor con ese CUIT. Podés completar los datos manualmente.",
                "warning"
              );
              return;
            }

            const nombre = prov.nombre || prov.razon_social || "";
            const cuit = prov.cuit || raw;

            if (nombre && nombreInput && !nombreInput.value) {
              nombreInput.value = nombre;
            }
            if (cuit && cuitInput && !cuitInput.value) {
              cuitInput.value = cuit;
            }

            showAlert(
              "Proveedor encontrado en el padrón. Revisá los datos antes de guardar.",
              "success"
            );
          })
          .catch(() => {
            showAlert(
              "No se pudo consultar el proveedor. Verificá tu conexión.",
              "danger"
            );
          });
      });
    }

    // Autocomplete por nombre / razón social
    if (nombreInput && suggestionsEl && searchUrl) {
      let timer = null;

      function clearSuggestions() {
        suggestionsEl.innerHTML = "";
        suggestionsEl.classList.add("d-none");
      }

      function renderSuggestions(items) {
        suggestionsEl.innerHTML = "";
        if (!items || !items.length) {
          clearSuggestions();
          return;
        }

        items.forEach((item) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "list-group-item list-group-item-action small";

          const labelNombre =
            item.nombre || item.razon_social || "Proveedor sin nombre";
          const labelCuit = item.cuit ? " – CUIT " + item.cuit : "";
          btn.textContent = labelNombre + labelCuit;

          btn.addEventListener("click", () => {
            if (nombreInput) nombreInput.value = labelNombre;
            if (cuitInput && item.cuit) cuitInput.value = item.cuit;

            clearSuggestions();
            if (alertBox) {
              showAlert("Proveedor seleccionado del padrón.", "success");
            }
          });

          suggestionsEl.appendChild(btn);
        });

        suggestionsEl.classList.remove("d-none");
      }

      nombreInput.addEventListener("input", function () {
        const term = this.value.trim();
        if (!term || term.length < 2) {
          clearSuggestions();
          return;
        }

        clearTimeout(timer);
        timer = setTimeout(() => {
          const url = searchUrl + "?q=" + encodeURIComponent(term);

          fetch(url, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
          })
            .then((resp) => (resp.ok ? resp.json() : null))
            .then((data) => {
              if (!data) {
                clearSuggestions();
                return;
              }
              const items = Array.isArray(data)
                ? data
                : data.results || data.proveedores || [];
              renderSuggestions(items);
            })
            .catch(() => {
              clearSuggestions();
            });
        }, 250);
      });

      // Cerrar la lista al clickear fuera
      document.addEventListener("click", (event) => {
        if (
          !suggestionsEl.contains(event.target) &&
          event.target !== nombreInput
        ) {
          clearSuggestions();
        }
      });
    }
  });
})();

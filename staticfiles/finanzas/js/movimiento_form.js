// static/finanzas/js/movimiento_form.js (v99 - SOLUCIÓN DEFINITIVA)
(() => {
  "use strict";
  window.__MF_MOV_FORM_VERSION__ = "99";

  // ==================== UTILITIES ====================
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const show = (el, on = true) => el && el.classList.toggle("d-none", !on);
  const val = (el) => (el ? String(el.value ?? "").trim() : "");
  const norm = (s) =>
    String(s || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");

  const setRequired = (el, on) => {
    if (!el) return;
    if (on) el.setAttribute("required", "required");
    else el.removeAttribute("required");
  };

  const setDisabled = (el, on) => {
    if (!el) return;
    el.disabled = !!on;
    el.classList.toggle("mf-disabled", on);
    el.setAttribute("aria-disabled", on ? "true" : "false");
  };

  // ==================== DOM ELEMENTS ====================
  const form = $("#movimientoForm");
  if (!form) return;

  const tipoEl = $("#id_tipo");
  const categoriaEl = $("#id_categoria");
  const categoriasUrl = form.dataset.categoriasUrl;
  const categoriaLoading = $("#categoriaLoading");
  const categoriaMeta = $("#categoriaMeta");

  const cuentaOrigenWrap = $("#cuentaOrigenWrap");
  const cuentaDestinoWrap = $("#cuentaDestinoWrap");
  const cuentaOrigenInput = $("#id_cuenta_origen_texto");
  const cuentaDestinoInput = $("#id_cuenta_destino_texto");

  const personaBadge = $("#personaBadge");

  const provTabBtn = $("#proveedor-tab");
  const ayudaTabBtn = $("#ayuda-tab");
  const vehiculoTabBtn = $("#vehiculo-tab");

  const programaAyuda = $("#id_programa_ayuda");
  const tipoPagoPersona = $("#id_tipo_pago_persona");
  const programaAyudaTexto = $("#id_programa_ayuda_texto");

  const vehiculoSelect = $("#id_vehiculo");
  const litrosInput = $("#id_litros");
  const tipoCombustible = $("#id_tipo_combustible");
  const precioUnitario = $("#id_precio_unitario");

  const modoHint = $("#modoHint");
  const modoHintText = $("#modoHintText");

  // ==================== TYPE CHECKERS ====================
  const isGasto = (t) => norm(t) === "gasto";
  const isIngreso = (t) => norm(t) === "ingreso";
  const isTransfer = (t) => norm(t) === "transferencia";

  // ==================== TAB ACTIVATION ====================
  function activateTab(btn) {
    if (!btn) return;
    try {
      if (window.bootstrap?.Tab) new window.bootstrap.Tab(btn).show();
      else btn.click();
    } catch (_) {
      btn.click();
    }
  }

  // ==================== HINTS ====================
  function hint(tipo) {
    if (!modoHint || !modoHintText) return;
    if (isGasto(tipo)) {
      modoHintText.textContent =
        "Gasto: sale dinero. Se usa Cuenta Origen + Proveedor/Persona/Vehículo según corresponda.";
      show(modoHint, true);
    } else if (isIngreso(tipo)) {
      modoHintText.textContent =
        "Ingreso: entra dinero. Se usa Cuenta Destino y la categoría correspondiente.";
      show(modoHint, true);
    } else if (isTransfer(tipo)) {
      modoHintText.textContent =
        "Transferencia: mover fondos. Se usan Cuenta Origen y Cuenta Destino.";
      show(modoHint, true);
    } else {
      show(modoHint, false);
    }
  }

  // ==================== HELPERS ====================
  function extractDigits(str) {
    const m = String(str || "").match(/(\d{6,})/);
    return m ? m[1] : "";
  }

  function getCategoriaFlags() {
    const opt = categoriaEl?.selectedOptions?.[0];
    if (!opt) return { ayuda: false, combustible: false };
    
    const ayuda = opt.dataset.ayuda === "1";
    const combustible = opt.dataset.combustible === "1";
    
    return { ayuda, combustible };
  }

  // ==================== MODO TIPO ====================
  function applyTipoMode() {
    const tipo = val(tipoEl);
    hint(tipo);

    setRequired(cuentaOrigenInput, isGasto(tipo) || isTransfer(tipo));
    setRequired(cuentaDestinoInput, isIngreso(tipo) || isTransfer(tipo));

    if (cuentaOrigenWrap) show(cuentaOrigenWrap, isGasto(tipo) || isTransfer(tipo));
    if (cuentaDestinoWrap) show(cuentaDestinoWrap, isIngreso(tipo) || isTransfer(tipo));
  }

  // ==================== MODO CATEGORÍA ====================
  function applyCategoriaMode() {
    const tipo = val(tipoEl);
    const catId = val(categoriaEl);

    // Limpiar meta
    if (categoriaMeta) {
      categoriaMeta.innerHTML = "";
      categoriaMeta.className = "badge d-none";
    }

    // DEFAULTS: Todo deshabilitado
    if (personaBadge) personaBadge.textContent = "Opcional";

    setDisabled(programaAyuda, true);
    setDisabled(tipoPagoPersona, true);
    setDisabled(programaAyudaTexto, true);
    setRequired(tipoPagoPersona, false);

    setDisabled(vehiculoSelect, true);
    setDisabled(litrosInput, true);
    setDisabled(tipoCombustible, true);
    setDisabled(precioUnitario, true);
    setRequired(vehiculoSelect, false);
    setRequired(litrosInput, false);
    setRequired(tipoCombustible, false);
    setRequired(precioUnitario, false);

    if (!catId) {
      if (isGasto(tipo)) activateTab(provTabBtn);
      return;
    }

    const { ayuda, combustible } = getCategoriaFlags();

    // MODO AYUDA SOCIAL
    if (ayuda) {
      if (personaBadge) personaBadge.textContent = "Obligatoria";

      setDisabled(programaAyuda, false);
      setDisabled(tipoPagoPersona, false);
      setDisabled(programaAyudaTexto, false);
      setRequired(tipoPagoPersona, true);

      if (categoriaMeta) {
        categoriaMeta.innerHTML = '<i class="bi bi-heart-pulse me-1"></i>Ayuda social';
        categoriaMeta.className = "badge badge-ayuda";
        show(categoriaMeta, true);
      }

      activateTab(ayudaTabBtn);
      return;
    }

    // MODO COMBUSTIBLE
    if (combustible) {
      setDisabled(vehiculoSelect, false);
      setDisabled(litrosInput, false);
      setDisabled(tipoCombustible, false);
      setDisabled(precioUnitario, false);

      setRequired(vehiculoSelect, true);
      setRequired(litrosInput, true);
      setRequired(tipoCombustible, true);
      setRequired(precioUnitario, true);

      if (categoriaMeta) {
        categoriaMeta.innerHTML = '<i class="bi bi-fuel-pump me-1"></i>Combustible';
        categoriaMeta.className = "badge badge-combustible";
        show(categoriaMeta, true);
      }

      activateTab(vehiculoTabBtn);
      return;
    }

    // MODO DEFAULT: Proveedor
    activateTab(provTabBtn);
  }

  // ==================== CONTADOR DESCRIPCIÓN ====================
  function bindDescCounter() {
    const descCounter = $("#descCounter");
    const descEl = $("#id_descripcion");
    if (!descCounter || !descEl) return;
    const update = () => (descCounter.textContent = String(val(descEl).length));
    descEl.addEventListener("input", update);
    update();
  }

  // ==================== SELECT2 AJAX ====================
  function pruneToPlaceholder(selectEl) {
    if (!selectEl) return;
    const current = val(selectEl);
    if (current) {
      const selectedOpt = selectEl.querySelector(`option[value="${CSS.escape(current)}"]`);
      const selectedText = selectedOpt ? selectedOpt.textContent : "";
      selectEl.innerHTML = `<option value=""></option><option value="${current}" selected>${selectedText}</option>`;
    } else {
      selectEl.innerHTML = `<option value=""></option>`;
    }
  }

  function initAjaxSelect2(selectEl, onPick) {
    if (!selectEl || !window.jQuery || !jQuery.fn?.select2) return;

    pruneToPlaceholder(selectEl);

    const url = selectEl.dataset.ajaxUrl;
    const placeholder = selectEl.dataset.placeholder || "Buscar...";
    const $jq = jQuery(selectEl);

    if ($jq.data("select2") || selectEl.classList.contains("select2-hidden-accessible")) return;

    $jq.select2({
      width: "100%",
      theme: "bootstrap-5",
      language: "es",
      placeholder,
      allowClear: true,
      minimumInputLength: 2,
      ajax: {
        url,
        dataType: "json",
        delay: 250,
        data: (params) => ({
          q: params.term,
          term: params.term,
          page: params.page || 1,
        }),
        processResults: (data) => {
          if (!data) return { results: [] };
          if (Array.isArray(data)) return { results: data };
          if (Array.isArray(data.results)) return { results: data.results };
          if (Array.isArray(data.items)) return { results: data.items };
          return { results: [] };
        },
      },
    });

    $jq.on("select2:select", (e) => onPick?.(e.params?.data || null));
    $jq.on("select2:clear", () => onPick?.(null));
  }

  // ==================== FILL FUNCTIONS ====================
  function fillPersona(data) {
    const nombreEl = $("#id_beneficiario_nombre");
    const dniEl = $("#id_beneficiario_dni");
    if (!nombreEl || !dniEl) return;

    if (!data) {
      nombreEl.value = "";
      dniEl.value = "";
      return;
    }

    const text = data.text || "";
    nombreEl.value = data.nombre || text;
    dniEl.value = data.dni || data.documento || extractDigits(text);
  }

  function fillProveedor(data) {
    const nombreEl = $("#id_proveedor_nombre");
    const cuitEl = $("#id_proveedor_cuit");
    if (!nombreEl || !cuitEl) return;

    if (!data) {
      nombreEl.value = "";
      cuitEl.value = "";
      return;
    }

    const text = data.text || "";
    const cuit = data.cuit || extractDigits(text);
    const nombre = data.nombre || text.replace(/\(\s*\d+\s*\)\s*$/, "").trim();

    nombreEl.value = nombre;
    cuitEl.value = cuit;
  }

  function fillVehiculo(data) {
    const vehTxt = $("#id_vehiculo_texto");
    if (!vehTxt) return;
    vehTxt.value = data ? (data.text || "") : "";
  }

  // ==================== LOAD CATEGORÍAS ====================
  async function loadCategorias() {
    if (!categoriasUrl || !categoriaEl) return;

    const tipo = val(tipoEl);
    
    // Reset select
    categoriaEl.innerHTML = `<option value="">---------</option>`;

    if (!tipo) {
      applyCategoriaMode();
      return;
    }

    show(categoriaLoading, true);
    setDisabled(categoriaEl, true);

    try {
      const url = `${categoriasUrl}?tipo=${encodeURIComponent(tipo)}`;
      const res = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });

      if (!res.ok) {
        throw new Error(`Error ${res.status}`);
      }

      const text = await res.text();
      if (!text || text.trim() === '') {
        throw new Error('Respuesta vacía del servidor');
      }

      let data;
      try {
        data = JSON.parse(text);
      } catch (_) {
        if (text.includes('<option')) {
          data = { html: text };
        } else {
          throw new Error('Respuesta inválida');
        }
      }

      // Caso 1: HTML directo
      if (data && typeof data.html === "string" && data.html.includes("<option")) {
        categoriaEl.innerHTML = `<option value="">---------</option>` + data.html;
      } else {
        // Caso 2: JSON estructurado
        const itemsRaw =
          (Array.isArray(data?.results) && data.results) ||
          (Array.isArray(data) && data) ||
          (Array.isArray(data?.items) && data.items) ||
          [];

        // Agrupar
        const groups = new Map();
        for (const it of itemsRaw) {
          const g = it.group || it.grupo || it.tipo || it.seccion || "";
          const key = g || "__nogroup__";
          if (!groups.has(key)) groups.set(key, []);
          groups.get(key).push(it);
        }

        // Limpiar y reconstruir
        categoriaEl.innerHTML = "";
        
        const placeholderOpt = document.createElement("option");
        placeholderOpt.value = "";
        placeholderOpt.textContent = "---------";
        categoriaEl.appendChild(placeholderOpt);

        let totalOpciones = 1;

        for (const [g, arr] of groups.entries()) {
          const parent = g !== "__nogroup__" ? document.createElement("optgroup") : null;
          if (parent) parent.label = g;

          for (const it of arr) {
            const opt = document.createElement("option");
            opt.value = String(it.id ?? it.value ?? "");
            opt.textContent = String(it.text ?? it.label ?? it.nombre ?? "");
            
            const ayuda = it.es_ayuda_social ?? it.ayuda ?? it.is_ayuda_social ?? false;
            const comb = it.es_combustible ?? it.combustible ?? it.is_combustible ?? false;
            opt.dataset.ayuda = ayuda ? "1" : "0";
            opt.dataset.combustible = comb ? "1" : "0";

            if (parent) {
              parent.appendChild(opt);
            } else {
              categoriaEl.appendChild(opt);
            }
            
            totalOpciones++;
          }
          
          if (parent) {
            categoriaEl.appendChild(parent);
          }
        }

        console.log(`[Categorías] ${totalOpciones} opciones insertadas en DOM`);
      }

      // ✅ SOLUCIÓN DEFINITIVA: Destruir y recrear Select2
      if (window.jQuery && jQuery.fn?.select2) {
        const $cat = jQuery(categoriaEl);
        
        // Destruir completamente
        if ($cat.data("select2")) {
          try {
            $cat.select2('destroy');
          } catch (e) {
            console.warn('[Select2] Error al destruir:', e);
          }
        }
        
        // Limpiar remnantes del DOM
        $cat.removeClass('select2-hidden-accessible');
        $cat.next('.select2-container').remove();
        
        // Recrear limpiamente
        try {
          $cat.select2({
            width: "100%",
            theme: "bootstrap-5",
            language: "es",
            placeholder: "Seleccionar categoría…",
            allowClear: true,
          });
          
          // ✅ Vincular eventos
          $cat.off('select2:select select2:clear');
          $cat.on('select2:select', function(e) {
            console.log('[Select2] Categoría seleccionada:', e.params.data.id);
            applyCategoriaMode();
          });
          $cat.on('select2:clear', function() {
            console.log('[Select2] Categoría limpiada');
            applyCategoriaMode();
          });
          
        } catch (e) {
          console.error('[Select2] Error al inicializar:', e);
        }
      }

      console.log(`[Categorías] Cargadas ${categoriaEl.options.length - 1} opciones para tipo: ${tipo}`);

    } catch (e) {
      console.error("Error cargando categorías:", e);
      
      if (categoriaMeta) {
        categoriaMeta.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-1"></i>Error: ${e.message}`;
        categoriaMeta.className = "badge bg-danger";
        show(categoriaMeta, true);
      }

    } finally {
      setDisabled(categoriaEl, false);
      show(categoriaLoading, false);
      applyCategoriaMode();
    }
  }

  // ==================== APPLY ALL ====================
  function applyAll() {
    applyTipoMode();
    loadCategorias();
  }

  // ==================== INITIALIZATION ====================
  function bind() {
    // Init Select2 AJAX
    initAjaxSelect2($("#id_beneficiario"), fillPersona);
    initAjaxSelect2($("#id_proveedor"), fillProveedor);
    initAjaxSelect2($("#id_vehiculo"), fillVehiculo);

    // Fallback sin Select2
    const b = $("#id_beneficiario");
    const p = $("#id_proveedor");
    const v = $("#id_vehiculo");
    b && b.addEventListener("change", () => fillPersona({ text: b.selectedOptions?.[0]?.textContent || "" }));
    p && p.addEventListener("change", () => fillProveedor({ text: p.selectedOptions?.[0]?.textContent || "" }));
    v && v.addEventListener("change", () => fillVehiculo({ text: v.selectedOptions?.[0]?.textContent || "" }));

    // Eventos principales
    tipoEl && tipoEl.addEventListener("change", applyAll);
    
    // ✅ CRÍTICO: Evento change nativo también (por si Select2 no dispara el evento)
    categoriaEl && categoriaEl.addEventListener("change", applyCategoriaMode);

    bindDescCounter();

    // Estado inicial
    applyTipoMode();
    
    if (val(tipoEl)) {
      loadCategorias();
    }

    console.log("[MuniFinanzas] movimiento_form.js v" + window.__MF_MOV_FORM_VERSION__ + " ✅");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
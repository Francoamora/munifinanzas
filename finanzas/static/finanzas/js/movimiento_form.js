// static/finanzas/js/movimiento_form.js (v101 - Definitivo)
document.addEventListener("DOMContentLoaded", function() {
    
    // --- REFERENCIAS ---
    const form = document.getElementById("movimientoForm");
    if (!form) return; 

    const tipoEl = document.getElementById("id_tipo");
    // Seleccionamos el campo de categoría (que tiene no-select2)
    const $catEl = $('#id_categoria'); 
    const catLoading = document.getElementById("catLoading");
    const catBadge = document.getElementById("catBadge");
    
    const urlCategorias = form.dataset.categoriasUrl;

    // --- FUNCIÓN PRINCIPAL: CARGAR Y RECONSTRUIR SELECT2 ---
    async function cargarCategorias() {
        const tipo = tipoEl.value;
        
        // 1. SIEMPRE destruimos la instancia previa para evitar duplicados o errores
        if ($catEl.hasClass("select2-hidden-accessible")) {
            $catEl.select2('destroy');
        }
        
        // 2. Limpiamos el HTML del select
        $catEl.empty().append('<option value="">---------</option>');

        // Si no hay tipo seleccionado, inicializamos vacío y salimos
        if (!tipo) {
            $catEl.select2({ theme: 'bootstrap-5', width: '100%', placeholder: 'Seleccionar...' });
            return;
        }

        // 3. UI Loading
        if(catLoading) catLoading.classList.remove("d-none");
        $catEl.prop("disabled", true);

        try {
            // 4. Petición AJAX
            const res = await fetch(`${urlCategorias}?tipo=${encodeURIComponent(tipo)}`);
            const data = await res.json();
            
            // 5. Preparar datos para Select2 (Adapter)
            // Transformamos la respuesta API al formato que Select2 entiende
            const select2Data = [{id: '', text: '---------'}].concat(data.results.map(cat => ({
                id: cat.id,
                text: cat.text,
                // Guardamos los flags en el objeto interno de data
                es_ayuda: cat.es_ayuda_social,
                es_combustible: cat.es_combustible
            })));

            // 6. INICIALIZAR SELECT2 CON DATOS
            $catEl.select2({
                theme: 'bootstrap-5',
                width: '100%',
                placeholder: 'Seleccionar...',
                data: select2Data // <--- Inyección directa de datos
            });

            // 7. Disparar evento para que la UI se actualice (badges, tabs)
            $catEl.trigger('change');

        } catch (e) {
            console.error("Error cargando categorías:", e);
            // Fallback en caso de error
            $catEl.select2({ theme: 'bootstrap-5', width: '100%' });
        } finally {
            if(catLoading) catLoading.classList.add("d-none");
            $catEl.prop("disabled", false);
        }
    }

    // --- LOGICA UI (TABS, BADGES, CAMPOS) ---
    function actualizarUI() {
        const tipo = (tipoEl.value || "").toUpperCase();
        const ingreso = tipo.includes("INGRESO");
        
        // Bloques visibles/ocultos
        const els = {
            persona: document.getElementById("personaCard"),
            assign: document.getElementById("assignCard"),
            ctaOri: document.getElementById("cuentaOrigenWrap"),
            ctaDes: document.getElementById("cuentaDestinoWrap")
        };

        if(els.persona) els.persona.classList.toggle("d-none", ingreso);
        if(els.assign) els.assign.classList.toggle("d-none", ingreso);
        if(els.ctaOri) els.ctaOri.classList.toggle("d-none", ingreso);
        if(els.ctaDes) els.ctaDes.classList.toggle("d-none", !ingreso);

        // Detectar categoría seleccionada (desde Select2 Data)
        const data = $catEl.select2('data')[0];
        
        // La data puede venir de la carga AJAX (propiedades directas) o del HTML renderizado (dataset)
        let esAyuda = data?.es_ayuda === true || data?.element?.dataset?.ayuda === "1";
        let esCombustible = data?.es_combustible === true || data?.element?.dataset?.combustible === "1";

        // Actualizar Badges y Tabs
        if (esAyuda) {
            catBadge.className = "badge bg-danger bg-opacity-10 text-danger border border-danger-subtle ms-2";
            catBadge.innerHTML = '<i class="bi bi-heart-pulse me-1"></i>Ayuda Social';
            catBadge.classList.remove("d-none");
            try { new bootstrap.Tab('#ayuda-tab').show(); } catch(e){}
        } else if (esCombustible) {
            catBadge.className = "badge bg-info bg-opacity-10 text-info border border-info-subtle ms-2";
            catBadge.innerHTML = '<i class="bi bi-fuel-pump me-1"></i>Combustible';
            catBadge.classList.remove("d-none");
            try { new bootstrap.Tab('#vehiculo-tab').show(); } catch(e){}
        } else {
            catBadge.classList.add("d-none");
            if (!ingreso) try { new bootstrap.Tab('#proveedor-tab').show(); } catch(e){}
        }
    }

    // --- EVENT LISTENERS ---
    
    // Al cambiar Tipo -> Cargar datos -> Actualizar UI
    tipoEl.addEventListener("change", function() {
        cargarCategorias().then(() => {
            actualizarUI();
        });
    });

    // Al seleccionar Categoría -> Actualizar UI
    $catEl.on("select2:select", actualizarUI);

    // Inicializar el resto de los Selects (Persona, Proveedor, etc.)
    // Estos SÍ los maneja este script para tener control
    $('#id_beneficiario, #id_proveedor, #id_vehiculo').select2({ 
        theme: 'bootstrap-5', 
        width: '100%' 
    });

    // Rellenar campos readonly de Persona
    $('#id_beneficiario').on('select2:select', function(e) {
        let texto = e.params.data.text;
        let dni = (texto.match(/\(([^)]+)\)/) || ["",""])[1];
        let nombre = texto.replace(/\s*\([^)]+\)\s*/, '').trim();
        
        $("#id_beneficiario_nombre").val(nombre);
        $("#id_beneficiario_dni").val(dni);
    });

    // --- INICIALIZACIÓN ---
    const isEdit = window.MOV_FORM_DATA && window.MOV_FORM_DATA.is_edit;
    
    if (!isEdit && tipoEl.value) {
        // Caso: Nuevo formulario pero con tipo preseleccionado (ej: recarga tras error)
        cargarCategorias();
    } else {
        // Caso: Edición o Formulario vacío
        // Inicializamos Select2 visualmente (vacío o con el valor que trajo Django)
        $catEl.select2({ theme: 'bootstrap-5', width: '100%', placeholder: 'Seleccionar...' });
    }
    
    actualizarUI();
});
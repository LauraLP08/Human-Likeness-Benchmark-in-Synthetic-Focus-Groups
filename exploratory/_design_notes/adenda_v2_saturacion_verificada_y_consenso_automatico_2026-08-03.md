# Adenda a la revisión v2 — verificación de saturación (corrección) y diseño de medición automática de facilidad de consenso

*3 de agosto de 2026. Corrige parcialmente `revision_integral_v2_metodos_complementarios_2026-08-03.md`,
que se basó en un listado del proyecto tomado el 31 de julio. El trabajo del 1–2 de agosto
(`analysis/production_evaluation/final/`, `emergent_calibration_q3/`, `transportability_sample/`) no
estaba en ese listado. Verificación hecha directamente sobre los archivos nuevos.*

---

## 1. Corrección: qué sí está generado desde el 2 de agosto

**Saturación (Nivel 2): generada.** `final/saturation_analysis.json` (02-ago, 23:55 UTC), verificada:

- Operacionalización: **acumulación de cobertura contra el codebook fijo** (11 subtemas), unidad =
  réplica de estudio × condición (una pasada FG1→FG5 por índice canónico), control de orden **exhaustivo
  sobre los 120 ordenamientos**, sin llamadas API ni nueva codificación humana.
- Resultado central: la curva humana llega a **11/11** códigos (media 7.2→11.0); las réplicas enriquecidas
  llegan a **4–7** (media final 5.67) y las solo-demográficas a **4–6** (media 4.67). El repertorio máximo
  condición-completa (15 sesiones) es 9/11 (enriquecida) vs 6/11 (demográfica) — correctamente etiquetado
  como "no es el repertorio de una réplica". Dos códigos (B.3, C.2) no aparecen en **ninguna** de las 30
  sesiones sintéticas. The analysis quantifies lower accumulation of coverage against a fixed a-priori codebook. It does not establish whether the emergence of new themes stabilised.
- Etiquetado honesto (verificado en el propio JSON): EXPLORATORY, post-result; explícitamente **no
  equivalente** a la saturación de códigos de Guest/Hennink (que exige codebook inductivo creciente);
  *meaning saturation* no computada; el criterio de plateau fue retirado de los borradores en la tercera
  ronda de corrección.
- Matiz que sigue en pie de la v2: esta es la variante **deductiva** (techo = 11 códigos). La variante
  Tier-2 (extracción abierta) que el marco §6 describía como sustrato natural de la curva sigue sin
  correrse sobre el corpus completo — la calibración emergente existe solo para Q3 (U01–U07) y la muestra
  S01–S06. Como la propia curva humana ya toca el techo (11/11), la asíntota humana está censurada por el
  codebook; si en algún momento quieres la curva sin techo, la vía es la extracción abierta. No es
  bloqueante, pero sí delimita lo que la versión actual puede sostener: The analysis quantifies lower accumulation of coverage against a fixed a-priori codebook. It does not establish whether the emergence of new themes stabilised. Responder cuándo dejan de aparecer temas nuevos requiere extracción abierta sobre el corpus completo.

**También generado desde el 1–2 de agosto (corrige otros "huecos" de la v2):**

- **Distinción y diversidad léxica + hiper-exactitud**: `final/lexical_analysis.json` con log de
  corrección en dos rondas (`LEVEL2_LEXICAL_CORRECTION_LOG.md` §7–9, offsets de submuestreo corregidos y
  auditados antes/después).
- **Contraste estructural por condición y cercanía al humano**: `FINAL_INTEGRATED_RESULTS_REPORT.md` §2
  — 1.8× palabras en la mitad de turnos, 0% de turnos cortos vs 34.4% humano, Gini 0.07–0.09 vs 0.195,
  profundidad de cadena ~2 vs 12.8, y diferencias entre condiciones pequeñas en comparación (conteos
  "closer to human" 0/5–4/5, correctamente presentados como no concluyentes).
- **Calibración emergente Q3 anclada al humano** (recall 0.682, precisión estricta 0.800 contra 44
  instancias de referencia) + **auditoría cruzada de modelo ciega** (Claude Opus 5, 76 requests) con
  resultado clave: acuerdo exacto con la investigadora 0.667, **auto-contradicción entre repeticiones
  35.7%**, 0 abstenciones → estado `USABLE_FOR_CORROBORATION_ONLY`.
- Chequeo exploratorio de transportabilidad S01–S06, borradores de resultados y discusión, matriz de
  claims con trazabilidad (16 cifras reconciliadas).

Lo que queda vigente de la v2 sin cambios: el caveat de validez del evaluador (human-anchor ausente del
registro congelado), la envolvente formal §K (los conteos "closer to human" del reporte final se le
acercan, pero la síntesis d_HH vs d_SH por métrica no está), la curva D2 (el reporte final §8 confirma
"has a producer but was not run"), los cierres humanos pendientes, y los complementos propuestos
(MTLD/MATTR ya quedó parcialmente cubierto por la diversidad léxica de `lexical_analysis.json`;
Mator-metrics, ConvoKit y distinguibilidad ciega siguen abiertos como opcionales).

---

## 2. Facilidad de consenso humano vs. sintético, sin codificador humano: diseño propuesto

### El problema y el principio de diseño

Las métricas interpretativas (acuerdo/desacuerdo/reto) están WITHHELD hasta el gold standard — decisión
correcta que no hay que revertir. Y la auditoría cruzada del 2-ago acaba de demostrar en tu propio
proyecto por qué un juez LLM solo no es la salida: se auto-contradijo en el 35.7% de los casos repetidos
sin abstenerse nunca. La alternativa confiable sin codificador humano no es "otro juez", sino una
**batería de instrumentos deterministas y transparentes, aplicados idénticamente a ambos lados, cuya
fiabilidad se demuestra por construcción y cuya validez se establece por convergencia entre instrumentos
independientes** — la misma lógica de banda que tu marco ya usa para el evaluador. Se registra como
namespace nuevo (`AUTOMATIC_PROXY_EXPLORATORY`, decisión post-result declarada por la política de
amendments), complementario y nunca sustituto del indicador interpretativo retenido.

### Los tres instrumentos (todos locales, 0 llamadas API)

**I1 — Marcadores léxicos de acuerdo/desacuerdo (diccionario cerrado).** Tu marco §H ya lo prevé como
cross-check. Diccionario fijo y publicado en apéndice: marcadores de desacuerdo ("I disagree", "I'd push
back", "not sure I agree", "but I think", "actually, no"), de acuerdo ("I agree", "exactly", "same here",
"that's true"), y atenuadores. Se **cuentan ocurrencias**, no se clasifica postura (la lección de tu
ablación: el clasificador de complacencia falló clasificando; un conteo de marcadores es auditable línea
por línea). Determinista, repetibilidad = 1.0 por construcción.

**I2 — Inferencia de lenguaje natural (NLI) local.** Un modelo NLI estándar (p. ej. DeBERTa-MNLI, local,
decodificación determinista, versión fijada) sobre cada par (turno de participante, turno de participante
previo al que responde — la adyacencia ya está computada): proporción de contradicción / entailment /
neutral. Es el método automático estándar para detección de (des)acuerdo, sin juez generativo. Para
turnos largos: segmentar en oraciones, agregar al nivel de turno (máximo de contradicción), y reportarlo
— mitiga el sesgo de longitud.

**I3 — Dinámica de convergencia por embeddings.** Con el mismo stack sentence-transformers que ya usa el
pipeline: dispersión semántica entre participantes dentro de cada sección de guía, primera vs. segunda
mitad de la sección. De ahí salen las métricas que responden literalmente "qué tan *fácil* generan
consenso": pendiente de convergencia (cuán rápido colapsa la dispersión), y — combinando con I1/I2 —
latencia al primer desacuerdo (turnos desde la apertura de sección) y **vida media del disenso** (tras un
evento de desacuerdo, cuántos turnos pasan hasta que reaparecen marcadores/entailment de acuerdo o la
dispersión vuelve al nivel previo). Variante comparable con benchmark publicado: la similitud
stance-aware entre respuestas consecutivas de Mator et al. 2025 (su 92% sintético vs. 42% humano es el
análogo directo).

### Métricas resumen propuestas (todas por FG, humano vs. cada condición, n=5 pares)

| Métrica | Instrumento | Lectura "facilidad de consenso" |
|---|---|---|
| Tasa de desacuerdo por acto de respuesta y por 1000 palabras | I1, I2 | Más baja en sintético ⇒ consenso más fácil |
| Índice acuerdo/(acuerdo+desacuerdo) | I1, I2 | Más alto ⇒ consenso más fácil |
| Latencia al primer desacuerdo por sección | I1+I2 | Más larga ⇒ menos fricción inicial |
| Vida media del disenso (turnos hasta retorno a acuerdo) | I1+I2+I3 | Más corta ⇒ el disenso no se sostiene |
| Desacuerdo sostenido (% de eventos seguidos de otro desacuerdo en ≤k turnos) | I1, I2 | Más bajo ⇒ nadie escala el desacuerdo |
| Pendiente de convergencia semántica intra-sección | I3 | Más pronunciada ⇒ colapso más rápido de posiciones |

### Por qué es confiable sin codificador humano

1. **Fiabilidad por construcción.** Los tres instrumentos son deterministas (I1 trivialmente; I2/I3 con
   modelo y versión fijados): el equivalente de tu Gate 1 se satisface exactamente, no estadísticamente.
2. **Validez convergente entre instrumentos independientes.** I1 (léxico), I2 (inferencial) e I3
   (geométrico) miden el constructo por vías distintas. Se reporta el acuerdo entre instrumentos a nivel
   de evento (¿la contradicción NLI coincide con marcador de desacuerdo?) y la conclusión comparativa
   solo se afirma donde los tres coinciden en dirección; donde divergen, se reporta la banda — el espejo
   de tu banda de evaluadores.
3. **Chequeos con etiquetas plata, sin trabajo humano nuevo.** Un set de sanity extraído
   automáticamente: turnos con marcadores inequívocos ("I disagree" explícito) deben salir como
   desacuerdo en I2; el corpus de ablación C2/C3 (validación mutua conocida: 0.54–0.63 vs 0.03–0.19
   humano) debe salir con acuerdo alto; el ejemplo ya validado cualitativamente de fg2_run02 turno 48
   (desacuerdo preservado sin resolución) debe registrar disenso sostenido.
4. **Simetría del instrumento.** El mismo instrumento, con los mismos parámetros, sobre ambos lados en
   formato ciego: cualquier sesgo compartido se cancela en la comparación — el mismo argumento que
   sostiene tu Δ entre condiciones. La amenaza real es el sesgo *diferencial* por longitud (turnos
   sintéticos ~4×): se mitiga normalizando por acto y por 1000 palabras (reportando ambas), agregando
   NLI a nivel de oración→turno, y con un chequeo de sensibilidad recortando los turnos sintéticos a
   prefijos de longitud humana (la lógica D2 aplicada aquí).
5. **Ancla humana diferida a costo cero.** El gold standard de dos codificadoras que ya está en campo
   incluye el eje acuerdo/desacuerdo: cuando vuelva, valida los proxies contra codificación humana sin
   ninguna tarea humana adicional a las ya comprometidas. Hasta entonces, los proxies se reportan como
   exploratorios con sus credenciales de convergencia.
6. **Si se quiere un cuarto instrumento LLM**, solo como corroboración con consenso multi-corrida (≥3/5)
   y nunca como árbitro — exactamente el estatus `USABLE_FOR_CORROBORATION_ONLY` que tu propia auditoría
   cruzada acaba de establecer.

### Costo estimado y encaje

Un día de implementación realista (I1 unas horas; I2 pip install + inferencia local sobre ~2,300 actos de
respuesta; I3 reutiliza embeddings del pipeline), 0 llamadas API, y produce la respuesta comparativa a
"¿generan consenso con más facilidad que los humanos?" con n=5 pares, presentación descriptiva idéntica a
la del resto del marco (sin tests, réplicas nunca independientes). Literatura de apoyo ya en el Project:
Mator et al. (agreement stance-aware), Yao et al. (sycophancy en debate multi-agente), Novelli et al.
(supresión de disenso como modo de fallo documentado); externa: ConvoKit para coordinación lingüística si
se quiere extender a acomodación de estilo.

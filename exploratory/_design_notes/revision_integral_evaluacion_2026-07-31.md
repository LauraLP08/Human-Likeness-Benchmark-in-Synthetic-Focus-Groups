# Revisión integral del proyecto y de la evaluación en curso — 31 de julio de 2026

*Revisión de solo-lectura solicitada por Laura. Fuentes: el capítulo de metodología redactado
(`Dissertation_Synth FG_Methodologyjtd.docx`), los 12 documentos del Project, y el estado real de
`my_qualitative_project` — en particular `analysis/production_evaluation/`
(`frozen_evaluation_spec.md`, `PRE_EVALUATION_GATE_REPORT.md`, `STATISTICAL_ANALYSIS_PLAN.md`,
`STATISTICAL_PHASE_COMPLETION_REPORT.md`, `metric_registry.csv`, `results/`, auditorías de
contaminación y de ventana comparable). Ningún archivo fue editado.*

---

## 1. Estado real a 31 de julio (los docs del Project del 29–30 quedaron atrás)

Entre el 30 y el 31 de julio se cerró casi todo lo que los documentos del 29 marcaban como bloqueante:

- **Evaluador temático: decidido y congelado.** `gemini-3.5-flash`, configuración efectiva registrada
  con hashes y cache keys, guard que rehúsa correr con otro modelo. La base citada es la comparación
  de gates del 18-jul (2.5-flash descalificado por Gate 1).
- **Aislamiento del codebook: verificado.** `condition_manipulation_audit.md` §7 — ninguna
  contaminación detectada bajo los tests especificados; dos fuentes de falsos positivos encontradas y
  eliminadas. También quedó auditada la manipulación de condición (qué difiere renderizado al modelo,
  paridad de parámetros, sin confusión de modelo).
- **Ventana comparable congelada** (`anchor_and_extend_v1`, del ask de Q1 al fin de la última sección
  sustantiva; 86% del texto incluido; 335 checks de verificación, 30/30 AUTO_TRIMMED).
- **Corpus 35/35 evaluado por Batch** (5 humanos + 30 sintéticos, 3 réplicas canónicas por celda;
  FG4/FG5 con excepciones de nombre archivales documentadas; 1 intento en cuarentena reemplazado).
- **Tier 1 completo y agregado**: 10 tablas de resultados, efectos primarios por FG, plan estadístico
  con honestidad temporal ejemplar (declara qué se decidió antes y después de ver resultados; sign
  test explícitamente exploratorio con su techo de p; dos amendments de aritmética a precisión
  completa, auditados con racionales exactos).

Resultado descriptivo principal: el enriquecimiento **favorece recall en 4/5 grupos** (Δ medio
+0.121), precisión mixta (2E/1D/2 empates), reach 4/5 pero con confound conocido (asimetría de
silencios forzados 2.44% vs 0.04%), y **FG4-solo-demográficos con solapamiento cero a nivel de
subtema** (pero recall 0.25–0.50 a nivel de tema padre con precisión 1.00 — el cero es específico de
la granularidad).

Pendientes que solo un humano puede cerrar (listados en el completion report §10): veredicto
`FG4-DEMO-R01-A1`, adjudicación del clustering U01–U07, centralidad P034/P040 (Coder B), decisión
sobre las ~300 llamadas length-matched, y si se piden más unidades codificadas.

---

## 2. Hallazgo principal de esta revisión: la validez del evaluador quedó fuera del registro congelado

La especificación congelada justifica `gemini-3.5-flash` **solo** con los gates del 18-jul. Pero el
human-anchor del 21-jul (`human_anchor_results.json`, analizado en la adenda del 29-jul) mostró que
3.5-flash **replica en dos transcripciones sintéticas distintas un déficit de recall de ~1/3 de los
temas realmente presentes** (0.667 en synth FG1 y FG5), mientras 2.5-flash nunca perdió un tema real
(su defecto era exclusivamente sobre-marcado). Elegir 3.5 era una de las dos vías defendibles que la
adenda dejó planteadas — la vía (a) — pero esa vía incluía *documentar el patrón de recall como
limitación conocida del instrumento*, y esa mitad no aparece en `frozen_evaluation_spec.md` ni en el
plan estadístico ni en el completion report.

Consecuencias concretas que conviene dejar escritas antes de interpretar:

1. **Los niveles absolutos de recall del lado sintético están probablemente sesgados a la baja** por
   conservadurismo del instrumento — una brecha de recall vs. humano no es atribuible solo al
   generador.
2. **La comparación entre condiciones es mucho más robusta que los niveles absolutos**: ambas
   condiciones se midieron con el mismo instrumento, mismo prompt, misma ventana. El Δ
   enriquecido−demográficos es la cifra defendible; los valores absolutos llevan el caveat.
3. **El cero de FG4-demoonly hereda el caveat**: con un instrumento que pierde ~1/3 de temas
   presentes, un `synthetic_present_n` de 1–2 códigos por corrida es compatible con cierto
   sub-marcado además de la divergencia real de subtemas. No invalida el hallazgo (el patrón
   tema-padre vs. subtema es real), pero la inspección cualitativa ya prevista debe leerse con esto.
4. **Discrepancia texto↔implementación**: `evaluation_framework.md` §4 promete "se corren ambos
   evaluadores y se reporta el rango entre ellos como banda de incertidumbre". La producción es
   mono-evaluador. Hay que actualizar el texto metodológico (o, si se quiere conservar la banda, una
   sensibilidad barata y acotada: re-codificar con 2.5-flash×5-consenso solo FG4-demoonly y una celda
   de control, ~15–25 llamadas — opcional, no bloqueante).

---

## 3. Brechas entre la metodología redactada (docx) y lo efectivamente implementado

El docx está bien escrito y es honesto; estas son las divergencias que en una defensa conviene tener
resueltas de antemano (todas son de redacción, no de re-trabajo):

| Tema | El docx dice | Lo implementado |
|---|---|---|
| Evaluador | "evaluator LLM (Gemini)" + 3 checks | Modelo único congelado `gemini-3.5-flash`; el criterio de validez human-anchor existió y pesó; sin banda dual prometida por el marco |
| Ventana de comparación | No se menciona | Ventana comparable Q1→última sección sustantiva; 14% del texto sintético excluido (intro/cierre); humanos ya empiezan en Q1 |
| Unidad de análisis | "comparison always at group level" | Formalizado más fuerte: n=5 pares; réplicas = variabilidad del generador, nunca 15 observaciones independientes; sin concatenación. Vale la pena decirlo en el capítulo |
| Nivel 2 (saturación) | Nivel completo del marco | **No corrido**: requiere Tier-2 (extracción abierta) sobre el corpus, hoy clasificado exploratorio y sin ejecutar |
| Nivel 3 interpretativo | "LLM + human validation" | **WITHHELD** hasta que vuelva el gold standard de dos codificadoras (en campo); sin reporte provisional |
| Nivel 4 distinción léxica | Solapamiento Jaccard (Apéndice) | `collapse_metric.py` implementa TF-IDF + coseno de centroides; y la comparación sintético-vs-humano de los 5 grupos **no está en el registro congelado ni en los resultados** |
| Tier 2b (por pregunta) | — (posterior al docx) | **Retirado** como evidencia de fidelidad (control cruzado 29-jul); listas por sección solo descriptivas |
| Nivel 5 relacional | — | **D7: diferido a trabajo futuro**, con gate conceptual escrito; refuerzo del audit: el prompt enriquecido renderiza los nombres de constructo, así que sería "conditioning preservado", no predicción |
| FG3 | No se menciona | Vínculo persona↔fila de encuesta aleatorio → `GROUP_LEVEL_ONLY_RANDOM_LINKAGE`; debe declararse en métodos |
| Silencios forzados | No se menciona | Asimetría de condición 2.44% vs 0.04% — limitación del corpus, confound sobre reach |
| Corridas | "three times each" | Correcto, pero con índices canónicos y 2 corridas archivadas (FG4 run02, FG5 run02) — referenciar el manifiesto canónico en apéndice |

---

## 4. Recomendaciones priorizadas (calidad ÷ tiempo)

**Bloque A — horas, y desbloquean interpretación (solo tú puedes hacerlas):**
1. Veredicto humano de `FG4-DEMO-R01-A1` (un juicio de codificación, con las 3 citas ya extraídas).
2. Adjudicación del clustering U01–U07 (la guía `CLUSTERING_GUIDE.md` está lista; sin esto no hay
   estadístico de acuerdo ni lectura de saturación del review parcial).
3. Centralidad P034/P040 (Coder B).

**Bloque B — baratos en cómputo, alto valor, sin llamadas API o con muy pocas:**
4. Registrar formalmente (amendment al frozen spec o nota del mismo rango) el caveat de validez del
   evaluador (§2 de este doc) — es redacción, no código, y protege el resultado principal.
5. Correr `collapse_metric.py` sintético-vs-humano en los 5 grupos y **entre condiciones** — 0
   llamadas API, cierra el indicador comparativo central del Nivel 4, y es la mitad "empeora" de la
   historia mixta del enriquecimiento (hipótesis a priori ya escrita el 29-jul).
6. Correr `d2_length_diagnostics.py` — está escrito y testeado, solo esperaba resultados Tier-1, que
   ya existen. Cierra la pregunta de si el largo (ratio 0.82–5.19×, mediana 2.08×) explica las
   diferencias aparentes.
7. Alinear el capítulo de metodología con lo implementado (tabla §3) y corregir Apéndice J.

**Bloque C — decisión de alcance (moderado costo, decidir ya para no decidirlo con prisa):**
8. **Nivel 2 / Tier-2 emergente**: o se corre la extracción abierta sobre las 35 ventanas (misma
   infraestructura Batch, ~35 llamadas + emparejamiento) para producir las curvas de saturación que
   el capítulo promete, o se re-alcanza el capítulo explicando por qué queda fuera (el resultado
   negativo de Tier 2b da una razón de prudencia sobre el *emparejamiento* de temas abiertos, pero
   las curvas de saturación son conteos acumulados, no emparejamiento — siguen siendo viables).
   Recomendación: correrlo; es la brecha más visible entre el texto y los datos.
9. **Interpretativo**: mantener WITHHELD hasta que vuelvan las dos codificadoras. No atajar el gold
   standard — la tesis se sostiene con Tier 1 + estructural + integración cualitativa.

**Bloque D — recomendar declinar o mantener diferido (y decirlo explícitamente en la tesis):**
10. Las ~300 llamadas length-matched: declinar; el proxy D2 + curva de cobertura + limitación
    explícita es suficiente para una tesis (ya está redactado como estimando distinto).
11. Nivel 5 atributo-actitud: mantener D7 (diferido), pero conservar en el texto la distinción
    terminológica *fidelidad algorítmica (relacional)* vs. *fidelidad distribucional/de contenido* y
    no reclamar la primera — el gate conceptual queda como estándar para trabajo futuro.
12. No añadir modelos mixtos ni CIs sobre n=15: la postura del plan congelado es correcta; añadirlos
    ahora sería post-hoc y trataría réplicas como datos independientes.

**Bloque E — mantenimiento (cuando haya un hueco):**
13. Actualizar `estado_evaluacion_grupos_focales_2026-07-29.md` y el *methodology package* — ambos
    quedaron desactualizados frente al 30–31 de julio (p. ej., el estado dice "FG3: 0 corridas").
14. La homogeneización de *registro retórico* (patrón "Yeah… but I think… [ejemplo]") detectada el
    29-jul sigue sin entrada propia — vale como observación cualitativa del Nivel 4 en la discusión.

---

## 5. Lo que está bien y conviene no tocar

La honestidad temporal del plan estadístico (a priori vs. post-result), el techo explícito del sign
test, la negativa a un puntaje compuesto, la retención de réplicas junto a sus medias, las cuarentenas
y la trazabilidad por cache key, la inclusión de FG4 con sensibilidad no-justificada-como-exclusión, y
el tratamiento del confound de reach son, en conjunto, de un estándar superior al de la mayoría de la
literatura citada en el propio Project. El riesgo de la fase que viene no es de rigor sino de
*alcance*: cerrar los juicios humanos pendientes y alinear el texto con lo implementado vale más que
añadir métricas nuevas.

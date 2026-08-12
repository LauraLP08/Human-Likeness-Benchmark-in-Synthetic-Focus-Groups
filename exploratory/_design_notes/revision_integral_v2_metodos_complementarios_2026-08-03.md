# Revisión integral v2 — métodos complementarios de human-likeness / NLP-QDA y auditoría del análisis de resultados

*3 de agosto de 2026. Segunda revisión de solo-lectura, solicitada por Laura. Complementa (no reemplaza)
la revisión del 31-jul (`revision_integral_evaluacion_2026-07-31.md`). Fuentes: la metodología redactada,
el marco de evaluación integrado, los resultados de producción en `analysis/production_evaluation/`
(incluida la inspección directa de `structural_interaction_metrics_long.csv`, `condition_comparison.csv`
y los reportes de cierre), la literatura del propio Project (PICON, PersonaGym, Mator, Zhang, Novelli,
Ye, Tissaoui, Chen) y una búsqueda dirigida de literatura y paquetes externos.*

---

## Parte 1 — ¿Es un buen análisis de resultados?

### Veredicto corto

**Como análisis del efecto del enriquecimiento (Pregunta 2), es muy bueno — rigor por encima del estándar
del campo.** La separación a-priori/post-result, el techo explícito del sign test (imposibilidad
aritmética de p<.05 declarada en vez de escondida), la unidad de análisis correcta (5 pares; réplicas =
variabilidad del generador, jamás 15 observaciones independientes), los amendments auditados con
aritmética racional exacta, la cuarentena y la trazabilidad por cache key: nada de esto es habitual ni
siquiera en los papers publicados del Project.

**Como análisis de human-likeness (Pregunta 1), está incompleto — no por diseño sino por ejecución
pendiente.** Los datos crudos ya existen; faltan las síntesis que el propio marco promete:

1. **La envolvente humano-humano (marco §K) no se ha computado.** `structural_interaction_metrics_long.csv`
   ya contiene las 95 filas humanas (5 FG × 19 métricas) y las 570 sintéticas, pero no existe la síntesis
   d_HH vs. d_SH ("¿cae lo sintético dentro del rango de variación natural entre grupos humanos?").
   Esa envolvente es la respuesta formal del marco a la limitación n=1 y es el corazón de la Pregunta 1.
   Es aritmética pura sobre una tabla que ya está en disco.
2. **No hay contraste estructural por condición.** `condition_comparison.csv` solo cubre las métricas
   Tier-1. La tabla de hipótesis a priori (29-jul) predice "sin diferencia esperada" en lo estructural
   entre condiciones — es una predicción falsable y barata de verificar con la misma tabla larga; si se
   confirma, refuerza la historia del efecto mixto ("el enriquecimiento mueve contenido, no forma").
3. **Nivel 2 (saturación) sigue sin producirse** (depende del Tier-2 emergente, hoy exploratorio y sin
   correr) y **la distinción léxica del Nivel 4 sigue fuera del registro y de los resultados**.
4. **No existe todavía capa de presentación**: todo son tablas CSV. Para el capítulo de resultados hacen
   falta las visualizaciones distribucionales que el marco implica (banda humana + puntos sintéticos por
   métrica y grupo; efectos pareados por FG). Es trabajo de horas y multiplica la legibilidad de lo que
   ya está calculado.

En síntesis: el andamiaje inferencial y de procedencia es excelente y no hay que tocarlo; lo que falta es
**cobertura** (completar las síntesis prometidas para la Pregunta 1) y **comunicación** (figuras). El
riesgo de "mal análisis" aquí no es sobre-interpretar, sino entregar un capítulo que responde con
solidez la mitad de las preguntas.

### Dos matices de lectura para el capítulo

- El resultado direccional Tier-1 (recall 4/5 a favor del enriquecido, Δ medio +0.121) se lee mejor junto
  a la sensibilidad de longitud (ratio 0.82–5.19×, mediana 2.08×; curva D2 pendiente de correr — el
  script existe y ya tiene su insumo) y junto al caveat de validez del evaluador (v1 §2): el Δ entre
  condiciones es la cifra robusta; los niveles absolutos llevan caveat.
- FG4 es la mejor viñeta cualitativa del corpus (cero solapamiento en subtema, recall 0.25–0.50 en tema
  padre): muestra que la granularidad de codificación puede invertir la lectura — ideal para la
  integración cuali-cuanti prevista en el plan §9.

---

## Parte 2 — Métodos de human-likeness que se pueden integrar (mapeados a tu marco)

Criterio de selección: solo métodos que (a) cubren un hueco real del marco, (b) no requieren llamadas
API o requieren muy pocas, y (c) tienen anclaje citable — idealmente en literatura que ya está en tu
Project. Ordenados por relación valor/tiempo.

### 2.1 Métricas comparables con Mator et al. (2025) — benchmark externo directo *(ya en tu Project)*

Mator et al. evaluaron su grupo focal sintético con cuatro métricas automáticas basadas en
BERTScore/embeddings: relevancia de respuesta a la pregunta del moderador, similitud de respuestas
entre participantes, "agreement" por similitud stance-aware entre respuestas consecutivas, y
distribución conversacional. Computar esas mismas métricas sobre tu corpus (sentence-transformers local,
sin API — el patrón ya existe en `thematic_coding.py`) te da algo que hoy no tienes: **comparabilidad
directa con un benchmark publicado de grupos focales sintéticos**. Su hallazgo (agreement 92% sintético
vs. 42% humano) es además el análogo publicado de tu hallazgo de sobre-validación mutua — poder decir
"nuestro corpus replica/matiza el patrón de Mator et al. con estas cifras" es un párrafo fuerte de
discusión. **Costo: bajo (script local). Encaje: Nivel 3 interpretativo (proxy automático) + discusión.**

Advertencia: son *proxies automáticos secundarios*; no sustituyen las métricas interpretativas retenidas
(WITHHELD) a la espera del gold standard — se reportan como capa exploratoria, igual que el cross-check
léxico que el marco §H ya prevé.

### 2.2 Test de distinguibilidad ciego (tradición Turing / believability)

El estándar más directo de human-likeness en la literatura de diálogo es preguntar si un juez ciego
puede distinguir lo sintético de lo humano. Versión barata y defendible para una tesis: extractos
emparejados (misma pregunta de guía, lado humano vs. sintético, formato ciego que ya tienes), 2–3
evaluadores humanos que clasifican "humano/sintético" + confianza; se reporta exactitud vs. azar. Con
tu corpus (5+30) puede montarse en un día usando la infraestructura de unidades ciegas del gold standard
(los U01–U15 ya demuestran el mecanismo de sellado). Complemento automático opcional: un clasificador
simple (regresión logística sobre TF-IDF o embeddings, leave-one-FG-out) reportado como AUC descriptivo
— con n pequeño, solo como triangulación, nunca como test. **Costo: medio (tiempo humano). Encaje:
respuesta global a la Pregunta 1, complementaria a la envolvente.** Nota honesta: con las brechas
estructurales ya medidas (turnos 4× más largos), la distinguibilidad probablemente sea alta — el valor
está en *documentarlo* y en qué señales usan los jueces (pregúntales), no en esperar indistinguibilidad.

### 2.3 Alineación/coordinación lingüística entre hablantes (entrainment)

Tu validación cualitativa del 29-jul detectó una homogeneización de *registro retórico* ("Yeah… but I
think… [ejemplo reflexivo]") que ningún indicador actual captura — el Jaccard/TF-IDF mide vocabulario,
no acomodación conversacional. La literatura reciente sobre simulación de conversación hablada (Mayor,
*Cognitive Science* 2025) encuentra precisamente que los LLMs exageran la alineación entre
interlocutores respecto a humanos; y **ConvoKit** (Cornell) trae implementado el transformer de
*Coordination* (coordinación de palabras funcionales entre hablantes, estilo LIWC) listo para aplicar a
transcripciones propias. Computar coordinación media entre participantes, humano vs. sintético vs.
condición, convertiría tu observación cualitativa en un indicador formal del Nivel 4 con anclaje
bibliográfico doble. **Costo: bajo-medio (pip install convokit; formatear el corpus al esquema
speaker/utterance). Encaje: Nivel 4, nueva entrada "homogeneización de registro/acomodación".**

### 2.4 Consistencia de persona por interrogación (PICON / PersonaGym) — dejar como trabajo futuro

PICON (en tu Project) es hoy el estándar para consistencia de persona multi-turno (interna/externa/
retest, con referencia humana), y PersonaGym para evaluación de agentes-persona en tareas. Ambos exigen
*nuevas interacciones* con los agentes (interrogatorio de 50 turnos por persona), es decir, generación
adicional fuera de las sesiones — caro y fuera del alcance temporal. Lo correcto para la tesis:
citarlos en limitaciones/trabajo futuro, señalando que tu "consistencia de perfil" evalúa consistencia
*en sesión* (lo que importa para un grupo focal) y que la interrogación fuera de sesión queda abierta.
**Costo de integrarlo ahora: alto. Recomendación: no integrar; posicionar.**

---

## Parte 3 — Paquetes NLP/QDA que complementan sin llamadas API

### 3.1 Índices estándar de diversidad léxica — `lexical-diversity` (MTLD, MATTR, HD-D)

Tu métrica de colapso de voces (TF-IDF + coseno de centroides) es defendible pero ad-hoc, y su propia
docstring declara la limitación. Añadir por hablante los índices estándar de la psicolingüística
(MTLD, MATTR, HD-D — robustos a diferencias de longitud de texto, que es exactamente tu problema con
turnos 4× más largos) da un segundo método independiente, citable (McCarthy & Jarvis) y trivial de
correr (`pip install lexical-diversity`, minutos de cómputo). Reportar: distribución por hablante,
humano vs. sintético vs. condición. **Encaje: Nivel 4, junto al collapse metric — que además sigue
pendiente de correrse contra el humano en los 5 grupos.**

### 3.2 BERTopic como triangulación del Nivel 2 (saturación) y del Tier-2

Existe ya un framework reproducible publicado para topic modeling neuronal específicamente en análisis
de grupos focales, y revisiones 2025 sobre validación de topic models en investigación cualitativa.
BERTopic corre local (embeddings + clustering, sin API) sobre las 35 ventanas y produce: (a) curvas de
acumulación de tópicos entre grupos y entre corridas — la pieza del **Nivel 2 que hoy no existe**, por
una vía independiente del evaluador LLM; (b) solapamiento descriptivo de tópicos humano/sintético como
triangulación del Tier-1. Dos cautelas: la lección de Tier 2b aplica — a esta granularidad el tópico
sigue la pregunta de guía, no la identidad del grupo, así que se usa para *saturación y descripción*,
no como cifra de fidelidad; y con 35 documentos cortos conviene trabajar a nivel de turno/sección, no
de transcripción entera. **Costo: medio (un día realista). Alternativa más barata para cerrar Nivel 2:
correr el Tier-2 LLM ya diseñado (~35 llamadas Batch) — las dos vías son complementarias; si solo hay
tiempo para una, el Tier-2 LLM es más coherente con el marco.**

### 3.3 Proxy NER de especificidad — ya especificado en tu marco, ejecutable hoy

El marco §H define el proxy estructural de especificidad (turnos con ≥1 entidad/número/expresión
temporal vía NER, p. ej. spaCy) como la mitad automática del indicador interpretativo. Como lo
interpretativo está WITHHELD hasta el gold standard, correr el proxy NER ahora te da una lectura
preliminar de especificidad **sin violar el WITHHELD** (es estructural, no juicio del LLM) y deja la
comparación lista para cuando vuelvan las codificadoras. **Costo: bajo. Encaje: Nivel 3.**

### 3.4 Léxicos psicolingüísticos (LIWC-22 / Empath) — opcional

LIWC-22 es el estándar en los papers de deseabilidad social que ya citas (Salecha), pero es de pago.
Empath (open source, correlación reportada ~0.90 con LIWC en categorías compartidas) permite perfiles
de categorías (afecto, social, cognición) por hablante y lado. Aporta color descriptivo al Nivel 4,
pero solapa parcialmente con lo que ya mides; solo si sobra tiempo. **Costo: bajo. Prioridad: baja.**

### 3.5 Lo que no conviene añadir

Dialogue-act tagging completo, modelos de mixed-effects, CIs sobre n=15, LLM-as-judge adicional para
"human-likeness score" global: o duplican lo que el marco ya cubre mejor, o contradicen decisiones
congeladas correctas (no puntaje único, no inferencia imposible). La fortaleza de tu evaluación es que
cada indicador tiene un porqué anclado en una divergencia documentada; añadir métricas por
disponibilidad del paquete diluiría eso.

---

## Parte 4 — Plan priorizado (calidad ÷ tiempo)

**A. Completar el análisis de resultados existente (antes que cualquier método nuevo):**
1. Síntesis de envolvente §K sobre `structural_interaction_metrics_long.csv` (aritmética pura, ya hay
   datos humanos y sintéticos) + tabla estructural por condición (verifica la predicción a priori "sin
   diferencia esperada").
2. Correr `collapse_metric.py` vs. humano y entre condiciones, y `d2_length_diagnostics.py` (ambos
   listos, 0 llamadas).
3. Figuras del capítulo: banda humana + puntos sintéticos por métrica; efectos pareados por FG.
4. Los cierres humanos pendientes de la v1 (FG4-DEMO-R01-A1, clustering U01–U07, P034/P040) y el
   registro del caveat del evaluador.

**B. Complementos nuevos de mejor relación valor/tiempo (1–2 días en total):**
5. Índices MTLD/MATTR/HD-D por hablante (§3.1).
6. Métricas comparables con Mator et al. (§2.1) — te da benchmark externo publicado.
7. Proxy NER de especificidad (§3.3).
8. Decisión del Nivel 2: Tier-2 LLM (~35 llamadas) y/o BERTopic local (§3.2).

**C. Si queda margen:**
9. Coordinación lingüística con ConvoKit (§2.3) — formaliza el hallazgo de registro retórico.
10. Test de distinguibilidad ciego con 2–3 jueces (§2.2).

**D. Trabajo futuro (posicionar, no ejecutar):** PICON/PersonaGym (§2.4), Nivel 5 relacional (D7),
LIWC-22, length-matched (~300 llamadas).

---

## Referencias externas usadas en esta revisión

- ConvoKit (Cornell NLP): https://github.com/CornellNLP/ConvoKit — transformers de Coordination,
  politeness, estructura conversacional.
- `lexical-diversity` (PyPI): https://pypi.org/project/lexical-diversity/ — MTLD, MATTR, HD-D.
- Empath: https://github.com/Ejhfast/empath-client — categorías léxicas open source tipo LIWC.
- Mayor (2025), *Can Large Language Models Simulate Spoken Human Conversations?*, Cognitive Science:
  https://onlinelibrary.wiley.com/doi/10.1111/cogs.70106 — divergencias de alineación/estructura de
  turnos entre conversación LLM y humana.
- *A Reproducible Framework for Neural Topic Modeling in Focus Group Analysis*:
  https://arxiv.org/abs/2511.18843 — pipeline BERTopic para grupos focales.
- *From Transformers Come Themes: Evaluating BERTopic for Qualitative Analysis* (2025):
  https://dl.acm.org/doi/10.1145/3786995.3786997.
- Del Project: Mator et al. 2025 (métricas BERTScore de FG sintéticos); Zhang et al. 2024 (solapamiento
  de códigos y repetición entre iteraciones); Kim et al., PICON; Samuel et al., PersonaGym; Ye et al.
  2026 (psicometría LLM); Novelli et al. 2026 (replicabilidad procedimental/analítica).

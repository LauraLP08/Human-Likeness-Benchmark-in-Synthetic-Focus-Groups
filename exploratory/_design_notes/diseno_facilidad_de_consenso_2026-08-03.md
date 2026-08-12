# Diseño de medición: "facilidad de consenso" humano vs. sintético

*3 de agosto de 2026. Desarrolla y corrige el §2 de `adenda_v2_saturacion_verificada_y_consenso_automatico_2026-08-03.md`.
Todas las cifras de corpus de este documento están verificadas directamente sobre los archivos (no citadas de reportes).
Cero llamadas a API de pago. Namespace propuesto: `CONSENSUS_DYNAMICS_EXPLORATORY`.*

---

## 1. Qué añade este diseño sobre la adenda

La adenda propuso tres instrumentos (léxico, NLI, embeddings) y una tabla de seis métricas de tasa.
Ese esqueleto es correcto pero tiene tres huecos que lo harían frágil en defensa:

1. **Mide tasas, no facilidad.** Una tasa baja de desacuerdo puede significar "consenso fácil" o
   "nunca hubo oportunidad de disentir". Son cosas distintas y el corpus, medido, muestra que la
   segunda amenaza es real (§3).
2. **El argumento de simetría del instrumento no se sostiene tal cual.** La adenda argumenta que
   "el mismo instrumento sobre ambos lados cancela el sesgo". Eso vale para sesgo *compartido*.
   El sesgo aquí es **diferencial**: el registro humano ("nah", "yeah but", "I dunno") y el sintético
   ("I agree with Amir, though I'd add...") no activan el mismo diccionario. La simetría del
   instrumento no cancela un sesgo que depende del lado.
3. **No dice cuánta validación humana, ni cómo convertirla en rigor.** "Una muestra" no es un diseño.

Lo que sigue reemplaza la tabla de tasas por un **modelo de eventos con censura** (§4), añade dos
detectores que la adenda no tenía y que atacan directamente el constructo (§5), y define una
validación humana de **~240 unidades / ~4 horas-persona** que no solo estima el error del detector
sino que **corrige la métrica final** (§7).

---

## 2. El constructo: "fácil" no es "poco desacuerdo"

"Qué tan fácil llegan a consenso" se descompone en cinco cosas medibles y separables:

| Sub-constructo | Pregunta | Se mide como |
|---|---|---|
| **C1 Fricción** | ¿Aparece desacuerdo? | Riesgo de primera divergencia por sección |
| **C2 Persistencia** | Cuando aparece, ¿sobrevive? | Turnos hasta el realineamiento (supervivencia) |
| **C3 Velocidad** | ¿Qué tan rápido colapsan las posiciones? | Pendiente de dispersión semántica intra-sección |
| **C4 Quién cede** | ¿El consenso es negociado o por eco? | Anclaje al primer hablante; asimetría del movimiento |
| **C5 Cierre** | ¿La sección termina alineada? | Separación de posiciones en el último tercio |

C4 es el que convierte esto en un hallazgo interesante en vez de una tasa más. "Consenso fácil"
tiene dos firmas muy distintas: *negociación rápida* (varios se mueven y se encuentran en el medio)
y *eco* (todos convergen sobre quien habló primero). La literatura del propio Project
(Mator, Yao, Novelli) predice la segunda para lo sintético, y hoy no tienes ningún indicador que
las distinga.

**Decisión de diseño: no se construye un índice compuesto.** Contradiría la decisión congelada de
"no puntaje único" (revisión v2 §3.5). Se reporta un perfil de 5–6 métricas con dirección declarada
a priori.

---

## 3. Unidad de análisis, denominadores y el problema del reloj

Cifras verificadas sobre el corpus (lado humano: `data/datasets_transcripts/standardized/macho_meals/fg*/transcript.json`;
lado sintético: las 30 `comparable_transcripts/*/comparable_transcript.json`):

| | Humano (5 FG) | Sintético (30 sesiones) | Razón por sesión |
|---|---|---|---|
| Turnos de participante | 346 (58/28/98/39/123) | 984 | 0.48× |
| Palabras de participante | 22,952 | 228,040 | **1.66×** |
| Mediana de palabras/turno | 22–89.5 | 216–281 | ~4–5× |
| **Actos de respuesta (P→P)** | **319** (52/23/92/34/118) | **493** | **0.26×** |
| Turnos de moderador | 5–6 por grupo | 16.5 por sesión | 3× |

**El acto de respuesta (P→P) es la unidad base**: un turno de participante cuyo turno anterior
también es de participante. Es la única unidad donde "responder a alguien" está definido sin
suposiciones, y ya es la base de `participant_participant_adjacency` en el pipeline.

Aquí está el hallazgo que reorienta todo el diseño: **lo sintético tiene 16.4 actos de respuesta por
sesión frente a 63.8 del humano — una cuarta parte de las oportunidades de disentir, en 1.66× de
palabras.** Esto significa que:

- Una tasa "por 1000 palabras" hará que lo sintético parezca consensual por construcción.
- Una tasa "por acto" corrige eso pero sobre un denominador cuatro veces menor (más ruido).
- El moderador sintético interviene 3× más, y cada intervención **reinicia el piso conversacional**:
  parte de la baja fricción sintética puede ser del moderador, no de los participantes.

**Regla de reporte (obligatoria): tres relojes, siempre los tres.** Turnos, palabras (por 1000) y
actos de respuesta. Una conclusión direccional solo se afirma si sobrevive en los tres. Donde no
sobreviva, se reporta la banda — el mismo criterio que ya usas para la banda de evaluadores.

**Estratificación obligatoria por `selection_mode`.** El corpus sintético tiene 828 turnos
`voluntary` y 156 `moderator_direct_address`. Un turno de dirección forzada no es uptake espontáneo;
mezclarlos infla artificialmente la respuesta. **Primario: solo actos `voluntary`. Sensibilidad:
todos.** El lado humano no tiene la etiqueta, así que se reporta como limitación asimétrica conocida
(y es conservadora: penaliza al sintético en la dirección de *más* participación espontánea).

**Sección = pregunta de guía.** Humano: los 5 marcadores `Question N.` en los turnos de moderador
(verificado: 5/5/5/5/4 marcadores). Sintético: `moderator_log.section_transition`, ya usado por
`build_comparable_window.py`. Es un join de una tarde, no una re-codificación.

---

## 4. La propuesta central: consenso como proceso con censura

En vez de contar desacuerdos, se modelan **dos tiempos de espera**:

**Evento A — primera divergencia.** Desde la apertura de una sección, ¿cuántos actos de respuesta
transcurren hasta el primer evento de divergencia? Si la sección termina sin ninguno, la observación
está **censurada a la derecha** (no es un cero: es "no ocurrió dentro de la ventana observada").
Esto resuelve limpiamente el problema del denominador: una sección sintética corta que nunca diverge
aporta información censurada, no un cero engañoso.

**Evento B — vida del disenso (el número titular).** Desde un evento de divergencia, ¿cuántos actos
transcurren hasta el realineamiento (marcador de acuerdo o entailment con la posición divergente, o
retorno de la dispersión semántica a su nivel previo)? Si la sección cierra antes, censurado.

De ahí sale la métrica más directa y más comunicable de todo el paquete:

> **T½ del disenso** = mediana de Kaplan–Meier de actos de respuesta desde una divergencia hasta el
> realineamiento. "En los grupos humanos, un desacuerdo tarda una mediana de *k* actos en resolverse
> — y en el 40% de los casos no se resuelve dentro de la sección. En lo sintético, *k'* actos, y el
> X% no se resuelve."

Por qué esto es mejor que una tasa:
- Maneja la censura correctamente (el problema que hunde a las tasas cuando las ventanas difieren).
- Produce una **curva**, no un punto: se ve *la forma* de la convergencia, no solo su promedio.
- Tiene una lectura verbal inmediata para el capítulo.
- `lifelines` lo implementa en tres líneas (KM + tabla de supervivencia + mediana con IC).

**Cautela estadística, no negociable.** Las curvas KM agregadas a nivel de acto son **descriptivas**;
los IC que produce `lifelines` tratarían 493 actos como independientes, lo cual es pseudo-replicación
(las réplicas nunca son independientes — decisión congelada). Por tanto: **la curva se muestra sin
IC**, y la comparación formal es **por par de FG (n=5)**, con la mediana KM por FG como el valor
comparado. Exactamente el mismo tratamiento que ya diste al resto del marco.

**Y aquí entra la envolvente §K, gratis.** Con 5 grupos humanos puedes calcular la variación
humano-humano de cada métrica de consenso (d_HH) y preguntar si el sintético cae dentro de ella
(d_SH). Es la respuesta formal del marco a n=1 y aplica a estas métricas sin trabajo adicional:
es aritmética sobre la tabla que produce este pipeline.

---

## 5. Los detectores

Cinco detectores independientes. Ninguno es árbitro; la conclusión se afirma donde convergen.

**D1 — Marcadores léxicos (determinista).**
Diccionario cerrado, publicado en apéndice, con tres clases: divergencia ("I disagree", "I'd push
back", "not sure I agree", "yeah but", "nah", "I dunno about that", "actually, no"), alineación
("I agree", "exactly", "same here", "definitely", "that's true"), y atenuadores. Se **cuentan
ocurrencias en posición inicial de turno o de cláusula**, no se clasifica postura (la lección de la
ablación: el clasificador de complacencia falló clasificando; un conteo es auditable línea por línea).
Repetibilidad = 1.0 por construcción.
*Limitación que hay que medir, no argumentar:* es el detector con mayor sesgo diferencial de registro.
Su recall por lado se **estima empíricamente** en §7 y se reporta.

**D2 — NLI sobre oraciones-postura.**
Modelo NLI local, determinista, versión fijada (familia DeBERTa/RoBERTa-MNLI; disponible localmente —
`torch 2.13.0+cpu` y `transformers 5.14.1` ya están instalados). El refinamiento importante frente
a la adenda: **no correr NLI sobre turnos completos ni sobre todas las oraciones.** Primero se extraen
las *oraciones-postura* de cada turno (regla: oración con marcador de opinión en primera persona,
adjetivo evaluativo o negación de una proposición previa; tope de 5 por turno). Después se corre NLI
sobre el producto cruzado de oraciones-postura del par adyacente.
Esto ataca dos problemas a la vez: (a) el sesgo de longitud — un turno sintético de 250 palabras ya
no aporta 15 oportunidades de contradicción contra las 3 de uno humano; (b) la falacia
"contradicción = desacuerdo" — que dos hombres prefieran pubs distintos es contradicción textual sin
desacuerdo alguno; las oraciones-postura filtran buena parte de eso.
*Costo:* ≤25 pares NLI × 812 pares adyacentes ≈ **≤20,300 forward passes**, ~20–90 min en CPU según
el tamaño del modelo. Nada de GPU necesaria.

**D3 — Dinámica de embeddings (`sentence-transformers 5.6.0`, ya instalado y ya usado por el pipeline).**
Por sección: dispersión semántica entre participantes (distancia media al centroide de posturas),
medida en ventanas móviles, y su **pendiente**. Más añadido: **curva de redundancia** — similitud
máxima de cada turno nuevo contra todos los anteriores de la sección. Redundancia creciente = la
discusión dejó de aportar. Se engancha conceptualmente con el trabajo de saturación ya hecho.

**D4 — Anclaje al primer hablante (nuevo).**
Por sección: correlación entre el orden de intervención y la similitud de la postura con la del
*primer* hablante. Si en lo sintético cada participante se parece más al primero cuanto más tarde
habla, eso es consenso por eco, no por negociación. Es una línea de código sobre los embeddings de
D3 y es, en mi lectura, **la métrica con mayor rendimiento por minuto invertido de todo el paquete**:
operacionaliza directamente la sobre-validación mutua que ya documentaste (0.54–0.63 vs 0.03–0.19),
y es el análogo interno del 92% vs 42% de Mator et al.

**D5 — Asimetría del movimiento (nuevo).**
Por participante y sección: desplazamiento de su postura (primera vs. última) y si el desplazamiento
va *hacia* el centroide del grupo. De ahí: proporción de participantes que se mueven, y **Gini del
movimiento**. Consenso humano típico = pocos se mueven mucho; consenso por complacencia = todos se
mueven un poco hacia el centro. Reutiliza el mismo Gini que ya calculas para participación (0.07–0.09
sintético vs 0.195 humano), así que la lectura es familiar para el lector del capítulo.

**D6 (opcional) — Coordinación lingüística, ConvoKit.**
Solo si sobra tiempo. Formaliza el hallazgo cualitativo de homogeneización de registro (§2.3 de la v2).
No es facilidad de consenso en sentido estricto; es acomodación. Dejarlo fuera del núcleo.

---

## 6. Métricas que se reportan

Todas por FG, humano vs. cada condición, n=5 pares, en los tres relojes, primario `voluntary`.

| # | Métrica | Detectores | Lectura de "más fácil" |
|---|---|---|---|
| M1 | Riesgo de primera divergencia por sección (KM) | D1+D2 | Más bajo |
| M2 | **T½ del disenso** (mediana KM hasta realineamiento) | D1+D2+D3 | Más corta |
| M3 | % de divergencias no resueltas al cierre de sección | D1+D2 | Más bajo |
| M4 | Pendiente de dispersión semántica intra-sección | D3 | Más pronunciada |
| M5 | Anclaje al primer hablante (ρ orden↔similitud) | D4 | Más alto |
| M6 | Proporción de participantes que se mueven / Gini del movimiento | D5 | Todos se mueven poco = eco |
| M7 | Envolvente: ¿d_SH cae dentro de d_HH? | todas | — (respuesta a Pregunta 1) |

**Direcciones pre-declaradas** (a congelar antes de mirar la comparación, §9): sintético = M1 menor,
M2 más corta, M3 menor, M4 más pronunciada, M5 mayor, M6 movimiento más repartido.

---

## 7. La validación humana mínima — y cómo convertirla en rigor

Esta es la parte que responde literalmente a tu pregunta: **cuánta codificación humana, y cómo
lograr que una muestra pequeña dé una cifra defendible.**

### 7.1 La idea que hace eficiente el diseño

No se codifica una muestra para "ver si el detector está bien". Se codifica una muestra para
**corregir la cifra final**. El estimador que se reporta no es la salida del detector, sino:

> tasa corregida = tasa del detector sobre todo el corpus + media ponderada del error medido en la muestra

Es el estimador de diferencia / asistido por modelo (la misma lógica que hoy se llama *prediction-powered
inference*). Propiedad clave: **es insesgado aunque el detector sea mediocre**, y su incertidumbre
depende del tamaño de la muestra humana, no de la calidad del detector. Un detector con 70% de recall
más 240 unidades codificadas produce una estimación honesta con intervalo declarado. Eso es
exactamente "validación humana no muy compleja, muestra suficiente pero no grande, sin perder calidad".

### 7.2 El muestreo

La divergencia es rara (probablemente 5–15% de los actos). Muestrear al azar 240 actos daría ~25
positivos: insuficiente para estimar recall. Solución: **muestreo estratificado por la predicción de
los detectores, con probabilidades de inclusión conocidas y estimación de Horvitz–Thompson.**

| Estrato | Definición | N aprox. corpus | n a codificar |
|---|---|---|---|
| S1 | D1 y D2 coinciden en divergencia | pequeño | censo (todos) |
| S2 | Solo uno de los dos marca divergencia | medio | ~80 |
| S3 | Ninguno marca (presunto acuerdo/neutro) | grande | ~90 |
| S4 | Control aleatorio simple, sobre todo el corpus | — | ~40 |

Objetivo **n ≈ 240, repartido 50/50 humano-sintético** (≈120 por lado). El estrato S4 es el seguro
antifraude: permite detectar si la estratificación misma introdujo sesgo.

Dos ventajas del tamaño real del corpus, que conviene explotar y decir en el capítulo:
- El corpus de actos es de **812 unidades**, así que 240 es el **30% del universo** — no es una
  muestra de conveniencia, es una fracción de muestreo alta.
- Con esa fracción, la **corrección por población finita** (√(1−n/N)) reduce el intervalo en ~16%
  gratis. Un argumento de eficiencia que la mayoría de las tesis no puede hacer.

### 7.3 La tarea de codificación

- **Unidad presentada:** el turno previo + el turno de respuesta, nombres enmascarados, lado oculto.
- **Etiqueta ternaria, una sola decisión:** `divergencia` / `alineación` / `ninguna de las dos`.
  Nada de intensidad, ni de tipo, ni de resolución. Una decisión por unidad es lo que mantiene
  κ alto y el tiempo bajo.
- **Ritmo:** 30–45 s por unidad ⇒ **~2.5–3 h** para el codificador principal.
- **Fiabilidad:** doble codificación del **25% (60 unidades, ~45 min)** ⇒ κ de Cohen /
  α de Krippendorff reportado. **Total ≈ 4 horas-persona.**
- **Cegamiento honesto:** es imperfecto — un turno de 250 palabras se delata frente a uno de 40.
  Por eso el diseño **no depende** del cegamiento: estima el error del detector *por lado por
  separado*, que es más fuerte que suponer simetría (y es la corrección al punto 4 de la adenda).
- **Compatibilidad con el gold standard en campo:** el codebook de esta tarea debe usar la
  **misma redacción del eje acuerdo/desacuerdo** del gold standard de dos codificadoras. Si coincide,
  cuando vuelva ese material se fusiona sin ninguna tarea humana adicional, y la validación
  exploratoria se convierte en validación anclada a costo cero.

### 7.4 Qué se obtiene

1. Recall y precisión de D1 y D2 **por lado** (la pregunta que decide si la comparación es legítima).
2. Tasas de divergencia **corregidas** con intervalo, para M1 y M3.
3. κ que documenta que la etiqueta de referencia es reproducible.
4. Un chequeo directo del sesgo diferencial de registro: si D1 tiene recall 0.80 en sintético y 0.45
   en humano, la comparación cruda estaba invertida — y lo habrías sabido con 4 horas de trabajo.

---

## 8. Amenazas a la validez y qué se hace con cada una

| Amenaza | Magnitud medida | Mitigación |
|---|---|---|
| Un cuarto de actos de respuesta en sintético | 16.4 vs 63.8 por sesión | Censura + KM; tres relojes; denominadores siempre visibles |
| Turnos 4–5× más largos | mediana 216–281 vs 22–89.5 | Oraciones-postura con tope de 5; sensibilidad recortando a prefijos de longitud humana (lógica D2) |
| Moderador 3× más presente en sintético | 16.5 vs 5–6 turnos | Primario solo `voluntary`; reporte de intervenciones por sección |
| Sesgo diferencial de registro (D1) | desconocida | **Se mide** en §7, no se argumenta |
| Contradicción ≠ desacuerdo (D2) | desconocida | Filtro de oraciones-postura + validación §7 |
| Dispersión baja por eco, no por acuerdo (D3) | — | D4 y D5 la distinguen |
| Pseudo-replicación | 5 pares, no 15 | KM sin IC; comparación por FG; sin tests |
| `selection_mode` ausente en el lado humano | asimetría estructural | Declarada como limitación; su dirección es conservadora |

---

## 9. Encaje con el marco congelado

- **Namespace nuevo** `CONSENSUS_DYNAMICS_EXPLORATORY`, decisión post-result declarada bajo la
  política de amendments. Filas nuevas en `metric_registry.csv` con `evidence_class` =
  `AUTOMATIC_EXPLORATORY` (no `AUTOMATIC_VALIDATED`) hasta que la validación §7 esté hecha; después,
  `AUTOMATIC_SAMPLE_CORRECTED`.
- **No toca el WITHHELD.** Las métricas interpretativas de acuerdo/desacuerdo siguen retenidas hasta
  el gold standard. Esto es una capa automática complementaria, jamás sustituto. Decirlo explícitamente
  en el reporte.
- **Pre-registro barato y de alto rendimiento:** escribir el spec (definiciones, diccionario,
  versión del modelo NLI, umbrales, direcciones predichas de §6) y **congelar su hash antes de correr
  la comparación**. Ya lo hiciste con la tabla de hipótesis del 29-jul; repetirlo aquí cuesta una hora
  y convierte todo el paquete en confirmatorio-de-dirección en vez de exploratorio puro.
- **Ningún juez LLM en el núcleo.** Tu propia auditoría cruzada (auto-contradicción 35.7%,
  0 abstenciones) es el argumento. Si quieres un cuarto detector LLM, solo como corroboración con
  consenso ≥3/5 corridas y con estatus `USABLE_FOR_CORROBORATION_ONLY`.

---

## 10. Plan de ejecución y costo

**Entorno ya listo:** `torch 2.13.0+cpu`, `transformers 5.14.1`, `sentence-transformers 5.6.0`,
`sklearn 1.9.0`, `numpy/pandas/scipy`.
**Faltan (pip, minutos):** `lifelines` (KM), `statsmodels`, `krippendorff`, `pysbd` o `spacy`
(segmentación de oraciones — `pysbd` funciona mejor con habla transcrita).
**Nota:** descargar los pesos del modelo NLI es una descarga de HuggingFace. No es una llamada a API
de pago ni toca la ruta de generación, pero **es tráfico de red y conviene que lo autorices explícitamente**
dada tu regla de no correr llamadas vivas.

| Fase | Trabajo | Tiempo |
|---|---|---|
| 0 | Spec congelado + direcciones predichas + filas de registry | 1–2 h |
| 1 | Capa de eventos: secciones, actos P→P, `selection_mode`, tres relojes | 0.5 día |
| 2 | D1 (diccionario) + D3/D4/D5 (embeddings, reutiliza el stack existente) | 0.5 día |
| 3 | D2 (oraciones-postura + NLI, ~20k forward passes CPU) | 0.5 día |
| 4 | Supervivencia: KM, T½, por FG + envolvente §K | 0.5 día |
| 5 | Construcción de la muestra estratificada + libro de codificación | 0.25 día |
| 6 | **Codificación humana** | **~4 horas-persona** |
| 7 | Corrección asistida por muestra, κ, tablas y figuras | 0.5 día |

**Total: ~3 días de implementación + 4 horas-persona de codificación. Cero llamadas de pago.**

**Ruta corta, si el tiempo aprieta:** Fases 0–2 + D4 + D5 solamente (~1 día, sin NLI, sin codificación
humana). D4 y D5 sobre embeddings ya dan una respuesta publicable a "¿el consenso sintético es
negociado o por eco?", que es la pregunta interesante. D2 y la validación humana se añaden después
sin rehacer nada.

---

## 11. La ruta solo-automatizada (Mator et al., 2025): qué da y qué no

*Añadido tras leer Mator et al. (2025) y Zhang et al. (2024) completos. Todo lo que sigue está
verificado en los PDFs.*

### 11.1 Qué hicieron exactamente

Mator et al. describen en §3 **cuatro** métricas de evaluación (realismo por BERTScore contra corpus
humano de referencia; coherencia de persona por coseno enunciado↔semilla psicográfica; **entropía de
postura**; y **convergencia, "para evaluar qué tan rápido se alinea la postura a lo largo del tiempo"**).
La Tabla 4 reporta **otras cinco** (completitud, relevancia, similitud entre participantes, acuerdo,
distribución conversacional).

**Es decir: las dos métricas que medirían literalmente tu constructo — entropía de postura y
convergencia — se anuncian en el método y no aparecen en los resultados.** La cifra que sí reportan
y que todo el mundo cita (**acuerdo 92% IA vs. 42% humano**) está definida en una sola línea:
*"averaged stance-aware sentence similarity between subsequent participant responses"*. No hay
modelo especificado, ni umbral, ni qué hace que la similitud sea "stance-aware", ni validación, ni
fiabilidad. Su propia sección de próximos pasos dice que la fiabilidad intercodificador
*"will be recorded"* — o sea, no se registró.

Base empírica: **n = 3 humanos, un grupo, 30 minutos**, contra un grupo IA.

### 11.2 Tres razones por las que no puede ser tu instrumento primario

**(a) Mide similitud, no acuerdo — y el confundido es exactamente tu asimetría conocida.**
Similitud de embeddings entre respuestas consecutivas sube cuando las respuestas son largas,
formales y cubren todos los aspectos del prompt. Mator lo documenta él mismo: *"AI participants
consistently addressed every aspect of the prompt"*, y respuesta media de 195 palabras (IA) vs 92
(humano), **2.1×**. En tu corpus la brecha es **4–5×** (216–281 vs 22–89.5). Una métrica de
similitud recuperaría el "92 vs 42" **por construcción**, midiendo verbosidad y exhaustividad, no
facilidad de consenso. Confirmaría tu hipótesis sin haberla puesto a prueba.

**(b) Mide un estado promedio, no un proceso.** Tu pregunta es *qué tan rápido* y *cómo* se genera
el consenso. La métrica de acuerdo de Mator es un promedio sobre toda la sesión: sin tiempo, sin
trayectoria, sin distinguir "convergieron tras negociar" de "todos repitieron al primero". La
métrica que sí tendría dinámica es la de convergencia — la que no reportaron.

**(c) Los números no son comparables con los tuyos, y eso es verificable.** Distribución
conversacional, share de palabras del moderador:

| | Moderador humano | Moderador IA |
|---|---|---|
| Mator et al. | 32% | 18% |
| **Tu corpus** | **2.1%** | **11.1%** |

Tu moderador humano es prácticamente silencioso (493 palabras en 5 grupos) y tu moderador sintético
habla 5× más que él; en Mator la relación va en dirección contraria. Con un moderador humano que
toma el 32% de una sesión de 30 minutos con 3 participantes, los pares de respuestas consecutivas
entre participantes sobre los que se calcula ese 42% son **una docena escasa, de un solo grupo**.
Tú tienes **319 actos de respuesta humanos en 5 grupos y 493 sintéticos en 30 sesiones**.

### 11.3 Lo que sí vale la pena, y que es mejor que "seguir a Mator"

No replicar por comparabilidad, sino **replicar y someter a prueba de esfuerzo**. Dos chequeos que
solo tú puedes hacer y ellos estructuralmente no:

1. **Envolvente humano-humano de la propia métrica de Mator.** Calcúlala sobre tus 5 grupos
   humanos. Si el rango humano es amplio (p. ej. 35–70%), el 42% de un solo grupo es ruido y el
   contraste "92 vs 42" pierde la fuerza que se le atribuye. Ellos, con n=1, no podían saberlo.
2. **Control de longitud.** Recalcula la métrica sobre turnos sintéticos recortados a prefijos de
   longitud humana (la lógica D2 que ya tienes implementada). Si el "acuerdo" cae sustancialmente,
   queda demostrado que la métrica mide verbosidad.

Eso convierte dos horas de script en un párrafo de contribución metodológica:
*"replicamos el hallazgo principal de Mator et al. sobre un corpus 25× mayor del lado humano y
mostramos que es parcialmente un artefacto de la longitud de respuesta"*. Es mucho más fuerte que
citarlos como benchmark.

### 11.4 El contrapunto de Zhang et al. (2024): los dos papers acotan la decisión

Zhang et al. hicieron **lo contrario** de una evaluación automatizada: análisis temático y de
contenido **humano** (39 códigos en los grupos humanos vs 47 en las simulaciones, solapamiento en
diagrama de Venn, y curvas de acumulación de códigos únicos por iteración — el antecedente directo
de tu análisis de saturación). Su hallazgo clave es de proceso: *"tras varias iteraciones los
agentes IA dejan de generar códigos nuevos, mientras los participantes humanos siguen produciéndolos"*.

Y tienen el mismo agujero que Mator por el otro lado: la codificación la hizo el autor principal y
los coautores la *"revisaron y validaron"*. Eso no es fiabilidad intercodificador; no reportan κ ni α.

**Consecuencia para tu tesis: ninguno de los dos benchmarks publicados reporta un solo estadístico
de fiabilidad.** Con 4 horas de codificación y un κ reportado, tu documentación instrumental supera
a ambos. Ese es el argumento para gastar las 4 horas — no la cautela metodológica abstracta, sino
que es barato y te pone por encima del estado del arte que estás citando.

### 11.5 Tres niveles de validación humana — elige uno

| Nivel | Costo humano | Qué licencia decir | Riesgo que queda |
|---|---|---|---|
| **N0 — solo automatizado** (Mator + D3/D4/D5 + control de longitud) | 0 h | "alineación textual", "convergencia semántica" | No puedes escribir "desacuerdo" ni "consenso" sin comillas; sesgo diferencial de registro sin medir |
| **N1 — triaje** (~80 unidades estratificadas, 40/lado) | **~1 h** | "desacuerdo (proxy con error estimado)" | Detecta sesgo diferencial *grueso*, que es el único que invalidaría la comparación; sin corrección de tasa |
| **N2 — completo** (240 unidades + 25% doble, §7) | ~4 h | Tasas corregidas con intervalo + κ | Ninguno relevante al estatus exploratorio |

**N1 es el punto de inflexión de valor/tiempo.** Una hora compra la diferencia entre "las respuestas
sintéticas se parecen más entre sí" (un hallazgo de similitud, que ya está publicado y que tu
asimetría de longitud explica sola) y "los grupos sintéticos disienten menos" (un hallazgo sobre
consenso). Es la frontera entre describir texto y describir interacción.

---

## 12. Lo que este diseño no puede sostener

Escribirlo en el capítulo, no esperar a que lo pregunte un examinador:

- **No mide consenso como resultado sustantivo** (si el grupo llegó a una posición común *correcta* o
  *significativa*). Mide la dinámica de alineación textual. Un grupo puede converger textualmente sin
  acordar nada real.
- **No hay inferencia.** n=5 pares; las réplicas son variabilidad del generador. Todo es descriptivo,
  igual que el resto del marco.
- **Las etiquetas de referencia son de una investigadora + 25% doble-codificado**, no un gold standard
  completo. Es una validación proporcionada al estatus exploratorio, y explícitamente provisional
  hasta que vuelva el gold standard.
- **`selection_mode` no existe del lado humano**, así que la restricción a turnos voluntarios es
  asimétrica.
- **El resultado más probable ya es predecible** (menos fricción, disenso más corto, más anclaje al
  primer hablante). El valor no está en la sorpresa: está en **cuantificar** con qué instrumento,
  con qué error medido, y en la firma de C4 — *cómo* se genera el consenso, no solo que se genera
  más rápido. Esa es la contribución.

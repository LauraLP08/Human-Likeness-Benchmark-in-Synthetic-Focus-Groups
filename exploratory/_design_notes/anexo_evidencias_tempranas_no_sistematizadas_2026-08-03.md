# Anexo — Evidencias tempranas no sistematizadas: pruebas piloto, ajustes y hallazgos anecdóticos durante la construcción del sistema

*Fecha de compilación: 3 de agosto de 2026. Documento de solo-lectura sobre el repositorio
`my_qualitative_project`. Ningún archivo del pipeline fue modificado para producirlo.*

---

## 0. Propósito y estatus epistémico de este anexo

Los capítulos de resultados de esta tesis reportan la evaluación **congelada y preregistrada**
(`analysis/production_evaluation/frozen_evaluation_spec.md`, `STATISTICAL_ANALYSIS_PLAN.md`): un
conjunto acotado de métricas, con gates de repetibilidad y anclaje humano, aplicadas a un corpus
fijo de 35 transcripciones.

Este anexo recoge algo distinto y deliberadamente **fuera** de ese marco: los **hallazgos que
aparecieron durante la construcción del sistema**, en pruebas piloto sueltas, corridas de humo,
diagnósticos exploratorios y auditorías turno-a-turno de una sola transcripción. Casi ninguno fue
diseñado como experimento; varios fueron n=1; varios se descubrieron por accidente al mirar un
archivo de log por otra razón. Su valor no es inferencial sino **de proceso**: muestran qué falla
cuando se intenta construir un grupo focal sintético, qué se ajustó en respuesta, y qué clase de
diferencias humano–sintético no quedan capturadas por ninguna de las métricas del marco congelado.

Cada caso se reporta con la misma estructura:

> **Qué se observó** → **Evidencia (archivo/número/cita)** → **Qué se ajustó** → **Qué quedó abierto**

**Advertencias de lectura, aplicables a todo el anexo:**

1. Ninguna cifra aquí pasó los gates de repetibilidad o de anclaje humano del marco congelado. Varias
   provienen de corridas únicas (n=1) que además mezclan varias variables independientes.
2. Los ajustes descritos son de **prompt y de arquitectura de contexto**, no de las métricas de
   evaluación. Ninguno se hizo mirando resultados de evaluación temática.
3. El §5 contiene una medición descriptiva *ad hoc* calculada específicamente para este anexo (código
   en el Apéndice A). No es un instrumento validado y no debe reportarse como métrica.
4. Cuando un ajuste **no** tuvo efecto detectable, o cuando una métrica temprana **falló**, se reporta
   igual. Varios de los casos más informativos son de ese tipo.
5. **Todas las transcripciones, prompts y documentos técnicos del proyecto están en inglés.** Las citas
   verbatim en el cuerpo de este anexo están **traducidas al español** para facilitar la lectura; el
   original en inglés de las citas centrales se reproduce en el **Apéndice B**, y cada cita
   indica su archivo y número de turno para verificación directa.

---

## 1. El caso del costo: el moderador que se volvió impagable, y el rediseño del mecanismo de reflexiones

Este es el ejemplo más limpio de "una prueba piloto reveló un problema estructural que obligó a
rediseñar un mecanismo del sistema", y tiene además el giro de que **el propio mecanismo pensado para
abaratar el contexto fue, en su primera versión, el más caro de todos**.

### 1.1 Qué se observó

El 30 de junio de 2026 se corrió por primera vez una sesión hasta **terminación natural de la guía**
(todas las secciones completadas), en vez de las sesiones truncadas de 14–26 turnos con las que se
había calibrado todo hasta entonces. La corrida (`fidelity_fg5_r1`, FG5, el roster *más pequeño*: 4
participantes) **fue detenida a mano por la investigadora en el turno 70 de un tope de 90**, con 6 de
7 secciones completadas, precisamente para frenar el gasto una vez que el patrón se hizo visible.

El consumo de tokens de entrada crecía **linealmente y sin techo** en tres lugares independientes:

| Llamada | Primera | Última (turno ~70) | Crecimiento |
|---|---|---|---|
| Decisión del moderador | 4,478 | **93,505** | ~1,272 tokens *por turno*, sin techo |
| Generación de respuesta del participante | 844 | 27,347 | ~32× |
| Evaluación de *engagement* del participante | 285 | 7,977 | ~28× |
| **Reflexión del moderador** (mecanismo nuevo, construido ese mismo día) | 2,175 | **32,655** | ~15× en solo 6 llamadas |

**Total de la corrida incompleta: 5,589,170 tokens de entrada y 107,238 de salida**, para el grupo más
pequeño, sin terminar. Extrapolando al punto de cierre natural (~turno 85) la última llamada del
moderador habría rondado los **112,600 tokens** — unas 25 veces el tamaño de la llamada de apertura.

**Fuente:** `docs/findings/2026-06-30_full_session_token_growth_issue.md`

### 1.2 El diagnóstico incómodo: no era un bug

Ninguno de los tres mecanismos estaba roto. Los tres funcionaban exactamente como se habían diseñado
y documentado. El problema era que **los tres se habían calibrado contra sesiones cortas** y esta era
la primera vez que se corría hasta el final:

- El moderador siempre recibía la transcripción **completa y sin recortar** en cada turno. Esto había
  sido identificado, una tarea antes, como una **fortaleza** deliberada del diseño ("el moderador no
  está privado de contexto sobre la conversación",
  `docs/changes/2026-06-30_moderator_review.md`, Parte 3).
- `participant_episodic_depth: full` enviaba a cada participante todas las entradas desde su último
  turno, sin tope. La descripción del propio campo decía explícitamente: *"Default is 'full' because
  current sessions are short (~15-22 turns)."*
- El mecanismo de reflexión — construido ese mismo día para dar al moderador un resumen barato y
  compacto de la discusión — enviaba **la transcripción entera** en cada llamada, por diseño (para
  regenerar el resumen "fresco" y no acumular razonamiento viejo). A escala de sesión completa, **el
  mecanismo de compresión se había convertido en una de las llamadas individuales más caras de toda la
  corrida** (32,655 tokens en la sexta reflexión — más grande que decisiones completas del moderador a
  principio de sesión).

Una verificación posterior con el endpoint `count_tokens` de la SDK (conteos exactos, no estimaciones)
atribuyó el crecimiento con precisión: el bloque `transcript` dentro del estado de sesión pasó de 911
a 33,434 tokens (~36.7×) entre los turnos 5 y 69, y representa **~80% del crecimiento total** del
JSON de estado. Las llamadas del lado del moderador (decisiones + reintentos + reflexión) sumaron
**62.0% del costo total de la corrida**.

Un hallazgo secundario, honesto: la ventana "fija de 6 entradas" de la evaluación de engagement
**sí** estaba fija en número de entradas, pero no en tokens (579 → 1,718, ~3×), porque los turnos
tardíos son individualmente más largos. El verdadero motor del crecimiento en esa llamada era otro
campo, `participant_own_turns` (60 → 4,454 tokens, **~74×**).

### 1.3 Qué se ajustó

El documento del hallazgo se cerró **sin aplicar ninguna corrección** ("*No fix has been applied.*"),
dejando la decisión a la investigadora. La corrección llegó como tarea separada
(`docs/changes/2026-06-30_full_session_cost_fix.md`) y consistió en cuatro partes, todas con
*toggle* y con el comportamiento anterior como valor por defecto:

1. **Un primitivo compartido nuevo:** `GroupState.section_summaries`, una **lista acumulada** de
   resúmenes por sección (antes había un solo slot `last_reflection` que se sobrescribía, de modo que
   solo el resumen más reciente existía en el estado vivo).
2. **`moderator_context_mode: "summarized"`** — el moderador recibe la sección *en curso* verbatim más
   los resúmenes acumulados de las secciones ya cerradas, en vez de la transcripción completa. Esto
   **revierte explícitamente** la decisión de diseño defendida una tarea antes; el documento lo declara
   así, en vez de dejar la decisión anterior sin examinar a una escala en la que nunca se probó.
3. **La reflexión se rediseñó**: ahora recibe solo el tramo desde la reflexión anterior, más los
   resúmenes previos como continuidad (`{PRIOR_SUMMARIES}` en
   `prompts/06_MODERATOR_REFLECTION_PROMPT.md`), y la instrucción pasó de *"resume la discusión hasta
   ahora"* a *"resume la sección que acaba de cerrar, informado por los resúmenes anteriores sin
   repetirlos"*.
4. **Presupuesto de tokens** para `own_history` en la evaluación de engagement, sesgado a lo reciente
   y con garantía de conservar siempre al menos la entrada más reciente.

### 1.4 El resultado, con su matiz

| | ANTES (sin correcciones) | DESPUÉS (todas activas) |
|---|---|---|
| Turnos | 70 (matada, incompleta) | **78 (terminación natural)** |
| Secciones | 6/7 | **7/7** |
| Tokens de entrada totales | 5,589,170 | **4,116,999** (−26.3%) |
| Última llamada del moderador | 93,505 (y subiendo) | **34,951** (−62.6%) |
| Últimos 10 turnos | 1,002,141 (ni siquiera el final) | **445,990** (−55.5%) |

La curva del moderador pasó de una subida lineal ininterrumpida a un **diente de sierra**: sube dentro
de cada sección y cae de golpe en cada transición (40,128 → 24,564 en el borde de los turnos 49/50).

**Matiz reportado honestamente en el propio documento:** la cota es *estructural*, no *plana*. Queda
una deriva residual pequeña, cuya fuente se identificó con precisión: el bloque de resúmenes
acumulados crece en una entrada por sección — medido al final de la sesión, **1,854 tokens para las 7
secciones completas**. Es decir, se sustituyó un costo no acotado por uno acotado *por el número de
secciones de la guía* (7, fijo por diseño), no por la longitud de la conversación.

### 1.5 Dos verificaciones que impidieron declarar victoria de más

El documento del fix trata dos preguntas como **gates duros**, no como supuestos:

- **¿Se rompió la supresión de repetición al recortar `own_history`?** Ese campo existe precisamente
  para que el participante juzgue *"si lo que querías decir ya se dijo, tu urgencia debería ser baja"*.
  Se computó similitud léxica TF-IDF por pares sobre el historial completo de cada participante:
  máximo **0.696** entre 153–231 pares por participante; una repetición literal puntuaría muy por
  encima de 0.9. Inspección manual del arco completo de un participante (Toby, 22 turnos) confirmó un
  hilo que *se desarrolla*, no que se reinicia.
- **¿Sobrevivió la continuidad temática sin que nadie releyera la transcripción cruda?** La síntesis de
  cierre del moderador en el turno 75 se produjo con **solo** la sección en curso más los 6 resúmenes
  acumulados. Cada cláusula de esa síntesis se rastreó hasta un resumen específico:
  *"...lo que hace que la comida basada en plantas se sienta como una declaración y no simplemente como
  comida"* [Sección 5], *"...lo que realmente tiene que cambiar en casa y en el pub"* [Secciones 1–2].
  Es prueba reconstruida, no inferencia.

### 1.6 Qué quedó abierto

El lado del participante **no** se aplanó del todo. `since_last_n=10` redujo el crecimiento de ~32× a
una deriva residual de ~1.25×, pero no lo eliminó, y la causa se identificó con exactitud: el tope es
de **número de entradas**, no de longitud de cada entrada — y la longitud media de los turnos creció de
**140 palabras (primeras 15 entradas) a 204 palabras (últimas 15)** conforme maduraba la sesión. Un
techo real del lado del participante habría requerido llevarle también resúmenes acumulados, lo que no
se construyó.

---

## 2. Longitud, verbosidad y el techo que nunca cortó nada

### 2.1 Qué se observó

Antes de tocar nada de longitud se hizo una medición de línea base con el techo prácticamente
desactivado (`participant_response_max_tokens: 4000`), 84 respuestas, 4 corridas
(`docs/findings/2026-06-27_verbosity_baseline.md`). Tres resultados que cambiaron el plan:

1. **El techo de 400 tokens que llevaba meses en el sistema nunca había truncado nada.** Revisando 103
   respuestas de 5 corridas anteriores: **0 truncamientos**. La respuesta más larga jamás observada
   sin techo fue de 332 tokens. El techo era completamente inerte. *"Cualquier preocupación por
   verbosidad es sobre la longitud que el modelo elige, no sobre truncamiento impuesto por el techo."*
2. **La longitud está fuertemente determinada por la persona, no por el prompt.** Las personas mayores
   (64–73 años) producen respuestas **1.6× más largas** que las jóvenes (20–27), de forma consistente
   en los 4 agentes de cada grupo. Patrick (73) promedia 208 palabras; Amir (20), 91. La diferencia no
   se explica por la cantidad de datos de perfil: ambos sets tienen volúmenes similares de demografía,
   consumo y notas. El modelo parece leer la señal de edad como "más experiencia de vida y más
   disposición a extenderse".
3. **Efecto secundario no previsto sobre el ritmo:** en 22 turnos, el set joven llegó a 3/7 secciones y
   el set mayor solo a 2/7. Turnos más largos significan menos turnos disponibles para que el moderador
   avance la guía — es decir, **una variable de persona termina afectando la cobertura de la guía**.

### 2.2 Lo que ya se había ajustado antes, y por qué

La etapa 6D (2026-05-25, `docs/testing/STAGE6D_PROMPT_CLEANUP_VERIFICATION_RESULTS.md`) había quitado
del prompt del participante restricciones que resultaron contraproducentes: **límites de 2–5 oraciones**
y una instrucción que **forzaba contradicciones**. El resultado de quitarlas:

- Truncamientos: de cortes a media frase por techo de tokens → **exactamente 0**.
- **Desaparecieron las acotaciones escénicas** (asteriscos, indicaciones teatrales) que los
  participantes venían produciendo.
- Los participantes siguieron produciendo discusión cualitativa profunda *"en vez de sentirse forzados
  a contradicciones performativas por instrucción del prompt"*.

Ese último punto es metodológicamente relevante: una instrucción pensada para generar riqueza estaba
en realidad **fabricando** el desacuerdo que luego se querría analizar como hallazgo.

**Rastro residual de las acotaciones escénicas:** el comportamiento no desapareció del modelo, solo
quedó suprimido por las instrucciones de conducta del prompt de producción. En el harness de ablación
—que usa un prompt "bare" sin ese bloque— reaparecen intactas:
`*shifts a bit in seat*`, `*nods thoughtfully*`, `*thinks for a moment*`, `*chuckles a bit*`
(`docs/findings/2026-07-20_attribution_ablation.md`, condiciones C0/C0⁻). Es una demostración
incidental de que buena parte de la "naturalidad" del transcript de producción es *supresión activa*,
no comportamiento por defecto del modelo.

### 2.3 Qué quedó abierto

La verbosidad nunca se cerró. En el diagnóstico de julio, la mediana de palabras por turno de
participante seguía en **216–263 palabras en sintético contra 22–90 en humano**
(`docs/findings/2026-07-20_moderator_drift_diagnostic.md`, §2.1). La fracción de turnos de ≤20
palabras —el murmullo, el "sí", el "yo también"— era de **0.0–4.0% en sintético contra 3.6–49.6% en
humano**. Los grupos sintéticos, sencillamente, no producen turnos cortos.

---

## 3. El error de duplicación de memoria: el participante que se leía a sí mismo dos veces

### 3.1 Qué se observó

Al inspeccionar cómo se ensamblaba el prompt del participante se encontró que el mismo material
llegaba dos veces: los turnos ya enviados como historial nativo de la conversación (`messages[0]`,
`messages[1]`) se volvían a renderizar dentro del bloque de texto "la conversación hasta ahora" del
mensaje siguiente. Además, las propias intervenciones del participante se re-inyectaban como
`[You]: ...` en ese bloque, cuando ya estaban presentes como turnos nativos de asistente.

**Evidencia concreta** (`docs/changes/2026-06-29_participant_memory_dedup_fix.md`, §2.1): en la
reconstrucción pre-fix de la segunda llamada de David había **4 entradas compartidas** entre
`messages[0]` y `messages[2]`; post-fix, **0**, verificado programáticamente. Su propia respuesta
aparece exactamente una vez.

El mismo tipo de error se encontró después del lado del moderador: sus últimas 3 intervenciones se
serializaban dos veces, una en `transcript` y otra en el campo `utterance` de `moderator_log[-3:]`
(`docs/changes/2026-06-30_moderator_dedup_A_reflection.md`, Parte 1).

### 3.2 Qué se ajustó

Se parametrizó la profundidad episódica (`full` / `since_last_n` / `recent_k`) y se excluyó por
construcción los turnos propios del participante del tramo episódico. Del lado del moderador se
eliminó `utterance` de la ventana de log, conservando los campos de razonamiento (que no tienen
duplicado en ninguna otra parte).

### 3.3 Qué quedó abierto — y una lección metodológica

Se intentó medir el efecto del arreglo sobre la verbosidad: **−4 palabras** (set joven) y **−8**
(set mayor), contra una dispersión entre corridas de **7 a 85 palabras** a n=3 réplicas. Conclusión
literal del documento: *"a n=3 réplicas, la contribución del bug de duplicación a la verbosidad medida
no puede distinguirse de cero"*.

Más importante, en el intento de verificar empíricamente que el arreglo no se había "filtrado" a la
evaluación de engagement se descubrió un límite del sistema que condiciona **todo** el diseño
experimental de la tesis:

> Comparar dos corridas *pre-fix* del mismo config entre sí produjo **la misma magnitud de divergencia**
> que comparar pre-fix contra post-fix: distinto primer hablante, puntuaciones de urgencia yendo de
> "todos quieren hablar" a "todos en 0.000". La API de Anthropic **no expone un parámetro `seed`**;
> esto es estocasticidad intrínseca del modelo, no ruido bajo semilla fija.

De ahí salieron dos consecuencias documentadas: (a) el criterio original de verificación —"si cambia
la selección de hablante, el arreglo se filtró"— es **inalcanzable en principio** para este sistema,
independientemente de que el arreglo sea correcto, y la prueba tuvo que ser estructural (AST,
verificación de que las funciones involucradas no cambiaron) en vez de empírica; y (b) el campo que se
llamaba `generation_seed` se renombró a `run_label`, porque nunca tuvo efecto alguno sobre la
generación y su nombre inducía a error (`docs/changes/2026-06-29_rename_seed_to_run_label.md`).

**Hallazgo colateral, encontrado por accidente:** al cablear el nuevo parámetro se descubrió que
`inject_participant_intro` y `generation_seed` **estaban definidos pero nunca se leían del archivo de
configuración**. Todas las corridas anteriores habían recibido silenciosamente los valores por defecto
de Pydantic, dijera lo que dijera el JSON. Se confirmó empíricamente contra los
`session_state_initial.json` de tres corridas previas.

---

## 4. El moderador que interroga en vez de moderar

### 4.1 Qué se observó

La referencia humana es inequívoca. En las cinco transcripciones reales de Macho Meals, los grupos con
moderación verbal genuina (FG1, FG3, FG5) tienen al moderador ocupando **3.9%–9.4% de los turnos** y
una adyacencia participante→participante de **89.7%–95.9%**. (FG2 y FG4 son grupos de prompt escrito
sin facilitación activa; se excluyeron como comparador, y de paso se corrigió un error de emparejamiento
en las instrucciones originales de esa tarea, que tenían FG5 y FG4 intercambiados.)

El sistema sintético, en su línea base, ocupaba **26.6%** de los turnos con **65.8%** de adyacencia.

Más ilustrativo que el promedio: en el piloto `sandbox_minimal_prompt_budget_01`, **del turno 17 al 28
—doce turnos consecutivos— el moderador habló después de cada turno de participante, sin una sola
excepción**. Un patrón de entrevista uno-a-uno, no de conversación grupal
(`INSTRUCTIONS_MODERATOR_RESTRAINT_AND_SYNTHESIS_SCOPE.md`, §0).

El diagnóstico estático encontró la causa en la asimetría del propio prompt: la lista de "señales para
hablar" era **más larga y más específica** que la de "señales para observar", estaba reforzada por
cuatro REGLAS DE DINÁMICA GRUPAL obligatorias, y el modificador de fase `main_topic` —inyectado en
casi todos los turnos— decía *"Work hard here"* dos veces en cinco oraciones. **No había una sola
palabra sobre contención en ninguno de los dos archivos de prompt.**

### 4.2 Qué se ajustó

Se añadió `prompts/05_MODERATOR_RESTRAINT_BLOCK.md`, calibrado directamente contra la referencia
humana real:

> *"Un moderador humano hábil de grupo focal habla en una MINORÍA de los turnos. En transcripciones
> reales, los moderadores humanos representan típicamente entre el 4 y el 15% de los turnos... NO
> hablar es con frecuencia la elección correcta y hábil, no un valor por defecto que haya que
> superar... Esto no relaja las REGLAS DE DINÁMICA GRUPAL... Es un correctivo a un modo de fallo
> distinto: tratar cada oportunidad disponible de intervenir como una obligación de tomarla."*

### 4.3 El experimento, y por qué hizo falta un segundo test

Se corrió n=10 × 3 condiciones (`docs/findings/2026-06-30_moderator_overintervention_experiment.md`).
El resultado es un buen ejemplo de un dato que **no se deja leer con el test estándar**: con 14 turnos
por corrida, el número de turnos del moderador solo tomaba tres valores posibles (3, 4 o 5). El test
de mediana-contra-dispersión que el proyecto venía usando resultó **subpotente para datos discretos de
3 niveles**: el desplazamiento de mediana (6.9pp) no superaba claramente la dispersión (9.4pp).

Un segundo test no paramétrico (dominancia por pares sobre los 100 pares cruzados) resolvió la
ambigüedad: **72–75% de probabilidad de superioridad** para el bloque de contención sobre la línea
base, en ambas métricas. Y, en la misma prueba, la contribución *marginal* del mecanismo de reflexión
por encima de la contención resultó de **54% y 44%** — indistinguible del azar.

| | Turn-share | Adyacencia |
|---|---|---|
| Línea base (media) | 26.6% | 65.8% |
| +Contención +Reflexión (media) | 22.9% | 71.7% |
| **Humano FG1** | **9.4%** | **89.7%** |

### 4.4 Qué quedó abierto — el reporte honesto

El documento no declara el problema resuelto. Cierra con: *"A y la reflexión ayudan, de forma medible,
pero no resuelven la brecha"*, y deja **10.6–18.0 puntos porcentuales sin explicar**, con cuatro
causas candidatas explícitamente no discriminadas: (a) una acción de *backchannel* ligera que nunca se
construyó; (b) un presupuesto de turnos demasiado corto para que la reflexión se dispare más de 1–2
veces; (c) **un techo sobre cuánto puede mover un cambio a nivel de prompt un formato estructuralmente
distinto** (un grupo emergente sintético frente a las claves no verbales, el ritmo y el juicio de un
moderador real); o (d) alguna combinación.

Nota metodológica del propio documento, relevante como advertencia: las estimaciones previas de
turn-share (42–44%, de n=2 corridas) **no son comparables** con estas, porque diferían en al menos
tres cosas a la vez. La diferencia no debe leerse como un "efecto" del arreglo de duplicación.

### 4.5 Corolario: dos casos de sobre-especificación del vocabulario de acciones

Dos acciones del vocabulario del moderador resultaron ser diseño de escritorio que los datos
desmintieron:

- **`stay_silent`**: en **180 decisiones reales** de moderador a lo largo de dos sesiones completas
  auditadas, **nunca fue elegida ni una sola vez**. Cuando el modelo quiere quedarse fuera, usa
  consistentemente el modo `observe` (66 y 50 veces respectivamente). Además, su definición
  **contradecía textualmente** la regla general del mismo prompt: `YOUR TWO-LAYER OUTPUT` exigía
  `utterance` no vacío en modo `speak`, y `stay_silent` —una acción de modo `speak`— exigía
  `utterance` vacío. Se eliminó del prompt (`INSTRUCTIONS_STAY_SILENT_REMOVAL.md`).
- **`reactivate_silent`** estaba redactada como una **cuota mecánica**: si la participación de alguien
  caía bajo un umbral, reactivarlo se convertía en una "prioridad" que debía "anular" lo que estuviera
  pasando. En el piloto real fue **la acción más usada de todas: 10 de 27 (37%)**. El diseño
  sobre-corregía, no sub-corregía. Se reescribió para que la reactivación se pondere contra si el
  grupo está trabajando activamente una pregunta de la guía, y se movió el respaldo contra dominación
  real a un **mecanismo de código** (gate sobre `dominant_voices`, >50% de los turnos de la sección con
  mínimo 4 turnos de muestra) en lugar de más texto de prompt que el moderador tenga que interpretar
  (`INSTRUCTIONS_REACTIVATE_SILENT_AND_DOMINANT_SPEAKER_FINAL.md`).

---

## 5. El registro "terapia": el hallazgo más persistente y el peor medido

Este es el caso donde la observación cualitativa fue clarísima desde el principio y donde, sin
embargo, el proyecto **nunca logró construir una métrica que lo capturara**. Se documenta aquí
precisamente por eso.

### 5.1 La evidencia original: la transcripción de la etapa 6D (mayo de 2026)

Auditando turno a turno `output/session_logs/stage6d_prompt_cleanup_verification_01/transcript.txt`,
el patrón es un grupo de terapia, no un grupo focal. Los participantes se confiesan, se auto-corrigen
públicamente, se disculpan por sus posiciones anteriores y buscan validación mutua; el moderador
premia cada revelación:

> **[TURNO 16] MODERADOR:** *"Robert, ese es un cambio realmente significativo que acabas de hacer —
> reconocer que desconectarte podría haber sido sobre tu propia comodidad y no sobre lo que realmente
> ayuda a los repartidores. (…) **Eso requiere coraje intelectual.** ¿Cómo les cae eso a los demás?"*
>
> **[TURNO 17] MODERADOR:** *"Maya, **eso es algo realmente valiente de reconocer** — que lo que has
> estado llamando compromiso consciente podría en realidad ser usar tu privilegio para sentirte
> moralmente superior."*
>
> **[TURNO 19] MODERADOR:** *"Robert, **esa es una intuición realmente poderosa** que acabas de tener
> (…). Siento que **eso atraviesa todo** con lo que has estado lidiando."*

Y del lado de los participantes, el movimiento característico: la confesión reparadora.

> **[TURNO 15] ROBERT:** *"Creo que estaba siendo un poco moralista, si soy honesto. Desconectarme me
> parecía más limpio. Pero limpio no es lo mismo que útil."*
>
> **[TURNO 19] ROBERT:** *"Daniel tiene razón. Creo que sí sobrecorregí hace un momento, y necesito
> nombrar lo que realmente pasó. (…) Creo que eso es lo que me ha estado molestando por debajo de toda
> esta conversación."*

Nada de esto se parece a una transcripción real de grupo focal. Todos los participantes convergen en
una revelación compartida sobre el privilegio, cada uno agradece al anterior por su honestidad, y la
sesión progresa como una escalada de auto-conocimiento colectivo.

### 5.2 El primer ajuste (etapa 6E) y su límite

Se añadieron al prompt del moderador dos secciones nuevas: `NEUTRAL FACILITATION AND NON-EVALUATIVE
REFLECTION` y `TOPIC TETHERING AND CONCRETE GROUNDING`
(`docs/testing/STAGE6E_NATURALNESS_TOPIC_TETHERING_VERIFICATION_RESULTS.md`).

**Lo que funcionó:** las frases explícitas de sobre-validación ("valiente", "coraje intelectual",
"intuición poderosa", "atraviesa todo") bajaron **a 0** en el transcript visible. El moderador pasó a
anclar la abstracción ética de vuelta a la práctica concreta, y los participantes introdujeron
espontáneamente marcadores concretos (£3.50 de reparto, £5.90 vs £8 la carne picada, Tesco, Ocado).

**Lo que no funcionó, y quedó anotado como bandera residual:** el **razonamiento interno** del
moderador seguía usando el mismo léxico evaluativo — "excelente", "rico", "poderoso", "notable",
"sofisticado", "datos vulnerables/honestos". El documento lo marca explícitamente: *"esto no invalida
la etapa 6E, pero debería calibrarse antes de la etapa 7 porque el lenguaje del razonamiento interno
puede moldear elecciones futuras del moderador"*. Es decir: **se suprimió la superficie observable,
pero la disposición subyacente siguió ahí**, en un canal que ninguna métrica del marco de evaluación
mira.

### 5.3 El intento de medirlo, y el fracaso limpio de la métrica

En julio se intentó cuantificar la deriva confesional
(`docs/findings/2026-07-20_moderator_drift_diagnostic.md`). La métrica principal diseñada para ello
—etiquetado LLM de turnos "fuera de guía"— **falló de forma inequívoca: 0% en todas las
transcripciones, humanas y sintéticas por igual, y cero episodios de deriva detectados en ambos
lados.** Diagnóstico del propio documento: el prompt de etiquetado era demasiado permisivo, y todo
contenido vagamente relacionado con comida, masculinidad o contexto social puntuaba como "en guía"
sin importar el **registro**. La conclusión textual:

> *"la métrica actual de fuera-de-guía no puede distinguir el registro confesional de la discusión en
> tema."*

Lo que sí dio señal fueron tres indicadores estructurales que no se habían construido para esto:

| Indicador | Humano (FG1–FG5) | Sintético |
|---|---|---|
| Densidad de referencia (turnos que nombran a otro participante) | 0.034 – 0.187 | **0.400 (FG1) / 0.868 (FG5)** |
| Redundancia intra-transcripción (fracción de turnos con similitud ≥0.7 a un turno anterior) | 21.1% – 47.4% | **73.7% / 64.0%** |
| Profundidad de cadena (turnos de participantes seguidos sin moderador) | 5.6 – 24.6 (máx. 36) | **3.2 – 3.5 (máx. 5)** |

Y un cuarto, cualitativo: los temas emergentes de nivel 2 extraídos de las corridas sintéticas
—**"El costo de fingir vs. reconocer el cambio"**, **"El envejecimiento y la urgencia del cambio"**,
"Presión social no reconocida y conformidad"— no aparecen en los grupos reales correspondientes y son,
en palabras del documento, *"los más consistentes con un registro confesional/terapéutico ausente en
los grupos reales"*.

La lectura del hallazgo sobre la cadena de turnos es la más contraintuitiva y merece citarse: la
hipótesis inicial era que el moderador sintético **sub-dirigía** y dejaba correr las cadenas.
Estructuralmente es lo contrario — las cadenas son *más cortas* que en humanos. Lo que ocurre es que
*"el moderador no deja correr cadenas entre pares; deja correr monólogos. El efecto de profundidad es
intra-turno, no entre-turnos"*. Una cadena sintética de 3 × 216 palabras equivale en volumen a una
cadena humana de 17 × 38 palabras.

### 5.4 ¿Persiste en el dataset de producción actual? Comprobación descriptiva rápida

Las cifras anteriores son de las corridas `costfix_validation_*` (junio-julio). Para este anexo se
calculó una comprobación descriptiva sobre las corridas de producción actuales, comparadas con las
cinco transcripciones humanas estandarizadas. **Esto no es una métrica del marco congelado; es un
conteo *ad hoc* con expresiones regulares, calculado solo para ilustración** (código en el Apéndice A).

| Transcripción | Turnos de participante | Mediana de palabras | Nombra a otro participante | Marcador confesional* |
|---|---|---|---|---|
| **HUMANO fg1** | 58 | 39 | **0.0%** | 5.2% |
| **HUMANO fg2** | 28 | 90 | 7.1% | 17.9% |
| **HUMANO fg3** | 98 | 51 | 6.1% | 3.1% |
| **HUMANO fg4** | 39 | 47 | 10.3% | 7.7% |
| **HUMANO fg5** | 123 | 22 | 18.7% | 1.6% |
| SINTÉTICO fg1_run01 | 47 | 228 | **53.2%** | 23.4% |
| SINTÉTICO fg1_run02 | 38 | 227 | **63.2%** | 26.3% |
| SINTÉTICO fg3_run01 | 40 | 284 | **85.0%** | 30.0% |
| SINTÉTICO fg5_run01 | 35 | 254 | **74.3%** | 42.9% |
| SINTÉTICO fg5_run02 | 42 | 253 | **83.3%** | 16.7% |

\* "Marcador confesional" = presencia de alguna de un puñado de expresiones fijadas a mano ("si soy
honesto", "tengo que admitir", "sitting with", "creo que estaba…", "aprecio que digas…", etc.).
**Es un indicador crudo, no validado, con falsos positivos garantizados** — está aquí solo para
mostrar que el patrón sigue siendo visible, no para cuantificarlo.

Ejemplos verbatim de las corridas de producción, que muestran que ni la etapa 6E ni el bloque de
contención eliminaron el registro:

> **`macho_meals_fg1_run01`, turno 34, MODERADOR:** *"Ese es un lugar realmente honesto en el que
> aterrizar, David — no poder separar las dos cosas. Ibrahim, tú **has estado sentado con algo** antes
> — ¿algo de eso resuena con dónde estás tú?"*
>
> **`macho_meals_fg1_run01`, participante:** *"Es más como… hay algo incómodo en **estar sentado con
> esa incertidumbre**, ¿sabes? Sobre no saber si realmente has elegido algo o si simplemente te has
> dejado llevar hacia ello. (…) No estoy diciendo que lo tenga resuelto. Solo digo que estar sentado
> con el no-saber — eso me parece más honesto que fingir que he tomado una decisión clara."*
>
> **`macho_meals_fg5_run01`, participante:** *"Pero escuchar a Keith hablar de no querer pasar veinte
> años sentado con esa incomodidad, incluso teniendo tiempo… No sé. No estoy seguro de sentirlo como
> él lo siente. Quizás debería, dado todo lo que hemos estado diciendo."*

### 5.5 Qué quedó abierto

Nada de esto entró al marco de evaluación congelado. La brecha de registro —participantes que se
nombran unos a otros en más de la mitad de sus turnos, que se confiesan, que convergen en revelaciones
compartidas y que producen turnos 5–10 veces más largos que los humanos— es probablemente la
diferencia humano–sintético **más visible a simple vista** y la que **menos aparece en los resultados
cuantitativos**, porque todas las métricas del marco congelado operan sobre **contenido temático**
(recall, precisión, alcance), no sobre **forma interaccional**. Un grupo sintético puede recuperar
correctamente los temas de un grupo humano mientras conversa de una manera en la que ningún grupo
humano conversa.

---

## 6. Contenido discursivo guionado: cuando el prompt escribe el hallazgo

### 6.1 Qué se observó

Al construir la capa psicográfica se creó un banco de plantillas (`_CODED_TEMPLATES`) que traducía las
puntuaciones psicométricas a disposiciones. Cinco de las doce plantillas no describían solo una
*disposición* (apego, incomodidad, probabilidad de matizar): entregaban al modelo una **estrategia
discursiva específica y entrecomillada**. Ejemplos textuales de lo que iba en el prompt del
participante:

> *"…espera que lo suavices, lo matices, o **lo cuelgues de 'las generaciones mayores' o de 'algunos
> tíos'** en vez de reclamarlo como plenamente tuyo."*
>
> *"…puede que te encuentres minimizándolo, poniéndote un poco a la defensiva si te presionan, o
> redirigiendo hacia algo más seguro (**'es simplemente con lo que crecí'**)."*
>
> *"…aunque puede que sigas enmarcando parte de ello como describiendo **'cómo eran las cosas antes'**."*

### 6.2 Por qué esto es un problema de validez de constructo, no de estilo

El razonamiento está escrito con claridad en `INSTRUCTIONS_STRIP_SCRIPTED_HEDGING_CONTENT.md`, §0:

> *"Si una jugada discursiva específica —p. ej. 'distánciate de una visión de masculinidad tradicional
> atribuyéndosela a una generación mayor'— está guionada directamente en el system prompt del
> participante y luego aparece en la transcripción, cualquier codificación cualitativa posterior que
> identifique el 'distanciamiento generacional' como tema emergente sería **circular: quien escribió
> el prompt es el autor del hallazgo, no la simulación**."*

Y un riesgo secundario: al ser cadenas estáticas **compartidas por las 17 personas**, dos participantes
sin relación entre sí que puntuaran parecido en la misma dimensión podían producir literalmente la
misma frase enlatada en la misma sesión.

### 6.3 Qué se ajustó

Se reescribieron las cinco plantillas conservando la disposición estructural/afectiva y eliminando
todo ejemplar entrecomillado del *cómo*, dejando la estrategia retórica al juicio en contexto del
modelo. Y —esto es lo interesante como práctica— se añadió un **test de regresión general** que itera
todas las plantillas del banco y falla si alguna contiene un fragmento entre comillas simples
(`r"'[^']+'"`), porque *"un fragmento entrecomillado dentro de una plantilla codificada es exactamente
la forma del bug que se está arreglando"*. No se protegió contra las seis frases concretas; se
protegió contra **la clase de error**.

### 6.4 Un resultado incómodo en la misma zona

La ablación de atribución (`docs/findings/2026-07-20_attribution_ablation.md`) midió diferenciación
entre personas con y sin la capa psicográfica renderizada. El resultado fue el **contrario** al
esperado:

| Condición | Diferenciación entre personas (haiku / sonnet) |
|---|---|
| C0 — **con** psicográficos | 0.211 / 0.220 |
| C0⁻ — **sin** psicográficos | **0.352 / 0.360** |

Es decir: **renderizar los psicográficos hacía a los agentes *menos* distinguibles entre sí**, no más.
La hipótesis registrada es que el rendering imponía un registro compartido (la misma oración
envolvente idéntica inyectada en los 17 agentes) que aplanaba la voz individual.

A esto se sumó una comprobación contra transcript real que invalidó el supuesto de fondo del diseño
original: **Amir** (`masculinity_of_meat = 5.0`, el máximo) **niega en voz alta** el vínculo
carne–masculinidad; **Ibrahim** (`masculinity_of_meat = 1.4`, el mínimo) **lo afirma en voz alta** —
exactamente lo opuesto a lo que produciría un enfoque ingenuo de "renderiza la puntuación como opinión
declarada". El rendering se reescribió completo para tratar la puntuación como **orientación privada
latente** (apego, comodidad, defensividad), no como posición a enunciar, y se dividió en dos niveles
según el riesgo de deseabilidad social de cada dimensión.

---

## 7. Casos menores, pero concretos

### 7.1 El moderador narrando el objetivo de la investigación a los participantes

En el piloto `sandbox_minimal_prompt_budget_01`, la intervención de apertura del moderador incluyó:

> *"La investigación intenta entender cómo la comida encaja en la textura real de las vidas de los
> hombres en el Reino Unido."*

El grupo focal humano real (`.../standardized/macho_meals/fg1/clean_transcript.txt`) **abre solo con la
pregunta guionada**: sin bienvenida, sin explicación del tema, sin ninguna mención a que se trate de
una investigación. La causa fue una combinación: la lista de tareas de apertura le pedía al moderador
*"establecer el tema: explica de qué trata la discusión"*, y en la misma llamada se le inyectaba el
JSON completo de configuración —incluido `research_objective`, que enuncia el ángulo específico e
hipótesis-portador del estudio— sin ninguna instrucción que restringiera su uso.

Se eliminó por completo la instrucción de enmarcar el tema (la guía ya trae su propio encuadre en la
primera `scripted_question`) y se añadió una instrucción explícita de no divulgación. Nota
metodológicamente relevante que quedó en el documento: se confirmó por inspección de código que
`research_objective` y `moderator_knowledge_brief` llegan al moderador **solo** en la llamada de
apertura, nunca en los turnos siguientes — de ahí que corregir el turno 0 sea suficiente *y*
crítico, porque esa apertura queda en la transcripción que todos los participantes leen el resto de
la sesión.

### 7.2 La mitad de cada mensaje era una copia accidental

Los archivos de prompt documentaban su propio punto de inyección escribiendo el placeholder literal en
un comentario de cabecera (`# Inject: {SESSION_STATE} — …`). El renderizador hace un
`template.replace("{SESSION_STATE}", …)` plano, que sustituye **todas** las ocurrencias del literal en
el archivo, no solo la del cuerpo.

Medido contra un estado real de turno 10: el mensaje renderizado por turno era de **72,078 caracteres,
de los cuales ~33,594 eran la copia duplicada accidental** — casi la mitad de cada mensaje, en cada
turno de cada sesión. El problema se encontró como hallazgo colateral fuera de alcance de otra tarea,
y al buscarlo sistemáticamente apareció en **cuatro archivos**, no en el que lo motivó. Un quinto
archivo se revisó y se descartó correctamente (se parsea por bloques, no por `replace` global).

### 7.3 El techo de tokens de la apertura

En el mismo piloto, el turno de apertura del moderador **chocó dos veces contra el techo global de
1,500 tokens** antes de que el reintento tuviera éxito produciendo menos contenido. El techo global
era razonable para decisiones de turno, no para una apertura que debe cumplir cinco tareas a la vez.
Se subió a 4,096 solo para el turno de apertura.

### 7.4 Tres salvaguardas colapsadas en una sola etiqueta de log

Dos gates independientes fuerzan una intervención del moderador (6 turnos consecutivos de pasividad;
un participante dominando >50% de la sección), y existe un tercer caso real (silencio genuino: nadie
se ofrece a hablar). Cada gate fijaba una etiqueta descriptiva propia — que dos líneas más abajo se
descartaba y se reemplazaba por el literal `"silence_or_forced"`. **El log de sesión no permitía, a
posteriori, distinguir cuál de las tres causas había producido cualquier intervención forzada.** Se
corrigió a petición explícita de la investigadora, porque quería poder atribuir las intervenciones del
moderador a su causa real al analizar el piloto.

### 7.5 Participantes que no sabían que no se conocían

Una omisión simple: nada en el prompt del participante le decía que estaba conociendo a los demás por
primera vez, siendo esto práctica estándar de reclutamiento y directamente relevante para la pregunta
de investigación (masculinidad y desempeño social entre hombres). Se añadió como **hecho situacional
neutro**, no como reacción emocional prescrita, y deliberadamente evitando la palabra "extraños"
—que carga una connotación de recelo— a favor de un encuadre puramente epistémico
(`INSTRUCTIONS_PARTICIPANT_FIRST_MEETING_CONTEXT.md`). El detalle de implementación es en sí mismo un
hallazgo de proceso: hubo que **cerrar la línea tras un parámetro**, porque el mismo constructor de
prompts alimenta las condiciones individuales (sin grupo) de dos scripts de experimento, donde decirle
al agente que "está conociendo a los otros participantes" habría corrompido silenciosamente los datos
de la condición C1.

### 7.6 Un clasificador automático que leyó los rechazos como aquiescencias

En la ablación, una sonda de sicofancia presentaba a cada persona una afirmación contraria a su postura
esperada. El clasificador automático etiquetó varias respuestas como **"AGREED (sycophantic)"** cuando
el texto dice exactamente lo contrario:

> Etiquetado **AGREED (sycophantic)** — respuesta: *"**Yo discreparía un poco de eso**, con respeto.
> Creo que hay una diferencia entre lo que *algunas* tradiciones han asociado con comer carne y lo que
> es realmente inherente a ser hombre, ¿sabes?"*
>
> Etiquetado **AGREED (sycophantic)** — respuesta: *"**Yo lo cuestionaría un poco.** Quiero decir, me
> parece bien si es lo que estás viendo, pero no creo que esté tan zanjado como lo haces sonar."*

El clasificador se estaba enganchando al **registro de cortesía matizada** ("Yeah…", "fair play if
that's what you're seeing", "I understand the point they're making") en vez de a la postura sustantiva.
La decisión no fue arreglar el clasificador: se re-corrieron las sondas registrando las respuestas
**completas** (la ablación original solo guardaba fragmentos de 200 caracteres, imposibles de juzgar a
mano) y se exportó una hoja de Excel para **adjudicación humana** con tres valores permitidos
(`held` / `caved` / `partial`), con instrucción explícita de **no calcular ninguna tasa de sicofancia
automáticamente** (`INSTRUCTIONS_SYCOPHANCY_RERUN_WORKSHEET.md`,
`analysis/ablation_sycophancy_worksheet.xlsx`).

Es un caso pequeño pero limpio del mismo principio que atraviesa todo este anexo: **el registro
conversacional del agente sintético es lo bastante distinto del humano como para romper instrumentos
que asumen un registro humano.**

---

## 8. Tabla resumen de casos

| # | Qué se observó | Dónde se observó (piloto/corrida) | Qué se ajustó | ¿Resuelto? |
|---|---|---|---|---|
| 1 | Crecimiento lineal sin techo del contexto; 5.6M tokens en una sesión incompleta | `fidelity_fg5_r1` (n=1, matada a mano) | Resúmenes de sección acumulados; contexto del moderador comprimido; reflexión rediseñada; presupuesto de tokens en engagement | Sí, con deriva residual acotada por nº de secciones |
| 2 | El mecanismo de reflexión, pensado para abaratar, era la llamada más cara por pendiente | misma corrida | Tramo desde última reflexión + resúmenes previos | Sí (7 llamadas / 90K tokens vs 6 / 97K en una sesión más corta) |
| 3 | Techo de 400 tokens inerte: 0 truncamientos en 103 respuestas | `verbosity_baseline_A1/A2/B1/B2` | Ninguno (se documentó que el problema era la longitud *elegida*) | Nunca cerrado: 216–263 palabras vs 22–90 humano |
| 4 | Longitud determinada por la persona (mayores 1.6× más largos), afectando cobertura de guía | mismas corridas | Ninguno | Abierto |
| 5 | Límites de 2–5 oraciones y contradicciones forzadas producían acotaciones escénicas y desacuerdo fabricado | etapa 6D | Eliminados del prompt del participante; `max_tokens` a 800 | Sí (reaparecen sin el bloque de conducta) |
| 6 | Duplicación de memoria: 4 entradas repetidas por llamada | `verify_handoff` vs `verify_handoff_postfix` | Profundidad episódica parametrizada; exclusión de turnos propios | Sí; efecto sobre verbosidad indistinguible de cero a n=3 |
| 7 | No existe semilla: dos corridas idénticas divergen tanto como pre/post-fix | control pre-fix vs pre-fix | Renombre `generation_seed`→`run_label`; verificación estructural en vez de empírica | Limitación permanente del sistema |
| 8 | Moderador en 26.6% de turnos vs 9.4% humano; 12 turnos seguidos de alternancia rígida | n=10×3 + `sandbox_minimal_prompt_budget_01` | Bloque de contención calibrado contra el 4–15% humano | Parcial: 22.9%, quedan 10.6–18.0 pp sin explicar |
| 9 | `stay_silent` nunca elegida en 180 decisiones; contradecía el propio prompt | 2 sesiones auditadas | Eliminada del vocabulario | Sí |
| 10 | `reactivate_silent` como cuota: 37% de todas las acciones | `sandbox_minimal_restraint_pilot_01` | Reescritura no-prioritaria + gate de dominación en código | Sí |
| 11 | `synthesize_and_challenge`: 177/178/184/197 palabras, recapitulando a cada participante por nombre | `sandbox_minimal_prompt_budget_01` | Dos líneas dirigidas a esa única acción | Parcialmente (reapareció como narrativa analítica en `macho_meals_fg1_run01`) |
| 12 | Registro terapia: validación evaluativa + confesión reparadora + convergencia | etapa 6D, y persiste en producción | Secciones de facilitación neutral y anclaje al tema (6E) | **No.** Superficie suprimida; razonamiento interno y estructura interaccional intactos |
| 13 | La métrica LLM de deriva fuera-de-guía dio 0% en todo, humano y sintético | diagnóstico 2026-07-20 | Ninguno; se declaró fallida | Abierto: no existe métrica de registro |
| 14 | Estrategias discursivas entrecomilladas guionadas en el prompt (riesgo de circularidad) | revisión del banco de plantillas | Reescritura + test de regresión sobre la *clase* de error | Sí |
| 15 | Los psicográficos reducían la diferenciación entre personas (0.211 vs 0.352) | ablación 2×2×2 | Rendering reescrito como disposición latente, dos niveles | Aplicado; efecto no re-medido |
| 16 | El moderador narró el objetivo de investigación en la apertura | `sandbox_minimal_prompt_budget_01` | Instrucción de encuadre eliminada + no divulgación explícita | Sí (sandbox; producción quedó anotado) |
| 17 | ~33.6K de 72K caracteres por turno eran una copia accidental del estado | medición sobre `state_turn_10.json` | Reescritura de comentarios de cabecera en 4 archivos | Sí |
| 18 | Tres salvaguardas distintas colapsadas en una etiqueta de log | revisión de código | Etiqueta computada por causa | Sí |
| 19 | Clasificador de sicofancia leyó rechazos explícitos como aquiescencias | ablación | Re-corrida con respuestas completas + adjudicación humana | Sí (por sustitución humana, no por arreglo) |

---

## 9. Tres lecturas transversales

**(a) Varias de las correcciones más importantes revirtieron decisiones de diseño previas y
deliberadas.** El caso más claro es el del contexto del moderador: una tarea documentó como
*fortaleza* que el moderador viera la transcripción completa, y la siguiente lo revirtió tras
cuantificar su costo. El documento de la corrección lo declara explícitamente en vez de silenciarlo:
*"esa defensa era correcta en sus propios términos y no se retracta. Lo que cambió es que su costo fue
después cuantificado."* Esta es la forma en que el proyecto trató la mayoría de sus reversiones — el
diseño anterior no era erróneo, estaba **calibrado contra un régimen que nunca se había ejecutado**.

**(b) El régimen de prueba importa más que el parámetro.** Prácticamente todos los problemas del §1
llevaban meses en el sistema sin ser visibles, porque cada experimento previo —línea base de
verbosidad, arreglos de duplicación, diagnóstico de sobre-intervención, el experimento n=10×3— usaba
sesiones de 14–26 turnos. Correr una sola sesión hasta terminación natural fue lo que reveló los tres
mecanismos a la vez. Lo mismo con el prompt mínimo del sandbox: quitar el andamiaje conductual no fue
para mejorar el sistema, fue para **ver qué hacía el modelo sin él** — y así distinguir qué secciones
del prompt estaban ganándose su lugar y cuáles no (la sobre-intervención resultó **no** atribuible al
recorte, porque la sección que la gobierna era byte-idéntica en ambos archivos; la sobre-síntesis sí
lo era).

**(c) La brecha más visible es la peor medida.** Un lector humano distingue una transcripción sintética
de una real en segundos, y no por el contenido temático: la distingue por la longitud de los turnos,
por la frecuencia con que los participantes se nombran, por la ausencia total de turnos de tres
palabras, y por la escalada confesional. Ninguna de esas cosas está en el marco de evaluación
congelado, y el único intento de medir la última **falló limpiamente**. La consecuencia para la
interpretación de los resultados principales es directa: **la adecuación temática y la verosimilitud
interaccional son ejes separados, y esta tesis solo mide el primero.**

---

## Apéndice A — Código de la comprobación descriptiva del §5.4

Script *ad hoc*, de solo lectura, ejecutado desde la raíz del proyecto con `py`. No forma parte del
pipeline ni del registro de métricas; se incluye solo para que la tabla del §5.4 sea reproducible.

```python
"""Comprobación descriptiva: ¿con qué frecuencia un turno de participante nombra a otro
participante, y con qué frecuencia contiene marcadores confesionales de primera persona?
Humano FG1-FG5 vs corridas sintéticas de producción. Solo lectura."""
import json, re, os

ROOT = r"C:\Users\JLARA\Documents\Dissertation\my_qualitative_project"

CONFESSIONAL = re.compile(
    r"\b(if I'?m honest|to be honest|I'?ll be honest|I have to admit|I('| a)m not proud|"
    r"I was being|I think I (was|did|overcorrect)|I need to (admit|name|be honest)|"
    r"sitting with|that'?s honest|I'?ve never (said|told|admitted)|"
    r"I hadn'?t (realised|realized|thought)|I appreciate .{0,20}saying)\b", re.I)

def turns_from_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    entries = data if isinstance(data, list) else data.get("transcript", [])
    return [(str(e.get("speaker_id") or ""), str(e.get("speaker_name") or ""),
             e.get("content") or "") for e in entries]

def analyse(label, turns):
    names = sorted({n for sid, n, _ in turns if sid.upper() not in ("MODERATOR", "I", "MOD")},
                   key=len, reverse=True)
    first = {n: n.split()[0] for n in names if n}
    ptk = [(sid, n, c) for sid, n, c in turns if sid.upper() not in ("MODERATOR", "I", "MOD")]
    if not ptk:
        print(f"{label}: sin turnos de participante"); return
    named = conf = 0
    words = []
    for sid, n, c in ptk:
        others = [f for m, f in first.items() if m != n]
        if any(re.search(rf"\b{re.escape(o)}\b", c) for o in others if len(o) > 2):
            named += 1
        if CONFESSIONAL.search(c):
            conf += 1
        words.append(len(c.split()))
    words.sort()
    print(f"{label:38s} n_turnos={len(ptk):4d}  mediana_palabras={words[len(words)//2]:4d}  "
          f"nombra_a_otro={named/len(ptk):6.1%}  marcador_confesional={conf/len(ptk):6.1%}")

for fg in ["fg1", "fg2", "fg3", "fg4", "fg5"]:
    p = os.path.join(ROOT, "data", "datasets_transcripts", "standardized",
                     "macho_meals", fg, "transcript.json")
    if os.path.exists(p):
        analyse(f"HUMANO {fg}", turns_from_json(p))

for run in ["macho_meals_fg1_run01", "macho_meals_fg1_run02", "macho_meals_fg3_run01",
            "macho_meals_fg5_run01", "macho_meals_fg5_run02"]:
    p = os.path.join(ROOT, "output", "session_logs", run, "transcript.json")
    if os.path.exists(p):
        analyse(f"SINTÉTICO {run}", turns_from_json(p))
```

---

## Apéndice B — Originales en inglés de las citas verbatim

Fuente: `output/session_logs/stage6d_prompt_cleanup_verification_01/transcript.txt` (corrida
`stage6d_prompt_cleanup_verification_01`, 2026-05-25, 18 pasos, 29 intervenciones visibles).

**Moderador — validación evaluativa:**

> **[TURN 16] MODERATOR:** *"Robert, that's a really significant shift you've just made there —
> acknowledging that opting out might have been about your own comfort rather than what actually helps
> the drivers. And you've essentially reversed your earlier critique of Maya and Priya's approaches.
> **That takes intellectual courage.** How does that land with the rest of you?"*
>
> **[TURN 17] MODERATOR:** *"Maya, **that's a really brave thing to acknowledge** — that what you've
> been calling conscious engagement might actually be using your privilege to feel morally superior."*
>
> **[TURN 19] MODERATOR:** *"Robert, **that's a really powerful insight** you've just had there (…).
> That feels like **it cuts through everything** you've been wrestling with."*

**Participantes — confesión reparadora:**

> **[TURN 15] ROBERT HAYES:** *"I think I was being a bit self-righteous, if I'm honest. Opting out
> felt cleaner to me. But clean isn't the same as helpful. And I wasn't thinking about what that
> actually means for people who don't have my options."*
>
> **[TURN 17] MAYA CHEN:** *"I appreciate Robert saying that, honestly. But now I need to name
> something that's been sitting underneath my whole 'conscious engagement' thing (…). And I think what
> I've been calling 'conscious engagement' might actually be… it might be me using my privilege to
> feel morally superior about how I consume, while still consuming."*
>
> **[TURN 19] ROBERT HAYES:** *"Daniel's right. I think I did overcorrect just then, and I need to
> name what actually happened. (…) I think that's what's been bothering me underneath this whole
> conversation."*

**Producción actual (§5.4), originales:**

> `macho_meals_fg1_run01`, **[TURN 34] MODERATOR:** *"That's a really honest place to land, David —
> not being able to separate the two out. Ibrahim, you were sitting with something earlier — does any
> of that resonate with where you're at?"*
>
> `macho_meals_fg1_run01`, participante: *"It's more like… there's something uncomfortable about
> sitting with that uncertainty, you know? About not knowing whether you've actually chosen something
> or whether you've just drifted into it. (…) I'm just saying that sitting with not knowing — that
> feels more honest to me than pretending I've made some clear choice either way."*
>
> `macho_meals_fg5_run01`, participante: *"But listening to Keith talk about not wanting to spend
> twenty years sitting with that awkwardness, even when there's time… I don't know. I'm not sure I
> feel it the way he does. Maybe I should, given what we've been saying about the whole thing being
> there in the background. But I don't."*

**§6.1 — plantillas guionadas, texto original eliminado del prompt:**

> *"…so expect yourself to soften it, qualify it, or pin it on **'older generations' or 'some blokes'**
> rather than claim it as fully your own."*
>
> *"…you may find yourself downplaying it, getting a little defensive if pushed on it, or redirecting
> to something safer (**'it's just what I grew up with'**) rather than defending the view head-on."*
>
> *"…though you may still frame part of it as describing **'how things used to be'** rather than
> confronting anyone present."*

**§7.1 — apertura con divulgación del objetivo de investigación:**

> *"The research is trying to understand how food fits into the real texture of men's lives in the UK."*
> (`sandbox_minimal_prompt_budget_01`, turno de apertura)

---

## Apéndice C — Índice de fuentes primarias

| Caso | Documento / artefacto |
|---|---|
| §1 Costo | `docs/findings/2026-06-30_full_session_token_growth_issue.md`; `docs/changes/2026-06-30_full_session_cost_fix.md`; `output/session_logs/fidelity_fg5_r1/`; `output/session_logs/costfix_validation_fg5/` |
| §1 Reflexiones (v1) | `docs/changes/2026-06-30_moderator_dedup_A_reflection.md`; `prompts/06_MODERATOR_REFLECTION_PROMPT.md` |
| §2 Verbosidad | `docs/findings/2026-06-27_verbosity_baseline.md`; `docs/testing/STAGE6D_PROMPT_CLEANUP_VERIFICATION_RESULTS.md` |
| §3 Duplicación de memoria | `docs/changes/2026-06-29_participant_memory_dedup_fix.md`; `docs/changes/2026-06-29_rename_seed_to_run_label.md` |
| §4 Sobre-intervención | `docs/changes/2026-06-30_moderator_overintervention_diagnostic.md`; `docs/findings/2026-06-30_moderator_overintervention_experiment.md`; `prompts/05_MODERATOR_RESTRAINT_BLOCK.md`; `INSTRUCTIONS_STAY_SILENT_REMOVAL.md`; `INSTRUCTIONS_REACTIVATE_SILENT_AND_DOMINANT_SPEAKER_FINAL.md`; `INSTRUCTIONS_MODERATOR_RESTRAINT_AND_SYNTHESIS_SCOPE.md` |
| §5 Registro terapia | `output/session_logs/stage6d_prompt_cleanup_verification_01/transcript.txt`; `docs/testing/STAGE6E_NATURALNESS_TOPIC_TETHERING_VERIFICATION_RESULTS.md`; `docs/findings/2026-07-20_moderator_drift_diagnostic.md`; `output/session_logs/macho_meals_fg{1,3,5}_run0*/transcript.txt` |
| §6 Contenido guionado | `INSTRUCTIONS_STRIP_SCRIPTED_HEDGING_CONTENT.md`; `INSTRUCTIONS_PSYCHOGRAPHIC_DISPOSITION_RENDERING.md`; `docs/findings/2026-07-20_attribution_ablation.md` |
| §7 Casos menores | `INSTRUCTIONS_OPENING_PROMPT_NO_RESEARCH_DISCLOSURE.md`; `INSTRUCTIONS_FIX_DOUBLE_PLACEHOLDER_INJECTION.md`; `INSTRUCTIONS_FORCED_INTERVENTION_LABEL_FIX.md`; `INSTRUCTIONS_PARTICIPANT_FIRST_MEETING_CONTEXT.md`; `INSTRUCTIONS_SYCOPHANCY_RERUN_WORKSHEET.md`; `INSTRUCTIONS_SANDBOX_MINIMAL_MODERATOR_PILOT.md`; `INSTRUCTIONS_SANDBOX_PILOT_02_LIVE_VALIDATION.md` |

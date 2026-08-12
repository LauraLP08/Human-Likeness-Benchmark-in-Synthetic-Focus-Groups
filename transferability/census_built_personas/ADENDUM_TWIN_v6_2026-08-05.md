# Adendum v6 — Brazo twin poblacional (FG3 + FG4)

*5 de agosto de 2026. Archivo nuevo. La v5 se conserva en `ADENDUM_TWIN_v5_2026-08-05.md`
(SHA-256 `95a72674…288cc89a`) y la v4 en `ADENDUM_TWIN_v4_2026-08-05_SUPERSEDED.md`.*

> **DOCUMENTO FRONTERA.** El piloto `macho_meals_fg3_twinpop_run01` ya se lanzó, y es la
> **réplica canónica run01 de FG3** — G5 registró `output_dir_absent: true` para ese mismo
> `session_id` justo antes. Por la regla de congelación dura de la v5, **la primera sesión ya
> ocurrió y esta es la última enmienda posible**. Todo cambio posterior es **desviación
> declarada**, no enmienda.

---

## 0. Registro de enmiendas (continuación)

| # | Entrada | Clase de causa | Datos vistos entonces | Dirección | Hash |
|---|---|---|---|---|---|
| 5 | 5, 7, 9, G1 | (iv) reparación de instrumento | narrativas y puertas offline; sin sesión | **desfavorable al brazo** | `95a72674…` |
| 6 | 5, 6, 9, 11 + G1/G2/G3(b) | (iv) reparación de instrumento tras auditoría | piloto corrido; **estilometría twinpop NO computada** | mixta | *este documento* |
| 7 | 0.2 (alcance) | **decisión declarada de la investigadora**, no enmienda de instrumento | ninguna métrica de twinpop | reduce el alcance del brazo | *este documento* |
| 8 | 0.3 (reconocedor Q5) | (iv) reparación de instrumento | 6 sesiones corridas y segmentadas; **ninguna métrica de R4 computada** | recupera 1 réplica, pierde 1 | *este documento* |

### 0.1 Precisión obligatoria sobre la ceguera

La v5 afirmaba que la regla de R4 se fijó "antes de ver datos de twinpop". La formulación exacta,
que es la auditable:

> Fijada **antes de computar estilometría alguna sobre twinpop**, y **después** de una inspección
> cualitativa de salud del piloto cuyo alcance fue: conteo de turnos, secciones completadas,
> silencios forzados, longitud de turno, y **conteo de los términos de estado de pareja** que
> produjo la observación de Andrew. Ninguna métrica de R4 se ha calculado sobre twinpop.

Y la asimetría que hay que nombrar en vez de esperar a que la nombren: las clasificaciones se
diseñaron **conociendo dónde caen human, enriched y demoonly**, y a ciegas únicamente de twinpop.
**La categoría a priori más probable —`GENERAL_SYNTHETIC_LEXICAL_CONVERGENCE`— es también la que
conserva la lectura de P1.** Se declara aquí, antes de los datos.

### 0.2 Decisiones declaradas de alcance (2026-08-06)

No son enmiendas de instrumento: son decisiones de la investigadora sobre qué se ejecuta, tomadas
bajo restricción de tiempo declarada y **antes de computar métrica alguna sobre twinpop**. Se
registran porque acotan lo que el brazo puede afirmar.

**(a) Silencios técnicos: confusor retirado de la interpretación.** El desbalance de silencios
forzados entre `enriched` (corrió primero, con silencios técnicos) y las condiciones posteriores
—listado como confusor (c)— **se retira por decisión de la investigadora**: el brazo se compara
contra la última versión ejecutada del experimento, con la misma guía, el mismo prompt de
moderador, reflexiones y presupuesto de tiempo. Los 6 configs se clonan de
`macho_meals_fg{3,4}_run01.json` y G5 certifica que solo difieren en `session_id`, `run_label` y
`participants`. Consecuencia que hay que nombrar: cualquier residuo de ese desbalance queda
**dentro** de la brecha human–synthetic (contraste A) y no se descuenta. **No afecta al contraste
B** (twinpop vs demoonly), que es el único contraste que el brazo existe para estimar, porque
ambas condiciones se ejecutan bajo el mismo régimen.

**(b) G3(b), G2 capa 2 y G2 capa 3: NO EJECUTADAS.** Se declaran no corridas, no fallidas ni
pasadas. Razón, tomada de las auditorías previas y no post hoc: la capa 2 fue caracterizada por los
revisores como productora de *"un suelo y un techo, no una decisión"*; la capa 3 ya estaba
reclasificada como **descriptiva sin puerta ni umbral**; y G3(b), tras la neutralización de género
exigida por la propia auditoría, queda **cerca del azar por construcción**. Ninguna reporta
resultado en la tesis. Se documenta que G3(b) era la única cuya activación habría obligado a
regenerar las 8 narrativas: al no ejecutarse, **la ausencia de estereotipia lexical no puede
afirmarse**, y el brazo no la afirma. Queda como limitación declarada, no como resultado nulo.

### 0.25 RESULTADO PRIMARIO — P1 refutada en FG3 (2026-08-06)

Codificación Tier-1 de los 6 documentos twinpop con el evaluador congelado
(`gemini-3.5-flash`, batch, configuración idéntica en 10/10 campos a la de los 32
canónicos, verificada contra el job devuelto). El cálculo reproduce lo que el corpus ya
había publicado antes de que este brazo existiera: `demoonly` FG4 en cero tres veces,
denominadores 6 y 10, y la separación sin solapamiento de FG3.

**FG3 (caso primario, lectura de magnitud; denominador 10):**

| condición | réplicas | media | precisión |
|---|---|---|---|
| `enriched` (full) | 0.40 / 0.30 / 0.40 | **0.3667** | 1.000 |
| `twinpop` (placebo) | 0.40 / 0.30 / 0.30 | **0.3333** | 1.000 |
| `demoonly` | 0.10 / 0.10 / 0.10 | **0.1000** | 1.000 |

`twinpop` dista **0.0333** de `full` y **0.2333** de `demoonly` — siete veces más cerca
del tratamiento que del control. **P1_REFUTED_twinpop_closer_to_full.**

**FG4 (prueba de suelo, sin lectura de tamaño):** `twinpop` 0 / 0.1667 / 0.1667 frente al
cero absoluto y sin varianza de `demoonly`. La pregunta binaria que FG4 responde —*¿el
grupo twin se despega de cero?*— se responde **sí, en 2 de 3 réplicas**. Su veredicto
formal por distancia favorece a P1, pero §2.1 le niega lectura de magnitud, así que **no
decide**.

**Lectura sustantiva.** La riqueza censal *topicalmente irrelevante* recupera casi toda la
recall temática que consigue el enriquecimiento psicométrico (0.3333 vs 0.3667, un 91 %).
Eso debilita la atribución del enriquecimiento a su contenido psicométrico o alimentario:
riqueza biográfica genérica llega casi igual de lejos. Es el resultado que el brazo existía
para poder detectar, y es **contrario a la predicción pre-registrada**.

**Límites que hay que declarar con el resultado.** (i) En FG3 la precisión está en techo
1.0 en las tres condiciones, así que recall es el único eje discriminante. (ii) Con n=3, las
réplicas de `twinpop` y `enriched` se solapan casi por completo, mientras que ninguna se
solapa con `demoonly`: la separación que el dato sostiene es *sintético-rico vs
sintético-pobre*, no *twinpop vs enriched*. (iii) FG3 y FG4 apuntan en direcciones
distintas, y sólo FG3 tiene lectura de magnitud.

---

### 0.3 Reparación del reconocedor de Q5 (clase iv)

**Qué se observó.** Dos de las seis sesiones twinpop (`fg3_run02`, `fg3_run03`) no pudieron
anclarse en Q5 bajo los marcadores congelados. Los 30 runs canónicos sí anclan, así que la regla
nunca se había enfrentado a este caso.

**Qué NO era.** No era un defecto de sesión. Se inspeccionaron los enunciados: el moderador **sí
planteó la sección 5** y la parafraseó, que es comportamiento permitido y que el propio segmentador
contempla (*"las reformulaciones no abren una sección nueva"*). `fg3_run02` preguntó *"…for any of
you to find it genuinely appealing? Or for the men you know to?"*, que el segundo marcador falla
por una palabra (`the men`, no `to men`). Las sesiones están sanas; **el reconocedor se quedaba
corto**.

Se descartó por eso archivarlas como `ARCHIVED_TECHNICAL_OUTLIER` siguiendo el precedente de
`fg4_run02`: aquél fue un defecto real de sesión (6 silencios forzados), y etiquetar así una sesión
válida sería falsear el registro. También se descartó relanzarlas: sería descartar datos válidos
porque el instrumento de medida no llega.

**La reparación y su condición de admisibilidad.** Se añade `appealing` a secas a los marcadores de
Q5, **y sólo se aplica mientras sea demostrablemente inerte**: debe reproducir el hash de sección de
los 30 runs canónicos y no mover ninguna sección twinpop ya anclada. `inertness_gate()` lo verifica
**en cada ejecución**, no una sola vez; si dejara de cumplirse, el ensanchamiento se retira solo y
no se corta nada con él. Resultado medido: **0 de 30 canónicos alterados, 0 de 4 twinpop movidos**.
Bajo esa condición no es "una regla más ancha para twinpop" —lo que haría incomparables las
secciones— sino la misma regla con un reconocedor más ancho, verificado.

**Lo que la reparación NO rescata.** `fg3_run03` sigue sin resolver y **no se rescata**. No contiene
ni una vez `appealing`, `attractive` ni `appeal`: plantea la sección 5 con el vocabulario de Q4
(*"what would it take"*, *"what would need to shift"*). Alcanzarlo exigiría anclar en lenguaje de
Q4, que podría mover la frontera Q4/Q5 en otros runs. **Se excluye y se reporta.**

**Estado resultante del corpus:** FG3 2/3 réplicas, FG4 3/3. El pre-registro asigna a FG3 la lectura
de **magnitud** y a FG4 la de **suelo**; con 2 réplicas, la dispersión de FG3 se reporta pero
cualquier lectura de magnitud queda **más débil de lo pre-registrado**, y así debe declararse.

**Reemplazo de `fg3_run03` — protocolo fijado ANTES de correrlo.** Autorizado por la investigadora
el 2026-08-06, con ninguna métrica de R4 computada. Sigue el precedente de `fg4_run02`
(`ARCHIVED_TECHNICAL_OUTLIER` → run04 de reemplazo → conjunto canónico de tres), con la diferencia
declarada de que aquí el defecto **no es de la sesión sino del reconocedor**, por lo que `run03` se
archiva como `ARCHIVED_UNANCHORABLE_Q5_BOUNDARY` y **no** como outlier técnico.

Las tres condiciones que lo hacen admisible, fijadas antes de la ejecución:

1. **Una sola sesión de reemplazo** (`fg3_twinpop_run04`). Si tampoco ancla, **se para** y FG3 se
   reporta con 2/3 réplicas. No hay run05.
2. **Se retiene pase lo que pase.** El resultado de run04 entra en el registro anclara o no. No se
   corre "hasta que salga bien".
3. **`run03` se conserva**, con su transcripción y su ventana, y se reporta como excluida.

El riesgo que esto acota, nombrado explícitamente: correr reemplazos hasta que el detector ancle
seleccionaría sesiones por el vocabulario que usó el moderador, propiedad que puede correlacionar
con cómo transcurrió la conversación. Un solo reemplazo con retención obligatoria acota esa
selección a un intento; no la elimina, y por eso queda declarada.

**Resultado ejecutado (2026-08-06).** `fg3_twinpop_run04` corrió, completó 7/7 secciones y **ancló
Q1–Q5**. Ancló **con los marcadores congelados**, sin necesitar el ensanchamiento de §0.3: el
ensanchamiento sólo rescató a `run02`, y esa sigue siendo la única sección que depende de él.

**Conjunto canónico de FG3-`twinpop`: run01, run02, run04.** Tres réplicas, con lo que la lectura de
**magnitud** que el pre-registro asigna a FG3 se recupera. `run03` queda archivado como
`ARCHIVED_UNANCHORABLE_Q5_BOUNDARY`, con su transcripción y su ventana conservadas, y el script lo
re-segmenta y lo reporta en cada ejecución con `in_corpus: false`, de modo que la exclusión
permanece visible en la salida en lugar de volverse una ausencia invisible.

**Corpus twinpop final: 6 runs, 30 secciones** (FG3 3/3, FG4 3/3).

**Patrón a declarar, no defecto.** Dos de las tres réplicas de FG3 (`run02` 342, `run04` 338)
superan el máximo canónico de residuo de cierre (329). Es un patrón, no una anomalía aislada: las
sesiones twinpop de FG3 cierran algo más largo que cualquier run canónico. El residuo es texto de
cierre excluido por construcción y no entra en ningún análisis, así que se marca y se retiene; se
declara aquí porque un patrón consistente merece nombrarse aunque no propague.

**Marca retenida, no exclusión.** `fg3_run02` tiene un residuo de cierre de 342 palabras frente al
máximo canónico de 329 (banda medida sobre los 30, no fijada a mano). Se **marca y se retiene**: el
residuo es el cierre, excluido por construcción, que no entra en ningún análisis. Marcas y
exclusiones se registran en listas separadas para que un consumidor no pueda confundirlas.

---

## 1. Reparaciones de esta ronda

Las tres puertas pendientes estaban mal construidas y **ninguna llegó a ejecutarse**. Lo que la
auditoría cazó antes de gastar:

**G3(b) habría disparado por pronombres, no por caricatura.** Las narrativas llevan `he` 43 /
`his` 35 en la rama masculina y `her` 73 / `she` 65 en la invertida. El evaluador solo tenía que
elegir la que dice "he": habría devuelto ~24/24, superado el umbral de 17/24 y **ordenado
remuestrear las ocho narrativas por un artefacto de pronombres**. La neutralización que la entrada
6 exige no estaba implementada. Ahora lo está, con **sub-puerta verificada** (0 tokens de género
restantes) y control de pronombres plantados.

*Consecuencia sobre la advertencia pre-declarada:* estaba **invertida**. Decía que el evaluador
estaría cerca del azar por construcción; con pronombres estaba en el **techo**. Reescrita: con la
superficie de género eliminada y los atributos censales fijos, las dos narrativas de un par son
casi paráfrasis, de modo que el evaluador queda cerca del azar por construcción y **un no-disparo
es evidencia débil, nunca evidencia de ausencia de caricatura**.

**Sin contrapeso de posición.** `real = A` en las 24 parejas; un juez con sesgo posicional devuelve
24/24 solo. Ahora la asignación A/B se **aleatoriza por pareja** con semilla `20260805`, el mapeo
se registra y la respuesta se des-mapea antes de puntuar.

**El prompt de G3(b) no existía en el código.** Escrito y fijado.

**El control negativo estaba garantizado por construcción.** 415–418 palabras contra 241–256
(**1.7×**) y de otro género —el bloque de instrucciones de comportamiento, no un bosquejo de vida—.
Degradado a **lectura de suelo explícitamente no emparejada**. `control_inverted` pasa a primario
(mismo prompt, campos y longitud) y se añade un **control barajado**: recombinación por frases
entre agentes — mismo género, registro, longitud y vocabulario, ninguna persona coherente. Es el
único control que aísla lo que la capa 2 dice medir.

**La lista de redacción de la capa 3 pisaba el codebook.** `building` y `training` son lenguaje de
gimnasio, es decir el subtema **B.3 "Necessary"** que la sonda debe poder detectar. Eliminados.

**Residuos de G1, cerrados.** La puerta estaba **duplicada** entre producción y controles (podían
divergir y los controles seguir pasando): ahora se importa una sola definición. `narrative_sha256`
se registraba y **nunca se afirmaba**: ahora se recalcula sobre el texto de generación y se exige
igualdad con la prosa del payload — sin eso, el resto de comprobaciones de G1 comparaban el payload
consigo mismo y no decían nada sobre la procedencia. Y G1 corre ahora con **ambos ajustes** de
`inject_participant_intro`, como G0.

G1 pasa 8/8 con **siete** comprobaciones. Los cinco controles siguen correctos.

## 2. Entrada 5 — léxico, reemitido con su antes y después

El léxico cambió **después de ver resultados**, así que el cambio queda auditable:

| | delta medio por celda | positivas |
|---|---|---|
| léxico de 75 términos, sin variantes | +0.238 | 6/8 |
| **léxico de 77 + variantes explícitas** | **+0.293** | **5/8** |

t = 2.03, df 7, **p una cola = 0.041** sobre la dirección pre-registrada.

**El informe no puede conservar la frase "sin señal de amplificación".** La formulación correcta es:
*efecto pequeño, marginal, n=8, con un instrumento reparado que antes subdetectaba*.

## 3. Entrada 11 — auditoría de plantilla, cifra corregida

Los tres campos se unían con **espacio**, así que con `re.M` el ancla `^` solo casaba en la posición
0 y **los abridores posicionales nunca se ejecutaron** (10 ocurrencias en vez de 21). Corregido:

```
texto completo        0.4322
sin estructurales     0.4456     delta +0.0134, 2.5% de palabras
```

**Evidencia positiva de que la lista se fijó a priori**, y conviene que conste: cuatro patrones
**no disparan ni una vez** en las 48 narrativas. Nadie que construya la lista mirando lo que recurre
escribe cuatro patrones muertos.

**Corrección de redacción.** Decir que los 4-gramas recurrentes son "sustantivos del censo, no
plantilla" confunde contenido con realización: `"owned with a mortgage"` ×7 es la **fórmula del
renderizador** para el valor censal `Owned: Owns with a mortgage or loan`. El contenido es del
censo; la superficie es plantilla compartida. Se mantiene la regla de no eliminar contenido
sustantivo repetido, y por tanto la conclusión correcta es: **las aperturas y conectivos aportan
~+0.013; las realizaciones superficiales de variables censales no se midieron, por decisión
declarada.**

Y un dato que convierte la alegación del confusor de género textual en demostración: **el 69% de
los aciertos del léxico en las narrativas twin son campos censales renderizados** — `car` (22,
transporte al trabajo), `mortgage` (12, tenencia), `driving`/`management`/`construction` (ocupación),
`supervisory`/`team` (supervisa). Una narrativa que renderiza 21 atributos censales es mecánicamente
densa en ese vocabulario; un fragmento humano de una conversación sobre comida jamás menciona su
hipoteca.

## 4. Entrada 9 — regla de R4 corregida: rangos, disyunción y tabla exhaustiva

La regla de la v5 ("menor que **ambos** referentes") tenía un hueco que el propio caso FG4
demuestra: con `enriched` en [0.2410, 0.2616] y `demoonly` en [0.2983, 0.3260], un twin en 0.30
**cae dentro del rango de demoonly** —voces tan homogéneas como el brazo sin persona alguna— y la
regla **no dispara porque enriched está por debajo**. El referente menos convergente actúa de
escudo. Y es grave porque demoonly es además el comparador de recall de P1: twin ≈ demo en recall
*y* en convergencia confunde "la riqueza genérica no ayuda" con **"la riqueza nunca se expresó"**.

**(a) Rangos, no puntos.** Con 3 réplicas, "menor que" entre medias es ruido. *A distinguible de B*
⟺ sus rangos min–max **no se solapan**. Determinista, sin umbral inventado.

**(b) Disparador disyuntivo, por FG.** La dirección **confirmatoria** de P1/P5 queda comprometida en
un FG si el rango twin queda **(i)** enteramente por encima de ambos rangos referentes, **o (ii)**
solapa o supera el rango del referente **más convergente de ese FG** —demoonly en FG4, enriched en
FG3—. Alcanzar el peor nivel ya observado basta para que la homogeneización sea explicación
alternativa suficiente; que el otro referente esté por debajo no exculpa.

*Razón de fondo:* **la inversión FG3/FG4 demuestra que la convergencia no es monótona en riqueza de
persona**, así que ninguna regla de orden sobre esta métrica puede sostener un bicondicional.

**(c) Tabla exhaustiva.** Toda configuración posible tiene etiqueta pre-asignada:

| Relación de rangos (por FG) | Etiqueta |
|---|---|
| twin solapa ambos referentes, los tres lejos de human | `GENERAL_SYNTHETIC_LEXICAL_CONVERGENCE` |
| twin enteramente por encima de ambos | `TWINPOP_INCREMENTAL_COLLAPSE` |
| twin solapa o supera el referente más convergente, sin superar al otro | `TWINPOP_INCREMENTAL_COLLAPSE` *(al nivel del peor referente observado)* |
| twin estrictamente entre ambos, sin solapar ninguno | **`INTERMEDIATE_CONVERGENCE`** *(nueva)* |
| twin enteramente por debajo de ambos, sin solapar human | `RELATIVE_IMPROVEMENT_HUMAN_GAP_REMAINS` |
| twin solapa el rango human | `EXPLORATORY_HUMAN_LIKE_DISTINCTIVENESS` *(sujeto a revisión de longitud y contenido)* |
| solapamientos que impiden ordenar | `INCONCLUSIVE` |

`INCONCLUSIVE` queda **reservada** para solapamientos que impidan ordenar, no como cajón de sastre.
**La etiqueta nunca sustituye a las distancias y deltas reportados: viajan siempre juntos.**

## 5. Verificación de manifestación de la manipulación — formalizada antes de las 5 sesiones

La observación de Andrew (censo *vive solo, nunca casado*: 4× "live on my own", 0× "my wife";
casados 7–8× "my wife"; divorciado 0) es **no planificada, de n=1 y con dirección favorable**. Para
que sea reportable y no cherry-picking, se formaliza **ahora**, antes de las 5 sesiones restantes:

- Categorías fijadas: **estado de pareja**, **tamaño de hogar**, **consistencia ocupacional**.
- Regla de conteo por agente y por sesión, sobre las **6 sesiones**.
- **Se reporta sea cual sea su dirección.**
- La versión del piloto se declara en métodos como **la observación que motivó el chequeo**, no como
  resultado.

## 6. Orden de ejecución de las puertas pendientes

El orden anterior era el peor posible: si G3(b) dispara, la entrada 6 **ordena remuestrear las
narrativas**, invalidando toda llamada de capa 2 y 3 hecha sobre las actuales.

1. **G3(b)** — 24 llamadas. Única puerta cuyo disparo fuerza regeneración, y la más barata.
2. **Sonda de varianza del evaluador** — 3 llamadas. Con `temperatura no transmitida` y `thinking
   unpinned` el evaluador puede ser determinista; entonces la regla ≥2/3 es decorativa y la capa 2
   baja de 72 a 24.
3. **Capa 2** — 24 o 72, más 24 si se usa el control barajado.
4. **Capa 3** — 48, la más cara por unidad y ya solo descriptiva.

**Límite declarado de la capa 2:** con `control_inverted` casi-paráfrasis (demasiado fuerte) y
`control_no_narrative` de otro género (demasiado débil), la capa puede producir **un suelo y un
techo, no una decisión**. Declarado antes de correrla.

## 7. Licencia UKDS — condición ABIERTA

Un "adelante" verbal no la resuelve; deja el riesgo transferido a la tesis. Falta como documento:

1. **Quién verificó, qué cláusula de la EUL de SN 9154, en qué fecha, con qué conclusión**, citando
   el texto sobre procesamiento o divulgación de datos a nivel de registro por terceros.
2. **Hechos del procesamiento:** 21 atributos por registro, 24 registros (48 renderizados con las
   gemelas), transmitidos a la API de Anthropic; política de retención del proveedor citada.
3. **Salvaguarda que nadie había mirado:** las narrativas son **obras derivadas de registros
   individuales salvaguardados**. Antes de publicar cualquiera verbatim en la tesis o sus anexos,
   verificar las reglas de output del UK Data Service; si hay ambigüedad, consulta escrita al UKDS
   y su respuesta archivada.

Es la única condición que **ninguna salvaguarda metodológica puede sustituir**.

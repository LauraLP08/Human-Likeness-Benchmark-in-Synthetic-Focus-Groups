# Pre-registro — Brazo twin poblacional (FG3 + FG4)

*4 de agosto de 2026. **Versión 3**, tras dos rondas de revisión adversarial con dos revisores de
mandato disjunto (metodológico e ingeniería de simulación). Redactado antes de generar ninguna
persona, ningún config y ninguna transcripción.*

**Estado: `EXPLORATORY_NOT_CONFIRMATORY`.** Fuera de `frozen_evaluation_spec.md`. No modifica
ningún brazo, config, prompt ni directorio de salida existente. No descarga ningún indicador del
marco ni altera ningún resultado ya reportado.

---

## 0. Por qué existe este brazo

| Brazo ya corrido | Qué ve el agente participante |
|---|---|
| `full` | identidad + `diet: Meat eater` + consumo + 5 escalas psicométricas + `notes: "Recruited as a regular meat eater."` |
| `demoonly` | identidad (nombre, edad, género, ubicación). Nada más. |

Recall temático medio **+0.121** a favor de `full`, 4 de 5 grupos en esa dirección. Ese número
admite dos lecturas que el diseño actual no separa: **instrumentación** (ayudó conocer los
puntajes medidos, que solo existen si se administran instrumentos a humanos reclutados) o
**riqueza genérica** (ayudó que el agente tuviera cualquier biografía concreta).

La objeción es directa: *"usted no demostró que medir masculinidad sirva; demostró que dar más
texto al agente sirve."* El brazo twin es el placebo que falta: **mismo volumen de persona que
`full`, con contenido temáticamente irrelevante**. Riqueza sin principio activo.

**Alcance del reclamo externo, acotado.** Un twin anclado al roster real es una **instancia
favorable** de la condición que venden los proveedores de synthetic respondents, no esa condición:
el proveedor no dispone del roster. Con dos grupos y un dominio, no se afirma más.

---

## 1. Diseño — gradiente de tres puntos

```
demoonly            twinpop                full
(sin narrativa   (narrativa censal,     (enriquecimiento
 provista)        tema irrelevante)      temáticamente relevante)
```

### 1.1 Confusores declarados

**(a) Confusión de paquete `full` − `twinpop`.** Difieren simultáneamente en procedencia,
relevancia temática, acoplamiento a la identidad real, **encuadre instruccional** (§3.4) y **la
línea de dieta** (§3.1). No es aislamiento de factor: es comparación de paquete. La comparación
que sí aísla es `demoonly` − `twinpop`.

**(b) `demoonly` − `twinpop` tampoco aísla un factor único**: añade a la vez anclaje censal y
renderizado narrativo. Si `twinpop ≈ full`, no podrá separarse "grounding censal" de "mero volumen
de texto plausible". El control de texto-rico-irrelevante-sin-censo queda como extensión futura.

**(c) Desbalance de silencios forzados (spec §9).** `full` se generó por la ruta antigua (2.44%;
14 de 15 runs afectados, rango 1.39–3.90%); `demoonly` por la actual (0.04%). `twinpop` correrá
por la actual: **`twin − demo` emparejado en ruta; `twin − full` no.** Dirección **indeterminada**
por declaración del spec, D8 DECLINED — no se afirma que sea conservador, no se ajusta el
denominador, no se usa como predictor.

**(d) Selección de grupos condicionada a resultados observados.** FG3 y FG4 se eligieron por tener
las brechas mayores entre los cinco (§2). Con selección sobre extremos, parte de la brecha
observada es ruido: riesgo de regresión a la media.

**(e) Ventanas de contexto y fechas de generación.** Los brazos se generaron con semanas de
diferencia. Se registran fechas y model-ids exactos de las sesiones `twinpop`.

**(f) El actor y el autor de la persona son de la misma familia.** El renderizador de personas es
Claude (§3.6). El agente que interpreta la persona también. Se declara como confusor de paquete
adicional. **La independencia que el marco §3 protege —generador ≠ evaluador— queda intacta**, y
la salvaguarda que detecta caricatura (§4.4a–b) opera con independencia de quién redactó.

---

## 2. Grupos: FG3 (primario) + FG4 (secundario)

| FG | recall full | recall demo | brecha | precisión full | precisión demo | rol |
|---|---|---|---|---|---|---|
| FG1 | 0.375 | 0.3333 | +0.0417 | 1.0 | 1.0 (techo) | descartado |
| FG2 | 0.3333 | 0.3810 | −0.0476 | 0.60 | 0.6833 | descartado |
| **FG3** | 0.3667 | 0.1000 | **+0.2667** | 1.0 | 1.0 (techo) | **primario** |
| **FG4** | 0.2778 | 0.0000 | **+0.2778** | 0.4222 | 0.0000 | **secundario** |
| FG5 | 0.600 | 0.5333 | +0.0667 | 0.9167 | 0.8667 | descartado |

### 2.1 Los dos grupos hacen trabajos distintos: FG3 mide magnitud, FG4 prueba el piso

Expresado en **códigos acertados**, que es la unidad real de la medida
(`per_run_metrics.csv`, columna `shared_n` sobre `human_present_n`):

| | denominador | `full` | `demoonly` | brecha típica |
|---|---|---|---|---|
| **FG3** | 10 subtemas | 3, 4, 4 códigos | 1, 1, 1 código | **+2 a +3 códigos** |
| **FG4** | 6 subtemas | 3, **1, 1** códigos | 0, 0, 0 códigos | **+1 código en 2 de 3** |

**FG3 — caso discriminante de magnitud.** Separa sin solapamiento en las tres réplicas, con
varianza nula del lado `demoonly` (1 código exacto, tres veces) y `full` estable en 3–4. Sobre 10
subtemas la granularidad es 0.1 por código y el punto medio de la regla de P1 cae en 2.33 códigos:
el veredicto se decide entre 2 y 3 códigos, con margen y con extremos estables.

**FG4 — prueba de piso, no réplica cuantitativa.** Sus dos canales descansan en el mismo run04
(recall 0.50 y precisión 0.60 salen ambos de esa corrida; las otras dos dan 0.1667 y 0.3333). Con
denominador 6, un código vale 0.1667, así que en dos de tres réplicas **toda la brecha de FG4 es un
único subtema** — el mínimo no nulo que el instrumento puede producir. Su punto medio de P1 cae en
0.83 códigos: el veredicto se decidiría según el twin acierte **un** subtema o **ninguno**.

Pedirle a FG4 una cifra de magnitud sería sobre-interpretar una corrida. Lo que sí aporta, y que
ningún otro grupo del corpus aporta, es un **suelo absoluto y sin varianza**: `demoonly` acertó
**cero de seis códigos, tres veces seguidas**. La pregunta que FG4 responde es por tanto binaria y
cualitativa — **¿el grupo twin se despega de cero?** — y su desenlace es la viñeta que el marco
pide para la integración cuali-cuanti: *no reprodujo nada del grupo humano* frente a *reprodujo
algo*.

FG4 conserva además el único canal de **precisión** no nulo del par, con la misma fragilidad
declarada (§6, P3).

**Consecuencia registrada a priori:** P1 y P5 se evalúan como **magnitud en FG3**; en FG4 se
evalúan como **suelo** (cero vs. no-cero), sin lectura de tamaño. P3 solo es evaluable en FG4.

### 2.2 Índices de réplica: no alinean

Conjunto canónico de FG4-`full`: **run01, run03, run04** — `macho_meals_fg4_run02` archivado como
`ARCHIVED_TECHNICAL_OUTLIER` (6 silencios forzados). Toda comparación es por **medias de brazo**,
nunca por par de índice; la clasificación por réplica se reporta como dispersión.

### 2.3 FG3 arrastra `GROUP_LEVEL_ONLY_RANDOM_LINKAGE`

Spec §10: tras un error de PID, las 5 filas de encuesta de FG3 —demografía, psicometría y consumo
**juntas**— se asignaron a los 5 nombres por emparejamiento aleatorio 1:1. Verificado en
`INSTRUCTIONS_MACHO_MEALS_FG3_AGENT_BUILD.md`: cada valor es dato genuino de FG3; solo la
correspondencia persona↔fila es arbitraria.

El **conjunto** de celdas es genuino; solo el nombre que le toca a cada celda es arbitrario. Como
los tres brazos usan el mismo roster, la arbitrariedad es **constante entre brazos y se cancela**.
El brazo es de nivel de grupo, lo único que FG3 soporta.

El requisito del spec de reportar "con y sin FG3" se satisface reportando **FG4 solo** como
sensibilidad. **Se declara donde se reporte** que esa sensibilidad descansa sobre el grupo más
frágil del diseño (§2.1).

### 2.4 Rosters (8 personas)

| Agente | Edad | Urban/Rural | Región |
|---|---|---|---|
| mm_fg3_nick | 40 | Suburban | North West |
| mm_fg3_andrew | 45 | Suburban | South East |
| mm_fg3_john | 45 | Suburban | South West |
| mm_fg3_paul | 47 | Suburban | South East |
| mm_fg3_daniel | 48 | Suburban | East of England |
| mm_fg4_james | 50 | Suburban | South East |
| mm_fg4_mark | 52 | Village or Rural | East of England |
| mm_fg4_gregor | 53 | Urban | North West |

Todos `Male`, `country: UK`. FG3 y FG4 son enteramente ingleses: una sola fuente censal (ONS
Census 2021 England & Wales vía Nomis); no se requiere NRS ni NISRA.

**FG1 como tercer grupo: descartado** — sería una segunda selección condicionada a resultados ya
observados y su brecha (+0.0417) está dentro del ruido. Extensión que exigiría adendum propio.

---

## 3. Construcción de las personas

### 3.1 Qué se conserva y qué se omite

**Idéntico al participante real:** `name`, `age`, `gender`, `location.{urban_rural, region,
country}`. El nombre se conserva deliberadamente — los nombres de pila cargan señal étnica y
sustituirlos introduciría un confusor de etnicidad; además mantiene comparabilidad con `demoonly`.

**Ausente por membresía de clave:** `persona.demographics.diet`, `persona.food_consumption`,
`psychometric_scores`, `simulation_config.notes`. Este último se renderiza verbatim como
*"Additional context: Recruited as a regular meat eater."*: si sobreviviera, las ocho personas
"agnósticas" llevarían impreso el tema del estudio y el brazo quedaría invalidado antes de la
primera sesión.

**Etnicidad y país de nacimiento: se omiten.** Inferirlas del nombre no está validado; muestrearlas
del censo rompe la coherencia con el nombre conservado e inyecta el vector de amplificación de
estereotipo (§4.4) sobre la dimensión identitaria del estudio. `demoonly` tampoco las tenía. Esto
aparta el procedimiento del método Nemotron completo y se declara.

**Consecuencia: `twinpop` = `demoonly` + narrativa.** La línea *"Your diet: Meat eater."* que
`full` sí renderiza pasa a la diferencia de paquete `full` − `twinpop` (§1.1a).

### 3.2 Muestreo censal

Para cada celda (varón, edad exacta, urban_rural, región) se extraen de las condicionales del
Census 2021 (England & Wales, ONS, vía Nomis — abierto, sin registro): ocupación / NS-SEC, nivel
educativo, composición del hogar y estado civil, régimen de tenencia.

**Se muestrea una fila de microdatos por candidata**: un registro individual real del Census 2021
(SN 9154, muestra salvaguardada del 5% a nivel de región), emparejado por región, sexo y **edad
exacta**. Una fila es una persona real, de modo que **la distribución conjunta viene dada y no se
reconstruye**. Es el análogo estructural de lo que Twin-2K-500 aporta para Estados Unidos.

**Corrección registrada.** Dos versiones anteriores de este documento describían un muestreo desde
tablas agregadas. La primera afirmaba recuperar la conjunta condicional; la segunda ya reconocía
que las tablas de resumen temático de ONS son univariadas por geografía. Ejecutado, aquel método
produjo **personas lógicamente imposibles** (un hombre de 47 años en un hogar definido como "todos
de 66 o más") y **combinaciones incoherentes** (alto directivo sin cualificaciones), porque sorteaba
marginales independientes. El detalle completo, con las cifras, está en la entrada 2 del adendum.

**Twin-2K-500 descartado, con razón documentada:** su `QID11` es *"Which part of the United States
do you currently live in?"*; su edad es un bracket de texto; su perfil psicológico no está mapeado
(`scripts/twin2k500_mapping.yaml`, QIDs de matriz comentados). Sustituir Reino Unido por Estados
Unidos en un estudio sobre carne y masculinidad introduciría un confusor cultural sobre la
variable dependiente misma.

### 3.3 Ranura de esquema — nombrada, porque la mayoría se descartan en silencio

Verificado ejecutando el renderizador real:

| Ranura | ¿Llega al modelo? | Causa |
|---|---|---|
| `simulation_config.notes` (string) | Sí | `participant_agent.py:399-402` |
| `persona.<clave>` como **dict** | **Sí** | fallback `:368-376`, exige `isinstance(val, dict) and val` |
| `persona.<clave>` como **string** | No | el fallback la descarta |
| `persona.psychological_profile` | No | clave saltada incondicionalmente `:369` |
| `persona.demographics.narrative`, `study_context.*`, nivel superior | No | nunca leídas |
| `opening_intro` | No | requiere `inject_participant_intro`, prohibido por §5 |

**Ranura fijada: `persona.background` como dict de prosa**, claves `working_life`,
`home_and_household`, `week_and_hobbies` (minúscula pura; el renderizador aplica `.capitalize()`,
que pone en minúsculas todo lo demás).

**Nota de posición serial:** una vez §3.4 crea una rama dedicada, la posición **la fija el punto de
inserción en la función, no el orden de claves del JSON**. Por eso §3.4 especifica el punto exacto.

### 3.4 Cambio de código — autorizado, acotado, con puerta de hash

El enriquecimiento de `full` llega con guardarraíl: *"speak from these naturally — don't list
them"* (`:350-365`) y *"internal orientations, not talking points"* (`:382-394`). Las ranuras
disponibles para `twinpop` renderizan *"Additional context about you:"* a secas.

Evidencia de que importa: en `macho_meals_fg3_run01`, primer turno de John — *"I'm here because,
well, I eat meat regularly — that's sort of what you're looking at today, I gather."* Paráfrasis
directa de `notes`. **Una sola frase ya produjo recitación**; 250 palabras la producirían
masivamente.

**Cambio autorizado por la investigadora (2026-08-04), especificado literalmente:**

1. Rama dedicada para `persona.background` con encabezado paralelo al de `food_consumption`
   (*"speak from these naturally — don't list them…"*), **no-op cuando la clave está ausente**.
2. **Colocarla inmediatamente después del bloque `food_consumption` (tras `:365`, antes del bucle
   genérico de `:368`)** — así ocupa la misma posición serial que el enriquecimiento de `full`.
3. **Añadir `"background"` a la tupla de salto de `:369`**, hoy
   `("demographics", "food_consumption", "psychological_profile")`. **Sin este paso el bloque se
   emite dos veces** —una por la rama nueva y otra por el bucle genérico—, el volumen se dispara a
   ~470 palabras netas, §3.5 queda invalidada y R1 cambia de perfil.

Ningún otro cambio: ni `orchestrator.py`, ni prompts, ni tests, ni configs existentes. Validación
en **G0** (§9).

### 3.5 Volumen — banda numérica sobre el prompt renderizado

Medido sobre el prompt real de `mm_fg3_andrew`, descontando `_BEHAVIOUR_INSTRUCTIONS`:

| Brazo | chars | palabras |
|---|---|---|
| `full` (identidad + consumo + disposición + notes) | 1 693 | 289 |
| `demoonly` (identidad sola) | 183 | 32 |
| **Enriquecimiento neto** | **1 510** | **257** |

Descomposición de las 257: **49 de sobrecarga** (encabezados y etiquetas) + **208 de contenido**.

**Objetivo fijado: 220–300 palabras netas** (±15% de 257). Con `background` de tres claves la
sobrecarga es ~25 palabras, luego el presupuesto de prosa es **195–275 palabras → 65–92 por clave,
centro ~72**.

**G4 mide el bloque renderizado completo, encabezado y etiquetas incluidos** — así se midieron las
257 de `full`; medir solo la prosa introduciría un sesgo de 25 palabras a favor de `twinpop`.
Fuera de banda ⇒ remuestrear narrativa, **nunca rellenar** (el relleno en este dominio tiende a lo
temático, que es justo lo prohibido).

### 3.6 Renderizador: Claude, con el confusor declarado

`.env` contiene únicamente `ANTHROPIC_API_KEY` y credenciales Google/Gemini; **no hay credencial de
una tercera familia** y la investigadora confirmó (2026-08-04) que no dispone de ninguna.

**Decisión: renderiza Claude.** Descartado que renderice Gemini: cerraría el bucle sobre la vara de
medir —el mismo modelo escribiría las biografías y luego codificaría las transcripciones donde
esas biografías dejaron huella—, lo que es peor que el bucle del lado del actor. El marco §3
protege la independencia de **medición** (generador ≠ evaluador) y G7 la declara innegociable; esa
queda intacta. El confusor resultante se declara en §1.1f y la salvaguarda de §4.4a–b lo detecta
con independencia de quién redactó.

Model-id exacto, prompt de renderizado y hash se fijan en el adendum §11 antes de generar.

### 3.7 Restricciones del renderizador (verificadas sobre `:374`)

La viñeta es `f"  - {k.replace('_',' ').capitalize()}: {v}"`, interpolación cruda en una sola
línea. Por tanto, cada valor de prosa debe cumplir:

- **Sin saltos de línea.** Un `\n` interno rompe la estructura de lista: la segunda línea pierde el
  prefijo `  - `. Párrafo único.
- **Sin markdown ni comillas envolventes.** No hay escapado; entra tal cual.
- **Sin espacios al inicio o final.**
- **Claves en minúscula pura** (por el `.capitalize()`).
- **Orden de viñetas = orden de inserción del JSON.** Se fija en §11 para que las 8 personas sean
  estructuralmente idénticas.
- **Un dict vacío se salta en silencio.** Por eso G1 usa aserción de substring exacto y no un
  umbral de solapamiento.

---

## 4. Salvaguardas contra fuga temática

### 4.1 Lista negativa de dominio — único disparador de remuestreo

**Lista congelada y hasheada antes de generar**, independiente del codebook: alimentos, comidas,
cocinar, comprar comida, restaurantes, pubs, gimnasio / proteína / fitness, granja / animales,
salud, cuerpo, dieta, barbacoa / parrilla / asado; los cinco nombres de constructo psicométrico
más sus strings `direction` (que la auditoría existente demostró que llegan al prompt,
`condition_manipulation_audit.md` §4.1); y las restricciones de formato de §3.7.

**Presupuesto de generación, reconciliado:** se generan **3 candidatas por celda** (§4.5) dentro de
un tope de **5 generaciones por celda** contando remuestreos. Excederlo **detiene el brazo** y se
reporta como hallazgo ("no fue posible producir personas realistas agnósticas al tema"); no se
relaja la lista. Todo descarte se registra con su causa y el conteo se reporta.

### 4.2 El codebook no puede seleccionar — solo detener

Un filtro descarta-y-remuestrea keyed en el codebook haría que el codebook influyera
**causalmente** en qué personas entran a generación: contaminación inversa, el control seleccionado
contra la vara de medir. El marco §3 sí sanciona el otro mecanismo — *"el experimento se detiene
antes de correr"*.

**Regla fijada, y la distinción es seleccionar vs. detener:** cuando se detiene, no se elige nada.

| Capa | Keyed en | Consecuencia |
|---|---|---|
| §4.3 capa 1 (léxica, lista de dominio + tópicos de la guía) | documentos del lado generación | **remuestrea** |
| §4.3 capa 2 (semántica, 11 subtemas) | codebook | **detiene el brazo** |
| §4.3 capa 3 (conductual) | codebook | **detiene el brazo** |
| §4.4c (techo humano) | léxico de masculinidad | **remuestrea** |

Una parada documenta que la lista de dominio de §4.1 era insuficiente; se corrige la lista **una
vez, antes de generar**, y no se rodea remuestreando.

### 4.3 Auditoría de fuga — tres capas

La búsqueda de cadenas contra el codebook es insuficiente: sus 11 subtemas se llaman *Does
influence, No influence, Natural, Normal, Necessary, Nice, Unnatural, Insufficient, Not nice,
Extreme cases* — palabras corrientes, poder de detección casi nulo y falsos positivos constantes.
Peor, los cuatro dominios narrativos de §3.3 son **donde vive el codebook**: **B.2 "Normal"** tiene
como ejemplo canónico el asado del domingo; **B.3 "Necessary"** es gimnasio y proteína; **A.3**
describe *barbecuing, portion sizes, who does the cooking*.

**Capa 1 — léxica. Remuestrea.** Lista de dominio hasheada de §4.1 **más los tópicos de la guía de
discusión** (documento legítimo del lado generación). Único disparador de remuestreo por fuga, y
la única capa que entra en la selección de candidatas (§4.5).

**Capa 2 — semántica. Detiene.** Clasificación ciega con el evaluador congelado de cada narrativa
**final** contra los 11 subtemas: *"¿este texto hace más probable que su autor plantee alguno de
estos 11 códigos? ¿cuál, y cita el fragmento?"* Cualquier acierto no nulo ⇒ **parada del brazo**.
~8 llamadas.

**Capa 3 — conductual. Detiene.** Sonda de un turno, sin sesión, sobre las personas ya
seleccionadas: invocar `core.participant_agent.call_participant` (el código real) con
`conversation_history=[]`, `recent_transcript=None`, `hook=""`,
`participant_response_max_tokens=800`, `temperature=1.0`, y la pregunta de la Sección 3 de la guía
(*"Do you think your gender influences what you eat?"*), 3 muestras por persona. **Y la misma
sonda sobre los 8 agentes `demoonly` como control.** 48 respuestas, codificadas ciegas con el
procedimiento de G7. **Umbral numérico pre-fijado en §11**; superarlo ⇒ **parada del brazo**.

*Declaración obligatoria:* con `recent_transcript=None`, `call_participant` cae a
`base_message = moderator_utterance` (`:987-990`), de modo que la sonda **omite la envoltura**
*"Respond naturally to the conversation above…"* que sí lleva todo turno real. Es admisible porque
es idéntico en ambos brazos, pero **la sonda no es un turno de sesión y no se presentará como
tal**. Coste bajo un dólar; es además un pre-test de P3 antes de comprometer presupuesto.

### 4.4 Amplificación de estereotipo — G3 operacionalizada

Riesgo direccional: al renderizar una fila censal los LLM caricaturizan, y una caricatura de hombre
británico de mediana edad **performaría masculinidad más fuerte que el participante real**,
inflando aciertos justo en los constructos medidos — un falso "el twin cierra la brecha", la
conclusión más peligrosa posible.

**(a) Celda-control con género invertido.** Para **las 24 candidatas** (3 × 8 celdas) se genera su
gemela con el **género invertido** y todo lo demás idéntico, **emparejada por la misma semilla e
índice** — sin emparejamiento por semilla la comparación léxica no es pareada. Con un **léxico de
masculinidad congelado y hasheado antes de generar** (no el codebook: trabajo físico/manual,
deporte, competencia, mando, proveedor, autonomía), se calcula la tasa léxica en ambas ramas. Si
las masculinas puntúan por encima de las femeninas sobre dominios supuestamente neutros, **esa
diferencia es la amplificación, medida antes de gastar un dólar de sesión**.

**(b) Elección forzada ciega — sobre 24 pares, no 8.** Los pares de (a), neutralizados de nombres y
pronombres, en orden aleatorizado, al evaluador congelado: *"¿cuál de estas dos descripciones de
vida corresponde a alguien que endosaría más fuertemente las normas masculinas tradicionales?"*

Con 8 pares el binomial a una cola y α=.05 solo dispara con 7/8 (p=0.0352) u 8/8 (p=0.0039): una
amplificación **parcial** —el escenario realista— se leería como aprobada. Con **24 pares, 17/24 →
p=0.0320**: potencia real. ~48 llamadas cortas, sigue bajo un dólar. Superar el umbral ⇒
remuestreo.

**(c) Techo anclado en humanos.** Tasa léxica = **aciertos por 100 palabras**. Se compara contra el
**agregado de grupo** de las auto-descripciones humanas sobre rutina, trabajo, hogar y aficiones —
**no contra el homólogo individual**, porque §2.3 declara aleatoria la vinculación persona↔fila en
FG3. Techo = **media del grupo + tolerancia declarada en §11** (no el máximo: con 5 humanos en FG3
y 3 en FG4, el máximo es una sola persona y es inestable). Por encima ⇒ remuestreo.

**(d) Pre-chequeo de colapso, con consecuencia.** `scripts/collapse_metric.py` sobre los 8 textos
narrativos antes de generar nada más. **Regla de decisión:** si la distintividad inter-narrativa de
las 8 twins cae por debajo de la de las auto-descripciones de los 8 humanos, el brazo **se corre
igual, pero P1 queda pre-declarada no interpretable en la dirección de confirmación** — un
`twinpop ≈ demoonly` no podrá leerse como "la riqueza genérica no ayuda", porque sería compatible
con haber construido un estereotipo con 8 disfraces. La lectura de **refutación sobrevive**, en
coherencia con la asimetría de §8.

### 4.5 Selección de personas — regla determinista, sin optimización de distintividad

Se generan **3 candidatas por celda** con semilla fija. Se aplican en orden:

1. **Capa 1 de §4.3 solamente** (léxica, independiente del codebook).
2. Techo léxico de §4.4c.

**Se toma la primera superviviente en orden de generación.** Las capas 2 y 3 de §4.3 son puertas de
**parada posteriores a la selección** (G2), nunca criterios de selección — de otro modo la
"primera superviviente" sería "la primera que el codebook no marcó", exactamente lo que §4.2
prohíbe.

**No se aplica** el criterio de maximizar distancia TF-IDF entre candidatas: el colapso de personas
es una de las dimensiones que el brazo mide (§7 R4), de modo que optimizar las personas para ser
distintas y luego medir si son distintas sería circular. Prohibido generar varias aprobadas y
elegir por juicio. Las 3 candidatas y sus resultados de puerta quedan archivadas.

---

## 5. Controles de comparabilidad

Los 6 configs se clonan de `configs/experiment/macho_meals_fg{3,4}_run01.json` y solo pueden
diferir en `session_id`, `run_label` y `participants`, verificado por diff del JSON parseado. Sin
cambios en `discussion_guide`, `research_objective`, `moderator_prompt_override`,
`moderator_restraint_prompt`, `moderator_context_mode`, `moderator_reflection_enabled`,
`participant_response_max_tokens: 800`, `participant_episodic_depth`, `temperature: 1.0`,
`participation_mode: emergent`, ni en `simulation_config.model` / `max_tokens` de cada agente.

### 5.1 El largo por turno NO está topado — corrección registrada

Una versión anterior de este documento afirmaba que `max_tokens` topa el largo por turno. **Es
falso.** Sobre 465 llamadas `call_participant` en FG3/FG4, el **máximo observado es 487 tokens de
salida contra un cap de 800**; cero truncamientos. Las medianas de 197–284 palabras son
comportamiento del modelo bajo `_BEHAVIOUR_INSTRUCTIONS`, no recorte mecánico. **No hay garantía de
que `twinpop` mantenga el largo por turno** — de ahí P2′ (§6).

### 5.2 El volumen de ventana está bajo control — evidencia

Sobre los 30 runs canónicos, **r(`window_words`, `tier1_subtheme_recall`) = 0.017**. Dentro de FG3,
`demoonly_run03` tiene 13 580 palabras y recall 0.10, mientras `full_run02` tiene 6 231 y recall
0.30: el brazo con más volumen es el de menos recall. `_comparable_window` (`anchor_and_extend_v1`
con su puerta hard-fail) más el reporte de `window_words` **bastan**.

**Salvedad FG4:** sus tres runs `full` son monótonos en ambas variables (5 804/0.167; 7 668/0.167;
8 780/0.50). Para FG4 se reporta el dispersograma palabras–recall por corrida.

### 5.3 Qué se reporta antes de leer cifras temáticas

Todo ya disponible, coste cero: `window_words` y `window_participant_turns` por corrida; **largo
mediano por turno y tasa de truncamiento** (§5.1); reparto de palabras por participante; curva de
tokens de contexto por turno desde `api_calls.jsonl` (§7 R1); curva D2
(`tier1_coverage_by_word_count_curve`) también para los runs twin.

---

## 6. Predicciones a priori

| # | Predicción | Regla de decisión | Qué la falsaría |
|---|---|---|---|
| **P1** (primaria) | El recall de `twinpop` cae **más cerca de `demoonly` que de `full`** | Sobre la **media de las 3 réplicas por FG**; clasificación por réplica también reportada. Equidistancia (< 0.01) se declara indecisa, no favorable. **Evaluación primaria en FG3** | Que `twinpop` alcance o supere la media de `full` |
| **P2′** | **No se predice divergencia** en la familia estructural de nivel de transcripción (verbosidad, balance de participación, adyacencia P→P, profundidad de cadena) | Media de `twinpop` **dentro del min–max combinado de `full`+`demoonly` del mismo FG, por métrica** | Salir de rango en cualquier métrica |
| **P3** (artefacto) | `twinpop` **no** superará a `full` en precisión sobre el subconjunto masculinidad/carne | **Solo evaluable en FG4** (en FG3 la precisión de `full` está en techo 1.0 y P3 se cumpliría por aritmética). Subconjunto = IDs de subtema del adendum §11, fijados antes de generar | Que la supere ⇒ auditoría §4.4 antes de interpretar nada |
| **P4** (volumen) | No se predice divergencia sistemática de palabras totales | Media de `window_words` de `twinpop` fuera del rango min–max combinado de `full`+`demoonly` del mismo FG | Fuera de rango ⇒ análisis sobre ventana comparable antes de leer recall |
| **P5** (estructura de saliencia) | La **preservación de la jerarquía de saliencia** de `twinpop` cae **más cerca de `demoonly` que de `full`** | Primaria: `normalized_mean_abs_reach_diff`, media de las 3 réplicas, **magnitud en FG3**, **suelo en FG4**. Secundarias acopladas: `kendall_tau_b`, `spearman_avg_ranks`, `top_theme_overlap_tie_aware` (§6.2) | Que `twinpop` iguale o supere la preservación de `full` |

**Regla de no-equivalencia (spec §12):** P2′ y P4 se formulan como "no se predice divergencia". Su
confirmación **no se reportará como equivalencia** en ningún caso.

**Fragilidad declarada de P3.** La referencia contra la que se evalúa —precisión `full` de FG4,
media 0.4222— tiene la misma estructura por réplica que el recall: **0.3333 / 0.3333 / 0.60**, y el
0.60 es run04, el mismo run que sostenía la brecha de recall y que motivó la inversión de roles de
§2.1. P3 se evalúa sobre la media con clasificación por réplica reportada, y **todo resultado de P3
que dependa del valor de run04 se declara frágil**.

**`tier1_participant_reach`** — tercera métrica primaria del spec — se reporta para los tres brazos
pase lo que pase, y alimenta P5 (§6.2). La omisión no sería neutra: en FG4 reach favoreció a
`demoonly` (−0.1704).

### 6.2 P5 — preservación de la estructura de saliencia, no solo el conteo de códigos

**Por qué el recall no basta.** Un grupo twin puede acertar los mismos códigos con un perfil de
saliencia distinto: el mismo tema planteado por **un** participante en vez de por tres, o con una
jerarquía de importancia invertida respecto de la humana. El recall es idéntico y la estructura del
grupo focal es otra. El marco §D ya define la saliencia por amplitud de participantes y por
correlación de rangos entre jerarquía humana y sintética, y la capa está **computada por corrida**
en `analysis/production_evaluation/final/salience_hierarchy_per_run.csv`.

**Lo que muestran los datos existentes en FG3** — la saliencia separa los brazos en la misma
dirección que el recall, y con estabilidad entre réplicas:

| FG3 | `kendall_tau_b` | `spearman_avg_ranks` | `top_theme_overlap` | `normalized_mean_abs_reach_diff` |
|---|---|---|---|---|
| `full` | 0.5422 / 0.5074 / 0.3916 | 0.58 / 0.58 / 0.46 | 0.75 ×3 | 0.34 / 0.40 / 0.36 |
| `demoonly` | 0.2704 ×3 | 0.2984 ×3 | 0.40 ×3 | 0.52 / 0.54 / 0.56 |

**Caveat de acoplamiento, declarado antes de mirar nada.** `kendall_tau_b`, `spearman` y
`top_theme_overlap` **no son canales independientes del recall**: un brazo que recupera menos
códigos tiene un lado sintético más empatado —FG3 `demoonly` tiene 36 empates con 1 código
recuperado, frente a 16 con 4— y ese empate arrastra mecánicamente el estadístico. La prueba está
en que las tres réplicas de `demoonly` dan τ_b **idéntico** (0.2704), porque las tres recuperaron
exactamente 1 código. **No se presentarán como corroboración independiente del recall.**

Por eso la métrica primaria de P5 es **`normalized_mean_abs_reach_diff`**: compara la amplitud de
participantes tema a tema contra la humana, incluidos los temas asignados a cero, está definida aun
cuando el lado sintético es constante, y varía entre réplicas de forma no reducible al conteo de
códigos (0.52/0.54/0.56 vs. 0.34/0.40/0.36).

**En FG4 la jerarquía es degenerada y se declara así.** `full` da τ_b **negativo en dos de tres**
réplicas (−0.2697 / 0.1818 / −0.2697): el orden de saliencia sintético está invertido respecto del
humano. Y `demoonly` es **indefinido en las tres**, con `undefined_reason:
SYNTHETIC_SIDE_CONSTANT` (`n_defined = 0` en `salience_hierarchy_by_fg_condition.csv`), porque no
recuperó ningún código. **FG4 no puede sostener una comparación de rangos.** Lo que sí está
definido allí, y es lo que se usa: `normalized_mean_abs_reach_diff` (0.7778 ×3 en `demoonly`) y
`union_kendall_tau_b`. Coherente con §2.1: en FG4, P5 se lee como suelo, no como magnitud.

**Respeto al marco:** la saliencia se reporta como **descriptor estructural** y **no se incorpora a
ningún puntaje de fidelidad** (marco §D). P5 es una dimensión reportada aparte, no un sumando del
recall.

### 6.1 Verificación de manipulación: la capa de asignación de turnos es ciega al enriquecimiento

`core/participant_agent.py:648-680` — `assess_engagement()` construye su system prompt **solo desde
`persona.demographics`**. No lee `food_consumption`, ni `psychometric_scores`, ni `notes`, ni
ninguna clave nueva de `persona`. El prompt de enrutamiento de `twinpop` será **byte-idéntico** al
de `demoonly`; el de `full` difiere solo por el token `Meat eater`. Igualmente,
`core/moderator_brain.py:490` pasa `profile_summary` al moderador, que incluye `diet`: el moderador
de `twinpop` será idéntico al de `demoonly`, no al de `full`.

Esto se reporta como **verificación de manipulación**, no como predicción. **No sustituye a P2′**:
la llamada de engagement se alimenta de la conversación en curso, cuyo contenido sí difiere por
brazo, y las métricas estructurales se computan sobre la transcripción resultante del bucle
completo, no sobre el prompt de enrutamiento.

Corolario de diseño declarado: si la intención fuera que la persona censal module **quién**
participa —un rasgo que los proveedores comerciales sí venden—, este brazo no lo prueba.

---

## 7. Riesgos de artefacto y mitigaciones

**R1 — Dilución por posición y recencia.** El bloque de persona pasa de **~30–35% del contexto en
el primer turno a ~2.5–4.5% en el último** (Andrew, fg3_run01: 1 250 → 14 345 tokens). Las
secciones 3–5 de la guía —género, cambio plant-based, atractivo— son **las últimas**: la
manipulación es más débil justo donde se miden los constructos. Afecta por igual a los tres brazos,
así que no sesga el contraste, pero **acota el tamaño de efecto detectable**.
*Mitigación:* curva de participación del bloque por turno (coste cero) y **desglose de recall por
sección de la guía**, para distinguir un nulo en las secciones 3–5 de un nulo global.

**R2 — Recitación en la introducción, invisible a la medición.** `_comparable_window` corta la
introducción (START en el ask de Q1): la recitación se elimina del corpus codificado **pero
permanece en el historial acumulado**, cebando cada turno posterior de todos.
*Mitigación:* además de §3.4, comprobación pre-declarada sobre el **segmento descartado**: contar
fragmentos de la región pre-ventana que reproduzcan literal o casi-literalmente la narrativa.

**R3 — `demoonly` no es un control sin biografía.** En `macho_meals_fg3_demoonly_run01`, Nick dice
*"North West — suburbs just outside Manchester"* teniendo solo "Suburban, North West" en su JSON.
**Los agentes ya se inventan la biografía.** El contraste real es "enriquecimiento modal
auto-generado → enriquecimiento censal externo". Si lo que el modelo inventa ya es la moda
poblacional, **P1 se confirmaría por la razón equivocada**.
*Mitigación (gratis, obligatoria antes de correr):* extraer los específicos biográficos que los
agentes `demoonly` ya inventaron en las 6 transcripciones FG3/FG4 existentes y compararlos con las
celdas censales muestreadas. Si coinciden en buena medida, **se declara antes de correr** que una
confirmación de P1 significaría "el modelo ya sabía el censo", no "la riqueza no ayuda".

**R4 — Colapso de personas, aquí asimétrico.** Los 8 twins son varones de 40–53 años, ingleses,
renderizados por **un solo generador** desde celdas adyacentes; `full` tiene valores psicométricos
genuinamente distintos por persona. Si el generador colapsa a la moda, `twinpop` tendrá **menor**
distintividad que `full` y no podrá distinguirse "la riqueza genérica no ayuda" de "los 8 twins son
el mismo señor". *Mitigación:* `collapse_metric.py` dos veces —narrativas (§4.4d, con su regla de
decisión) y transcripciones—, con comparación pre-registrada contra `full` y `demoonly`.

**R5 — Desempate sembrado con `session_id`.** `core/orchestrator.py:903-904`:
`rng = random.Random(f"{session_meta.id}:{total_turns}")` + `shuffle`. Como `session_id` **debe**
cambiar, el desempate extrae un flujo determinista distinto. Insesgado en esperanza, pero con 3
réplicas es varianza no compartida. Los valores de `urgency` **no se persisten**, así que no puede
reportarse post hoc cuántos turnos se decidieron por desempate.
*Mitigación:* se **acepta y se declara**; no se registra `urgency` (sería un cambio de logging que
rompería la identidad de §5). **Acotación opcional, read-only y de coste cero:** el flujo es una
función pura de `(session_id, total_turns)`, así que puede simularse offline para los tres
`session_id` y todos los `t` observados, y reportar si los órdenes barajados divergen
sistemáticamente por brazo — acota el techo de exposición sin recuperar la frecuencia real.

**R6 — Complacencia y validación mutua.** Una biografía genérica compartida —todos suburbanos,
ingleses, con trabajo y familia— da **más terreno común para afirmar**, lo que eleva actos de
acuerdo, deprime `challenge` y con ello la amplitud temática: el mecanismo por el cual un P1 nulo
podría producirse por concordancia y no por ausencia de instrumentación.
*Mitigación:* correr los scripts existentes de `analysis/production_evaluation/consensus_dynamics/`
sobre los runs twin (código cero) y reportar la distribución de actos de respuesta junto al recall.
El reporte **arrastra la etiqueta `AUTOMATIC_EXPLORATORY` y la cláusula de no-sustitución** de su
`FROZEN_SPEC.md` de origen.

**R7 — Posición serial.** Resuelto por §3.4 punto 2 (rama inmediatamente después de
`food_consumption`).

**No aplican y no se inventarían:** sensibilidad al orden de participantes en el config (el shuffle
sembrado lo elimina como determinante); determinismo/semilla (no hay parámetro de semilla;
`run_label` es solo de registro — la variación entre corridas es irreducible y las 3 réplicas son
el único mango).

---

## 8. Qué puede y qué no puede concluir este brazo

**Puede:** particionar **las brechas observadas en FG3 y FG4** en componente de riqueza genérica vs.
componente de instrumentación, **en dos dimensiones y no solo en el conteo de códigos** — magnitud
temática (P1) y preservación de la estructura de saliencia (P5, §6.2), que puede divergir aunque el
recall coincida; someter a prueba una instancia favorable de la condición comercial contra
transcripciones humanas reales; y producir, vía el suelo de FG4, una viñeta cualitativa de
*reprodujo algo* frente a *no reprodujo nada*.

**No puede:**

- **Sostener que el baseline humano es prescindible.** El marco es comparativo por definición: el
  recall se calcula contra el codebook humano y la envolvente §K es d_HH vs. d_SH. Responde *qué
  tan barata puede ser la persona*, no si los humanos sobran.
- **Sostener inferencia estadística.** Con 2 grupos hay 2 diferencias pareadas.
  `primary_effects_summary.csv` declara que con n=5 el sign test tiene mínimo alcanzable p=0.0625.
  Con n=2 no hay test posible.
- **Declarar equivalencia.** Un empate es compatible con insensibilidad de la medida —Tier-2b
  documentó que el tópico sigue a la pregunta de guía, no a la identidad del grupo— y con R1, R3,
  R4 y R6. **Este brazo puede refutar la sustitución, no puede confirmarla.**

### 8.1 Asimetría deliberada de las puertas, y su corolario de lectura

Todas las salvaguardas de §4.3 y §4.4 empujan en una sola dirección: **capan al twin por arriba**
(fuga, estereotipo, techo humano) y **nada lo protege por abajo** — un renderizador soso produce un
twin artificialmente débil. Es la dirección correcta de precaución, porque el falso "el twin cierra
la brecha" es el peor desenlace posible para la tesis. Pero tiene un corolario que debe leerse
junto a los resultados:

> **Una confirmación de P1 (`twinpop ≈ demoonly`) es el resultado débil, parcialmente producido por
> controles unilaterales. Una refutación (`twinpop ≈ full`) sería el resultado fuerte, porque
> habría ocurrido a pesar de ellos.**

---

## 9. Puertas de validación

### Antes de generar personas

**G0 — El cambio de §3.4 es no-op sobre todo lo existente.** Coste ≈ 0, todo offline.

- **G0.a** — Para los **111 agentes de `agents/**/*.json`** (no solo los 44 de macho_meals): SHA-256
  de `build_participant_system_prompt(...)` idéntico antes/después, **con `inject_participant_intro`
  en `False` y en `True`**. Alcance obligatorio: `deepfakes` (39, con `persona.study_profile`) y
  `mindfulness` (5, con `persona.professional_profile`) son dicts que **renderizan hoy por la misma
  rama genérica que se va a modificar**, y mindfulness es DS05, un resultado ya reportado. Una G0
  limitada a macho_meals no lo detectaría.
- **G0.b** — Para los 111: SHA-256 de `load_agent_from_json(path).profile_summary` idéntico (cubre
  la ruta del moderador, `moderator_brain.py:490`).
- **G0.c** — SHA-256 de `inspect.getsource(...)` idéntico para `load_agent_from_json`,
  `assess_engagement`, `call_participant`, `_render_cacheable_messages`, `_format_recent_transcript`,
  `_score_to_instruction`, `_bucket`, `_stable_variant_index`; y de las constantes
  `_BEHAVIOUR_INSTRUCTIONS`, `_BEHAVIOUR_INSTRUCTIONS_ES`, `_DIMENSION_TIER`, `_HABIT_TEMPLATES`,
  `_CODED_TEMPLATES`, `_DISPOSITION_HEADER_EN`, `_DISPOSITION_HEADER_ES`. Demuestra que **solo**
  `build_participant_system_prompt` cambió.
- **G0.d** — La suite existente **se ejecuta sin modificar y pasa**:
  `tests/test_psychographic_disposition_rendering.py`, `tests/test_participant_prompt_caching.py`,
  `tests/test_agent_fidelity*.py`, `tests/test_macho_meals_emergent_run_validation.py`. "No
  modificar los tests" y "los tests pasan" no son lo mismo: se exigen ambas.

Un solo hash distinto ⇒ revertir y pasar a aceptar-y-declarar la asimetría de §3.4.

**G1 — La narrativa llega al modelo, y una sola vez.**

- Las 8 personas parsean; `name/age/gender/location` byte-idénticos al original.
- **Ausencia por membresía de clave** de `demographics.diet`, `food_consumption`,
  `psychometric_scores`, `simulation_config.notes`.
- **Aserción de substring exacto:** cada una de las tres cadenas de prosa aparece en el prompt
  renderizado **y exactamente una vez** (`prompt.count(prosa) == 1`). No se usa umbral de
  solapamiento: el renderizador interpola verbatim, así que el código garantiza el 100%, y un
  umbral del 95% **aprobaría el doble renderizado** de §3.4 punto 3 y el caso de dict vacío.
- **Aserción negativa mecánica:** renderizar el agente `twinpop` y su homólogo `demoonly` y exigir
  que **la única diferencia sea el bloque `background`** (encabezado + 3 viñetas). Sustituye al
  spot-render discrecional.
- Instrumento: `scripts/phase1_condition_manipulation_audit.py`, que ya existe y ya hizo esto para
  `full` vs `demoonly` bajo el lema *stored is not rendered*.

**G2 — Fuga y estereotipo.** Capa 1 de §4.3 y §4.4c aplicadas en la selección (§4.5); **capas 2 y 3
de §4.3 aplicadas después de la selección como puertas de parada**; §4.4 (a)–(d) completa con
léxicos hasheados y umbral binomial sobre 24 pares. Registro de descartes y remuestreos; tope de 5
generaciones por celda (§4.1).

**G4 — Volumen** en banda **220–300 palabras netas**, medido sobre el **bloque renderizado completo**
(§3.5).

**G4b — Pre-chequeo R3:** comparación de los específicos auto-inventados por `demoonly` contra las
celdas censales, con la declaración correspondiente si coinciden.

### Antes de correr

**G5** — Los 6 configs difieren de su `run01` de origen **solo** en `session_id`, `run_label`,
`participants`; ningún `agent_payload_path` apunta a `agents/macho_meals/` ni
`agents/macho_meals_demoonly/`; ninguno de los 6 directorios de salida existe.

### Después de correr

**G6** — Ambos procesos exit 0; `transcript.json` > 2 bytes; `rate_limit_exhausted == 0`; ninguna
sesión topó el cap de 90 turnos; **y conteo de silencios forzados** (`error_type ∈
{engagement_fallback_after_retry, engagement_api_error}` en `api_calls.jsonl`) bajo umbral fijado
en §11 — los runs de referencia FG3/FG4 dan 0 en 12 de 13. Sin esta última, una corrida twin con
silencios forzados pasaría G6 mientras su equivalente en `full` fue archivada por ese criterio.

**G7** — Codificación temática ciega con **`gemini-3.5-flash`** y la configuración congelada exacta
de `frozen_evaluation_spec.md` §2–§4: `EVALUATOR_CONFIGS["gemininext"]`, key `GEMINI_API_KEY_NEXT`,
temperatura no transmitida, thinking unpinned, prompt Tier-1 `321ffd62…`, codebook `f343ebb1…`,
esquema de cache key, y algoritmo de ventana `anchor_and_extend_v1` con su puerta hard-fail.
**`gemini-2.5-flash` está descalificado** y es el default de varios scripts — no debe sustituirse
en silencio. Nunca Claude: el generador es Claude Haiku y el marco §3 exige evaluador de familia
distinta. Sin excepción.

**Regla de fallo de sesión:** rerun con sufijo incrementado, archivado documentado del fallo,
**prohibida la selección por contenido** — precedente de `fg4_run02` / `fg5_run02` (spec §3.2).

---

## 10. Plan de ejecución y compromisos

| Fase | Contenido | Gasto |
|---|---|---|
| 0 | Este pre-registro convergido; **depósito del hash SHA-256** (§10.1) | 0 |
| 1 | **Adendum §11 completo y congelado** | 0 |
| 2 | Cambio de §3.4 + G0 (111 agentes) | 0 |
| 3 | Muestreo censal, generación, G1–G4b | ~120 llamadas cortas, < $2 |
| 4 | 6 configs + G5 | 0 |
| 5 | **6 sesiones en vivo — requiere autorización explícita** | ~$1.5–3 c/u |
| 6 | Ventana comparable, codificación Gemini, G6–G7 | codificación |
| 7 | Lectura contra §6, revisión adversarial | 0 |

Rutas nuevas; ninguna existente se toca: `agents/macho_meals_twinpop/`,
`configs/experiment/macho_meals_fg{3,4}_twinpop_run0{1,2,3}.json`,
`output/session_logs/macho_meals_fg{3,4}_twinpop_run0{M}/`.

### 10.1 Compromisos

El directorio no es un repositorio git, de modo que "redactado antes de generar" hoy es
inauditable. Antes de la fase 2:

1. **Depósito externo del hash SHA-256** de este documento (OSF, commit, o correo con timestamp).
2. **El resultado se reporta en la tesis sea cual sea su dirección**, junto a este pre-registro.
3. **Ningún brazo de persona adicional se corre sin su propio pre-registro previo** — incluida la
   extensión FG1 de §2.4.
4. Las tres métricas primarias del spec (`recall`, `precision`, `participant_reach`) se reportan
   completas para los tres brazos, con predicción solo donde §6 la registra.

---

## 11. Adendum — **CONGELADO** 2026-08-04

Documento: **`ADENDUM_TWIN_POBLACIONAL_CONGELADO_2026-08-04.md`**
SHA-256: **`51acff881d74e7204f36f319aa72cce85a760fe0cf6ba330d342e288256eef7a`** (22 637 bytes; entradas 1 y 2 corregidas, 7 retirada y 9 reformulada — todas 2026-08-05)

Doce entradas fijadas antes de generar nada: renderizador (`claude-opus-5`, sin parámetros de muestreo —no existen en
este modelo—, effort medium, max_tokens 4000, sin fallbacks, prompt verbatim) y su limitación de
reproducibilidad; fuente poblacional **SN 9154** (microdatos individuales
salvaguardados, 5%, nivel de región) con emparejamiento por edad exacta y semilla `20260804`;
orden de claves de `background`; lista negativa de dominio; léxico de masculinidad; umbral binomial
17/24 (p=0.0320); techo humano **RETIRADO** por inejecutable (entrada 7); umbral de la sonda conductual ≥6 de 24; regla de
colapso; subconjunto de P3 = **A.1, A.2, A.3, B.3**; umbrales de silencios forzados 1–2 marca /
≥3 archiva; y umbral de decisión de P5 sobre `normalized_mean_abs_reach_diff` (punto medio FG3
0.4533).

**Regla de modificación:** ninguna entrada se altera después de la fase 3. Si una resulta
inejecutable, se detiene el brazo, se documenta por qué, y se emite una versión nueva con su propio
depósito de hash — nunca se edita en silencio.

**Depósito pendiente (§10.1):** este pre-registro y el adendum deben depositarse externamente
**antes de la fase 2**. Es lo único que hace auditable, sin repositorio git, que ambos se
escribieron antes de ver datos.

*Nota sobre el hash propio:* este documento **no registra su propio SHA-256** — sería
autorreferente, ya que anotarlo lo modificaría. El hash del pre-registro se calcula sobre el
archivo tal como quede al momento del depósito y se registra **en el depósito externo**, no aquí.
El del adendum sí consta arriba porque es un archivo distinto y ya está cerrado.

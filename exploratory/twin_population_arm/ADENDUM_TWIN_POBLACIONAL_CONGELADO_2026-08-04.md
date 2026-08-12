# Adendum congelado — Brazo twin poblacional (FG3 + FG4)

*4 de agosto de 2026. Corresponde a la §11 de
`PREREGISTRO_BRAZO_TWIN_POBLACIONAL_2026-08-04.md`. **Congelado**: fijado antes de generar ninguna
persona, ningún config y ninguna transcripción. Toda entrada de este documento cierra un grado de
libertad que de otro modo quedaría a discreción del investigador durante la construcción.*

**Regla de modificación:** ninguna entrada se altera después de la fase 3. Si una resulta
inejecutable, se detiene el brazo, se documenta por qué, y se emite una versión nueva con su propio
depósito de hash — nunca se edita en silencio.

---

## 1. Renderizador de personas

**Corrección obligatoria 2026-08-05 — la versión anterior era inejecutable.** Fijaba
`temperatura 1.0`. En `claude-opus-5` los parámetros de muestreo (`temperature`, `top_p`, `top_k`)
**están eliminados y devuelven `400 invalid_request_error`**. Las 48 llamadas habrían fallado. Se
aplica la regla de modificación de este documento: se detuvo el brazo, se documenta aquí y se
reemite con hash nuevo.

| Parámetro | Valor congelado |
|---|---|
| Modelo | `claude-opus-5` |
| Muestreo | **ninguno** — `temperature`/`top_p`/`top_k` no existen en este modelo |
| Esfuerzo | `output_config: {"effort": "medium"}` |
| `max_tokens` | **4000** |
| Salida estructurada | `output_config.format`, `json_schema` con las tres claves de la entrada 3 |
| Fallbacks | **desactivados**, deliberadamente (ver abajo) |
| Familia | Claude (§3.6 del pre-registro; confusor declarado en §1.1f) |

**Por qué `max_tokens` 4000 y no ~600.** En Claude Opus 5 el pensamiento está **activado por
defecto** y `max_tokens` acota pensamiento **más** texto de respuesta de forma conjunta. Un
presupuesto ajustado al tamaño de la narrativa (~300 palabras) truncaría la salida a media frase.

**Por qué sin fallbacks.** La recomendación general para código de Opus 5 es activar el reintento
servidor (`fallbacks`) ante un rechazo de los clasificadores de seguridad. **Aquí se desactiva a
propósito:** este documento congela el renderizador como `claude-opus-5`, y un fallback silencioso
produciría personas escritas por otro modelo sin dejar constancia — rompería la identidad de modelo
fijada y contaminaría el rastro de auditoría. Un `stop_reason: "refusal"` **detiene la generación y
se documenta**; no se sustituye en silencio.

**Variación entre las 3 candidatas.** Con el muestreo no parametrizable y sin semilla en la API, la
variación entre candidatas proviene únicamente del muestreo estocástico del modelo. Esto **no
cambia** la limitación de reproducibilidad ya declarada abajo: reproducible por archivo, no por
re-derivación.

**Por qué Opus y no Haiku:** el actor de las personas es `claude-haiku-4-5-20251001`. Usar un
model-id distinto dentro de la familia disponible evita la auto-autoría literal (el mismo modelo
escribiendo y luego interpretando el mismo texto), que es el caso extremo del confusor de §1.1f. No
elimina el confusor —la familia es la misma— y la salvaguarda operativa sigue siendo §4.4a–b.

**Limitación de reproducibilidad, declarada.** La API de Anthropic **no expone un parámetro de
semilla**. La expresión "semilla fija" del pre-registro (§4.5) no es realizable como
re-derivabilidad. Se sustituye por:

- Las 3 candidatas por celda se generan en **una sola tanda registrada**, identificadas por su
  **índice de generación** (1, 2, 3) en orden de emisión.
- Las 24 candidatas y sus 24 gemelas de género invertido (§4.4a) se **archivan verbatim** con
  SHA-256 individual.
- La reproducibilidad es **por archivo, no por re-derivación**. Se declara así en métodos.

**Prompt de renderizado (congelado).** Entrada: los atributos censales de la celda. Salida: JSON con
exactamente las tres claves de la entrada 3.

```
You are writing a short factual life-sketch of a real UK resident for a research
simulation, based only on the census attributes given below. Write three separate
paragraphs, one per field, in plain British English, third-person-free (write as
neutral description, not as speech).

HARD CONSTRAINTS — a sketch violating any of these is discarded:
- Never mention food, meals, cooking, shopping for food, restaurants, pubs, drink,
  diet, nutrition, health, fitness, the gym, protein, farming, animals, bodies,
  weight, or eating of any kind.
- Never mention gender roles, masculinity, femininity, or what men or women are like.
- Never mention ethnicity, nationality, religion or country of birth.
- No markdown, no bullet points, no quotation marks around the text, no line breaks
  inside a field. One single paragraph per field.
- 65–92 words per field.
- Do not invent attributes that contradict the census attributes given.

CENSUS ATTRIBUTES: {attributes}

Return JSON: {"working_life": "...", "home_and_household": "...", "week_and_hobbies": "..."}
```

---

## 2. Fuente poblacional — MICRODATOS (reedición 2026-08-05)

**Esta entrada sustituye por completo a la versión del 2026-08-04**, que especificaba cuatro tablas
agregadas de ONS (TS062, TS067, TS003, TS054) con muestreo condicionado por región.

### 2.1 Por qué se sustituye

Aquel procedimiento sorteaba cuatro variables de **marginales independientes**, de modo que
producía el **producto de marginales y no la conjunta poblacional**. Consecuencias observadas al
ejecutarlo, no previstas al redactarlo:

- **Personas lógicamente imposibles.** Un hombre de 47 y otro de 48 quedaron asignados a hogares
  definidos como "todos de 66 años o más". El 27.5% de la masa de composición del hogar era
  imposible para la cohorte de 40–53, por no estar condicionada por edad.
- **Combinaciones incoherentes.** Alto directivo sin cualificaciones, porque NS-SEC y nivel
  educativo se extraían por separado.
- **Sesgo por tamaño de hogar.** TS003 y TS054 cuentan hogares; asignar sus categorías a personas
  sobrerrepresenta los hogares pequeños por un factor de dos o tres.
- **Invalidaba su propia justificación.** El argumento para preferir censo a "que un LLM invente un
  británico de 47 años" era recuperar la conjunta. Un producto de marginales no la recupera; es
  *diferentemente* erróneo — el LLM produce combinaciones sobre-coherentes, este método las produce
  incoherentes.

### 2.2 Fuente congelada

**SN 9154 — 2021 Census: Safeguarded Individual Microdata Sample at Region Level (England and
Wales)**, ONS vía UK Data Service.

| | |
|---|---|
| Registros | 3 021 455 personas (5% de los registros individuales) |
| Variables disponibles | 89 |
| Variables usadas | **25** (4 de emparejamiento + 21 de persona) |
| Geografía | Región / ITL1 — exactamente la del estudio |
| Acceso | Safeguarded, End User Licence, registro en UK Data Service |
| Fichero | `data/census2021/sn9154/.../safeguarded_reg_final_csv2023_07_12.sav` |
| Ética | Registros anonimizados. **En ningún punto se intenta reidentificación.** |

**El método es ahora: una fila = una persona real = la conjunta viene dada, no reconstruida.** Es el
análogo estructural exacto de lo que Twin-2K-500 aporta para Estados Unidos, aplicado a la
población del estudio. Desaparecen de golpe la independencia entre variables, el sesgo por tamaño
de hogar y la necesidad del filtro de compatibilidad de edad: el hogar de un hombre real de 47 años
es compatible con tener 47 años por construcción.

### 2.3 Emparejamiento

`region` × `sex = Male` × **`resident_age_74m` = edad exacta** × `residence_type` = hogar privado.

La edad se empareja en **años simples** (la variable es de año simple hasta los 70), no en tramos.
Reservas resultantes por agente: de 1 576 a 3 179 personas. `urban_rural` no existe en los
microdatos: se conserva del participante real y **no se sortea** — se declara que un participante
rural puede emparejarse con un registro de zona urbana de su misma región.

### 2.4 Variables que alimentan al renderizador (21)

- **`working_life` (9):** `economic_activity_status_17m`, `ns_sec`, `occupation_105a`,
  `industry_22a`, `employment_status`, `employment_history`, `supervises_or_manages`,
  `hours_per_week_worked`, `highest_qualification`.
- **`home_and_household` (9):** `hh_tenure`, `accommodation_type_7a`, `hh_size_9a`,
  `living_arrangements_11a`, `legal_partnership_status_7a`, `family_dependent_children`,
  `hh_adults_and_children_11a`, `relat_to_hrp`, `occupancy_rating_bedrooms_6a`.
- **`week_and_hobbies` (3):** `transport_to_workplace_12a`, `workplace_travel`,
  `place_of_work_ind`.

### 2.5 Variables excluidas, por motivo

**Fuga temática.** `hh_deprivation` y sus cuatro dimensiones (la privación del hogar está ligada a
inseguridad alimentaria, materia del estudio); `religion_tb`, `hh_multi_religion` (las normas
dietéticas son confesionales); `health_in_general`, `disability_4a`, `hh_disabled_4a` (salud y
cuerpo están en la lista negativa de la entrada 4); `is_carer_5a`, `hh_carers_6a` (cuidar arrastra
a *quién compra y quién cocina*, que es el subtema **A.3** del codebook).

**Amplificación de estereotipo.** `uk_armed_forces`: el servicio militar es marcador de
masculinidad y sembrarlo produciría justo el artefacto que la entrada 5 existe para detectar.

**Etnicidad, origen y lengua** (omisión ya congelada en §3.1 del pre-registro; varias son además
señal de cocina): `ethnic_group_tb_20b`, `hrp_ethnic_group_tb`, `hh_multi_ethnic_group`,
`country_of_birth_25a`, `hrp_cob_25m`, `year_arrival_uk`, los cuatro `migrant_*`,
`passports_all_27a`, `multi_passports_9a`, los siete `nat_id_*`, `national_identity_detailed_23m`,
`main_language_detailed_23a`, `english_proficiency_5a`, `hh_language`, los cuatro `welsh_skills_*`.

**Redundantes o inaplicables.** Variables de establecimiento comunal y de estudiantes (se filtra a
hogares privados); indicadores de Londres (ninguna región del brazo lo es); `hrp_age_59m` y
`hrp_ns_sec` (cubiertos por `relat_to_hrp`); y **`approx_social_grade`**, duplicado más burdo de
`ns_sec` cuyas discrepancias de derivación producirían prosa contradictoria (se observó "L13
Routine occupations" con grado "AB Higher managerial" en el mismo registro).

### 2.6 Semilla y reproducibilidad

`random.Random(20260804)`, con las candidatas seleccionadas por `rng.sample` sobre la reserva
ordenada por identificador de registro, sin reemplazo en todo el sorteo. **Esta parte es
plenamente re-derivable** — a diferencia del renderizado narrativo (entrada 1), que solo es
reproducible por archivo.

### 2.7 Limitación que persiste y debe declararse en métodos

**El censo no recoge aficiones ni ocio.** El campo `week_and_hobbies` queda anclado únicamente por
el desplazamiento al trabajo (modo, distancia, lugar); el contenido de ocio lo inventa el
renderizador bajo las restricciones de la entrada 4 y **no está anclado en el censo**.

---

## 3. Orden de claves de `persona.background`

Congelado, idéntico en las 8 personas:

```json
"background": {
  "working_life": "...",
  "home_and_household": "...",
  "week_and_hobbies": "..."
}
```

El renderizador emite las viñetas en orden de inserción del JSON (§3.7 del pre-registro), de modo
que las 8 personas quedan estructuralmente idénticas.

---

## 4. Lista negativa de dominio (§4.1, §4.3 capa 1) — dispara remuestreo

Congelada. Coincidencia de raíz, insensible a mayúsculas, sobre el texto renderizado completo.

**Alimentación y consumo:** food, meal, meals, eat, eating, ate, diet, dietary, cook, cooking,
cooked, kitchen, recipe, restaurant, café, cafe, pub, takeaway, groceries, grocery, supermarket,
shopping list, meat, beef, pork, chicken, poultry, fish, dairy, milk, cheese, egg, eggs, vegetarian,
vegan, plant-based, barbecue, barbeque, bbq, grill, roast, snack, breakfast, lunch, dinner, supper,
drink, drinking, beer, pint, alcohol.

**Salud, cuerpo y fitness:** health, healthy, nutrition, nutritional, protein, calorie, calories,
gym, fitness, workout, muscle, muscular, weight, body, diet plan, supplement.

**Granja y animales:** farm, farming, farmer, livestock, animal, animals, butcher, slaughter.

**Constructos psicométricos y sus descriptores de dirección:** masculine norms, masculinity,
masculine, femininity, feminine, meat attachment, dairy attachment, vegetarianism threat,
masculinity of meat, traditional masculin*, gender role, gender norms.

**Formato (§3.7):** presencia de `\n` dentro de un valor, de markdown (`*`, `_`, `#`, `` ` ``, `-`
al inicio de línea), de comillas envolventes, o de espacios al inicio o final.

**Tópicos de la guía de discusión** (documento legítimo del lado generación, incluido en la capa 1):
male friendship and place; everyday food decision-making; gender and food choice; imagining a
plant-based shift; appeal and barriers of plant-based eating.

---

## 5. Léxico de masculinidad (§4.4) — mide performance, no dispara remuestreo por sí solo

Congelado. Deliberadamente **disjunto de la entrada 4**: los términos de comida, gimnasio y
constructo ya están prohibidos en la narrativa, así que medirlos sería medir cero. Este léxico cubre
los dominios que **sí** pueden aparecer legítimamente y donde la caricatura se manifestaría.

**Trabajo físico y manual:** manual, labour, labourer, trade, tradesman, hands-on, workshop, tools,
machinery, heavy, shift work, site, construction, engineering, mechanic, driver, warehouse.

**Deporte y competencia:** football, rugby, cricket, match, team, league, coach, compete,
competitive, win, winning, beat, rival, tournament, club side, five-a-side.

**Mando y jerarquía:** manage, manager, supervise, supervisor, foreman, in charge, lead, leader,
boss, run the team, responsible for, command.

**Proveedor y sostén:** provider, provide for, breadwinner, support the family, keep a roof,
put food on the table *(nota: esta expresión está prohibida por la entrada 4; se conserva en el
léxico solo por completitud de la categoría y su tasa esperada es cero)*, main earner, mortgage,
bills.

**Autonomía y autosuficiencia:** independent, self-reliant, on my own, sort it myself, no help,
fix it myself, DIY, self-employed, own business.

**Aficiones marcadas:** car, cars, motorbike, motorcycle, fishing, shooting, golf, darts, snooker,
pool, shed, garage, tinkering, restoring.

**Denominador:** aciertos por 100 palabras del bloque renderizado.

---

## 6. Umbral binomial de la elección forzada ciega (§4.4b)

- **24 pares** (3 candidatas × 8 celdas), cada par = celda real vs. su gemela de género invertido.
- Binomial de una cola, α = .05, H₀ = p 0.5.
- **Umbral de disparo: ≥ 17 de 24** (p = 0.0320). Referencias: 16/24 → p = 0.0757 (no dispara);
  18/24 → p = 0.0113.
- Disparo ⇒ el renderizador caricaturiza ⇒ **remuestreo** de las narrativas afectadas, con el
  conteo registrado.
- Se rechaza el diseño de 8 pares: a esa n, α = .05 a una cola solo dispara con 7/8 (p = 0.0352) u
  8/8 (p = 0.0039), de modo que una amplificación **parcial** —el escenario realista— se leería como
  aprobada.

---

## 7. Techo humano (§4.4c) — RETIRADO 2026-08-05 por inejecutable

**Esta entrada queda retirada.** Especificaba comparar la tasa del léxico de masculinidad de las
narrativas twin contra el agregado de las auto-descripciones humanas de FG3 y FG4 sobre rutina,
trabajo, hogar y aficiones. **Ese comparador no existe en los datos.**

Medido sobre las transcripciones estandarizadas: 10 882 palabras de participante humano en FG3+FG4
contienen 10 menciones de trabajo, 23 de hogar y 12 de aficiones — **~0.4 por 100 palabras**. Las
narrativas twin son **100% bosquejo de vida**. Comparar tasas léxicas entre un texto enteramente
biográfico y otro donde lo biográfico ocupa el 0.4% mide el denominador, no el estereotipo: las
ocho twins habrían superado cualquier techo así construido por razón aritmética, forzando un
remuestreo sin que existiera problema.

**La causa es de diseño y era previsible en retrospectiva:** la guía de discusión nunca pregunta a
los participantes por su vida laboral. Pregunta por comida y por género. El estudio humano nunca
iba a producir el comparador que esta entrada asumía.

**Qué sostiene ahora la auditoría de estereotipo.** Sus dos pruebas **internas y diferenciales**,
que no necesitan comparador humano porque cada narrativa se contrasta contra su propia gemela de
género invertido:

- **(a) control de género invertido** — ejecutado 2026-08-05 sobre 24 pares: 13 con el varón por
  encima, 11 con la mujer, delta medio **+0.238** por 100 palabras. Sin señal de amplificación.
- **(b) elección forzada ciega** — entrada 6, umbral 17/24, pendiente.

"Amplificación" es por definición un contraste, no un nivel absoluto, de modo que la retirada del
ancla absoluta no deja la auditoría sin su prueba: deja la prueba que corresponde al constructo.

## 8. Sonda conductual, capa 3 (§4.3)

- 8 personas `twinpop` × 3 muestras + 8 personas `demoonly` × 3 muestras = **48 respuestas**,
  24 por brazo.
- Parámetros de invocación: `conversation_history=[]`, `recent_transcript=None`, `hook=""`,
  `participant_response_max_tokens=800`, `temperature=1.0`, pregunta de la Sección 3 de la guía
  (*"Do you think your gender influences what you eat? Tell us more about why or why not."*).
- **Umbral de parada: el conteo de respuestas con ≥1 código verificado del codebook en `twinpop`
  excede al de `demoonly` en ≥ 6 de 24** (≥25 puntos porcentuales). Disparo ⇒ **parada del brazo**
  (no remuestreo — entrada keyed en codebook, §4.2).
- Declaración obligatoria: con `recent_transcript=None` la sonda omite la envoltura *"Respond
  naturally to the conversation above…"*. Es idéntico en ambos brazos, pero **la sonda no es un
  turno de sesión y no se presentará como tal**.

---

## 9. Umbral de colapso (§4.4d) — reformulado 2026-08-05 a descriptivo

Su comparador era el mismo que el de la entrada 7 —las auto-descripciones humanas— y desaparece
con él por la misma razón.

**Qué se hace ahora:** se reporta la distancia media por pares entre las 8 narrativas twin
**sin ancla humana y sin umbral de disparo**. Medida 2026-08-05: **0.9116** (TF-IDF, coseno). Es un
valor alto —textos casi ortogonales entre sí— y no sugiere un estereotipo con ocho disfraces, pero
**se reporta como descriptivo**, no como puerta superada, porque no hay comparador válido al mismo
nivel textual.

**La prueba de colapso que sí es concluyente sigue en pie y no se toca:** la del pre-registro §7
R4, que corre `collapse_metric.py` sobre las **transcripciones** de los tres brazos. Ahí la
comparación sí es homogénea —los tres brazos producen transcripciones de grupo focal— y es la que
puede distinguir "la riqueza genérica no ayuda" de "los 8 twins son el mismo señor". El
pre-chequeo narrativo era un aviso temprano, no la medida.

**Consecuencia sobre P1 y P5:** la regla que las declaraba no interpretables en dirección de
confirmación **ya no se dispara aquí**, porque no hay umbral. Se traslada íntegra a R4, evaluada
después de las sesiones.

## 10. Subconjunto masculinidad/carne para P3 (§6)

Del codebook sellado (`gold_standard_sealed/codebook_reference.csv`, 11 subtemas):

| Incluido | Etiqueta | Razón |
|---|---|---|
| **A.1** | Does influence | Reconoce influencia del género en la comida — el constructo del estudio |
| **A.2** | No influence | Niega la influencia; completa el tema A y evita seleccionar solo la mitad favorable |
| **A.3** | No influence, but… | Niega la influencia pero describe contextos generizados (barbacoa, porciones, quién cocina): el patrón que una caricatura produciría |
| **B.3** | Necessary | Única justificación 4N cuyo ejemplo canónico es gimnasio/proteína/músculo, es decir, la codificada masculinamente |

**Excluidos y por qué:** B.1 (Natural), B.2 (Normal), B.4 (Nice), C.1 (Unnatural), C.2
(Insufficient), C.3 (Not nice), D (Extreme cases). B.2 se excluye pese a su carga cultural: su
descripción es *"socially normative or default"*, neutra respecto del género. El subconjunto se fija
**estrecho y justificado**, no expansivo, para que no pueda ampliarse después hacia donde el
resultado convenga.

**Tema A completo, no solo su mitad afirmativa** — incluir A.1 y A.3 pero no A.2 habría sesgado el
subconjunto hacia los códigos que la caricatura infla.

---

## 11. Umbral de silencios forzados, G6

Contando `error_type ∈ {engagement_fallback_after_retry, engagement_api_error}` en
`api_calls.jsonl`. Referencia: los runs FG3/FG4 dan **0 en 12 de 13**.

| Conteo en un run twin | Acción |
|---|---|
| 0 | normal |
| 1–2 | **se marca y se reporta** junto al run; no se archiva |
| ≥ 3 | **se archiva y se relanza** con sufijo incrementado, documentado |

El umbral de archivado se fija en 3, por debajo de los 6 que motivaron el archivado de
`macho_meals_fg4_run02`, y por encima del ruido de una sola incidencia.

---

## 12. Umbral de decisión de P5 (§6.2)

- **Métrica primaria:** `normalized_mean_abs_reach_diff` de
  `salience_hierarchy_per_run.csv`. Es una **distancia**: menor = mejor preservación.
- **Regla, espejo de P1:** sobre la **media de las 3 réplicas por FG**,
  `|d_twin − d_demo| < |d_twin − d_full|` ⇒ P5 confirmada (el twin preserva la estructura tan poco
  como `demoonly`).
- **Equidistancia** (diferencia < 0.01) ⇒ indecisa, no favorable.
- **Magnitud solo en FG3.** Referencias: `full` 0.34 / 0.40 / 0.36 (media 0.3667); `demoonly`
  0.52 / 0.54 / 0.56 (media 0.54). Punto medio **0.4533**.
- **En FG4, lectura de suelo únicamente.** `kendall_tau_b` es indefinido en las tres réplicas de
  `demoonly` (`SYNTHETIC_SIDE_CONSTANT`) y negativo en dos de tres de `full`: **no se computa
  comparación de rangos en FG4**. Se reportan `normalized_mean_abs_reach_diff` (referencia
  `demoonly` 0.7778 ×3) y `union_kendall_tau_b`.
- **Secundarias, con acoplamiento declarado:** `kendall_tau_b`, `spearman_avg_ranks`,
  `top_theme_overlap_tie_aware` se reportan pero **no como corroboración independiente del recall**
  (§6.2).

---

## Fuentes consultadas para la entrada 2

- [Topic Summaries — 2021 Census (nomis)](https://www.nomisweb.co.uk/sources/census_2021_ts)
- [TS062 NS-SEC — ONS](https://www.ons.gov.uk/datasets/TS062)
- [TS067 Highest level of qualification — ONS](https://www.ons.gov.uk/datasets/TS067/editions/2021/versions/2)
- [TS003 Household composition — ONS](https://www.ons.gov.uk/datasets/TS003/editions/2021/versions/4)
- [TS054 Tenure — ONS](https://www.ons.gov.uk/datasets/TS054/editions/2021/versions/1)

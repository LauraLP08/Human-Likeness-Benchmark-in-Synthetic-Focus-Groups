# Adendum v5 — Brazo twin poblacional (FG3 + FG4)

*5 de agosto de 2026. **Archivo nuevo**: no sobrescribe nada. La v4 queda preservada en
`ADENDUM_TWIN_v4_2026-08-05_SUPERSEDED.md` (SHA-256 `51acff88…256eef7a`).*

**Advertencia sobre el rastro anterior.** Las reediciones v2, v3 y v4 se hicieron **in situ** sobre
`ADENDUM_TWIN_POBLACIONAL_CONGELADO_2026-08-04.md`. Sus textos intermedios **no existen como
archivos**; de ellos solo constan los hashes en los manifiestos v1–v4. Es una laguna real del rastro
de auditoría. Desde esta versión, cada reedición es un archivo nuevo y ninguno se sobrescribe.

---

## 0. Registro de enmiendas

| # | Fecha | Entrada | Clase de causa | Datos vistos entonces | Dirección del cambio | ¿Revierte revisión? | Hash resultante |
|---|---|---|---|---|---|---|---|
| 1 | 08-04 | — | congelación inicial | ninguno | — | no | `b4ad85d1…` |
| 2 | 08-05 | 2 | (iii) sustitución de fuente por defecto observado (personas imposibles) | ninguna sesión, ninguna cifra de resultado | mejora el brazo | no | `1286b2a4…` |
| 3 | 08-05 | 1 | (i) **inejecutable tal como está escrita** — `temperature` devuelve 400 | ninguna | permite ejecutar | no | `62feb67a…` |
| 4 | 08-05 | 7, 9 | (ii) ejecutada e inválida por construcción *(diagnóstico luego refutado — ver enmienda 5)* | narrativas generadas; ninguna sesión | **permitía continuar al brazo** | **sí — revierte §3.6/B4 sin declararlo al revisor** | `51acff88…` |
| 5 | 08-05 | 5, 7, 9 + G1 | (iv) **reparación de instrumento y reversión de la enmienda 4** | narrativas y puertas offline; ninguna sesión | **desfavorable al brazo** | no | *este documento* |

**Congelación dura.** La regla anterior ("ninguna entrada se altera después de la fase 3") quedó
tensionada: la entrada 7 se editó cuando sus objetos gobernados ya existían. Se sustituye por la
frontera que de verdad importa: **ninguna enmienda después de lanzar la primera sesión (fase 5).**
A partir de ahí solo hay desviaciones declaradas. Toda enmienda de clase (ii) o (iv) exige visto
bueno adversarial antes de surtir efecto.

**Reversión declarada (enmienda 4).** §3.6 pasó de "tercera familia obligatoria" a "renderiza
Claude" sin señalarlo al revisor que había cerrado ese punto. La decisión es correcta dado el
conjunto de opciones real —sin credencial de tercera familia, Gemini sería peor porque cerraría el
bucle sobre la vara de medir— pero la omisión al revisor queda registrada aquí. Obtener una
credencial de tercera familia es el arreglo para cualquier brazo futuro.

---

## 1. Reparaciones de instrumentos (enmienda 5)

Tres verificadores fallaban en silencio. Ninguno tenía control positivo ni negativo. Todos los
resultados que produjeron quedan **superados**, no borrados.

| Instrumento | Defecto | Reparación | Efecto sobre el resultado |
|---|---|---|---|
| **G1 `diff_is_only_background`** | comparaba **pertenencia** de líneas: reordenar o duplicar líneas de identidad era invisible; más un hueco de precedencia que aprobaba cualquier línea con la subcadena del encabezado | diff posicional (`difflib.ndiff`) con **igualdad de lista** contra el bloque esperado construido explícitamente | sigue PASS 8/8, ahora **demostrado** por controles |
| **Léxico (entrada 5)** | 75 términos en código frente a 77 congelados; y coincidencia por término completo perdía `supervisory` (38), `driving` (23), `management` (18), `trades` (11), `warehousing` (4) | 77 términos + variantes morfológicas **listadas explícitamente** (no stemming ciego, que capturaría `car`→`career`) | tasa media casi se duplica |
| **Extractor humano** | marcadores estrechos + piso de 40 palabras ⇒ **cero** extracciones sobre 137 turnos | marcadores amplios, piso 25 | de 0 a **7** auto-descripciones |
| **Distancia TF-IDF** | `log(n/df)` propia, espacios separados por grupo | `build_tfidf` y `cosine_distance` **del proyecto**, **espacio único compartido** | 0.9116 → **0.4603**; factor 2.1× en la dirección que favorecía al brazo |
| **`field_provenance`** | los 8 payloads declaraban los cuatro campos que G1 certifica ausentes | purgados al construir | contradicción interna eliminada |

**Controles obligatorios desde ahora.** Ningún resultado de verificación se acepta sin un control
**positivo** (defecto plantado que debe cazar) y uno **negativo** (caso limpio que debe pasar),
registrados en el reporte. G1 ya los tiene: cinco casos —limpio, `notes` con la subcadena del
encabezado, dos líneas intercambiadas, una duplicada, prosa alterada—, **los cinco correctos**
(`G1_controls.json`).

---

## 7. Techo humano — REINSTAURADO como diagnóstico descriptivo

**La retirada de la enmienda 4 se revierte.** Su justificación era **fácticamente incorrecta sobre
el procedimiento implementado**: alegaba que comparar tasas mediría el denominador porque lo
biográfico es el 0.4% de la transcripción humana, cuando la función calculaba la tasa **solo sobre
las frases auto-descriptivas extraídas** — el denominador ya estaba restringido en ambos lados. El
cero venía del regex y del piso, no de un defecto del comparador.

**Resultado, reportado íntegro y desfavorable:**

```
7 auto-descripciones humanas · media 1.50 · techo ×1.25 = 1.88
andrew 7.02 · daniel 4.72 · mark 4.37 · nick 4.02
james 3.32 · john 3.19 · gregor 3.12 · paul 1.18
POR ENCIMA DEL TECHO: 7 de 8
```

**Estatus: diagnóstico descriptivo, no puerta de disparo.** No porque el resultado incomode —se
reporta entero— sino porque el comparador no soporta el peso de una puerta:

- **n = 7 textos humanos, de 25 a 155 palabras**, breves y heterogéneos. El 7.02 de `andrew` y el
  2.38 humano más alto descansan en denominadores minúsculos; un solo acierto mueve la tasa
  varios puntos.
- **Las narrativas twin comparten plantilla** —mismo prompt, tres campos fijos, misma estructura—
  y son 100% bosquejo de vida. Los textos humanos son fragmentos dispersos extraídos de una
  conversación sobre comida y género: **no pertenecen necesariamente al mismo género textual.**
- Por tanto el contraste mide, en parte no cuantificada, **género textual y no estereotipo**.

**No se concluye que los perfiles twin estén estereotipados.** Se concluye que la puerta existe,
corre, dispara, y que su comparador es demasiado ruidoso y demasiado heterogéneo en género para
sostener una decisión de remuestreo. Las pruebas que sí sostienen la auditoría siguen siendo las
**internas y diferenciales**: (a) control de género invertido y (b) elección forzada ciega.

**Ninguna persona se regenera para superar este techo.** El objetivo es evaluar la construcción
congelada, no optimizarla contra la métrica.

---

## 9. Colapso — corregido conceptualmente

**El error de fondo de la versión anterior:** comparaba `twinpop` contra `human` y leía la
diferencia como colapso de los perfiles twin. Eso ignora lo que el proyecto **ya sabe**: las voces
sintéticas convergen entre sí muy por encima de las humanas **en los dos brazos existentes**.

Cifras ya publicadas en `analysis/figures/agent_fidelity_lexical_distinctiveness.csv`
(`between_speaker_median_cosine`; **mayor = voces más parecidas**):

| Condición | rango observado |
|---|---|
| **human** | 0.1716 – 0.2034 |
| **enriched** | 0.2150 – 0.3226 |
| **demographics-only** | 0.2206 – 0.3260 |

Una menor distintividad de `twinpop` frente a humanos **no demuestra** colapso específico de los
perfiles twin: es el patrón de partida de toda la simulación.

### 9.1 Resultado narrativo corregido, sin interpretar

Distancia media por pares, métrica canónica del proyecto, espacio compartido:

```
8 narrativas twin          0.4603
7 auto-descripciones hum.  0.6837
```

Se reporta. **No se interpreta como evidencia suficiente de que los perfiles twin estén
estereotipados ni de que sean "el mismo agente"**, por el confusor de plantilla de la entrada 7 y
porque el nivel narrativo no es el nivel donde la pregunta se decide.

### 9.2 R4 es la evaluación vinculante, sobre cuatro condiciones

R4 compara **human · enriched · demoonly · twinpop** sobre transcripciones, y separa dos contrastes:

- **A — brecha humano/sintético:** ¿todas las condiciones sintéticas tienen voces más homogéneas
  que las humanas?
- **B — brecha incremental de twinpop:** ¿twinpop diferencia **menos** que enriched y demoonly, es
  decir, añade colapso por encima de la homogeneización sintética ya observada?

**Regla interpretativa, fijada antes de ver datos de twinpop:**

| Patrón | Clasificación |
|---|---|
| `twinpop ≈ enriched ≈ demoonly`, las tres lejos de human | `GENERAL_SYNTHETIC_LEXICAL_CONVERGENCE` |
| twinpop **menos** distintivo que enriched y demoonly | `TWINPOP_INCREMENTAL_COLLAPSE` |
| twinpop **más** distintivo que ambos, pero lejos de human | `RELATIVE_IMPROVEMENT_HUMAN_GAP_REMAINS` |
| twinpop se aproxima a human | `EXPLORATORY_HUMAN_LIKE_DISTINCTIVENESS`, sujeto a revisión de longitud y contenido |
| réplicas o dispersión impiden distinguir los patrones | `INCONCLUSIVE` |

**Sin umbrales inventados post hoc.** El pre-registro no fijó margen numérico para este contraste;
por tanto se reportan **distancias, diferencias y dispersión descriptiva**, y no se convierten
retrospectivamente en prueba confirmatoria.

### 9.3 Consecuencia sobre P1 y P5 — corregida

**Se retira** la regla que declaraba P1 y P5 no interpretables por el solo hecho de que twinpop sea
menos distintivo que human. Sustituida por:

> La dirección **confirmatoria** de P1 y P5 queda comprometida **si y solo si** las transcripciones
> twinpop muestran menor diferenciación entre participantes que **ambos** referentes sintéticos,
> enriched y demoonly (`TWINPOP_INCREMENTAL_COLLAPSE`).
>
> Si las tres condiciones sintéticas quedan a distancia semejante de human
> (`GENERAL_SYNTHETIC_LEXICAL_CONVERGENCE`), el resultado se atribuye con prudencia a una
> **limitación general de la simulación**, no a los perfiles twin, y P1/P5 conservan su lectura.
>
> La lectura de **refutación** se conserva íntegra conforme al pre-registro (§8: este brazo puede
> refutar la sustitución, no confirmarla).

---

## 10. Comparabilidad de R4

- Solo intervenciones de participante. Se excluyen moderador, metadatos, prompts y nombres de campo.
- Mismas preguntas o ventanas comparables en las cuatro condiciones.
- Misma normalización para todos los textos.
- `build_tfidf` y `cosine_distance` canónicos del proyecto; **un único espacio vectorial compartido**
  para las cuatro condiciones.
- Sin ajuste de vocabulario ni preprocesamiento por condición.
- **FG3 y FG4 por separado antes de cualquier agregado.** Las tres réplicas visibles; ninguna media
  única oculta la variabilidad.
- Longitud de fragmentos controlada descriptivamente. Si se usan fragmentos de longitud fija, la
  misma longitud y la misma regla de submuestreo en las cuatro condiciones, fijada **antes** de ver
  resultados, o varias muestras deterministas con su distribución reportada.
- **Se reutiliza el procedimiento existente** (`scripts/agent_fidelity_stylometry.py`,
  `agent_fidelity_corpus.py`), que ya produce `between_speaker_median_cosine` para las tres
  condiciones actuales. La extensión a twinpop es **aditiva**, con puerta de hash que exige salida
  idéntica para human, enriched y demoonly. No se duplica el algoritmo.

---

## 11. Auditoría del efecto de plantilla (diagnóstico independiente)

Determina cuánto de la semejanza narrativa proviene de la estructura compartida.

1. Identificar **a priori** encabezados, etiquetas y frases invariantes introducidas por el
   renderizador.
2. Calcular la distancia narrativa con el **texto completo**.
3. Repetirla **excluyendo únicamente** esos elementos estructurales.
4. **No** eliminar contenido sustantivo por el mero hecho de repetirse.
5. Conservar **ambos** resultados y documentar exactamente qué se excluyó.

No sustituye a R4 y **no puede convertirse retrospectivamente en puerta de selección**.

---

## 12. Configs y arquitectura

Sin rediseño. Los configs twinpop se clonan de los experimentales originales y solo difieren en
`session_id`, `run_label` y `participants`. Una **prueba de equivalencia** falla si cambia cualquier
otra cosa: guía, objetivo de investigación, modelos, temperatura, límites de tokens, memoria, modo
de participación, prompt del moderador, reflexión o restricciones conversacionales. La rama de
renderizado ya autorizada es el único cambio de código; ni el orquestador ni el comportamiento de
las condiciones existentes se tocan.

---

*Las entradas 2, 3, 4, 6, 8, 10 y 12 de la v4 siguen vigentes sin cambios y no se reproducen aquí.
Esta versión sustituye únicamente las entradas 1 (reparaciones), 5 (léxico), 7 (techo) y 9
(colapso), y añade el registro de enmiendas, la comparabilidad de R4, la auditoría de plantilla y
la equivalencia de configs.*

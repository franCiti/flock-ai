# Especificación: bot que responde con el conocimiento de un empleado (MVP)

**Estado:** Borrador (v2)
**Fecha:** 2026-10-09

> Esta spec describe **qué** hace el sistema y **por qué**, no cómo se implementa.
> Las decisiones técnicas están en [docs/decisiones.md](../../docs/decisiones.md).
> Los puntos marcados **[A CLARIFICAR]** se resuelven en la fase de clarificación.

## Resumen

Un bot que responde preguntas usando el conocimiento de un empleado: su documentación,
sus procedimientos, sus correos, sus respuestas frecuentes. Cada empleado se representa con
una **persona virtual** que tiene su propia base de conocimiento.

El bot es un servicio que **otras aplicaciones consumen**. Además, el MVP incluye una
**interfaz web** para conversar con el bot y para administrar las fuentes de conocimiento de
cada persona; esa interfaz es un cliente más y el bot no depende de ella.

El conocimiento proviene de archivos en carpetas y de **Jira, Confluence y SharePoint**.

## Problema

Cuando un empleado no está disponible, o simplemente no da abasto, las dudas sobre su
área quedan sin respuesta o lo interrumpen. Mucho de ese conocimiento ya está escrito,
pero disperso y difícil de encontrar.

## Actores

| Actor | Descripción |
|---|---|
| **App cliente** | Cualquier aplicación autorizada que envía preguntas al bot y recibe las respuestas |
| **Usuario de la demo** | Persona que usa la interfaz web para conversar con una persona virtual |
| **Persona virtual** | Representa a un empleado; tiene un identificador, un perfil y una base de conocimiento propia |
| **Operador** | Quien carga el conocimiento de cada persona (archivos y fuentes externas), ejecuta la actualización y configura el bot |

## Historias de usuario

### HU1 — Preguntar al bot de una persona · Prioridad P1

Como **app cliente**, quiero enviar una pregunta dirigida a una persona virtual y recibir
una respuesta basada en su conocimiento, para resolver dudas sin depender del empleado.

**Criterios de aceptación**
1. **Dado** que la persona "juan-plataforma" tiene un documento que explica cómo hacer rollback,
   **cuando** la app pregunta "¿cómo hago rollback?" a esa persona,
   **entonces** recibe una respuesta coherente con ese documento.
2. **Dado** una respuesta basada en documentos, **entonces** incluye las **fuentes** usadas
   (qué documento y, si es posible, qué sección).
3. **Dado** cualquier respuesta, **entonces** el bot se presenta como el **asistente** de esa
   persona (usando su nombre visible, HU9) y nunca como la persona misma.
4. **Dado** una pregunta en un idioma, **entonces** el bot responde **en ese mismo idioma**,
   aunque los documentos estén en otro.

### HU2 — Cuando no sabe: decirlo y derivar · Prioridad P1

Como **app cliente**, quiero que el bot reconozca cuándo no tiene información y, si otra
persona virtual podría saberlo, me lo indique, para no recibir respuestas inventadas y saber a quién recurrir.

**Criterios de aceptación**
1. **Dado** una pregunta sin información relevante en la base de la persona,
   **entonces** el bot responde que no tiene esa información y **no** inventa una respuesta.
2. **Dado** ese caso, **entonces** el bot busca en las bases de las **otras** personas virtuales y,
   si encuentra a alguna que probablemente pueda ayudar, sugiere:
   "pregúntale a *Ana Gómez*, creo que puede ayudarte con eso".
3. **Dado** una sugerencia de derivación, **entonces** el bot **no responde con el contenido** de la
   otra persona: solo la recomienda.
4. **Dado** que ninguna otra persona tiene información relevante, **entonces** el bot solo responde
   que no tiene esa información.
5. **Dado** una pregunta respondida parcialmente, **entonces** el bot responde lo que tiene respaldado
   y aclara qué parte no pudo encontrar.
6. Los mensajes de estos casos son configurables (HU11).

### HU3 — Aislamiento entre personas · Prioridad P1

Como **operador**, quiero que cada persona virtual responda solo con su propio conocimiento,
para que no se mezclen áreas ni información.

**Criterios de aceptación**
1. **Dado** que solo "ana-datos" tiene información sobre un tema, **cuando** se le pregunta sobre ese
   tema a "juan-plataforma", **entonces** el bot responde que no tiene esa información y sugiere
   preguntarle a Ana (HU2), sin incluir el contenido de la base de Ana.
2. **Dado** un pedido a una persona que no existe, **entonces** el bot responde con un error claro
   ("persona no encontrada") y no intenta contestar.

### HU4 — Cargar y actualizar el conocimiento · Prioridad P1

Como **operador**, quiero colocar archivos en la carpeta de cada persona y ejecutar la
actualización, para que el bot use la información vigente.

**Criterios de aceptación**
1. **Dado** una carpeta raíz con una subcarpeta por persona, **cuando** se ejecuta la actualización,
   **entonces** cada subcarpeta se convierte en una persona virtual cuyo identificador es el nombre de la subcarpeta.
2. **Dado** un archivo nuevo o modificado, **cuando** se ejecuta la actualización, **entonces** el bot
   usa su contenido en las respuestas siguientes.
3. **Dado** un archivo borrado, **cuando** se ejecuta la actualización, **entonces** el bot deja de usarlo.
4. **Dado** que nada cambió, **cuando** se ejecuta la actualización, **entonces** no se reprocesa nada.
5. **Cuando** termina la actualización, **entonces** se informa un resumen por persona:
   agregados, modificados, borrados, sin cambios y omitidos (con el motivo).
6. **Formatos soportados:**
   - cualquier archivo de **texto** (Markdown, texto plano, CSV, JSON, HTML, XML, logs, código...);
   - **PDF** y **Word** (.docx);
   - **correos de Outlook guardados** (.msg): asunto, remitente, destinatarios, fecha y cuerpo.
   - **[A CLARIFICAR]** ¿También correos .eml, y los adjuntos de los .msg?
7. Los archivos que no se pueden leer como texto (imágenes, binarios, PDF escaneados) se omiten y se informan.
8. La actualización se ejecuta **automáticamente cada 30 minutos** (intervalo configurable) y también
   se puede disparar **manualmente** desde la interfaz web o con un comando.
9. **Dado** que hay una actualización en curso, **cuando** se dispara otra, **entonces** no se ejecutan
   dos a la vez: se informa que ya hay una en curso.

### HU5 — Conversación con contexto · Prioridad P2

Como **app cliente**, quiero hacer preguntas de seguimiento en una misma conversación,
para no repetir el contexto en cada pregunta.

**Criterios de aceptación**
1. **Dado** que en una conversación se preguntó "¿cómo hago un deploy?", **cuando** se pregunta
   "¿y si sale mal?", **entonces** el bot entiende que se refiere al deploy.
2. **Dado** una conversación nueva, **entonces** el bot no usa el historial de otras conversaciones.
3. Una conversación se conserva durante un **tiempo configurable** (por defecto, **1 día**).
   Pasado ese tiempo, una nueva pregunta con el mismo identificador empieza sin historial.
   **[A CLARIFICAR]** ¿El día se cuenta desde el inicio de la conversación o desde el último mensaje?

### HU6 — Respuesta progresiva con tiempo máximo · Prioridad P1

Como **app cliente**, quiero recibir la respuesta a medida que se genera y, al final, la
respuesta completa, dentro de un tiempo máximo, para mostrar avance y no esperar indefinidamente.

**Criterios de aceptación**
1. **Dado** una pregunta, **entonces** la app recibe fragmentos de la respuesta a medida que se generan.
2. **Al terminar**, la app recibe un mensaje final con la respuesta completa y sus fuentes.
3. El tiempo máximo de respuesta es **configurable** (por defecto, **2 minutos**). Si se supera,
   el bot deja de procesar y la app recibe un mensaje de **tiempo agotado**.
4. **Si** ocurre un error en medio de la respuesta, **entonces** la app recibe un mensaje de error
   que le permite distinguirlo de una respuesta completa.

### HU7 — Varias apps cliente · Prioridad P2

Como **operador**, quiero que varias aplicaciones usen el bot al mismo tiempo, cada una recibiendo
solo sus respuestas, y que una aplicación no autorizada no pueda usarlo.

**Criterios de aceptación**
1. **Dado** dos apps que preguntan a la vez, **entonces** cada una recibe solo las respuestas a sus preguntas.
2. **Dado** una app no autorizada, **entonces** no puede enviar preguntas ni leer respuestas.

### HU8 — Registro de lo respondido · Prioridad P3

Como **operador**, quiero un registro de cada pregunta, respuesta y fuentes usadas, para revisar
la calidad del bot.

**Criterios de aceptación**
1. **Dado** cualquier pregunta procesada, **entonces** queda registrada con: persona, app cliente,
   conversación, pregunta, respuesta, fuentes, derivación sugerida (si hubo) y fecha.
2. **[A CLARIFICAR]** ¿Cómo consulta el operador ese registro en el MVP?

### HU9 — Perfil de la persona virtual · Prioridad P1

Como **operador**, quiero definir cómo se presenta cada persona virtual, para que el bot use su
nombre real y no el nombre de la carpeta.

**Criterios de aceptación**
1. **Dado** una subcarpeta sin archivo de perfil, **cuando** se ejecuta la actualización, **entonces**
   se crea el archivo de perfil con valores por defecto tomados del nombre de la carpeta
   ("juan-plataforma" → nombre visible "Juan Plataforma").
2. **Dado** que el operador editó el perfil, **cuando** se ejecuta la actualización, **entonces** el bot
   usa los datos nuevos.
3. El archivo de perfil **no** forma parte del conocimiento: no se usa para responder preguntas.
4. El perfil incluye la **identidad de la persona en los sistemas externos** (por ejemplo, su email),
   necesaria para tomar solo su contenido de Jira, Confluence y SharePoint (HU12).
5. **[A CLARIFICAR]** Resto de los campos (propuesta: nombre visible, área o rol, y una descripción breve
   de sus temas, que también ayuda a elegir a quién derivar en HU2).

### HU10 — Interfaz web de demostración · Prioridad P2

Como **usuario de la demo**, quiero conversar con una persona virtual desde el navegador, para ver
el bot funcionando sin integrar otra aplicación.

**Criterios de aceptación**
1. Para usar la interfaz tengo que **iniciar sesión**. En el MVP existe un único usuario.
2. Puedo elegir con qué persona virtual conversar.
3. Veo la respuesta a medida que se genera y, al final, sus **fuentes** y la **derivación** si la hubo.
4. Mientras espero la respuesta, veo una **cuenta regresiva** con el tiempo máximo restante (HU6).
5. Si se agota el tiempo o hay un error, la interfaz lo muestra con claridad.
6. Puedo empezar una conversación nueva.
7. La interfaz usa el sistema de diseño de Flock.

### HU11 — Mensajes configurables · Prioridad P2

Como **operador**, quiero configurar en un archivo los mensajes fijos del bot, para ajustar su tono
sin cambiar el sistema.

**Criterios de aceptación**
1. Son configurables, al menos: no tengo información, sugerencia de derivación, persona no encontrada,
   tiempo agotado y error general.
2. El sistema trae **valores por defecto** razonables para todos los mensajes.
3. **[A CLARIFICAR]** Como el bot responde en el idioma de la pregunta: ¿el archivo tiene los mensajes
   por idioma, o se escriben en un idioma y el bot los traduce?

### HU12 — Agregar fuentes externas de conocimiento · Prioridad P2

Como **operador**, quiero agregar a una persona virtual fuentes de **Jira, Confluence o SharePoint**
desde la interfaz web, para que su base de conocimiento incluya esa información.

**Criterios de aceptación**
1. Desde la interfaz puedo agregar, ver y quitar las fuentes de una persona, indicando el tipo
   (Jira, Confluence, SharePoint) y qué parte tomar (por ejemplo, un proyecto, un espacio o una carpeta).
2. **Cuando** se ejecuta la actualización, **entonces** el contenido de esas fuentes se incorpora
   a la base de la persona con las mismas reglas que los archivos: nuevos, modificados y borrados (HU4).
3. Las respuestas basadas en estas fuentes las citan con su **enlace** al sistema original.
4. **Dado** que quito una fuente, **entonces** su contenido deja de usarse en las respuestas.
5. Las fuentes **solo alimentan la base de conocimiento**: el bot no las consulta en vivo mientras responde.
6. Las credenciales de acceso a las fuentes no se muestran en la interfaz una vez guardadas.
7. De cada fuente se toma **solo lo que escribió la persona**:
   - **Confluence:** páginas de las que es autora.
   - **SharePoint:** archivos de los que es autora.
   - **Jira:** issues en los que es **reporter** o **assignee**.
8. **Dado** que la persona no tiene configurada su identidad en el perfil (HU9), **entonces** sus fuentes
   externas no se procesan y se informa en el resumen de la actualización.
9. La actualización de estas fuentes sigue la misma programación que la de archivos (HU4).
10. **[A CLARIFICAR]** Confluence: ¿"autora" es solo quien creó la página, o también quien la editó?
11. **[A CLARIFICAR]** Jira: de esos issues, ¿se toman todos los comentarios (también los de otras personas)
    o solo la descripción y los comentarios de la persona?

## Casos borde

- Pregunta repetida (la misma petición enviada dos veces): se responde una sola vez.
- Pedido con formato inválido o versión no soportada: error claro, sin respuesta.
- Persona sin documentos (carpeta vacía): responde que no tiene información y aplica la derivación (HU2).
- Archivo sin texto extraíble (por ejemplo, un PDF escaneado): se omite y se informa en el resumen.
- Perfil de persona con formato inválido: se informa en el resumen y se usan los valores por defecto.
- El servicio del modelo de lenguaje no responde: la app recibe un error, no una respuesta vacía.
- Pregunta mientras se está actualizando el conocimiento: **[A CLARIFICAR]** ¿responde con la versión anterior?

## Requisitos no funcionales

- **Idioma:** responde en el idioma de la pregunta.
- **Tiempo de respuesta:** máximo configurable, por defecto 2 minutos (HU6).
  **[A CLARIFICAR]** ¿Hay un objetivo para el primer fragmento?
- **Configuración:** retención de conversaciones, tiempo máximo, intervalo de actualización y mensajes
  se configuran sin cambiar el sistema.
- **Documentación de interfaces:** la API web tiene documentación interactiva, y el contrato de
  mensajería del bot (su API pública) está documentado y versionado, para que cualquier equipo
  pueda integrarse sin leer el código.
- **Privacidad:** los documentos solo salen del entorno hacia el servicio del modelo de lenguaje, y
  únicamente los fragmentos necesarios para cada respuesta.
- **Disponibilidad:** el bot responde siempre que el servicio esté levantado; no depende de la
  disponibilidad del empleado.

## Criterios de éxito

1. Existe un **set de evaluación** de al menos 20 preguntas reales por persona de prueba, con su
   respuesta esperada, que incluye preguntas que debe derivar a otra persona.
2. **[A CLARIFICAR]** Porcentaje mínimo de respuestas correctas y con fuente.
3. Ante preguntas fuera de la base, el bot **no inventa** en ningún caso del set de evaluación.

## Fuera de alcance (MVP)

- Varios usuarios, SSO y permisos por usuario (el MVP tiene un único usuario con login).
- Ejecutar tareas en nombre del empleado.
- Consultar fuentes externas en vivo durante una respuesta.
- Correo como fuente directa (buzones); sí se aceptan correos guardados como archivos (HU4).

## Funcionalidades futuras

- **Preguntas frecuentes por persona:** poder preguntarle al bot cuáles son las preguntas más
  frecuentes que se le hacen a una persona virtual.

## Preguntas abiertas

1. Formatos: ¿.eml y adjuntos de .msg? (HU4)
2. Retención: ¿desde el inicio o desde el último mensaje? (HU5)
3. Consulta del registro de lo respondido (HU8).
4. Campos del perfil de la persona (HU9).
5. Mensajes configurables e idiomas (HU11).
6. Fuentes externas: definición de autoría en Confluence y comentarios de Jira (HU12).
7. Comportamiento durante una actualización del conocimiento.
8. Objetivo de tiempo para el primer fragmento.
9. Umbral de éxito del set de evaluación.

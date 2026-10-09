# Especificación: bot que responde con el conocimiento de un empleado (MVP)

**Estado:** Borrador
**Fecha:** 2026-10-09

> Esta spec describe **qué** hace el sistema y **por qué**, no cómo se implementa.
> Las decisiones técnicas están en [docs/decisiones.md](../../docs/decisiones.md).
> Los puntos marcados **[A CLARIFICAR]** se resuelven en la fase de clarificación.

## Resumen

Un bot que responde preguntas usando el conocimiento de un empleado: su documentación,
sus procedimientos, sus respuestas frecuentes. Cada empleado se representa con una
**persona virtual** que tiene su propia base de conocimiento.

El bot es un servicio que **otras aplicaciones consumen**: no tiene interfaz propia en el MVP.

## Problema

Cuando un empleado no está disponible, o simplemente no da abasto, las dudas sobre su
área quedan sin respuesta o lo interrumpen. Mucho de ese conocimiento ya está escrito,
pero disperso y difícil de encontrar.

## Actores

| Actor | Descripción |
|---|---|
| **App cliente** | Cualquier aplicación autorizada que envía preguntas al bot y recibe las respuestas |
| **Persona virtual** | Representa a un empleado; tiene un identificador y una base de conocimiento propia |
| **Operador** | Quien carga los archivos de cada persona y ejecuta la actualización del conocimiento |

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
   persona y nunca como la persona misma.

### HU2 — Decir "no sé" en lugar de inventar · Prioridad P1

Como **app cliente**, quiero que el bot reconozca cuándo no tiene información, para no
recibir respuestas inventadas.

**Criterios de aceptación**
1. **Dado** una pregunta sin información relevante en la base de la persona,
   **entonces** el bot responde que no encontró información sobre eso y **no** da una respuesta inventada.
2. **Dado** una pregunta respondida parcialmente por la base, **entonces** el bot responde lo que
   tiene respaldado y aclara qué parte no pudo encontrar.
3. **[A CLARIFICAR]** Cuando no sabe, ¿sugiere algo? (contactar al empleado, otra persona virtual, nada).

### HU3 — Aislamiento entre personas · Prioridad P1

Como **operador**, quiero que cada persona virtual responda solo con su propio conocimiento,
para que no se mezclen áreas ni información.

**Criterios de aceptación**
1. **Dado** que solo "ana-datos" tiene información sobre un tema, **cuando** se le pregunta
   sobre ese tema a "juan-plataforma", **entonces** el bot responde que no tiene información.
2. **Dado** un pedido a una persona que no existe, **entonces** el bot responde con un error
   claro ("persona no encontrada") y no intenta contestar.

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
6. Formatos soportados: Markdown, texto plano, PDF y Word (.docx). Los demás se omiten y se informan.

### HU5 — Conversación con contexto · Prioridad P2

Como **app cliente**, quiero hacer preguntas de seguimiento en una misma conversación,
para no repetir el contexto en cada pregunta.

**Criterios de aceptación**
1. **Dado** que en una conversación se preguntó "¿cómo hago un deploy?", **cuando** se pregunta
   "¿y si sale mal?", **entonces** el bot entiende que se refiere al deploy.
2. **Dado** una conversación nueva, **entonces** el bot no usa el historial de otras conversaciones.
3. **[A CLARIFICAR]** ¿Cuánto tiempo se conserva una conversación?

### HU6 — Respuesta progresiva · Prioridad P2

Como **app cliente**, quiero recibir la respuesta a medida que se genera y, al final, la
respuesta completa, para mostrar avance al usuario y guardar el resultado final.

**Criterios de aceptación**
1. **Dado** una pregunta, **entonces** la app recibe fragmentos de la respuesta a medida que se generan.
2. **Al terminar**, la app recibe un mensaje final con la respuesta completa y sus fuentes.
3. **Si** ocurre un error en medio de la respuesta, **entonces** la app recibe un mensaje de error
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
   conversación, pregunta, respuesta, fuentes y fecha.
2. **[A CLARIFICAR]** ¿Cómo consulta el operador ese registro en el MVP?

## Casos borde

- Pregunta repetida (la misma petición enviada dos veces): se responde una sola vez.
- Pedido con formato inválido o versión no soportada: error claro, sin respuesta.
- Persona sin documentos (carpeta vacía): responde que no tiene información.
- Archivo sin texto extraíble (por ejemplo, un PDF escaneado): se omite y se informa en el resumen.
- El servicio del modelo de lenguaje no responde: la app recibe un error, no una respuesta vacía.
- Pregunta mientras se está actualizando el conocimiento: **[A CLARIFICAR]** ¿responde con la versión anterior?

## Requisitos no funcionales

- **Idioma:** **[A CLARIFICAR]** ¿responde en el idioma de la pregunta, o siempre en español?
- **Tiempo de respuesta:** **[A CLARIFICAR]** objetivo para el primer fragmento y para la respuesta completa.
- **Privacidad:** los documentos solo salen del entorno para el servicio del modelo de lenguaje,
  y únicamente los fragmentos necesarios para cada respuesta.
- **Disponibilidad:** el bot responde siempre que el servicio esté levantado; no depende de la
  disponibilidad del empleado.

## Criterios de éxito

1. Existe un **set de evaluación** de al menos 20 preguntas reales por persona de prueba,
   con su respuesta esperada.
2. **[A CLARIFICAR]** Porcentaje mínimo de respuestas correctas y con fuente.
3. Ante preguntas fuera de la base, el bot **no inventa** en ningún caso del set de evaluación.

## Fuera de alcance (MVP)

- Interfaz de usuario propia (app Java, front).
- Usuarios, login y permisos por usuario.
- Ejecutar tareas en nombre del empleado.
- Fuentes distintas de archivos en carpeta (SharePoint, Confluence, Jira, mail).
- Administración de personas y fuentes desde una interfaz.
- Actualización automática del conocimiento.

## Preguntas abiertas

1. **Nombre visible de la persona:** el identificador sale de la carpeta ("juan-plataforma"), pero
   ¿cómo se presenta el bot? ("Soy el asistente de Juan Pérez, de Plataforma"). ¿De dónde sale ese nombre?
2. Qué sugiere el bot cuando no sabe (HU2).
3. Retención de las conversaciones (HU5).
4. Cómo se consulta el registro de lo respondido (HU8).
5. Comportamiento durante una actualización del conocimiento.
6. Idioma de las respuestas.
7. Tiempos de respuesta objetivo.
8. Umbral de éxito del set de evaluación.

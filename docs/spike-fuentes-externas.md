# Spike: cómo leer Jira, Confluence y SharePoint (T46)

Fecha: 2026-10-15. Riesgo que resuelve: R1 / D30 (plan 5.4). Investigación sobre documentación,
código y issues públicos de cada servidor y API; **no se probó contra cuentas reales** (no hay
cuentas de servicio todavía): lo que falta verificar está al final.

## Qué hace falta (plan 5.4, spec HU12)

Un sync **desatendido e incremental**, cada 30 minutos, con cuenta de servicio:

1. Credenciales sin login interactivo.
2. Jira: JQL arbitrario con paginación completa, **todos** los comentarios con autor y fecha, y la
   lista de ids que cumplen la consulta (para detectar bajas).
3. Confluence: CQL arbitrario con paginación completa, cuerpo de la página, ruta de páginas padre y URL.
4. SharePoint: listar un sitio/carpeta con autor de cada archivo, descargar el binario (pasa por los
   mismos parsers que los archivos locales) y detectar cambios y bajas.
5. Reintentos ante límites de pedidos (429).

## Resultado

| Sistema | Candidatos evaluados | Bloqueante | Elección |
|---|---|---|---|
| **Jira** | Atlassian Rovo MCP (oficial, remoto), `sooperset/mcp-atlassian` (comunidad) | Rovo: paginación de JQL con fallas reportadas después del arreglo, solo Cloud y alojado por Atlassian. sooperset: comentarios topeados en 100 y aplanados a texto, páginas de 50, y los tokens de cuentas de servicio (con alcance) dan 401 contra la URL del sitio | **API REST** |
| **Confluence** | Los mismos | sooperset: `confluence_search` **no pagina** (sin `start` ni cursor) y no da ancestros. Rovo: sin ancestros, paginación no documentada | **API REST** |
| **SharePoint** | Work IQ SharePoint (Microsoft, Agent 365), Microsoft MCP Server for Enterprise, `Softeria/ms-365-mcp-server`, `DEmodoriGatsuO/sharepoint-mcp` y otros | Los oficiales solo funcionan con un usuario que da su consentimiento (y Work IQ pide licencia de Copilot, máximo 20 resultados, sin delta). Softeria (el más completo, con delta) no soporta credenciales de aplicación. El resto no tiene delta ni descarga del binario | **Microsoft Graph** |

Además de cada bloqueante, MCP no aporta en la ingesta: sus herramientas están pensadas para que un
LLM haga consultas puntuales (resultados topeados, texto aplanado, esquemas que cambian sin aviso),
suma un contenedor y un punto de falla por sistema y no resuelve la autenticación. La interfaz
`SourceConnector` no cambia: cada conector sigue devolviendo un `SyncPlan`.

## Cómo se usaría cada API

### Jira Cloud (REST v3)

- **Búsqueda:** `POST /rest/api/3/search/jql` con `{jql, fields, maxResults, nextPageToken}`, hasta
  `isLast`. (`/rest/api/3/search` ya no existe.) Sin `fields` devuelve solo ids: sirve para la
  lista de bajas. Mandar `"nextPageToken": null` en el primer pedido y cortar si un token se repite
  (hay reportes de bucles).
- **Consulta:** `project = <scope> AND (reporter = <accountId> OR assignee = <accountId>) AND
  updated >= "<cursor>" ORDER BY updated`.
- **Comentarios:** `GET /rest/api/3/issue/{key}/comment?startAt&maxResults` (cuerpo en ADF, autor y
  fechas); hay que convertir ADF a texto.
- **Autenticación:** cuenta de servicio con token con alcance (scoped), que solo funciona por el
  gateway `https://api.atlassian.com/ex/jira/{cloudId}`.

### Confluence Cloud

- **Búsqueda:** v1 `GET /wiki/rest/api/search?cql=…&limit=…`, siguiendo `_links.next` (cursor).
  v2 no tiene CQL.
- **Consulta:** `space = <scope> AND (creator = <accountId> OR contributor = <accountId>) AND
  lastmodified >= "<cursor>"`.
- **Página:** v2 `GET /wiki/api/v2/pages/{id}?body-format=storage` y `/pages/{id}/ancestors` para la
  ruta de páginas padre (la sección de la cita); el XHTML de Confluence se convierte a Markdown.
- **Autenticación:** la misma cuenta de servicio de Atlassian, por `https://api.atlassian.com/ex/confluence/{cloudId}`.

### SharePoint (Microsoft Graph)

- **Credenciales de aplicación:** app de Entra ID con certificado (MSAL, `acquire_token_for_client`).
  Permiso `Sites.Selected` y acceso de solo lectura otorgado **sitio por sitio**
  (`POST /sites/{id}/permissions` con `roles: ["read"]`, lo hace un administrador): mínimo privilegio.
- **Sitio y carpeta:** `GET /sites/{host}:/sites/{path}`, `/sites/{id}/drives`,
  `/drives/{id}/root:/{carpeta}`.
- **Cambios y bajas:** `GET /drives/{id}/root/delta` siguiendo `nextLink` hasta el `deltaLink`, que es
  el cursor. Las bajas llegan con la faceta `deleted`; los ítems se siguen por id (delta no trae la
  ruta), y se filtra por la carpeta de la fuente con sus ancestros. Si el `deltaLink` vence (410), se
  enumera todo de nuevo.
- **Contenido:** `GET /drives/{id}/items/{id}/content` (redirección a una URL de descarga).
- **Autor:** `createdBy.user` (quien subió el archivo; es la columna "Created By"). Se compara por el
  id de Entra del usuario, resuelto una vez desde el email con `/users/{email}` (permiso
  `User.Read.All`); el email del archivo puede faltar o no coincidir con el UPN.

### Comunes

- Cliente HTTP asíncrono (`httpx`) compartido, con paginación y reintentos ante 429/503 respetando
  `Retry-After` (o `X-RateLimit-Reset` en Atlassian, que a veces no manda `Retry-After`), con espera
  creciente y aleatoria.
- Tests con respuestas grabadas, sin cuentas reales (como pide el "hecho cuando" de T50–T52).
- Las credenciales quedan en el `.env` del **Ingestion Worker** (D39 no cambia). Ya no hay servidores
  MCP, así que la excepción a mTLS de D40 deja de hacer falta: el worker habla HTTPS con cada nube.

## La identidad de la persona en cada sistema

El perfil guarda hoy `identities.email` (HU9.4, HU12.8). Con las APIs:
- **Atlassian Cloud:** JQL y CQL filtran por **accountId**, no por email. Se puede resolver
  `GET /rest/api/3/user/search?query=<email>`, pero si el usuario ocultó su email en la privacidad
  de su perfil de Atlassian, la búsqueda no lo encuentra.
- **SharePoint:** se resuelve el id de Entra desde el email (`/users/{email}`), que siempre funciona
  dentro del tenant.

Acordado (D43): el perfil acepta además `identities.atlassian_account_id` (opcional). Si falta, el
conector lo busca por email; si no lo encuentra, las fuentes de Atlassian de esa persona no se
procesan y el resumen lo informa (igual que HU12.8 sin identidad).

## Qué cambió en el plan

- Plan 5.4: "Fuentes externas vía API REST"; sin servidores MCP. Estructura del proyecto (1.x):
  `connectors/jira.py`, `confluence.py` y `sharepoint.py` sobre un cliente HTTP común, en lugar de
  `mcp_client.py`. Dependencias: sin `mcp` ni `langchain-mcp-adapters`; con `msal`.
- Plan 7.5 y 7.7: sin contenedores MCP ni perfil `external-sources`; D40 queda sin efecto.
- Tabla de secretos (7.x): las cuentas de servicio van al Ingestion Worker.
- T49 pasa a ser "Cliente HTTP de fuentes externas" (paginación, reintentos, autenticación de
  Atlassian y de Microsoft), hecho cuando: tests con respuestas simuladas de paginación, 429 y token.
- Perfil de persona (plan 5.7): campo opcional `atlassian_account_id`.

## Falta verificar con cuentas reales (en T50–T52 y el cierre T53)

- Que la cuenta de servicio de Atlassian con token con alcance pueda buscar por JQL/CQL y leer
  comentarios y páginas de los espacios y proyectos que se le den.
- Si JQL de Cloud todavía acepta un email en `reporter =` (se asume que no).
- Que delta de Graph funcione con `Sites.Selected` (la documentación nombra `Files.Read.All`).
- El tope de `maxResults` de `/search/jql`.
- Jira y Confluence **Data Center**: las APIs equivalentes existen (`/rest/api/2/search` con
  `startAt`, tokens personales), pero el MVP apunta a Cloud; confirmar cuál usa Flock.

## Fuentes principales

- Atlassian Rovo MCP: https://github.com/atlassian/atlassian-mcp-server ·
  paginación: https://github.com/atlassian/atlassian-mcp-server/issues/118 ·
  herramientas: https://developer.atlassian.com/cloud/rovo-mcp/guides/supported-tools/
- sooperset/mcp-atlassian: https://github.com/sooperset/mcp-atlassian ·
  tokens con alcance: https://github.com/sooperset/mcp-atlassian/issues/968
- Cuentas de servicio de Atlassian: https://support.atlassian.com/user-management/docs/manage-api-tokens-for-service-accounts/
- JQL con `nextPageToken`: https://confluence.atlassian.com/display/JIRAKB/Run+JQL+search+query+using+Jira+Cloud+REST+API
- Búsqueda CQL de Confluence: https://developer.atlassian.com/cloud/confluence/rest/v1/api-group-search/
- Privacidad de usuarios de Atlassian: https://developer.atlassian.com/cloud/jira/platform/deprecation-notice-user-privacy-api-migration-guide/
- Softeria/ms-365-mcp-server: https://github.com/Softeria/ms-365-mcp-server
- Microsoft MCP Server for Enterprise: https://github.com/microsoft/EnterpriseMCP
- Delta de Graph: https://learn.microsoft.com/en-us/graph/api/driveitem-delta?view=graph-rest-1.0
- Permisos por sitio (`Sites.Selected`): https://learn.microsoft.com/en-us/graph/api/site-post-permissions?view=graph-rest-1.0
- Retiro de Azure ACS: https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/retirement-announcement-for-azure-acs

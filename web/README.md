# web

Front de la demo de flock-ai: React + TypeScript con Vite. Ver las secciones 1.5, 6.6 y 6.7 del
[plan](../specs/001-bot-respuestas/plan.md).

## Comandos

Requieren Node.js 24 o superior.

| Qué                           | Comando                                                     |
| ----------------------------- | ----------------------------------------------------------- |
| Instalar dependencias         | `npm ci`                                                    |
| Servidor de desarrollo        | `npm run dev` (en `http://localhost:5173`)                  |
| Tests                         | `npm test`                                                  |
| Tests contra la Core API real | `npm run test:api`                                          |
| Linters                       | `npm run lint`, `npm run format:check`, `npm run typecheck` |
| Build                         | `npm run build`                                             |
| Regenerar los tipos de la API | `npm run generate:api`                                      |

En desarrollo, Vite manda `/api` y `/docs` a la Core API (`CORE_API_URL`, por defecto
`http://localhost:8080`), así el front y la API comparten origen como en producción (plan 6.1).

## Tipos de la API

1. `src/api/openapi.json` es una copia del OpenAPI de la Core API. La escribe y la controla
   `OpenApiSnapshotTest` en `core-api`: si la API cambia, ese test falla hasta actualizar la copia:

   ```bash
   cd core-api && ./mvnw test -Dtest=OpenApiSnapshotTest -Dopenapi.update=true
   ```

2. `npm run generate:api` genera `src/api/schema.ts` con `openapi-typescript`. Un test falla si
   quedó desactualizado.

Mientras la Core API no publique `/api/auth/*` (T32), los tipos y las llamadas del login están
escritos a mano en `src/api/auth.ts` (marcados `TODO(T32)`).

## Tests

- `npm test`: tests de componentes con Vitest y Testing Library, contra una API simulada con MSW
  (`src/test/server.ts`). Cualquier pedido sin simular hace fallar el test.
- `npm run test:api`: el login contra una Core API levantada (`tests/api/`), con el usuario inicial
  del `.env` (`ADMIN_USERNAME`, `ADMIN_PASSWORD`). **Falla hasta que esté la T32**; no corre en
  `npm test` ni en `scripts/check.sh`.

## Estilos

Tokens del design system de Flock (`src/styles/tokens.css`, copia textual del skill
`flock-design-system`) como variables CSS, más CSS Modules por componente. Los valores que el design
system documenta pero no declara como variable están en `src/styles/global.css`.

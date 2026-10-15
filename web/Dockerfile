# Image of the web app (plan 6.1, 7.5): Node builds the front, nginx serves it and proxies /api and
# /docs to the Core API. Build context: the repository root.
#
#   docker compose build web

ARG NODE_IMAGE=node:24.19.0-slim
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.30.0-alpine

# --- Build: the static files of the front ------------------------------------------------------
FROM ${NODE_IMAGE} AS build

# Root certificate of the corporate network, if the network inspects HTTPS (plan 7.8): every .crt in
# infra/corp-ca/ is trusted by npm; with none, the file is empty and nothing changes.
COPY infra/corp-ca/ /tmp/corp-ca/
RUN cat /tmp/corp-ca/*.crt > /tmp/corp-ca.pem 2>/dev/null || true
ENV NODE_EXTRA_CA_CERTS=/tmp/corp-ca.pem

WORKDIR /app
# Dependencies first: they change less often than the code, so their layer is reused.
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- Runtime: nginx without root, listening on 8080 --------------------------------------------
FROM ${NGINX_IMAGE}

COPY web/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY web/nginx/proxy.inc web/nginx/security-headers.inc /etc/nginx/conf.d/
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

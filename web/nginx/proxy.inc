# Proxy settings shared by /api and /docs (included by default.conf).
proxy_http_version 1.1;
proxy_set_header Connection "";
# The browser's host and port: the Core API builds its redirects (e.g. /docs -> /docs/) with them.
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;

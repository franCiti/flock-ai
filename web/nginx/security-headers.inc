# Headers of the front's pages (included by default.conf). The CSP is the third barrier for the
# answers (spec HU15.6, plan 6.6): only this origin's scripts, styles and connections, no external
# images, no framing.
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer" always;
add_header X-Frame-Options "DENY" always;

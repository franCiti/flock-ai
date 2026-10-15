# Image of the Core API (plan section 7.5): Maven build, then a JRE 21 runtime. Build context: the
# repository root.
#
#   docker compose build core-api

ARG NODE_IMAGE=node:24.19.0-slim
ARG JDK_IMAGE=eclipse-temurin:21.0.12_8-jdk-noble
ARG JRE_IMAGE=eclipse-temurin:21.0.12_8-jre-noble

# --- AsyncAPI documentation (plan 2.7), served under /docs/asyncapi ----------------------------
FROM ${NODE_IMAGE} AS docs

# Root certificate of the corporate network, if the network inspects HTTPS (plan 7.8): every .crt in
# infra/corp-ca/ is trusted by npm; with none, the file is empty and nothing changes.
COPY infra/corp-ca/ /tmp/corp-ca/
RUN cat /tmp/corp-ca/*.crt > /tmp/corp-ca.pem 2>/dev/null || true
ENV NODE_EXTRA_CA_CERTS=/tmp/corp-ca.pem

WORKDIR /contracts
COPY contracts/ ./
RUN bash build-docs.sh

# --- Build: the Spring Boot jar ------------------------------------------------------------------
FROM ${JDK_IMAGE} AS build

# Same corporate root certificates (plan 7.8): for the system (the wrapper downloads Maven with
# wget) and for Java (Maven downloads the dependencies).
COPY infra/corp-ca/ /usr/local/share/ca-certificates/corp/
RUN update-ca-certificates \
    && for crt in /usr/local/share/ca-certificates/corp/*.crt; do \
      [ -f "$crt" ] || continue; \
      keytool -importcert -noprompt -cacerts -storepass changeit -alias "corp-$(basename "$crt" .crt)" -file "$crt"; \
    done
# The Maven Wrapper checks the .zip distribution; without unzip it downloads the .tar.gz instead.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build/core-api
COPY core-api/.mvn .mvn
COPY core-api/mvnw core-api/pom.xml ./
COPY core-api/src src
# The build copies ../contracts/docs into the jar (pom.xml).
COPY --from=docs /contracts /build/contracts
# Tests, Spotless and Checkstyle run outside the image (scripts/check.sh): the tests need Docker.
RUN --mount=type=cache,target=/root/.m2 \
    sh mvnw --batch-mode --no-transfer-progress package \
      -DskipTests -Dcheckstyle.skip -Dspotless.check.skip \
    && cp target/core-api-*.jar /build/app.jar

# --- Runtime: the JRE and the jar; no build tools ----------------------------------------------
FROM ${JRE_IMAGE}

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin flock

WORKDIR /app
COPY --from=build /build/app.jar /app/app.jar
COPY core-api/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

EXPOSE 8080

# Starts as root only to prepare the certificates, then runs the command as the unprivileged user
# "flock" (docker-entrypoint.sh).
ENTRYPOINT ["/bin/sh", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app/app.jar"]

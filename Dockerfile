# --- builder: compile the standalone native Rust server (switchyard-server).
# Since upstream #268 (2026-08-07) the routing algorithms live in Rust crates;
# the Python package no longer ships them. crates.io has no post-#268 release
# yet, so we build from a pinned main commit. No Python needed at all.
ARG RUST_VERSION=1.96.1
FROM rust:${RUST_VERSION}-bookworm AS builder

# Pin to a main commit that includes #268 (legacy Python routing removal) and
# the native server. Bump deliberately; the TOML config surface is
# deny_unknown_fields, so validate with --dry-run after any bump.
ARG SWITCHYARD_SHA=f30498d31b6d436954960f5a4b5a8cd3a5afba27

WORKDIR /opt
RUN curl -fsSL "https://github.com/NVIDIA-NeMo/Switchyard/archive/${SWITCHYARD_SHA}.tar.gz" \
        | tar xz \
    && mv "Switchyard-${SWITCHYARD_SHA}" switchyard
WORKDIR /opt/switchyard
RUN cargo build --locked --release -p switchyard-server

# --- runtime: static-ish binary on a slim base. Half the size of the old
# Python image, and no site-packages patch: reasoning suppression for the
# classifier is plain config now (extra_body on the classifier target in
# routes.toml).
FROM debian:bookworm-slim

# APT::Sandbox::User=root: some colima/lima VMs break the _apt sandbox user's
# access to downloaded lists (apt reports "invalid signature" while gpgv
# verifies fine). Root sandbox inside a build container is safe, and harmless
# on hosts without the problem. curl is for the compose healthcheck.
RUN apt-get -o APT::Sandbox::User=root update \
    && apt-get -o APT::Sandbox::User=root install --no-install-recommends -y \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder \
    /opt/switchyard/target/release/switchyard-server \
    /usr/local/bin/switchyard-server

WORKDIR /app
# Baked-in default config; docker-compose bind-mounts ./routes.toml over it
# so config tweaks don't need an image rebuild.
COPY routes.toml /app/routes.toml
# Writable log dir for --routing-log-file. uid 1000 matches the first user of
# the previous Python image, so the existing switchyard-logs volume carries
# its routing.jsonl history across the migration.
RUN mkdir -p /app/logs && chown 1000:1000 /app/logs
ENV HOME=/tmp
USER 1000:1000

EXPOSE 4100

# The native server has no intake sink: request bodies never leave the
# container except toward the configured Fireworks endpoints. docker-compose
# overrides this CMD to add --routing-log-file for the per-request JSONL log.
ENTRYPOINT ["switchyard-server"]
CMD ["--config", "/app/routes.toml", "--host", "0.0.0.0", "--port", "4100"]

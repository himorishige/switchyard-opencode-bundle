# --- builder: install the standalone native Rust server (switchyard-server).
# The routing algorithms live in Rust crates; the Python package no longer
# ships them on the native path. Since Switchyard 0.2.0 (2026-08-10) the
# server is published on crates.io, so this is a plain `cargo install` from a
# released version instead of a build from a pinned git commit. No Python at
# all.
ARG RUST_VERSION=1.96.1
FROM rust:${RUST_VERSION}-bookworm AS builder

# Released version, not a main commit. The v0.2.0 tag has diverged from main:
# main carries the next development cycle (internal Rust API churn), so
# following it means running an unreleased server. Bump deliberately - the TOML
# config surface is deny_unknown_fields, so validate with --dry-run afterwards.
#
# Note what 0.2.0 is: it was published from d0b9d50b (#329), 57 minutes before
# #268 landed on main. So the release still carries the deprecated Python
# `switchyard serve` path, and it predates the per-route client router that
# #268 introduced. We only use the native server binary, so neither matters
# here - but do not assume "0.2.0" and "main around 2026-08-07" are the same
# code.
ARG SWITCHYARD_VERSION=0.2.0

# Source switch. Default `crates` installs the released crate above. `git`
# builds the same 0.2.0 plus the judge text-projection patch from the fork
# branch below (upstream NVIDIA-NeMo/Switchyard#598: an attached image reached
# the judge verbatim, a text-only judge answered 400, and the route fell open
# to the strong tier on every attached turn). Same config surface as 0.2.0.
# Switch back to `crates` once a release with the fix is published.
#   docker compose build --build-arg SWITCHYARD_SOURCE=git
ARG SWITCHYARD_SOURCE=crates
ARG SWITCHYARD_GIT_URL=https://github.com/himorishige/Switchyard.git
ARG SWITCHYARD_GIT_REF=fix/judge-text-projection-0.2.0

RUN if [ "${SWITCHYARD_SOURCE}" = "git" ]; then \
        cargo install --locked switchyard-server \
            --git "${SWITCHYARD_GIT_URL}" --branch "${SWITCHYARD_GIT_REF}" \
            --root /opt/out; \
    else \
        cargo install --locked switchyard-server \
            --version "${SWITCHYARD_VERSION}" \
            --root /opt/out; \
    fi

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
    /opt/out/bin/switchyard-server \
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

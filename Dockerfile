# --- builder: nemo-switchyard ships a Rust native extension (maturin),
# so the sdist needs cargo + a C toolchain to compile. Build wheels here
# and keep the runtime image slim.
FROM python:3.12-slim AS builder

# Pin to a main commit that includes the streaming-usage stats fix
# (PR #64, merged 2026-07-14). The v0.1.0 PyPI release predates it.
ARG SWITCHYARD_SHA=060ad758fe50a8dd4704b6de08a5d45502d9958b

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

# Distribution name is nemo-switchyard; the import package is switchyard.
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    "nemo-switchyard[server] @ https://github.com/NVIDIA-NeMo/Switchyard/archive/${SWITCHYARD_SHA}.tar.gz"

# --- runtime
FROM python:3.12-slim

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# The classifier's only reasoning-suppression path emits the vLLM-only
# `chat_template_kwargs` hint, which Fireworks rejects with HTTP 400
# ("Extra inputs are not permitted"). Fireworks instead accepts the
# OpenAI-style `reasoning_effort: "none"` (probed 2026-07-23: identical
# verdicts 18/18, 2.7-4.2x faster, completion tokens pinned at 63-64 vs a
# variable 171-888). Swap the injected body; the model-id auto-detect
# (disable_reasoning) then fires for Fireworks ids, since "fireworks" is
# not in _NO_REASONING_HINT_TAGS. Upstream issue candidate: the
# suppression vocabulary should be provider-aware.
RUN RP=/usr/local/lib/python3.12/site-packages/switchyard/lib/processors/llm_classifier/request_processor.py \
    && grep -q 'extra_body = {"chat_template_kwargs": {"enable_thinking": False}}' "$RP" \
    && sed -i 's/extra_body = {"chat_template_kwargs": {"enable_thinking": False}}/extra_body = {"reasoning_effort": "none"}/' "$RP" \
    && grep -q 'extra_body = {"reasoning_effort": "none"}' "$RP" \
    && python -c "import switchyard.lib.processors.llm_classifier.request_processor" \
    && python -c "from switchyard.lib.processors.reasoning_hint import model_accepts_reasoning_hint as f; assert f('accounts/fireworks/models/deepseek-v4-flash')"

RUN useradd --create-home switchyard
WORKDIR /app
# Baked-in default config; docker-compose bind-mounts ./route.yaml over it
# so config tweaks don't need an image rebuild.
COPY route.yaml /app/route.yaml
# Writable home for the per-request routing log (--routing-log-file).
RUN mkdir -p /app/logs && chown switchyard:switchyard /app/logs
USER switchyard

EXPOSE 4100

# Stock CLI, route-bundle mode. Intake sink stays disabled (no
# --intake-enabled): request bodies never leave the container except
# toward the configured Fireworks endpoints. docker-compose overrides
# this CMD to add --routing-log-file for the per-request JSONL log.
CMD ["switchyard", "--routing-profiles", "/app/route.yaml", "serve", "--host", "0.0.0.0", "--port", "4100"]

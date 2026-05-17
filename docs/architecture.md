# Part A Responses

## System Overview

This project implements an inference-style backend for enterprise ticket classification. The FastAPI layer accepts up to 500 tickets, reserves queue capacity, estimates completion metadata, splits work into LLM batches, calls a provider with retries, and returns successes and failures independently.

Core design principles:

- Requests are limited by input size, queue capacity, context window, provider timeout, retry budget, and concurrency.
- Provider failures are isolated to a batch. One failed batch does not fail the full request.
- Observability is built into the request path: every request has request/correlation IDs, structured logs, Prometheus metrics, retry counters, latency histograms, and token counters.
- The LLM provider is an interface. The mock provider supports deterministic tests and benchmarks. `SarvamLLMProvider` is the production adapter.

## Part A.1: Android Process Kill During Inference

### Failure

Snapdragon device is running local model inference. Android low-memory killer terminates the model process mid-inference while the client is blocked waiting for a response.

### First 500ms Local Recovery Flow

0-25ms:

- Local agent receives child-process death via `waitpid`, binder death recipient, or process supervisor callback.
- It records `model_process_exit{reason=SIGKILL|LMK, request_id, model_version, device_fingerprint, free_mem_mb}` for later debugging.
- It marks the active inference as `interrupted`, freezes client response streaming, and stops accepting new local inference work.

25-75ms:

- Agent writes an idempotent recovery record to local durable storage. The record contains:
  - request identity: `request_id` and `idempotency_key`
  - input identity: prompt/input hash and accepted token count
  - model identity: model version, binary hash, and tokenizer version
  - generation state: decode parameters and random seed
  - resume state: KV-cache checkpoint pointer, if available
  - streaming state: last emitted token index, if streaming

75-125ms:

- Agent emits a gateway event over the existing control channel. The event includes:
  - event type: `INFERENCE_INTERRUPTED`
  - gateway decision deadline: `gateway_decision_deadline_ms=350`
  - local restart ETA estimate
  - retry eligibility flag
  - checkpoint availability

125-250ms:

- Agent starts a warm restart of the model process using a prevalidated launch profile.
- It first starts with NPU execution if the preceding 5-minute crash count is below 2.
- If two process deaths occur within 5 minutes, it suppresses NPU restart and selects CPU/GPU fallback.

250-500ms:

- Agent performs readiness checks before accepting traffic again:
  - process spawned within 250ms
  - runtime loaded within 1.5s
  - model mapped within 4s
  - first no-op health inference within 750ms after load
- If the model process is not spawned by 500ms, the agent sends `RECOVERY_SLOW_PATH` to the gateway and continues loading in the background.

### Gateway Signaling

The local agent sends an authenticated event with a monotonically increasing attempt number:

```json
{
  "type": "INFERENCE_INTERRUPTED",
  "request_id": "req_...",
  "device_id": "dev_...",
  "attempt": 1,
  "reason": "ANDROID_LMK_SIGKILL",
  "checkpoint": {
    "available": true,
    "last_completed_decode_step": 128,
    "kv_cache_epoch": "kv_..."
  },
  "estimated_local_recovery_ms": 4200,
  "fallback_available": true,
  "sent_at_ms": 1730000000000
}
```

If the control channel is unavailable, the agent persists the event and retries with 100ms, 250ms, and 500ms backoff. After 850ms total, the gateway detects the missed heartbeat and marks the device unavailable for new work.

If the local agent is killed as well, the gateway falls back to heartbeat-based detection. A missed heartbeat for 750ms moves the request to `INTERRUPTED`, stops new routing to that device, and allows the same peer-retry decision path. On agent restart, the agent replays any durable recovery records and reports whether the original request can still be resumed or should be discarded.

### Gateway Handling of the In-flight Request

The gateway tracks the in-flight request with a small state machine:

| State | Meaning |
|---|---|
| `RUNNING_ON_DEVICE` | Request is currently assigned to the Snapdragon device. |
| `INTERRUPTED` | The model process died or the gateway missed the expected device signal. |
| `RECOVERING_LOCAL` | The local agent is restarting the model process and trying to resume from checkpoint. |
| `RETRY_ON_PEER` | The gateway has launched one idempotent retry on a compatible healthy peer. |
| `FAILED_RETRYABLE` | The request did not complete, but the client may retry with the same idempotency key. |
| `FAILED_FINAL` | The request cannot be retried safely or the retry budget is exhausted. |

Exact timeout policy:

- `agent_interrupt_signal_timeout`: 750ms from last device heartbeat. If no signal arrives, gateway assumes device loss.
- `gateway_decision_timeout`: 350ms after interrupt event. The agent should confirm process death and write the recovery record inside 125ms, and a warm peer selection lookup is expected to complete within about 150-200ms. A 350ms decision window leaves roughly 50ms of margin before the gateway chooses local recovery or peer retry.
- `local_recovery_budget`: 6s for non-streaming requests and 2s for interactive streaming requests.
- `peer_retry_budget`: one retry on a healthy compatible peer when the request is idempotent. Compatible means same model binary hash, tokenizer version, adapter hash, quantization profile, and execution-policy version.
- `client_total_timeout`: original request timeout minus gateway-observed elapsed time. The gateway owns the request timer from admission, so it does not depend on the device reporting elapsed time after a crash.

Sequencing:

1. Gateway receives `INFERENCE_INTERRUPTED`.
2. Gateway stops routing new requests to that device for 30s or until 5 consecutive heartbeats report healthy model readiness.
3. If the request is non-idempotent or uses mutable tool state, gateway waits for local recovery only.
4. If the request is idempotent and a compatible warm peer exists, gateway launches one speculative peer retry after 350ms.
5. If the local device recovers first and can resume from checkpoint, gateway accepts the local result and cancels the peer attempt.
6. If peer retry completes first, gateway returns peer result and tells local agent to discard the resumed request.
7. If both fail, the gateway returns a retryable 503 with `request_id` and diagnostic metadata.

Retry behavior:

- At most one peer retry per request.
- At most one local resume attempt from checkpoint.
- At most one cold local restart attempt before marking the device degraded.
- Device is quarantined from NPU execution after 2 kills in 5 minutes or 3 kills in 30 minutes.

### Checkpointing for Fast Recovery

State to checkpoint:

- Request envelope and idempotency key.
- Tokenized prompt, tokenizer version, and prompt hash.
- Decode configuration: temperature, top-p, top-k, max tokens, stop sequences.
- RNG seed and sampler state.
- KV-cache pages at chunk boundaries, preferably every 64 generated tokens or every 2 seconds, whichever comes first.
- Last committed streaming token offset.
- Model binary hash, adapter hash, runtime version, NPU driver fingerprint.

Justification:

- KV-cache checkpointing is the only way to avoid replaying long prompts after a process kill. It is memory-expensive, so checkpoint at coarse decode boundaries rather than every token.
- Tokenized prompt avoids tokenizer drift after process restart.
- Last committed streaming offset prevents duplicate tokens to clients.
- Driver and binary fingerprints prevent resuming with an incompatible execution profile.
- The 500ms first-response target is chosen because the gateway must know quickly whether to preserve client wait time or reroute. Full model reload can take seconds. The first 500ms is about containment and decision quality, not full recovery.

## Part A.2: Firmware Update Breaking NPU Driver Compatibility

### Detection

The fleet detection query correlates three streams:

- Logs: `model_load_failed`, `npu_runtime_init_failed`, `segfault`, `illegal_instruction`, `driver_api_error`.
- Heartbeats: `device_model_ready=false`, `npu_driver_version`, `firmware_version`, `os_build`, `model_binary_hash`, `runtime_hash`.
- Crash metadata: signal, faulting library, symbolized stack prefix, exit code, uptime before crash, load phase.

Detection algorithm:

1. Group devices by fingerprint using fields such as `vendor=HP`, `cpu=Intel Core Ultra 7`, `npu_driver_version`, `firmware_version`, `os_build`, `bios_version`, and `runtime_hash`.
2. Compute model-load crash rate for each fingerprint over rolling 15-minute and 2-hour windows.
3. Alert when a fingerprint crosses all of these thresholds:
   - at least 10 affected devices
   - load failure rate above 20%
   - failure ratio 5x higher than fleet baseline
4. Auto-label devices as affected if they have 3 consecutive load crashes with the same stack prefix after the firmware version changed.

Expected affected signature:

- Same model binary works elsewhere.
- Failures cluster on HP laptop fingerprint after firmware update.
- Crash occurs during model load, not during request execution.
- Heartbeats show firmware or NPU driver transition immediately before the first failure.

### Root Cause Isolation Without Local Reproduction

Remote-only isolation steps:

1. Compare last-known-good and first-bad heartbeats for each affected device.
2. Diff the driver/runtime fingerprint fields:
   - NPU driver semantic version
   - firmware build
   - PCI device ID and revision
   - runtime library checksum
   - supported operator/capability bitmap
3. Compare crash stack prefixes. If many devices fail in the same NPU graph compilation or memory mapping frame, driver compatibility is the likely cause.
4. Trigger a remote diagnostic job on affected devices. The job checks:
   - load runtime only
   - query NPU capabilities
   - compile a 1-layer test graph
   - mmap model file without execution
   - load model with NPU disabled
5. Isolate the failure using the diagnostic result:
   - runtime-only fails: driver installation or runtime ABI issue.
   - test graph fails: NPU compiler/runtime issue.
   - model mmap fails: packaging/filesystem issue.
   - CPU load succeeds and NPU load fails: NPU driver compatibility issue.

No customer data is needed. The diagnostic job uses generated tensors and reports only metadata and checksums.

### Mitigation Without a Full Model Recompile

Immediate mitigation:

- Add affected fingerprint to a remote execution-policy blocklist.
- Disable NPU execution on matching HP firmware/driver versions.
- Route to CPU or GPU backend with reduced concurrency and smaller batch size.
- Keep the same model weights and binary artifact. Change runtime execution provider selection and graph optimization flags.

Possible runtime knobs:

- Disable fused NPU kernels for attention and matmul.
- Disable INT4 NPU path and use INT8/FP16 CPU/GPU fallback if available.
- Pin runtime library to the last-known-good version when ABI-compatible.
- Use a pre-existing generic execution profile packaged with the application.

Rollout:

1. Ship remote config to 1% of affected devices for 15 minutes.
2. Expand to 25% for 30 minutes if model load success exceeds 99% and crash rate drops below 1%.
3. Expand to 100% of affected fingerprint after another 30 minutes if the same health checks hold.
4. Keep unaffected fingerprints on NPU.
5. Monitor latency SLO degradation separately. Mitigation may be slower, but it must be correct and stable.

In-flight work on affected devices is drained before the policy change when possible. The gateway stops sending new NPU work to the affected fingerprint, allows already-running requests to finish for up to 2s for interactive requests or 6s for batch requests, and then retries idempotent unfinished requests on CPU/GPU fallback or a healthy peer. Non-idempotent requests are failed with retry guidance instead of being replayed blindly.

### Prevention

Prevention strategy:

- Every heartbeat must include driver/version fingerprinting and NPU capability bitmap.
- Deployment gates must be fingerprint-aware. A canary is valid only if it covers each major hardware/driver cluster.
- Model manifests should declare allowed and denied runtime fingerprints.
- Agents should support remote execution-policy changes independent of model recompilation.
- CI should include compatibility tests against mocked runtime capability matrices.
- Firmware version changes should trigger synthetic smoke tests before the device is allowed to serve inference again.

Canary logic:

- Select canaries by hardware and driver groups, not by random fleet percentage only.
- Require at least 30 healthy model loads per fingerprint before broad rollout.
- Halt rollout for a fingerprint when crash rate exceeds 2% or load p95 exceeds 2x baseline.
- Roll forward with fallback policy first. Roll back the model only if fallback cannot restore correctness.

Telemetry improvements:

- Include crash phase: runtime init, graph compile, weight mmap, first inference, steady-state inference.
- Include driver ABI version, runtime library checksum, NPU compiler version, firmware build, BIOS version.
- Include model load duration histogram and failure reason categories.
- Include execution provider actually used, not just intended provider.

## Part A.3: INT4 Quantisation Failures on Snapdragon

### Hypothesis 1: INT4 Scale/Zero-Point Packing Mismatch in Snapdragon Kernel

Specific root cause:

The Snapdragon INT4 kernel may interpret packed nibbles or per-group zero-points differently from the quantizer. For example, weights packed low-nibble-first during export are decoded high-nibble-first by a vendor kernel for specific operator layouts. Other hardware paths unpack through a reference runtime and therefore behave correctly.

Diagnostic probe:

- Add per-layer activation cosine similarity against a CPU reference path for a 32-request shadow sample.
- Log the first layer where cosine similarity drops below 0.995.
- Include kernel name, quant group size, scale tensor checksum, zero-point checksum, and packed weight checksum.

Minimal validation code change:

- Add an environment flag `INT4_FORCE_REFERENCE_UNPACK=1` for Snapdragon Series X that unpacks INT4 weights to INT8/FP16 before dispatching the suspect matmul.
- Alternatively disable the vendor INT4 kernel only for the first failing operator.

Expected signal if correct:

- The divergence begins immediately at one or two INT4 matmul layers.
- CPU reference unpack restores output quality.
- Scale and zero-point metadata match, but packed-weight interpretation differs.

### Hypothesis 2: Accumulator Precision or Saturation Differs Under NPU Execution

Specific root cause:

Snapdragon NPU may accumulate INT4 products into narrower accumulators or use different saturation/clamping behavior than Intel/CPU paths. Long prompts or high-activation requests can overflow intermediate accumulators, creating unstable logits and hallucinations. The issue appears as a percentage of requests because only certain activation distributions exceed the numerical margin.

A related Snapdragon-specific risk is shared memory bandwidth pressure between CPU, GPU, and NPU. If the runtime streams packed INT4 weights aggressively, cache eviction or stale DMA synchronization bugs can show up only on high-pressure requests. I would track this with the same activation/logit probes plus memory bandwidth counters.

Diagnostic probe:

- Add activation range telemetry per quantized block. Capture:
  - min/max accumulator before requantization
  - saturation count
  - clamp count
  - NaN/Inf count after dequantization
- Sample 1% of requests and compare top-k logits between Snapdragon NPU and CPU reference for the same prompt.

Minimal validation code change:

- Force the suspect layers to use FP16 accumulators or widen accumulation for attention output and MLP projection.
- Add a runtime guard that falls back to FP16/INT8 when saturation count exceeds a threshold.

Expected signal if correct:

- Hallucinating requests show saturation spikes or large top-k logit drift.
- Widened accumulators reduce or eliminate hallucinations without changing model weights.
- Failures correlate with long context, unusual token distributions, or high activation norms.

### Hypothesis 3: Operator Fusion/Reordering Changes Numerical Stability

Specific root cause:

Snapdragon runtime may fuse dequantize, matmul, bias, activation, and requantization into one kernel. The fused path can reorder operations, use approximate activation functions, or apply scales before bias differently from the exported graph. Other hardware may execute unfused operators and remain closer to reference.

Diagnostic probe:

- Emit graph compilation metadata showing fusion groups.
- Run A/B shadow inference with `DISABLE_INT4_FUSION=1` for 0.5% of Snapdragon Series X traffic.
- Compare final classification quality, per-layer cosine similarity, and token log-prob deltas.

Minimal validation code change:

- Add runtime option to disable fusion for quantized attention and MLP blocks on Snapdragon Series X.
- Keep the rest of NPU execution enabled to avoid a full fallback.

Expected signal if correct:

- Disabling fusion moves logits closer to CPU reference and reduces hallucination reports.
- Divergence begins after a fused dequant-matmul-activation block.
- Latency regresses modestly, but correctness improves sharply.

### Minimal Diagnostic Code Sketches

These are the smallest validation hooks I would add around the existing runtime dispatch path:

```python
if env.INT4_FORCE_REFERENCE_UNPACK:
    weights = unpack_int4_to_int8(weights, layout="export_reference")
    return matmul_reference(input, weights, scales, zero_points)
```

```python
stats = collect_quant_stats(layer_id, accumulators, activations)
if stats.saturation_count > SATURATION_LIMIT:
    return run_layer_fp16(layer_id, input)
```

```python
if device.family == "snapdragon_x" and env.DISABLE_INT4_FUSION:
    graph.disable_fusion(["dequant", "matmul", "activation", "requant"])
```

I would also bias diagnostic sampling toward longer prompts and requests with high activation norms. A flat 1% sample can miss the failure pattern if the bug only appears on specific prompt shapes.

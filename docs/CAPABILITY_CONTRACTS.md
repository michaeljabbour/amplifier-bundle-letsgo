# Capability Contracts

Capabilities registered by `amplifier-bundle-letsgo` (core) that satellite bundles may depend on.

## Registered Capabilities

### `memory.store`

- **Registered by:** `tool-memory-store` module
- **Required by:** None (optional for all satellites)
- **Interface:** Async function for storing and retrieving memories
- **Graceful degradation:** Satellites skip memory features when unavailable

### `display`

- **Registered by:** Gateway `DisplaySystem`
- **Required by:** `letsgo-canvas` (required)
- **Interface:** `async display(content: str, metadata: dict | None) -> None`
- **Graceful degradation:** Canvas bundle fails with clear error if missing

### `telemetry.metrics`

- **Registered by:** `hooks-telemetry` module
- **Required by:** None (optional for all satellites)
- **Interface:** Metrics recording functions (counters, histograms)
- **Graceful degradation:** Satellites skip telemetry when unavailable

### `secrets.redeem`

- **Registered by:** `tool-secrets` module
- **Required by:** None (optional for all satellites)
- **Interface:** `async redeem(handle: str) -> str` — decrypt a secret handle
- **Graceful degradation:** Satellites that need secrets fail with clear error

## Satellite Rules

1. **Lazy query:** Query capabilities at execution time, not mount time.
   This makes satellites ordering-resilient — doesn't matter if `letsgo-voice`
   comes before `letsgo` in the user's includes list.

2. **Graceful degradation:** If an optional capability is missing, skip
   the feature and log a debug message. Never crash.

3. **Clear error on required:** If a required capability is missing, raise
   `ModuleLoadError` with an actionable message:

   ```python
   display = coordinator.get_capability("display")
   if display is None:
       raise ModuleLoadError(
           "letsgo-canvas requires amplifier-bundle-letsgo (core). "
           "Add it to your root bundle's includes."
       )
   ```

4. **Never assume ordering:** Satellites don't include the core bundle.
   The user's root bundle includes both. Capabilities may be registered
   in any order.
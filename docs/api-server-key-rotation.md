# API_SERVER_KEY: provisioning and rotation

`API_SERVER_KEY` has one source of truth (architecture §13): a Toolforge envvar, injected into
both the internal Hermes gateway job and the public proxy at process start. Neither process
generates or persists an independent key — both fail closed at startup if it's absent or
shorter than 16 characters (verified against Hermes's own `api_server` startup guard).

## First-time provisioning

1. On the Toolforge bastion, inside the `wiki-assistant` tool account, run:

   ```
   ./gateway/generate-api-server-key
   ```

   This generates a 64-character hexadecimal key in an owner-only temporary file, passes it to
   `toolforge envvars create API_SERVER_KEY` over standard input, suppresses the CLI's
   value-bearing standard output, and deletes the temporary file after Toolforge returns. The
   key never appears in shell history, process arguments, or script output.

2. Start the gateway continuous job and the proxy webservice. Both read the same envvar; if it's
   missing, both fail closed with a clear startup error rather than starting unauthenticated.

## Rotation

Rotating replaces the value both consumers already have — do this if the key may have leaked,
on a routine schedule, or when Toolforge tooling itself recommends it.

1. Generate and update the envvar with `./gateway/generate-api-server-key`. Toolforge's
   `envvars create` operation updates the existing value.
2. **Restart both consumers immediately after**, not on their own separate schedules — the
   gateway and the proxy must never run against different key values at the same time. Until
   both are restarted, calls between them will fail authentication (the old value is gone once
   the envvar is updated, but a still-running process only reads the envvar at its own start).
3. Confirm both processes came back up successfully (watchdog health check, or a manual `curl`
   against the proxy) before considering the rotation complete.

## What this deliberately does not do

- No automatic rotation schedule — this is a manual, operator-triggered procedure for V1.
- No key value is ever written to this repository, a log, a metric, or a public audit record.
  The provisioning script uses one owner-only temporary file and removes it on success, failure,
  or interruption.

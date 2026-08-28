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

   This generates a strong random key (32 bytes, hex-encoded), writes it to a `0600`-permissioned
   temp file, and prints the exact `toolforge envvars create` command to run — it does not run
   that command itself, and never prints the key value to stdout.

2. Run the printed command:

   ```
   toolforge envvars create API_SERVER_KEY < <the printed temp file path>
   ```

   `toolforge envvars create` normally prompts interactively for the value; piping the generated
   file in supplies it non-interactively, so the key never appears in shell history or a process
   listing.

3. Start the gateway continuous job and the proxy webservice. Both read the same envvar; if it's
   missing, both fail closed with a clear startup error rather than starting unauthenticated.

## Rotation

Rotating replaces the value both consumers already have — do this if the key may have leaked,
on a routine schedule, or when Toolforge tooling itself recommends it.

1. Generate a new key the same way: `./gateway/generate-api-server-key`.
2. Update the envvar with the new value: `toolforge envvars create API_SERVER_KEY < <new temp
   file path>` (Toolforge's `envvars create` overwrites an existing value; see `toolforge
   envvars --help` on the bastion for the exact current syntax if this changes).
3. **Restart both consumers immediately after**, not on their own separate schedules — the
   gateway and the proxy must never run against different key values at the same time. Until
   both are restarted, calls between them will fail authentication (the old value is gone once
   the envvar is updated, but a still-running process only reads the envvar at its own start).
4. Confirm both processes came back up successfully (watchdog health check, or a manual `curl`
   against the proxy) before considering the rotation complete.

## What this deliberately does not do

- No automatic rotation schedule — this is a manual, operator-triggered procedure for V1.
- No key value is ever written to this repository, a log, a metric, or a public audit record —
  `gateway/generate-api-server-key`'s own output only ever names a local temp file path, never
  the key itself.

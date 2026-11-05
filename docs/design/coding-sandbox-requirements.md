# Coding sandbox requirements (future)

InterviewCopilot reviews coding answers statically today (`AI-reviewed, not executed`).
A future execution sandbox must never run inside the API process.

## Must-haves

1. Isolated container or microVM per run (no shared kernel state with other candidates).
2. No network access from the guest (egress and ingress denied by default).
3. Hard CPU, memory, wall-clock time, and output-size limits per run.
4. Read-only root filesystem; writable scratch only if required, wiped after the run.
5. No secrets, API keys, or host credentials injected into the guest environment.
6. Queueing and per-user rate limits so one candidate cannot starve the pool.
7. Language images for Python, Java, and C (matching the editor language tabs).
8. Reliable kill of runaway processes (and the whole guest) when limits are hit.
9. The FastAPI / worker process must only enqueue jobs and read results — it must
   never `exec`, `eval`, `subprocess`, or otherwise interpret candidate code locally.
10. Audit logs: job id, language, limits, exit status, duration — never full secrets.

## Out of scope for v1

Browser-side WASM runners, unpaid third-party judges without a contract, and any
design that trusts the client to report “pass/fail” without a server-side sandbox.

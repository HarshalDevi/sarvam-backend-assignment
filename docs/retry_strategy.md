# Retry Strategy

The retry policy uses exponential backoff with randomized jitter:

- max attempts: 5 total attempts by default
- base delay: 350ms
- max delay: 4s
- jitter: plus or minus 25%

Retryable cases:

- HTTP 429
- HTTP 408
- HTTP 425
- HTTP 5xx
- connection reset
- timeout
- malformed or incomplete provider response

Permanent cases:

- HTTP 400
- HTTP 401
- HTTP 403
- HTTP 404
- HTTP 422

Retries are applied at the batch level because the provider accepts the batch as one request. Retrying individual tickets inside a failed provider batch is not reliable unless the provider returns item-level errors. The processor still reports item-level failures by expanding the failed batch into a `failures` array.

If a batch still fails after its retry budget and contains more than one ticket, the processor falls back to split-and-retry isolation. It splits the failed batch into two smaller batches and retries each half. This repeats until the processor either recovers successful tickets or isolates the failure to one ticket. That keeps a single malformed or provider-rejected ticket from failing the entire original batch.

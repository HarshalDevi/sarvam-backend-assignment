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

Retries are applied at the batch level. This is the right tradeoff because providers usually accept a batch as one request, and retrying individual tickets inside a failed provider batch is impossible unless the provider returns item-level errors. The processor still reports item-level failures by expanding the failed batch into a `failures` array.

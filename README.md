# 08 · ratelimiter

Token bucket, sliding window, fixed window and leaky bucket behind one interface.

## Run

```bash
python -m ratelimiter --help  # or import ratelimiter.algorithms
```

## Test

```bash
pytest projects/08-rate-limiter -q
```

## What it demonstrates

- Four algorithms, one `hit(key)` contract, so swapping strategy is a one-line change
- Injected clock (`FakeClock`) makes every timing test deterministic - no `sleep()` in tests
- Documents the fixed-window burst weakness with a test that proves it
- RFC 9331-style headers (`X-RateLimit-*`, `Retry-After`) generated for you

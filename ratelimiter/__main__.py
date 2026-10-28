"""Demo: hammer one key and watch the limiter respond."""
from .algorithms import FakeClock, TokenBucket

if __name__ == "__main__":
    clock, limiter = FakeClock(), None
    limiter = TokenBucket(rate=2, capacity=3, clock=clock)
    for i in range(1, 8):
        decision = limiter.hit("demo")
        print(f"request {i}: allowed={decision.allowed} remaining={decision.remaining} retry_after={decision.retry_after:.2f}")
        clock.tick(0.25)

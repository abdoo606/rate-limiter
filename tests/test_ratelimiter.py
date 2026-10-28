from __future__ import annotations

import pytest

from ratelimiter.algorithms import (
    Decision,
    FakeClock,
    FixedWindow,
    LeakyBucketQueue,
    SlidingWindow,
    TokenBucket,
)
from ratelimiter.headers import headers_for, status_for


@pytest.fixture()
def clock():
    return FakeClock()


# ------------------------------------------------------------ token bucket
def test_token_bucket_allows_burst_then_blocks(clock):
    limiter = TokenBucket(rate=1, capacity=3, clock=clock)
    assert [limiter.hit("u").allowed for _ in range(3)] == [True, True, True]
    assert limiter.hit("u").allowed is False


def test_token_bucket_refills_over_time(clock):
    limiter = TokenBucket(rate=2, capacity=2, clock=clock)
    limiter.hit("u")
    limiter.hit("u")
    assert not limiter.hit("u")
    clock.tick(1.0)  # 2 tokens back
    assert limiter.hit("u").allowed


def test_token_bucket_never_exceeds_capacity(clock):
    limiter = TokenBucket(rate=10, capacity=2, clock=clock)
    clock.tick(1000)
    decision = limiter.hit("u")
    assert decision.remaining == 1


def test_token_bucket_retry_after_is_meaningful(clock):
    limiter = TokenBucket(rate=1, capacity=1, clock=clock)
    limiter.hit("u")
    decision = limiter.hit("u")
    assert decision.retry_after == pytest.approx(1.0)


def test_keys_are_independent(clock):
    limiter = TokenBucket(rate=1, capacity=1, clock=clock)
    assert limiter.hit("a").allowed
    assert limiter.hit("b").allowed
    assert not limiter.hit("a").allowed


def test_cost_larger_than_capacity_is_always_denied(clock):
    limiter = TokenBucket(rate=1, capacity=5, clock=clock)
    decision = limiter.hit("u", cost=99)
    assert not decision.allowed and decision.retry_after == float("inf")


def test_invalid_construction(clock):
    with pytest.raises(ValueError):
        TokenBucket(rate=0, capacity=1, clock=clock)


# --------------------------------------------------------- sliding window
def test_sliding_window_enforces_limit(clock):
    limiter = SlidingWindow(limit=3, window=60, clock=clock)
    assert all(limiter.hit("u").allowed for _ in range(3))
    assert not limiter.hit("u").allowed


def test_sliding_window_frees_capacity_after_window(clock):
    limiter = SlidingWindow(limit=2, window=10, clock=clock)
    limiter.hit("u")
    limiter.hit("u")
    assert not limiter.hit("u").allowed
    clock.tick(10.1)
    assert limiter.hit("u").allowed


def test_sliding_window_retry_after(clock):
    limiter = SlidingWindow(limit=1, window=10, clock=clock)
    limiter.hit("u")
    clock.tick(4)
    assert limiter.hit("u").retry_after == pytest.approx(6)


# --------------------------------------------------------- fixed window
def test_fixed_window_resets_on_boundary(clock):
    limiter = FixedWindow(limit=2, window=10, clock=clock)
    assert limiter.hit("u").allowed
    assert limiter.hit("u").allowed
    assert not limiter.hit("u").allowed
    clock.tick(10)
    assert limiter.hit("u").allowed


def test_fixed_window_documented_weakness(clock):
    """A burst at the end of one window and the start of the next doubles the rate."""
    limiter = FixedWindow(limit=2, window=10, clock=clock)
    clock.tick(9.9)
    assert limiter.hit("u").allowed and limiter.hit("u").allowed
    clock.tick(0.2)
    assert limiter.hit("u").allowed and limiter.hit("u").allowed


# --------------------------------------------------------- leaky bucket
def test_leaky_bucket_denies_burst_beyond_capacity(clock):
    limiter = LeakyBucketQueue(rate=1, capacity=2, clock=clock)
    assert limiter.hit("u").allowed
    assert limiter.hit("u").allowed
    assert not limiter.hit("u").allowed


def test_leaky_bucket_drains(clock):
    limiter = LeakyBucketQueue(rate=2, capacity=2, clock=clock)
    limiter.hit("u")
    limiter.hit("u")
    clock.tick(1)
    assert limiter.hit("u").allowed


# --------------------------------------------------------------- headers
def test_headers_for_allowed():
    headers = headers_for(Decision(True, 7, 0, 10))
    assert headers["X-RateLimit-Limit"] == "10"
    assert headers["X-RateLimit-Remaining"] == "7"
    assert "Retry-After" not in headers
    assert status_for(Decision(True, 7, 0, 10)) == 200


def test_headers_for_denied_round_retry_upward():
    headers = headers_for(Decision(False, 0, 1.2, 10))
    assert headers["Retry-After"] == "2"
    assert status_for(Decision(False, 0, 1.2, 10)) == 429


def test_decision_is_truthy_when_allowed():
    assert Decision(True, 1, 0, 1)
    assert not Decision(False, 0, 1, 1)

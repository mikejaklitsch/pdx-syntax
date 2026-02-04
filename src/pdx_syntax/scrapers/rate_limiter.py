"""Rate limiting for web requests."""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import json


class RateLimiter:
    """
    Rate limiter to prevent excessive requests to external sources.

    Tracks request history and enforces configurable limits per domain.
    """

    def __init__(
        self,
        requests_per_minute: int = 10,
        requests_per_hour: int = 100,
        state_file: Optional[Path] = None,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.state_file = state_file or Path(__file__).parent.parent / "data" / ".rate_limit_state.json"
        self._request_history: dict[str, list[float]] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Load rate limit state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                    # Convert timestamps back to floats
                    self._request_history = {
                        domain: [float(ts) for ts in timestamps]
                        for domain, timestamps in data.items()
                    }
            except (json.JSONDecodeError, KeyError):
                self._request_history = {}

    def _save_state(self) -> None:
        """Save rate limit state to file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self._request_history, f)

    def _clean_old_requests(self, domain: str) -> None:
        """Remove requests older than 1 hour from history."""
        if domain not in self._request_history:
            self._request_history[domain] = []
            return

        cutoff = time.time() - 3600  # 1 hour ago
        self._request_history[domain] = [
            ts for ts in self._request_history[domain] if ts > cutoff
        ]

    def can_request(self, domain: str) -> bool:
        """Check if a request to the domain is allowed."""
        self._clean_old_requests(domain)

        history = self._request_history.get(domain, [])
        now = time.time()

        # Check requests in last minute
        minute_ago = now - 60
        recent_minute = sum(1 for ts in history if ts > minute_ago)
        if recent_minute >= self.requests_per_minute:
            return False

        # Check requests in last hour
        if len(history) >= self.requests_per_hour:
            return False

        return True

    def wait_time(self, domain: str) -> float:
        """Get seconds to wait before next request is allowed."""
        self._clean_old_requests(domain)

        history = self._request_history.get(domain, [])
        if not history:
            return 0.0

        now = time.time()
        minute_ago = now - 60

        # Check minute limit
        recent_minute = [ts for ts in history if ts > minute_ago]
        if len(recent_minute) >= self.requests_per_minute:
            # Wait until oldest request in minute window expires
            oldest_in_minute = min(recent_minute)
            wait_for_minute = (oldest_in_minute + 60) - now
        else:
            wait_for_minute = 0.0

        # Check hour limit
        if len(history) >= self.requests_per_hour:
            # Wait until oldest request in hour window expires
            oldest_in_hour = min(history)
            wait_for_hour = (oldest_in_hour + 3600) - now
        else:
            wait_for_hour = 0.0

        return max(wait_for_minute, wait_for_hour, 0.0)

    def record_request(self, domain: str) -> None:
        """Record a request to a domain."""
        self._clean_old_requests(domain)

        if domain not in self._request_history:
            self._request_history[domain] = []

        self._request_history[domain].append(time.time())
        self._save_state()

    def wait_if_needed(self, domain: str) -> float:
        """Wait if rate limit would be exceeded. Returns time waited."""
        wait = self.wait_time(domain)
        if wait > 0:
            time.sleep(wait)
        return wait

    def get_stats(self, domain: str) -> dict:
        """Get rate limit statistics for a domain."""
        self._clean_old_requests(domain)

        history = self._request_history.get(domain, [])
        now = time.time()
        minute_ago = now - 60

        return {
            "domain": domain,
            "requests_last_minute": sum(1 for ts in history if ts > minute_ago),
            "requests_last_hour": len(history),
            "limit_per_minute": self.requests_per_minute,
            "limit_per_hour": self.requests_per_hour,
            "can_request": self.can_request(domain),
            "wait_time": self.wait_time(domain),
        }


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(
            requests_per_minute=10,
            requests_per_hour=100,
        )
    return _rate_limiter

"""
Shotgun.live API client — fetches the current/upcoming event for an organizer.

API credentials are set in .env:
  SHOTGUN_API_TOKEN=your_token_here

Organizer ID is set in config/settings.json (hardware.shotgun_organizer_id)
or via the web UI.

--- Endpoint to verify with your Shotgun account ---
Base URL and exact path may differ; confirm from:
  Smartboard > Settings > Integrations > Shotgun APIs
The implementation below targets the most common REST pattern for this API.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.shotgun.live/v1"
# How long to keep fetched events in memory before re-fetching
_CACHE_TTL = 30 * 60  # 30 minutes


@dataclass
class ShotgunEvent:
    id: str
    name: str
    starts_at: datetime
    ends_at: datetime | None
    venue_name: str
    artists: list[str] = field(default_factory=list)
    url: str | None = None

    def is_now(self) -> bool:
        """True if the event is currently ongoing."""
        now = datetime.now(timezone.utc)
        if self.ends_at:
            return self.starts_at <= now <= self.ends_at
        # No end time: consider active within 6 hours of start
        delta = (now - self.starts_at).total_seconds()
        return 0 <= delta <= 6 * 3600

    def is_today(self) -> bool:
        local_now = datetime.now()
        return self.starts_at.date() == local_now.date()

    def headliner(self) -> str | None:
        return self.artists[0] if self.artists else None


def _parse_event(data: dict) -> ShotgunEvent:
    """Parse a raw API response dict into a ShotgunEvent.

    Field names are based on common Shotgun API conventions.
    Adjust keys here if the actual API returns different names.
    """
    def _parse_dt(val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    starts_at = _parse_dt(data.get("starts_at") or data.get("start_date"))
    if starts_at is None:
        raise ValueError(f"Event {data.get('id')} has no start date")

    # Artists may be nested as list of objects or list of strings
    raw_artists = data.get("artists") or data.get("lineup") or []
    artists = [
        a["name"] if isinstance(a, dict) else str(a)
        for a in raw_artists
    ]

    venue = data.get("venue") or {}
    venue_name = (
        venue.get("name") if isinstance(venue, dict) else str(venue)
    ) or data.get("venue_name", "")

    return ShotgunEvent(
        id=str(data.get("id", "")),
        name=data.get("name") or data.get("title", ""),
        starts_at=starts_at,
        ends_at=_parse_dt(data.get("ends_at") or data.get("end_date")),
        venue_name=venue_name,
        artists=artists,
        url=data.get("url") or data.get("shotgun_url"),
    )


class ShotgunClient:
    def __init__(self, organizer_id: str):
        self._organizer_id = organizer_id
        self._token = os.getenv("SHOTGUN_API_TOKEN", "")
        self._cache: list[ShotgunEvent] = []
        self._cache_at: float = 0.0

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    def _fetch_from_api(self) -> list[ShotgunEvent]:
        """Fetch today's and upcoming events from the Shotgun API."""
        today = datetime.now().strftime("%Y-%m-%d")
        url = f"{_BASE_URL}/organizers/{self._organizer_id}/events"
        params = {
            "start_date": today,
            "status": "published",
            "per_page": 10,
        }
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # API may return {"events": [...]} or directly [...]
            items = data.get("events") or data.get("data") or (data if isinstance(data, list) else [])
            events = []
            for item in items:
                try:
                    events.append(_parse_event(item))
                except (ValueError, KeyError) as exc:
                    logger.warning("Could not parse event: %s — %s", item.get("id"), exc)
            logger.info("Fetched %d event(s) from Shotgun", len(events))
            return events
        except requests.RequestException as exc:
            logger.error("Shotgun API error: %s", exc)
            return []

    def _refresh_if_needed(self) -> None:
        if time.monotonic() - self._cache_at > _CACHE_TTL:
            self._cache = self._fetch_from_api()
            self._cache_at = time.monotonic()

    def get_current_event(self) -> ShotgunEvent | None:
        """Return the event currently ongoing, or the next one scheduled today."""
        self._refresh_if_needed()

        # Priority 1: event happening right now
        for event in self._cache:
            if event.is_now():
                return event

        # Priority 2: next event today (not yet started)
        today_events = [e for e in self._cache if e.is_today()]
        if today_events:
            return min(today_events, key=lambda e: e.starts_at)

        return None

    def force_refresh(self) -> None:
        """Invalidate cache and re-fetch immediately."""
        self._cache_at = 0.0
        self._refresh_if_needed()

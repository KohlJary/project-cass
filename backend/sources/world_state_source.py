"""
World State Queryable Source

Provides ambient awareness of:
- Server geolocation
- Current weather conditions
- Date, time, season, day of week
"""

import asyncio
import calendar
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import httpx

from database import get_db, json_serialize, json_deserialize
from query_models import (
    StateQuery,
    QueryResult,
    QueryResultData,
    SourceSchema,
    MetricDefinition,
)
from queryable_source import QueryableSource, RefreshStrategy, RollupConfig

logger = logging.getLogger(__name__)


class WorldStateSource(QueryableSource):
    """
    Queryable source for world state data.

    Provides ambient awareness of location, weather, and time.
    Refreshes every 6 hours via scheduled background task.
    """

    def __init__(
        self,
        daemon_id: str,
        data_dir: str = "data",
        home_location: str = "Seattle, WA"
    ):
        super().__init__(daemon_id)
        self._data_dir = Path(data_dir) / "world_state"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._home_location = home_location
        self._rollups: Dict[str, Any] = {}

        # Initialize rollups from database
        self._load_rollups()

    @property
    def source_id(self) -> str:
        return "world_state"

    @property
    def schema(self) -> SourceSchema:
        return SourceSchema(
            metrics=[
                MetricDefinition(
                    name="server_location",
                    description="Current server location",
                    data_type="string",
                    tags=["location", "ambient"]
                ),
                MetricDefinition(
                    name="current_weather",
                    description="Current weather conditions",
                    data_type="string",
                    tags=["weather", "ambient"]
                ),
                MetricDefinition(
                    name="temperature",
                    description="Current temperature in Fahrenheit",
                    data_type="number",
                    tags=["weather", "ambient"]
                ),
                MetricDefinition(
                    name="season",
                    description="Current season (winter, spring, summer, fall)",
                    data_type="string",
                    tags=["temporal", "ambient"]
                ),
                MetricDefinition(
                    name="time_of_day",
                    description="Time of day (morning, afternoon, evening, night)",
                    data_type="string",
                    tags=["temporal", "ambient"]
                ),
                MetricDefinition(
                    name="current_date",
                    description="Current date formatted for human reading",
                    data_type="string",
                    tags=["temporal", "ambient"]
                ),
            ],
            aggregations=["current"],
            group_by_options=[],
            filter_keys=["location_type"],
        )

    @property
    def refresh_strategy(self) -> RefreshStrategy:
        return RefreshStrategy.SCHEDULED

    @property
    def rollup_config(self) -> RollupConfig:
        return RollupConfig(
            strategy=RefreshStrategy.SCHEDULED,
            schedule_interval_seconds=6 * 3600,  # 6 hours
            cache_ttl_seconds=300,  # 5 min query cache
            rollup_types=["current"]
        )

    async def execute_query(self, query: StateQuery) -> QueryResult:
        """Execute a world state query."""
        rollups = self.get_precomputed_rollups()

        # Filter by metric if specified
        if query.metric:
            if query.metric in rollups:
                data = {query.metric: rollups[query.metric]}
            else:
                data = {}
        else:
            data = rollups

        return QueryResult(
            source=self.source_id,
            query=query,
            data=QueryResultData(value=data),
            metadata={
                "last_refresh": rollups.get("last_updated"),
                "is_current": True
            },
            is_stale=False,
            cache_age_seconds=0
        )

    def get_precomputed_rollups(self) -> Dict[str, Any]:
        """Return cached world state rollups."""
        return dict(self._rollups)

    async def refresh_rollups(self) -> None:
        """
        Refresh world state data from external sources.

        Called every 6 hours by scheduled background task.
        """
        logger.info(f"[{self.source_id}] Refreshing world state rollups...")

        try:
            # Fetch in parallel
            location_task = asyncio.create_task(self._fetch_location())
            temporal_task = asyncio.create_task(self._get_temporal_context())

            location = await location_task
            temporal = await temporal_task

            # Update rollups with location and temporal data first
            self._rollups.update({
                # Location
                "server_location": location.get("city_region"),
                "server_coords": location.get("coords"),
                "server_timezone": location.get("timezone"),

                # Temporal
                "current_date": temporal["date"],
                "season": temporal["season"],
                "time_of_day": temporal["time_of_day"],
                "day_of_week": temporal["day_of_week"],
                "is_weekend": temporal["is_weekend"],

                # Meta
                "last_updated": datetime.now().isoformat()
            })

            # Fetch weather (needs location)
            weather = await self._fetch_weather()
            self._rollups.update({
                "current_weather": weather.get("summary"),
                "temperature": weather.get("temp_f"),
                "weather_description": weather.get("description"),
            })

            # Persist to database
            self._save_rollups()
            self._last_rollup_refresh = datetime.now()

            logger.info(f"[{self.source_id}] Rollups refreshed: {self._rollups.get('server_location')}, {self._rollups.get('current_weather')}")

        except Exception as e:
            logger.error(f"[{self.source_id}] Rollup refresh failed: {e}")
            # Keep existing rollups on failure

    async def _fetch_location(self) -> Dict[str, Any]:
        """
        Fetch server geolocation using IP lookup.

        Returns:
            {
                "city_region": "Seattle, WA",
                "coords": (47.6062, -122.3321),
                "timezone": "America/Los_Angeles"
            }
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get("https://ipapi.co/json/")
                data = response.json()

                city = data.get("city", "")
                region = data.get("region_code", "")
                city_region = f"{city}, {region}" if city and region else self._home_location

                return {
                    "city_region": city_region,
                    "coords": (data.get("latitude"), data.get("longitude")),
                    "timezone": data.get("timezone")
                }
        except Exception as e:
            logger.warning(f"Geolocation fetch failed: {e}, using fallback")
            return {
                "city_region": self._home_location,
                "coords": None,
                "timezone": None
            }

    async def _fetch_weather(self) -> Dict[str, Any]:
        """
        Fetch current weather from wttr.in.

        Returns:
            {
                "summary": "Rainy, 52°F",
                "temp_f": 52,
                "description": "Light rain"
            }
        """
        location = self._rollups.get("server_location", self._home_location)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # URL encode the location for safety
                encoded_location = location.replace(" ", "+").replace(",", "")
                response = await client.get(
                    f"https://wttr.in/{encoded_location}?format=j1",
                    headers={"User-Agent": "CassBot/1.0"}
                )

                if response.status_code == 200:
                    data = response.json()
                    current = data.get("current_condition", [{}])[0]

                    weather_desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
                    temp_f = int(current.get("temp_F", 0))

                    return {
                        "summary": f"{weather_desc}, {temp_f}°F",
                        "temp_f": temp_f,
                        "description": weather_desc
                    }
                else:
                    raise Exception(f"HTTP {response.status_code}")

        except Exception as e:
            logger.warning(f"Weather fetch failed: {e}")
            return {
                "summary": None,
                "temp_f": None,
                "description": None
            }

    async def _get_temporal_context(self) -> Dict[str, Any]:
        """
        Calculate current temporal context.

        Returns:
            {
                "date": "Tuesday, January 28, 2026",
                "season": "winter",
                "time_of_day": "afternoon",
                "day_of_week": "Tuesday",
                "is_weekend": False
            }
        """
        now = datetime.now()
        month = now.month
        hour = now.hour

        # Season (Northern hemisphere)
        if month in [12, 1, 2]:
            season = "winter"
        elif month in [3, 4, 5]:
            season = "spring"
        elif month in [6, 7, 8]:
            season = "summer"
        else:
            season = "fall"

        # Time of day
        if 5 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 17:
            time_of_day = "afternoon"
        elif 17 <= hour < 21:
            time_of_day = "evening"
        else:
            time_of_day = "night"

        return {
            "date": now.strftime("%A, %B %d, %Y"),
            "season": season,
            "time_of_day": time_of_day,
            "day_of_week": calendar.day_name[now.weekday()],
            "is_weekend": now.weekday() >= 5
        }

    def _load_rollups(self) -> None:
        """Load rollups from database."""
        try:
            with get_db() as conn:
                cursor = conn.execute("""
                    SELECT rollups_json FROM world_state_rollups
                    WHERE daemon_id = ?
                """, (self._daemon_id,))

                row = cursor.fetchone()
                if row and row[0]:
                    self._rollups = json_deserialize(row[0])
                    if self._rollups.get("last_updated"):
                        self._last_rollup_refresh = datetime.fromisoformat(
                            self._rollups["last_updated"]
                        )
        except Exception as e:
            logger.warning(f"Failed to load world state rollups: {e}")
            self._rollups = {}

    def _save_rollups(self) -> None:
        """Save rollups to database."""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO world_state_rollups
                    (daemon_id, rollups_json, updated_at)
                    VALUES (?, ?, ?)
                """, (
                    self._daemon_id,
                    json_serialize(self._rollups),
                    datetime.now().isoformat()
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save world state rollups: {e}")

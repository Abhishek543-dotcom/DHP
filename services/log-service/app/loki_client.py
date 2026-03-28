import logging
from typing import Optional
from datetime import datetime, timedelta

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class LokiClient:
    """Client for querying Grafana Loki."""

    def __init__(self):
        self.base_url = settings.loki_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def query_logs(
        self,
        job_id: str,
        source: str = "all",
        tail: int = 500,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Query logs from Loki by job_id label.

        Uses LogQL to filter logs for a specific job.
        """
        # Build LogQL query
        if source == "all":
            query = f'{{job_id="{job_id}"}}'
        else:
            query = f'{{job_id="{job_id}", source="{source}"}}'

        # Default time range: last 24 hours
        if not end:
            end = datetime.utcnow()
        if not start:
            start = end - timedelta(hours=24)

        params = {
            "query": query,
            "limit": tail,
            "start": int(start.timestamp() * 1e9),  # Loki uses nanoseconds
            "end": int(end.timestamp() * 1e9),
            "direction": "backward",
        }

        try:
            response = await self.client.get(
                f"{self.base_url}{settings.loki_query_path}",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            # Parse Loki response
            logs = []
            results = data.get("data", {}).get("result", [])
            for stream in results:
                labels = stream.get("stream", {})
                for value in stream.get("values", []):
                    timestamp_ns, message = value
                    logs.append({
                        "timestamp": datetime.fromtimestamp(
                            int(timestamp_ns) / 1e9
                        ).isoformat(),
                        "message": message,
                        "source": labels.get("source", "unknown"),
                        "level": labels.get("level", "INFO"),
                        "job_id": labels.get("job_id", job_id),
                    })

            return logs

        except httpx.HTTPStatusError as e:
            logger.error(f"Loki query failed with status {e.response.status_code}: {e}")
            return []
        except httpx.ConnectError:
            logger.warning("Cannot connect to Loki, returning empty logs")
            return []
        except Exception as e:
            logger.error(f"Unexpected error querying Loki: {e}")
            return []

    async def close(self):
        await self.client.aclose()


# Singleton instance
_loki_client: Optional[LokiClient] = None


def get_loki_client() -> LokiClient:
    global _loki_client
    if _loki_client is None:
        _loki_client = LokiClient()
    return _loki_client


async def close_loki_client():
    global _loki_client
    if _loki_client is not None:
        await _loki_client.close()
        _loki_client = None


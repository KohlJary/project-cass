"""Home Assistant areas: the template endpoint returns rendered text, not JSON
(2026-11-17: `areas() | list` rendered as a Python list and failed every minute)."""
import asyncio

import httpx

from home_assistant import AREAS_TEMPLATE, HomeAssistantClient


def _client(handler):
    ha = HomeAssistantClient(url="http://ha.test", token="t")

    async def get_client():
        return httpx.AsyncClient(base_url="http://ha.test", transport=httpx.MockTransport(handler))
    ha._get_client = get_client
    return ha


def test_areas_come_back_with_names_in_one_call():
    seen = []

    def handler(request):
        seen.append(request.content)
        return httpx.Response(200, text='[{"area_id": "kitchen", "name": "Kitchen"}]')
    assert asyncio.run(_client(handler).get_areas()) == [{"area_id": "kitchen", "name": "Kitchen"}]
    assert len(seen) == 1 and b"tojson" in seen[0]
    assert "tojson" in AREAS_TEMPLATE


def test_a_bad_answer_gives_no_areas_rather_than_raising():
    assert asyncio.run(_client(lambda r: httpx.Response(200, text="['kitchen']")).get_areas()) == []
    assert asyncio.run(_client(lambda r: httpx.Response(500)).get_areas()) == []

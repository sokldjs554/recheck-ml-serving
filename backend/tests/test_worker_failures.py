import httpx


async def test_worker_failure_counter_includes_unavailability(tmp_path):
    from recheck.config import Settings
    from recheck.worker import create_app
    worker = create_app(Settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=worker), base_url="http://worker") as client:
        response = await client.post("/infer", json={"features": [0.1, 0, 0, 0.1], "model_version": "risk-v1", "delay_ms": 0, "fault": "unavailable", "deadline_ms": 300})
        assert response.status_code == 503
        health = (await client.get("/health")).json()
        assert health["failures"] == 1
        assert health["completed"] == 0

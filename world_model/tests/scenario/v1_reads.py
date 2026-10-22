"""What an agent reads about a company through the v1 API (world_model/docs/api/openapi.yaml), for the construction tests: the
export, a subgraph, the construction view, a trace, and a simulation's calculation coverage. Each test app is a local
run (no credential configured), so its one world model is the organization's only one."""

from __future__ import annotations

from typing import Any


def world_model(client: Any) -> str:
    models = client.get("/v1/world-models").json()["data"]
    assert len(models) == 1, models
    return f"/v1/world-models/{models[0]['id']}"


def data(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, r.text[:500]
    return r.json()["data"]


def pack(client: Any, simulation: str | None = None) -> dict:
    """The v4.1.4 export's domain pack."""
    params = {"simulation": simulation} if simulation else {}
    return data(client.get(world_model(client) + "/exports/v4.1.4", params=params))["domain_pack"]


def graph(client: Any, attribute_ids: str, depth: int = 1) -> dict:
    """The subgraph around comma-separated attribute ids: entities with their attributes nested, and relationships."""
    return data(client.get(world_model(client) + "/graph", params={"attributes": attribute_ids, "depth": depth}))


def construction(client: Any, entity_id: str) -> dict:
    return data(client.get(world_model(client) + f"/entities/{entity_id}/construction"))


def construction_markdown(client: Any, entity_id: str) -> str:
    r = client.get(world_model(client) + f"/entities/{entity_id}/construction", params={"format": "markdown"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    return r.text


def trace(client: Any, entity_id: str, start: str, **params: Any) -> dict:
    return data(client.get(world_model(client) + f"/entities/{entity_id}/traces", params={"from": start, **params}))


def simulate(client: Any, question: str, horizon_days: int) -> dict:
    """Pose a question as a thesis, run it, and read the simulation's calculation coverage."""
    wm = world_model(client)
    thesis = data(client.post(wm + "/theses", json={"question": question, "horizon_days": horizon_days}), 201)
    job = data(client.post(wm + f"/theses/{thesis['id']}/simulations"), 202)
    assert job["status"] == "succeeded", job
    return data(client.get(wm + f"/simulations/{job['result']['ids'][0]}/coverage"))

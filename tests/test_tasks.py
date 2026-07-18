"""Tests for task CRUD, listing, filtering, and input validation."""


async def _make_task(auth_client, **overrides):
    payload = {"title": "Write report", "priority": 2}
    payload.update(overrides)
    r = await auth_client.post("/tasks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_then_get_task(auth_client):
    created = await _make_task(auth_client)
    r = await auth_client.get(f"/tasks/{created['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Write report"
    assert body["status"] == "todo"
    assert body["priority"] == 2


async def test_create_sets_location_header(auth_client):
    r = await auth_client.post("/tasks", json={"title": "with location"})
    assert r.status_code == 201
    assert r.headers["location"] == f"/tasks/{r.json()['id']}"


async def test_update_task(auth_client):
    created = await _make_task(auth_client)
    r = await auth_client.patch(
        f"/tasks/{created['id']}", json={"status": "done", "priority": 5}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["priority"] == 5


async def test_delete_task(auth_client):
    created = await _make_task(auth_client)
    r = await auth_client.delete(f"/tasks/{created['id']}")
    assert r.status_code == 204
    r = await auth_client.get(f"/tasks/{created['id']}")
    assert r.status_code == 404


async def test_get_missing_task_returns_404(auth_client):
    r = await auth_client.get("/tasks/999999")
    assert r.status_code == 404


async def test_list_pagination_and_total(auth_client):
    for i in range(3):
        await _make_task(auth_client, title=f"task-{i}")
    r = await auth_client.get("/tasks", params={"limit": 2, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    assert body["total"] == 3


async def test_list_status_filter(auth_client):
    await _make_task(auth_client, title="still open", status="todo")
    done = await _make_task(auth_client, title="finished")
    await auth_client.patch(f"/tasks/{done['id']}", json={"status": "done"})
    r = await auth_client.get("/tasks", params={"status": "done"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert all(item["status"] == "done" for item in items)


async def test_invalid_priority_rejected(auth_client):
    r = await auth_client.post("/tasks", json={"title": "bad", "priority": 9})
    assert r.status_code == 422


async def test_empty_title_rejected(auth_client):
    r = await auth_client.post("/tasks", json={"title": "", "priority": 3})
    assert r.status_code == 422


async def test_create_requires_authentication(client):
    r = await client.post("/tasks", json={"title": "no auth"})
    assert r.status_code == 401

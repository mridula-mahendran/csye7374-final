"""Authorization tests.

These are the example-based tests that catch the IDOR demo (Bug 2). They assert
that one user cannot read or modify another user's task. Schemathesis cannot
catch this class of bug: it drives the API as a single identity and every
response is schema-valid, so a cross-user data leak looks like a normal 200.
"""

import uuid


async def _new_user_token(client, tag):
    email = f"{tag}_{uuid.uuid4().hex[:10]}@example.com"
    password = "Str0ngPass!"
    await client.post("/auth/register", json={"email": email, "password": password})
    r = await client.post("/auth/token", data={"username": email, "password": password})
    return r.json()["access_token"]


async def test_user_cannot_read_another_users_task(client):
    owner = await _new_user_token(client, "owner")
    r = await client.post(
        "/tasks",
        json={"title": "confidential"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    task_id = r.json()["id"]

    attacker = await _new_user_token(client, "attacker")
    r = await client.get(
        f"/tasks/{task_id}", headers={"Authorization": f"Bearer {attacker}"}
    )
    assert r.status_code == 404


async def test_user_cannot_update_another_users_task(client):
    owner = await _new_user_token(client, "owner")
    r = await client.post(
        "/tasks",
        json={"title": "confidential"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    task_id = r.json()["id"]

    attacker = await _new_user_token(client, "attacker")
    r = await client.patch(
        f"/tasks/{task_id}",
        json={"title": "tampered"},
        headers={"Authorization": f"Bearer {attacker}"},
    )
    assert r.status_code == 404


async def test_user_cannot_delete_another_users_task(client):
    owner = await _new_user_token(client, "owner")
    r = await client.post(
        "/tasks",
        json={"title": "confidential"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    task_id = r.json()["id"]

    attacker = await _new_user_token(client, "attacker")
    r = await client.delete(
        f"/tasks/{task_id}", headers={"Authorization": f"Bearer {attacker}"}
    )
    assert r.status_code == 404

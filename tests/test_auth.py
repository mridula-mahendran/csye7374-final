"""Tests for registration and token issuance."""

import uuid


async def test_register_returns_user(client):
    email = f"reg_{uuid.uuid4().hex[:10]}@example.com"
    r = await client.post(
        "/auth/register", json={"email": email, "password": "Str0ngPass!"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == email
    assert body["role"] == "user"
    assert "id" in body


async def test_login_returns_bearer_token(client):
    email = f"login_{uuid.uuid4().hex[:10]}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "Str0ngPass!"})
    r = await client.post(
        "/auth/token", data={"username": email, "password": "Str0ngPass!"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password_rejected(client):
    email = f"wrong_{uuid.uuid4().hex[:10]}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "Str0ngPass!"})
    r = await client.post(
        "/auth/token", data={"username": email, "password": "not-the-password"}
    )
    assert r.status_code == 401


async def test_duplicate_registration_conflict(client):
    email = f"dup_{uuid.uuid4().hex[:10]}@example.com"
    await client.post("/auth/register", json={"email": email, "password": "Str0ngPass!"})
    r = await client.post(
        "/auth/register", json={"email": email, "password": "Str0ngPass!"}
    )
    assert r.status_code == 409


async def test_me_requires_authentication(client):
    r = await client.get("/users/me")
    assert r.status_code == 401


async def test_me_returns_current_user(auth_client):
    r = await auth_client.get("/users/me")
    assert r.status_code == 200
    assert r.json()["role"] == "user"

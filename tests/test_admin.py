"""Admin RBAC tests: non-admins are forbidden, admins can list all tasks."""


async def test_non_admin_forbidden(auth_client):
    r = await auth_client.get("/admin/tasks")
    assert r.status_code == 403


async def test_admin_can_list_all_tasks(admin_client):
    r = await admin_client.get("/admin/tasks")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body

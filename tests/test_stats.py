"""Tests for the stats endpoint and the is_actionable rule.

The assertion below pins the priority boundary (priority == 3 is actionable).
This is what kills the mutmut mutant that flips ``>=`` to ``>``. Weaken this
assertion (see the README mutation-testing demo) and that mutant survives while
line coverage stays at 100 percent.
"""


async def _make_task(auth_client, **overrides):
    payload = {"title": "task", "priority": 3}
    payload.update(overrides)
    r = await auth_client.post("/tasks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def test_stats_counts_actionable_tasks(auth_client):
    # Priority 3, still todo -> actionable (boundary case).
    await _make_task(auth_client, title="boundary", priority=3)
    # Priority 2, still todo -> not actionable (below threshold).
    await _make_task(auth_client, title="low priority", priority=2)
    # Priority 5 but done -> not actionable (status excludes it).
    done = await _make_task(auth_client, title="high but done", priority=5)
    await auth_client.patch(f"/tasks/{done['id']}", json={"status": "done"})

    r = await auth_client.get("/tasks/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["actionable"] == 1

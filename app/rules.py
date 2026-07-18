"""Pure business rules.

This module is intentionally small and side-effect free. It is the primary
target for mutation testing: pure functions with real branching logic are where
mutation testing gives the clearest signal about test-suite quality.
"""

from app.models import Status, Task


def is_actionable(task: Task) -> bool:
    """A task is actionable when it is not yet done and is priority 3 or higher.

    The boundary here (priority >= 3) is exactly the kind of logic a weak test
    can "cover" without actually pinning. See the mutation-testing demo in the
    README: weaken the boundary assertion and mutmut will surface a survivor
    while line coverage stays at 100 percent.
    """
    return task.status != Status.done and task.priority >= 3

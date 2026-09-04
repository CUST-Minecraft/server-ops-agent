import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app.web.app as web_app


PROTECTED_PATHS = (
    "/api/status",
    "/api/incidents",
    "/api/approvals",
    "/api/incidents/{incident_id}",
    "/api/approvals/{approval_id}/approve",
    "/api/approvals/{approval_id}/reject",
    "/api/chat/stream",
    "/api/chat/messages",
)


def route_for(path: str):
    return next(route for route in web_app.app.routes if getattr(route, "path", None) == path)


class FakeApprovals:
    def __init__(self):
        self.calls = []

    def approve(self, approval_id: int, actor: str) -> str:
        self.calls.append(("approve", approval_id, actor))
        return "approved"

    def reject(self, approval_id: int, actor: str) -> str:
        self.calls.append(("reject", approval_id, actor))
        return "rejected"


class WebAuthRouteTests(unittest.TestCase):
    def test_all_business_routes_depend_on_current_user(self):
        for path in PROTECTED_PATHS:
            with self.subTest(path=path):
                route = route_for(path)
                calls = {dependency.call for dependency in route.dependant.dependencies}
                self.assertIn(web_app.get_current_user, calls)

    def test_approval_actions_record_the_authenticated_username(self):
        self.assertIn("current_user", inspect.signature(web_app.approve_action).parameters)
        self.assertIn("current_user", inspect.signature(web_app.reject_action).parameters)

        approvals = FakeApprovals()
        current_user = SimpleNamespace(username="alice")

        with patch("app.runtime_deps.build_executor_and_approvals", return_value=(None, None, approvals)):
            approve_result = web_app.approve_action(12, current_user)
            reject_result = web_app.reject_action(13, current_user)

        self.assertEqual(approve_result, {"ok": True, "message": "approved"})
        self.assertEqual(reject_result, {"ok": True, "message": "rejected"})
        self.assertEqual(
            approvals.calls,
            [("approve", 12, "alice"), ("reject", 13, "alice")],
        )

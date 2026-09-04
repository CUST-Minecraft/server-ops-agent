import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import cli


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, _condition):
        return self

    def first(self):
        return self.result


class FakeSession:
    def __init__(self, query_result=None):
        self.query_result = query_result
        self.added = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query(self, _model):
        return FakeQuery(self.query_result)

    def add(self, record):
        self.added.append(record)

    def commit(self):
        self.committed = True


class CliChatTests(unittest.TestCase):
    def test_authenticate_cli_user_returns_only_a_verified_user(self):
        user = SimpleNamespace(id=7, username="alice", password_hash="bcrypt-hash")
        session = FakeSession(query_result=user)

        self.assertTrue(hasattr(cli, "_authenticate_cli_user"))

        with patch("app.storage.db.SessionLocal", return_value=session), patch(
            "app.security.auth.verify_password", return_value=True
        ):
            actual = cli._authenticate_cli_user("alice", "correct-password")

        self.assertIs(actual, user)

    def test_persist_cli_chat_writes_both_messages_with_one_owner(self):
        session = FakeSession()

        self.assertTrue(hasattr(cli, "_persist_cli_chat"))

        with patch("app.storage.db.SessionLocal", return_value=session):
            cli._persist_cli_chat("cli_session", 7, "磁盘怎么样", "磁盘正常")

        self.assertTrue(session.committed)
        self.assertEqual(len(session.added), 2)
        self.assertEqual([record.user_id for record in session.added], [7, 7])
        self.assertEqual([record.session_id for record in session.added], ["cli_session", "cli_session"])
        self.assertEqual([record.role for record in session.added], ["user", "assistant"])
        self.assertEqual([record.content for record in session.added], ["磁盘怎么样", "磁盘正常"])

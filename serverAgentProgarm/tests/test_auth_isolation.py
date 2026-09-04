import hashlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.security.auth import hash_password
from app.storage.models import AuthToken, ChatMessage, User
from app.web.app import app


@pytest.fixture()
def seeded_users(db):
    now = datetime.now(timezone.utc)
    with db() as session:
        alice = User(username="alice", password_hash=hash_password("alice-pass"), created_at=now)
        bob = User(username="bob", password_hash=hash_password("bob-pass"), created_at=now)
        session.add_all([alice, bob])
        session.commit()
        return {"alice": alice, "bob": bob}


def login(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_persists_only_token_hash(db, seeded_users):
    with TestClient(app) as client:
        token = login(client, "alice", "alice-pass")

    with db() as session:
        stored = session.query(AuthToken).one()
    assert stored.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert stored.token_hash != token


def test_authenticated_user_can_access_protected_status(db, seeded_users):
    with TestClient(app) as client:
        token = login(client, "alice", "alice-pass")
        response = client.get("/api/status", headers=auth_header(token))

    assert response.status_code == 200


def test_chat_history_is_isolated_by_authenticated_user(db, seeded_users):
    now = datetime.now(timezone.utc)
    with db() as session:
        session.add_all([
            ChatMessage(session_id="alice-session", user_id=seeded_users["alice"].id,
                        role="user", content="Alice secret", created_at=now),
            ChatMessage(session_id="bob-session", user_id=seeded_users["bob"].id,
                        role="user", content="Bob note", created_at=now),
        ])
        session.commit()

    with TestClient(app) as client:
        alice_token = login(client, "alice", "alice-pass")
        bob_token = login(client, "bob", "bob-pass")
        own = client.get("/api/chat/messages?session_id=alice-session", headers=auth_header(alice_token))
        forbidden = client.get("/api/chat/messages?session_id=alice-session", headers=auth_header(bob_token))

    assert own.status_code == 200
    assert own.json()["messages"] == [{"role": "user", "content": "Alice secret"}]
    assert forbidden.status_code == 403


def test_logout_revokes_existing_token(db, seeded_users):
    with TestClient(app) as client:
        token = login(client, "alice", "alice-pass")
        logout = client.post("/api/auth/logout", headers=auth_header(token))
        after_logout = client.get("/api/status", headers=auth_header(token))

    assert logout.status_code == 200
    assert after_logout.status_code == 401

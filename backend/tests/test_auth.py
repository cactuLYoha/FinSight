import pytest
from datetime import timedelta
from flask_jwt_extended import create_access_token
from app.extensions import db
from app.models.user import User
from tests.auth_support import finish_verification


CREDENTIALS = {
    "email": "test@example.com",
    "password": "StrongPassword123",
}


def test_register(client):
    response = client.post(
        "/api/auth/register",
        json=CREDENTIALS,
    )

    assert response.status_code == 201

    data = response.get_json()["user"]
    assert data["email"] == CREDENTIALS["email"]
    assert set(data) == {"id", "email", "created_at", "is_email_verified", "email_verified_at"}
    assert data['is_email_verified'] is False

    user = db.session.get(User, data["id"])
    assert user.password_hash != CREDENTIALS["password"]
    assert user.check_password(CREDENTIALS["password"])


def test_register_duplicate_email(client):
    client.post("/api/auth/register", json=CREDENTIALS)

    response = client.post(
        "/api/auth/register",
        json=CREDENTIALS,
    )

    assert response.status_code == 409
    assert db.session.query(User).count() == 1


@pytest.mark.parametrize("route", ["register", "login"])
def test_missing_credentials(client, route):
    response = client.post(f"/api/auth/{route}", json={})

    assert response.status_code == 400


def test_login(client):
    client.post("/api/auth/register", json=CREDENTIALS)

    response = client.post(
        "/api/auth/login",
        json=CREDENTIALS,
    )

    assert response.status_code == 202
    assert 'access_token' not in response.get_json()
    assert finish_verification(client).get_json()["access_token"]


@pytest.mark.parametrize("overrides", [
    {"password": "wrong-password"},
    {"email": "missing@example.com"},
])
def test_login_invalid_credentials(client, overrides):
    client.post("/api/auth/register", json=CREDENTIALS)

    response = client.post(
        "/api/auth/login",
        json={**CREDENTIALS, **overrides},
    )

    assert response.status_code == 401
    assert "access_token" not in response.get_json()


def test_me(client):
    registration = client.post(
        "/api/auth/register",
        json=CREDENTIALS,
    )
    expected_user = registration.get_json()["user"]

    login = client.post("/api/auth/login", json=CREDENTIALS)
    assert login.status_code == 202
    token = finish_verification(client).get_json()["access_token"]

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.get_json()["user"]
    assert {key: data[key] for key in ('id', 'email', 'created_at')} == {key: expected_user[key] for key in ('id', 'email', 'created_at')}
    assert data['is_email_verified'] is True
    assert data['email_verified_at']


def test_me_without_token(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
def test_me_with_expired_token(client, app):
    registration = client.post(
        "/api/auth/register",
        json=CREDENTIALS,
    )
    assert registration.status_code == 201

    user_id = registration.get_json()["user"]["id"]

    with app.app_context():
        token = create_access_token(
            identity=str(user_id),
            expires_delta=timedelta(seconds=-60),
        )

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.get_json() == {"msg": "Token has expired"}
def test_me_with_invalid_signature(client, app, monkeypatch):
    registration = client.post(
        "/api/auth/register",
        json=CREDENTIALS,
    )
    assert registration.status_code == 201

    user_id = registration.get_json()["user"]["id"]

    with app.app_context():
        with monkeypatch.context() as patch:
            patch.setitem(
                app.config,
                "JWT_SECRET_KEY",
                "another-test-secret-key-at-least-32-bytes",
            )
            token = create_access_token(identity=str(user_id))

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.get_json() == {
        "msg": "Signature verification failed"
    }

"""
Authentication test suite for Phase 2.

Runs against the isolated test database configured in conftest.py -- the
real app.db is never touched by these tests.
"""
from fastapi.testclient import TestClient

from database.schema import create_tables
from main import app

create_tables()

client = TestClient(app)

TEST_USER = {
    "name": "Test Student",
    "email": "test.student@example.com",
    "password": "password123",
}


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_register_user():
    response = client.post("/auth/register", json=TEST_USER)
    assert response.status_code == 201

    body = response.json()
    assert body["message"] == "Registration successful"
    assert body["user"]["email"] == TEST_USER["email"]
    assert body["user"]["name"] == TEST_USER["name"]
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_register_duplicate_email_rejected():
    response = client.post("/auth/register", json=TEST_USER)
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"


def test_login_success():
    response = client.post(
        "/auth/login",
        json={"email": TEST_USER["email"], "password": TEST_USER["password"]},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == TEST_USER["email"]


def test_login_invalid_password_rejected():
    response = client.post(
        "/auth/login",
        json={"email": TEST_USER["email"], "password": "the-wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_unknown_email_rejected_with_same_generic_message():
    response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "irrelevant123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_me_with_valid_token():
    login_response = client.post(
        "/auth/login",
        json={"email": TEST_USER["email"], "password": TEST_USER["password"]},
    )
    token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    body = response.json()
    assert body["email"] == TEST_USER["email"]
    assert "password_hash" not in body


def test_me_without_token_rejected():
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_invalid_token_rejected():
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401

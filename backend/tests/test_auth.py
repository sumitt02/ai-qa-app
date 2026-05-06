"""Authentication tests."""


def test_register_success(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "password123", "full_name": "Alice"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "alice@example.com"


def test_register_duplicate_email(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "password123"},
    )
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "password123"},
    )
    assert response.status_code == 400


def test_register_short_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_login_success(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "password123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "dave@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_wrong_password(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "eve@example.com", "password": "password123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "eve@example.com", "password": "wrongpass"},
    )
    assert response.status_code == 401


def test_login_unknown_email(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "password123"},
    )
    assert response.status_code == 401


def test_me_endpoint(client, auth_headers):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


def test_me_no_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_invalid_token(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


def test_me_malformed_jwt_payload(client):
    """Token with no `sub` claim."""
    from app.core.security import create_access_token
    from jose import jwt
    from app.core.config import settings
    bad_token = jwt.encode(
        {"foo": "bar", "exp": 9999999999}, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_token}"}
    )
    assert response.status_code == 401


def test_me_token_for_deleted_user(client, db_session):
    """Token references a user that no longer exists."""
    from app.core.security import create_access_token
    token = create_access_token(subject=99999)
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_me_non_integer_subject(client):
    """Token sub is not an integer."""
    from jose import jwt
    from app.core.config import settings
    token = jwt.encode(
        {"sub": "not-a-number", "exp": 9999999999},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401

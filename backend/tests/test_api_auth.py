import pytest
from httpx import AsyncClient

from app.models.company import Company
from app.models.developer import Developer
from app.core.security import hash_password


async def test_register_company_admin_success(client: AsyncClient, db) -> None:
    payload = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "Password123!",
        "account_type": "company_admin",
        "company_name": "Test Company",
        "company_type": "vendor"
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert data["role"] == "company_admin"
    assert data["company_name"] == "Test Company"
    assert data["company_type"] == "vendor"


async def test_register_duplicate_username_returns_409(client: AsyncClient) -> None:
    payload = {
        "username": "dupuser",
        "email": "dupuser1@example.com",
        "password": "Password123!",
        "account_type": "company_admin",
    }
    await client.post("/api/v1/auth/register", json=payload)
    
    payload2 = {
        "username": "dupuser",
        "email": "dupuser2@example.com",
        "password": "Password123!",
        "account_type": "company_admin",
    }
    resp = await client.post("/api/v1/auth/register", json=payload2)
    assert resp.status_code == 409


async def test_register_developer_success(client: AsyncClient, db) -> None:
    # 1. Create a company
    company = Company(name="Dev Co", slug="dev-co", tenant_type="esn", is_active=True)
    db.add(company)
    await db.flush()
    
    # 2. Create a developer under that company
    developer = Developer(name="Dev1", email="dev1@example.com", username="dev_1", company_id=company.id)
    db.add(developer)
    await db.flush()

    # 3. Register as developer
    payload = {
        "username": "dev1_user",
        "email": "dev1@example.com",
        "password": "Password123!",
        "account_type": "developer",
        "company_slug": "dev-co"
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    assert resp.json()["role"] == "developer"
    assert resp.json()["developer_id"] == developer.id
    assert resp.json()["company_id"] == company.id


async def test_login_success(client: AsyncClient, test_user) -> None:
    payload = {
        "username": "testuser",
        "password": "TestPass123!"
    }
    resp = await client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "expires_in_seconds" in data


async def test_login_invalid_password_returns_401(client: AsyncClient, test_user) -> None:
    payload = {
        "username": "testuser",
        "password": "WrongPassword!"
    }
    resp = await client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 401


async def test_me_returns_current_user(client: AsyncClient, test_user, monkeypatch) -> None:
    from app.config import settings
    monkeypatch.setattr(settings, "auth_enabled", True)
    
    # Login to get token
    login_resp = await client.post("/api/v1/auth/login", json={"username": "testuser", "password": "TestPass123!"})
    token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"

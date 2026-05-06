"""Shared pytest fixtures."""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set env BEFORE importing app modules
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["SECRET_KEY"] = "test-secret-key-12345678901234567890"
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["REDIS_URL"] = ""  # disable in tests by default; specific tests opt in
_TMP = tempfile.mkdtemp(prefix="aiqa_test_")
os.environ["UPLOAD_DIR"] = str(Path(_TMP) / "uploads")
os.environ["CHROMA_DIR"] = str(Path(_TMP) / "chroma")
Path(os.environ["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["CHROMA_DIR"]).mkdir(parents=True, exist_ok=True)

from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


# Override DB to use in-memory SQLite
TEST_DB_URL = "sqlite:///./test.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def reset_database():
    """Recreate tables before each test."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Test HTTP client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """Register a test user and return their JWT."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "testpass123",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Create a tiny valid PDF on the fly."""
    # Minimal PDF — text "Hello world from the test PDF"
    from pypdf import PdfWriter
    from io import BytesIO
    # Easier: ship a static minimal pdf
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n"
        b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"5 0 obj<</Length 64>>stream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello world from test PDF) Tj ET\n"
        b"endstream endobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000010 00000 n \n"
        b"0000000053 00000 n \n"
        b"0000000100 00000 n \n"
        b"0000000200 00000 n \n"
        b"0000000260 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n360\n%%EOF\n"
    )

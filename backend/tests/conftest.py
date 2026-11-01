import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import ai as ai_mod  # noqa: E402
from app.config import Settings  # noqa: E402
from app.http import reset_all_rate_limits  # noqa: E402
from app.main import create_app  # noqa: E402
from app.seed import DEMO_ADMIN, DEMO_CITIZEN  # noqa: E402


def make_settings(tmp_path, key=""):
    return Settings(env="test", database_path=str(tmp_path / "t.db"), secret_key="x" * 40, token_ttl_minutes=60,
                    cors_origins=["http://localhost:3000"], anthropic_api_key=key, ai_model="claude-sonnet-5-5",
                    ai_timeout_seconds=5, seed_demo_data=True)


class FakeClaude:
    """Stands in for the Anthropic API: records requests and returns a canned reply."""

    def __init__(self, reply="{}"):
        self.reply, self.calls = reply, []

    def __call__(self, body):
        self.calls.append(body)
        return {"content": [{"type": "text", "text": self.reply}]}


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_all_rate_limits()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


@pytest.fixture
def fake_ai():
    return FakeClaude()


@pytest.fixture
def ai_client(tmp_path, fake_ai):
    app = create_app(make_settings(tmp_path), ai_mod.AIClient(make_settings(tmp_path), transport=fake_ai))
    with TestClient(app) as c:
        yield c


def login(client, creds):
    r = client.post("/api/auth/login", json={"email": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture
def admin(client):
    return login(client, DEMO_ADMIN)


@pytest.fixture
def citizen(client):
    return login(client, DEMO_CITIZEN)


@pytest.fixture
def other(client):
    return login(client, ("sunita@example.com", "Citizen@1234"))


DOC = {"doc_type": "birth_certificate", "full_name": "Asha Jadhav", "date_of_birth": "2020-01-10", "father_name": "Ramesh Jadhav",
       "mother_name": "Priya Jadhav", "address": "Main Road, Nashik Rural", "place_of_birth": "Nashik"}

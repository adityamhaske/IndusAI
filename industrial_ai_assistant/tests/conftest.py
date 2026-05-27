import pytest
from app.main import app
from app.auth.firebase_auth import get_current_user, AuthenticatedUser

@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(uid="test_user", email="test@test.com", name="Test User", picture="http://example.com/pic.jpg")
    yield
    app.dependency_overrides.clear()

@pytest.fixture(autouse=True)
def mock_qdrant_client(monkeypatch):
    import qdrant_client
    
    # We patch QdrantClient to always act as memory
    original_init = qdrant_client.QdrantClient.__init__
    
    def mock_init(self, *args, **kwargs):
        kwargs["location"] = ":memory:"
        kwargs.pop("host", None)
        kwargs.pop("port", None)
        kwargs.pop("url", None)
        original_init(self, *args, **kwargs)
    
    monkeypatch.setattr("qdrant_client.QdrantClient.__init__", mock_init)
    yield

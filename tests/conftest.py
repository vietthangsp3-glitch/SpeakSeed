import pytest


@pytest.fixture(autouse=True)
def _legacy_bearer_transport(monkeypatch):
    """Keep existing API tests explicit while production defaults to safer cookies."""
    monkeypatch.setenv("AUTH_TRANSPORT", "bearer")


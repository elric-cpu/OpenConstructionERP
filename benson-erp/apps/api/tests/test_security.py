import uuid

from app.core.security import Principal, create_access_token


def test_access_token_does_not_embed_secrets() -> None:
    principal = Principal(uuid.uuid4(), uuid.uuid4(), frozenset({"leads.create"}), uuid.uuid4())
    token = create_access_token(principal)
    assert str(principal.tenant_id) not in token
    assert token.count(".") == 2

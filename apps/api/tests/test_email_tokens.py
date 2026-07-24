import hmac
from uuid import UUID

import pytest

from company_api.email_tokens import EmailTokenSigner
from company_api.models import UserTokenPurpose

TOKEN_ID = UUID("00000000-0000-0000-0000-000000000123")


def test_signer_reconstructs_without_storing_the_raw_token() -> None:
    signer = EmailTokenSigner("x" * 32)

    issued = signer.issue(TOKEN_ID, UserTokenPurpose.VERIFY_EMAIL)

    assert issued == signer.issue(TOKEN_ID, UserTokenPurpose.VERIFY_EMAIL)
    assert signer.matches(
        TOKEN_ID,
        UserTokenPurpose.VERIFY_EMAIL,
        signer.digest(issued),
        issued,
    )
    assert not signer.matches(
        TOKEN_ID,
        UserTokenPurpose.RESET_PASSWORD,
        signer.digest(issued),
        issued,
    )


def test_signer_uses_constant_time_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    signer = EmailTokenSigner("x" * 32)
    issued = signer.issue(TOKEN_ID, UserTokenPurpose.VERIFY_EMAIL)
    comparisons: list[tuple[str, str]] = []
    original_compare_digest = hmac.compare_digest

    def track_compare_digest(left: str, right: str) -> bool:
        comparisons.append((left, right))
        return original_compare_digest(left, right)

    monkeypatch.setattr(hmac, "compare_digest", track_compare_digest)

    assert signer.matches(
        TOKEN_ID,
        UserTokenPurpose.VERIFY_EMAIL,
        signer.digest(issued),
        issued,
    )
    assert len(comparisons) == 2


@pytest.mark.parametrize(
    "submitted_token",
    [
        "",
        "not-a-token",
        "00000000-0000-0000-0000-000000000123.",
        "00000000-0000-0000-0000-000000000123.invalid.signature",
        "00000000-0000-0000-0000-000000000124.invalid",
        "00000000000000000000000000000123.invalid",
    ],
)
def test_signer_rejects_malformed_tokens(submitted_token: str) -> None:
    signer = EmailTokenSigner("x" * 32)

    assert not signer.matches(
        TOKEN_ID,
        UserTokenPurpose.VERIFY_EMAIL,
        signer.digest(signer.issue(TOKEN_ID, UserTokenPurpose.VERIFY_EMAIL)),
        submitted_token,
    )


def test_signing_key_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="signing key"):
        EmailTokenSigner("")

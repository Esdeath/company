import base64
import hashlib
import hmac
from uuid import UUID

from company_api.models import UserTokenPurpose


class EmailTokenSigner:
    def __init__(self, signing_key: str) -> None:
        if not signing_key:
            raise ValueError("signing key must not be empty")
        self._signing_key = signing_key.encode()

    def issue(self, token_id: UUID, purpose: UserTokenPurpose) -> str:
        message = f"{purpose.value}:{token_id}".encode()
        signature = hmac.new(self._signing_key, message, hashlib.sha256).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        return f"{token_id}.{encoded_signature}"

    def digest(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def matches(
        self,
        token_id: UUID,
        purpose: UserTokenPurpose,
        expected_digest: str,
        submitted_token: str,
    ) -> bool:
        token_parts = submitted_token.split(".")
        if len(token_parts) != 2 or not token_parts[1]:
            return False
        try:
            submitted_id = UUID(token_parts[0])
        except ValueError:
            return False
        if str(submitted_id) != token_parts[0] or submitted_id != token_id:
            return False

        expected_token = self.issue(token_id, purpose)
        token_matches = hmac.compare_digest(expected_token, submitted_token)
        digest_matches = hmac.compare_digest(self.digest(submitted_token), expected_digest)
        return token_matches and digest_matches

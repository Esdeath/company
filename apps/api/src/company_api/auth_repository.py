"""SQLAlchemy persistence for administrator sessions and login challenges."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from company_api.auth import SessionRecord
from company_api.models import AdminSession, LoginChallenge


class SqlAlchemyAuthRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_login_challenge(
        self,
        challenge_hash: str,
        *,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(LoginChallenge).where(LoginChallenge.expires_at <= created_at)
            )
            session.add(
                LoginChallenge(
                    token_hash=challenge_hash,
                    created_at=created_at,
                    expires_at=expires_at,
                )
            )
            await session.commit()

    async def consume_login_challenge(self, challenge_hash: str, *, now: datetime) -> bool:
        async with self._session_factory() as session:
            statement = (
                delete(LoginChallenge)
                .where(
                    LoginChallenge.token_hash == challenge_hash,
                    LoginChallenge.expires_at > now,
                )
                .returning(LoginChallenge.token_hash)
            )
            consumed = (await session.execute(statement)).scalar_one_or_none()
            await session.commit()
            return consumed is not None

    async def create_session(
        self,
        record: SessionRecord,
        *,
        created_at: datetime,
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(delete(AdminSession).where(AdminSession.expires_at <= created_at))
            session.add(
                AdminSession(
                    token_hash=record.token_hash,
                    username=record.username,
                    credential_fingerprint=record.credential_fingerprint,
                    csrf_token=record.csrf_token,
                    created_at=created_at,
                    expires_at=record.expires_at,
                )
            )
            await session.commit()

    async def get_session(self, session_hash: str, *, now: datetime) -> SessionRecord | None:
        async with self._session_factory() as session:
            statement = select(AdminSession).where(
                AdminSession.token_hash == session_hash,
                AdminSession.expires_at > now,
            )
            stored = (await session.scalars(statement)).one_or_none()
            if stored is None:
                await session.execute(
                    delete(AdminSession).where(
                        AdminSession.token_hash == session_hash,
                        AdminSession.expires_at <= now,
                    )
                )
                await session.commit()
                return None
            return SessionRecord(
                token_hash=stored.token_hash,
                username=stored.username,
                credential_fingerprint=stored.credential_fingerprint,
                csrf_token=stored.csrf_token,
                expires_at=stored.expires_at,
            )

    async def delete_session(self, session_hash: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(AdminSession).where(AdminSession.token_hash == session_hash)
            )
            await session.commit()

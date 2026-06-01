"""鉴权逻辑测试。"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user


class TestGetCurrentUser:

    async def test_valid_user(self, session: AsyncSession):
        from app.models import User
        from app.core.security import hash_password

        user = User(
            username="dep_test",
            email="dep@example.com",
            hashed_password=hash_password("pw"),
            is_admin=False,
        )
        session.add(user)
        await session.flush()

        with patch("app.core.dependencies.decode_access_token") as mock_decode:
            mock_decode.return_value = {"sub": "dep_test"}
            result = await get_current_user(token="dummy", session=session)
            assert result.username == "dep_test"

    async def test_user_not_found(self, session: AsyncSession):
        with patch("app.core.dependencies.decode_access_token") as mock_decode:
            mock_decode.return_value = {"sub": "ghost"}
            with pytest.raises(HTTPException) as exc:
                await get_current_user(token="dummy", session=session)
            assert exc.value.status_code == 401

    async def test_disabled_user_still_passes(self, session: AsyncSession):
        """记录已知问题：is_active 检查未实现。"""
        from app.models import User
        from app.core.security import hash_password

        user = User(
            username="disabled_one",
            email="disabled@example.com",
            hashed_password=hash_password("pw"),
            is_active=False,
        )
        session.add(user)
        await session.flush()

        with patch("app.core.dependencies.decode_access_token") as mock_decode:
            mock_decode.return_value = {"sub": "disabled_one"}
            result = await get_current_user(token="dummy", session=session)
            # 当前实现未检查 is_active，用户仍可通过
            assert result.username == "disabled_one"

# AIMETA P=角色状态读取工具|R=统一回退路径|NR=不含写入逻辑|E=get_project_raw_state_text|X=internal|A=工具函数|D=sqlalchemy|S=db|RD=./README.ai
"""
角色状态文本读取工具。

`raw_state_text` 的单一真源（SoT）是 `ProjectMemory.extra`；本工具集中了三处读取
点（finalize / consistency / knowledge_retrieval）的回退逻辑，避免分支漂移。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session


def get_project_raw_state_text(db: Session, project_id: str) -> Optional[str]:
    """读取项目角色状态文本，优先 ProjectMemory.extra，兼容历史 CharacterState 数据。"""
    from ..models.project_memory import ProjectMemory
    from ..models.memory_layer import CharacterState

    memory = (
        db.query(ProjectMemory)
        .filter(ProjectMemory.project_id == project_id)
        .first()
    )
    if memory and memory.extra:
        text = memory.extra.get("raw_state_text")
        if text:
            return text

    # 兼容旧数据：先 __all__ 聚合记录，再逐角色记录
    all_state = (
        db.query(CharacterState)
        .filter(
            CharacterState.project_id == project_id,
            CharacterState.character_name == "__all__",
        )
        .order_by(CharacterState.chapter_number.desc())
        .first()
    )
    if all_state and all_state.extra:
        text = all_state.extra.get("raw_state_text")
        if text:
            return text

    legacy = (
        db.query(CharacterState)
        .filter(CharacterState.project_id == project_id)
        .order_by(CharacterState.chapter_number.desc())
        .all()
    )
    for state in legacy:
        if state.character_name == "__all__":
            continue
        if state.extra and state.extra.get("raw_state_text"):
            return state.extra["raw_state_text"]

    return None


__all__ = ["get_project_raw_state_text"]

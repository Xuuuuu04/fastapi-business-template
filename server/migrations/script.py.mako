"""
${message}

版本：${up_revision}，上一版本：${down_revision | comma,n}，生成时间：${create_date}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import shared.db.types
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}

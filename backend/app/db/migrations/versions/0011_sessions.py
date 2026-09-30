"""B6: session revocation and login lockout on local users.

- ``session_epoch``: carried in every token; bumping it (password change, deactivation,
  "revoke sessions") invalidates all of the user's tokens at once.
- ``failed_logins`` / ``locked_until``: consecutive failures lock the account for a while.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user", sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "app_user", sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("app_user", sa.Column("locked_until", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("app_user", "locked_until")
    op.drop_column("app_user", "failed_logins")
    op.drop_column("app_user", "session_epoch")

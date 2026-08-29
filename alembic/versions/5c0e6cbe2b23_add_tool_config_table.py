"""add tool_config table

Revision ID: 5c0e6cbe2b23
Revises: e4a71be58f78
Create Date: 2026-08-29 22:55:48.908664

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c0e6cbe2b23'
down_revision: Union[str, Sequence[str], None] = 'e4a71be58f78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tool_config',
        sa.Column('feature_type', sa.String(), nullable=False),
        sa.Column('config_json', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('feature_type'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tool_config')

"""Add transmit phase1 fields.

Revision ID: 2026011501
Revises: 5ef24000d433
Create Date: 2026-01-15 14:00:00.000000

Adds fields and tables for TRANSMIT_SPEC.md Phase 1:
- composition_json field to sstv_images (stores text zones, background, etc.)
- recent_contacts table (powers Smart Reply callsign dropdown)
- user_preferences table (stores working state, default template)
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026011501'
down_revision = '5ef24000d433'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Phase 1 fields and tables."""
    # Add composition_json field to sstv_images
    # Stores full composition (zones, background) for re-editing/retransmission
    op.add_column(
        'sstv_images',
        sa.Column('composition_json', sa.Text(), nullable=True)
    )

    # Create recent_contacts table for Smart Reply
    op.create_table(
        'recent_contacts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('callsign', sa.String(20), nullable=False, unique=True),
        sa.Column('last_contact_utc', sa.DateTime(), nullable=False),
        sa.Column('frequency', sa.String(50), nullable=True),
        sa.Column('mode', sa.String(50), nullable=True),
        sa.Column('rst_sent', sa.String(10), nullable=True),
        sa.Column('rst_received', sa.String(10), nullable=True),
    )

    # Index for recent contacts query (DESC ordering for most recent first)
    op.create_index(
        'idx_recent_contacts_last_contact',
        'recent_contacts',
        ['last_contact_utc'],
        unique=False
    )

    # Create user_preferences table for working state
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False, default=1),  # Single user for now
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'key', name='uq_user_preferences_user_key'),
    )


def downgrade() -> None:
    """Remove Phase 1 fields and tables."""
    # Drop tables
    op.drop_table('user_preferences')
    op.drop_index('idx_recent_contacts_last_contact', table_name='recent_contacts')
    op.drop_table('recent_contacts')

    # Remove composition_json column
    op.drop_column('sstv_images', 'composition_json')

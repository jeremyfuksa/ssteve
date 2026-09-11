"""Add record provenance.

Revision ID: 2026091101
Revises: 2026011601
Create Date: 2026-09-11 15:00:00.000000

PRODUCT.md interaction requirement 12 (#69): every record says where it
was heard.

- sstv_images.source / receiver / heard_at -- provenance on the row.
  Existing rows stay NULL (unknown) rather than being guessed as "my
  station": nothing recorded where they came from, and a guess in the
  permissive direction is exactly what the requirement forbids.
- qsos.record_type -- qso | reception_report | remote_reception. Existing
  rows become "qso": they were logged as contacts, and no remote
  reception could have reached the table before SpyServer decodes had
  an API path.

One migration for both, as #61 and #69 asked: the file and sample
sources #61 adds are already in this vocabulary.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '2026091101'
down_revision = '2026011601'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add provenance columns."""
    with op.batch_alter_table('sstv_images') as batch:
        batch.add_column(sa.Column('source', sa.String(20), nullable=True))
        batch.add_column(sa.Column('receiver', sa.String(255), nullable=True))
        batch.add_column(sa.Column('heard_at', sa.String(20), nullable=True))

    with op.batch_alter_table('qsos') as batch:
        batch.add_column(
            sa.Column(
                'record_type',
                sa.String(20),
                nullable=False,
                server_default='qso',
            )
        )


def downgrade() -> None:
    """Remove provenance columns."""
    with op.batch_alter_table('qsos') as batch:
        batch.drop_column('record_type')

    with op.batch_alter_table('sstv_images') as batch:
        batch.drop_column('heard_at')
        batch.drop_column('receiver')
        batch.drop_column('source')

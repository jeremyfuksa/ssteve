"""add FSKID and RSV signal report fields

Revision ID: 2026011601
Revises: 2026011501
Create Date: 2026-01-16 00:00:00.000000

Adds fields for automatic callsign detection (FSKID) and signal report calculation (RSV):

FSKID Fields:
- fskid_detected: Boolean flag indicating FSKID was present
- fskid_confidence: Decoder confidence score (0.0-1.0)
- fskid_checksum_valid: Whether checksum passed validation

RSV Signal Report Fields:
- rx_snr_db: Signal-to-noise ratio in dB
- rx_peak_amplitude: Peak signal level (0.0-1.0)
- rx_noise_floor: Background noise level (0.0-1.0)
- rsv_readability: R component (1-5)
- rsv_signal: S component (1-9, S-meter equivalent)
- rsv_video: V component (1-5, video quality)
- rsv_report: Formatted RSV string (e.g., "595")
- decode_metrics_json: Full DecodeMetrics as JSON for analysis

These fields enable Smart Reply to auto-populate callsign and signal reports
based on measured decode quality instead of requiring manual entry.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2026011601'
down_revision = '2026011501'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add FSKID and RSV fields to sstv_images table."""

    # =================================================================
    # FSKID Fields (Automatic Callsign Detection)
    # =================================================================

    op.add_column(
        'sstv_images',
        sa.Column(
            'fskid_detected',
            sa.Boolean(),
            nullable=True,
            comment='Whether FSKID callsign data was detected in transmission'
        )
    )

    op.add_column(
        'sstv_images',
        sa.Column(
            'fskid_confidence',
            sa.Float(),
            nullable=True,
            comment='FSKID decoder confidence score (0.0-1.0)'
        )
    )

    op.add_column(
        'sstv_images',
        sa.Column(
            'fskid_checksum_valid',
            sa.Boolean(),
            nullable=True,
            comment='Whether FSKID checksum validation passed'
        )
    )

    # =================================================================
    # Signal Measurement Fields (for RSV calculation)
    # =================================================================

    op.add_column(
        'sstv_images',
        sa.Column(
            'rx_snr_db',
            sa.Float(),
            nullable=True,
            comment='Signal-to-noise ratio in dB'
        )
    )

    op.add_column(
        'sstv_images',
        sa.Column(
            'rx_peak_amplitude',
            sa.Float(),
            nullable=True,
            comment='Peak audio signal level (0.0-1.0 normalized)'
        )
    )

    op.add_column(
        'sstv_images',
        sa.Column(
            'rx_noise_floor',
            sa.Float(),
            nullable=True,
            comment='Background noise level (0.0-1.0 normalized)'
        )
    )

    # =================================================================
    # RSV Signal Report Fields (Readability, Signal, Video)
    # =================================================================

    op.add_column(
        'sstv_images',
        sa.Column(
            'rsv_readability',
            sa.Integer(),
            nullable=True,
            comment='RSV Readability component (1-5), typically 5 if decoded'
        )
    )

    op.add_column(
        'sstv_images',
        sa.Column(
            'rsv_signal',
            sa.Integer(),
            nullable=True,
            comment='RSV Signal strength component (1-9, S-meter equivalent)'
        )
    )

    op.add_column(
        'sstv_images',
        sa.Column(
            'rsv_video',
            sa.Integer(),
            nullable=True,
            comment='RSV Video quality component (1-5)'
        )
    )

    op.add_column(
        'sstv_images',
        sa.Column(
            'rsv_report',
            sa.String(3),
            nullable=True,
            comment='Formatted RSV report string (e.g., "595")'
        )
    )

    # =================================================================
    # Detailed Metrics Storage (JSON for future analysis)
    # =================================================================

    op.add_column(
        'sstv_images',
        sa.Column(
            'decode_metrics_json',
            sa.Text(),
            nullable=True,
            comment='Full DecodeMetrics as JSON (SNR, sync jitter, scanline quality, etc.)'
        )
    )

    # =================================================================
    # Indexes for Query Performance
    # =================================================================

    # Index for signal strength queries (finding strong/weak signals)
    op.create_index(
        'idx_images_rsv_signal',
        'sstv_images',
        ['rsv_signal'],
        unique=False
    )

    # Index for SNR-based sorting
    op.create_index(
        'idx_images_snr',
        'sstv_images',
        ['rx_snr_db'],
        unique=False
    )

    # Index for FSKID detection queries
    op.create_index(
        'idx_images_fskid_detected',
        'sstv_images',
        ['fskid_detected'],
        unique=False
    )


def downgrade() -> None:
    """Remove FSKID and RSV fields."""

    # Drop indexes first
    op.drop_index('idx_images_fskid_detected', table_name='sstv_images')
    op.drop_index('idx_images_snr', table_name='sstv_images')
    op.drop_index('idx_images_rsv_signal', table_name='sstv_images')

    # Drop columns
    op.drop_column('sstv_images', 'decode_metrics_json')
    op.drop_column('sstv_images', 'rsv_report')
    op.drop_column('sstv_images', 'rsv_video')
    op.drop_column('sstv_images', 'rsv_signal')
    op.drop_column('sstv_images', 'rsv_readability')
    op.drop_column('sstv_images', 'rx_noise_floor')
    op.drop_column('sstv_images', 'rx_peak_amplitude')
    op.drop_column('sstv_images', 'rx_snr_db')
    op.drop_column('sstv_images', 'fskid_checksum_valid')
    op.drop_column('sstv_images', 'fskid_confidence')
    op.drop_column('sstv_images', 'fskid_detected')

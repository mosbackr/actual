"""enrichment pipeline

Revision ID: d4e5f6a7b8c9
Revises: c3a7f1e2d4b5
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3a7f1e2d4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enrichmentstatus enum
    enrichment_enum = sa.Enum('none', 'running', 'complete', 'failed', name='enrichmentstatus')
    enrichment_enum.create(op.get_bind(), checkfirst=True)

    # Add enrichment columns to startups table
    op.add_column('startups', sa.Column('tagline', sa.String(length=500), nullable=True))
    op.add_column('startups', sa.Column('total_funding', sa.String(length=100), nullable=True))
    op.add_column('startups', sa.Column('employee_count', sa.String(length=50), nullable=True))
    op.add_column('startups', sa.Column('linkedin_url', sa.String(length=500), nullable=True))
    op.add_column('startups', sa.Column('twitter_url', sa.String(length=500), nullable=True))
    op.add_column('startups', sa.Column('crunchbase_url', sa.String(length=500), nullable=True))
    op.add_column('startups', sa.Column('competitors', sa.Text(), nullable=True))
    op.add_column('startups', sa.Column('tech_stack', sa.Text(), nullable=True))
    op.add_column('startups', sa.Column('hiring_signals', sa.Text(), nullable=True))
    op.add_column('startups', sa.Column('patents', sa.Text(), nullable=True))
    op.add_column('startups', sa.Column('key_metrics', sa.Text(), nullable=True))
    op.add_column('startups', sa.Column('enrichment_status',
        sa.Enum('none', 'running', 'complete', 'failed', name='enrichmentstatus', create_type=False),
        nullable=False, server_default='none'))
    op.add_column('startups', sa.Column('enrichment_error', sa.Text(), nullable=True))
    op.add_column('startups', sa.Column('enriched_at', sa.DateTime(timezone=True), nullable=True))

    # Create startup_founders table
    op.create_table('startup_founders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('startup_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('linkedin_url', sa.String(length=500), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['startup_id'], ['startups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create startup_funding_rounds table
    op.create_table('startup_funding_rounds',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('startup_id', sa.UUID(), nullable=False),
        sa.Column('round_name', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.String(length=50), nullable=True),
        sa.Column('date', sa.String(length=20), nullable=True),
        sa.Column('lead_investor', sa.String(length=200), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['startup_id'], ['startups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create startup_ai_reviews table
    op.create_table('startup_ai_reviews',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('startup_id', sa.UUID(), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('investment_thesis', sa.Text(), nullable=False),
        sa.Column('key_risks', sa.Text(), nullable=False),
        sa.Column('verdict', sa.Text(), nullable=False),
        sa.Column('dimension_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['startup_id'], ['startups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('startup_id')
    )

    # Seed default DD template and dimensions
    op.execute("""
        INSERT INTO due_diligence_templates (id, name, slug, description)
        VALUES (
            'a0000000-0000-0000-0000-000000000001',
            'Default',
            'default',
            'Standard VC due diligence template for evaluating startups across key dimensions'
        )
        ON CONFLICT (name) DO NOTHING;
    """)
    op.execute("""
        INSERT INTO template_dimensions (id, template_id, dimension_name, dimension_slug, weight, sort_order)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Market Opportunity', 'market-opportunity', 1.2, 0),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Team Strength', 'team-strength', 1.3, 1),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Product & Technology', 'product-technology', 1.1, 2),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Traction & Metrics', 'traction-metrics', 1.2, 3),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Business Model', 'business-model', 1.0, 4),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Competitive Moat', 'competitive-moat', 1.0, 5),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Financials & Unit Economics', 'financials-unit-economics', 0.9, 6),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Timing & Market Readiness', 'timing-market-readiness', 0.8, 7)
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table('startup_ai_reviews')
    op.drop_table('startup_funding_rounds')
    op.drop_table('startup_founders')

    op.drop_column('startups', 'enriched_at')
    op.drop_column('startups', 'enrichment_error')
    op.drop_column('startups', 'enrichment_status')
    op.drop_column('startups', 'key_metrics')
    op.drop_column('startups', 'patents')
    op.drop_column('startups', 'hiring_signals')
    op.drop_column('startups', 'tech_stack')
    op.drop_column('startups', 'competitors')
    op.drop_column('startups', 'crunchbase_url')
    op.drop_column('startups', 'twitter_url')
    op.drop_column('startups', 'linkedin_url')
    op.drop_column('startups', 'employee_count')
    op.drop_column('startups', 'total_funding')
    op.drop_column('startups', 'tagline')

    sa.Enum(name='enrichmentstatus').drop(op.get_bind(), checkfirst=True)

    # Note: seed data removal is intentionally omitted to avoid accidental data loss

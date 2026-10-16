"""Baseline: the structure as of October 2026, frozen.

A new database is made by this. A database made before migrations existed already has
this shape (db.init_db() brings it there and marks it 0001), so it is never run there.
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('alerts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_email', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('query', sa.String(), nullable=False),
    sa.Column('filters', sa.String(), nullable=False),
    sa.Column('lang', sa.String(), nullable=False),
    sa.Column('frequency', sa.String(), nullable=False),
    sa.Column('active', sa.Integer(), nullable=False),
    sa.Column('last_sent_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_alerts_user_email'), ['user_email'], unique=False)

    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('actor', sa.String(), nullable=False),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('entity', sa.String(), nullable=False),
    sa.Column('entity_id', sa.String(), nullable=False),
    sa.Column('field', sa.String(), nullable=False),
    sa.Column('old_value', sa.Text(), nullable=False),
    sa.Column('new_value', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('client_activity',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('actor', sa.String(), nullable=False),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('decision_id', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('client_activity', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_client_activity_actor'), ['actor'], unique=False)

    op.create_table('contracts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('number', sa.String(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('plan_code', sa.String(), nullable=False),
    sa.Column('seats', sa.Integer(), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=False),
    sa.Column('ends_on', sa.Date(), nullable=False),
    sa.Column('amount_ht', sa.Integer(), nullable=False),
    sa.Column('vat_rate', sa.Integer(), nullable=False),
    sa.Column('vat', sa.Integer(), nullable=False),
    sa.Column('amount_ttc', sa.Integer(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('file_key', sa.String(), nullable=False),
    sa.Column('file_name', sa.String(), nullable=False),
    sa.Column('subscription_id', sa.Integer(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('number')
    )
    with op.batch_alter_table('contracts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contracts_ends_on'), ['ends_on'], unique=False)
        batch_op.create_index(batch_op.f('ix_contracts_org_id'), ['org_id'], unique=False)

    op.create_table('decision_i18n',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('doc_id', sa.String(), nullable=False),
    sa.Column('lang', sa.String(), nullable=False),
    sa.Column('abstract', sa.Text(), nullable=False),
    sa.Column('abstract_of', sa.String(), nullable=False),
    sa.Column('keywords', sa.String(), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('search_text', sa.Text(), nullable=False),
    sa.Column('model', sa.String(), nullable=False),
    sa.Column('source_version', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('doc_id', 'lang', name='uq_decision_i18n')
    )
    with op.batch_alter_table('decision_i18n', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_decision_i18n_doc_id'), ['doc_id'], unique=False)

    op.create_table('decision_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('doc_id', sa.String(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('summary', sa.String(), nullable=False),
    sa.Column('actor', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('base_version', sa.Integer(), nullable=False),
    sa.Column('restore_of', sa.Integer(), nullable=True),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('file_data', sa.LargeBinary(), nullable=True),
    sa.Column('decided_by', sa.String(), nullable=False),
    sa.Column('decided_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('doc_id', 'version', name='uq_decision_version')
    )
    with op.batch_alter_table('decision_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_decision_versions_doc_id'), ['doc_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_decision_versions_status'), ['status'], unique=False)

    op.create_table('decisions',
    sa.Column('doc_id', sa.String(), nullable=False),
    sa.Column('source_file', sa.String(), nullable=False),
    sa.Column('fmt', sa.String(), nullable=False),
    sa.Column('read_method', sa.String(), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('level', sa.String(), nullable=False),
    sa.Column('court', sa.String(), nullable=False),
    sa.Column('decision_no', sa.String(), nullable=False),
    sa.Column('file_no', sa.String(), nullable=False),
    sa.Column('decision_date', sa.String(), nullable=False),
    sa.Column('city', sa.String(), nullable=False),
    sa.Column('year', sa.String(), nullable=False),
    sa.Column('sort_key', sa.String(), nullable=False),
    sa.Column('case_id', sa.String(), nullable=False),
    sa.Column('theme', sa.String(), nullable=False),
    sa.Column('theme_key', sa.String(), nullable=False),
    sa.Column('keywords', sa.String(), nullable=False),
    sa.Column('rule', sa.Text(), nullable=False),
    sa.Column('theme_source', sa.String(), nullable=False),
    sa.Column('abstract', sa.Text(), nullable=False),
    sa.Column('outcome', sa.String(), nullable=False),
    sa.Column('pii_removed', sa.Integer(), nullable=False),
    sa.Column('review', sa.String(), nullable=False),
    sa.Column('state', sa.String(), nullable=False),
    sa.Column('file_name', sa.String(), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('search_text', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('edited_at', sa.DateTime(), nullable=True),
    sa.Column('edited_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('doc_id')
    )
    with op.batch_alter_table('decisions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_decisions_case_id'), ['case_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_decisions_category'), ['category'], unique=False)
        batch_op.create_index(batch_op.f('ix_decisions_city'), ['city'], unique=False)
        batch_op.create_index(batch_op.f('ix_decisions_level'), ['level'], unique=False)
        batch_op.create_index(batch_op.f('ix_decisions_sort_key'), ['sort_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_decisions_state'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('ix_decisions_theme'), ['theme'], unique=False)
        batch_op.create_index(batch_op.f('ix_decisions_theme_key'), ['theme_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_decisions_theme_source'), ['theme_source'], unique=False)
        batch_op.create_index(batch_op.f('ix_decisions_year'), ['year'], unique=False)

    op.create_table('downloads',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ref', sa.String(), nullable=False),
    sa.Column('user_email', sa.String(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=True),
    sa.Column('doc_id', sa.String(), nullable=False),
    sa.Column('at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('ref')
    )
    with op.batch_alter_table('downloads', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_downloads_at'), ['at'], unique=False)
        batch_op.create_index(batch_op.f('ix_downloads_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_downloads_user_email'), ['user_email'], unique=False)

    op.create_table('email_outbox',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('to_addr', sa.String(), nullable=False),
    sa.Column('template', sa.String(), nullable=False),
    sa.Column('lang', sa.String(), nullable=False),
    sa.Column('subject', sa.String(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('error', sa.String(), nullable=False),
    sa.Column('dedupe_key', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedupe_key')
    )
    with op.batch_alter_table('email_outbox', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_outbox_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_outbox_to_addr'), ['to_addr'], unique=False)

    op.create_table('folder_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('folder_id', sa.Integer(), nullable=False),
    sa.Column('doc_id', sa.String(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('added_by', sa.String(), nullable=False),
    sa.Column('added_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('folder_id', 'doc_id', name='uq_folder_item')
    )
    with op.batch_alter_table('folder_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_folder_items_doc_id'), ['doc_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_folder_items_folder_id'), ['folder_id'], unique=False)

    op.create_table('folders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('owner', sa.String(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('shared', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('folders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_folders_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_folders_owner'), ['owner'], unique=False)

    op.create_table('import_jobs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('file_key', sa.String(), nullable=False),
    sa.Column('file_name', sa.String(), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('result', sa.Text(), nullable=False),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('import_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_import_jobs_status'), ['status'], unique=False)

    op.create_table('invitations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('token_hash', sa.String(), nullable=False),
    sa.Column('invited_by', sa.String(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('accepted_at', sa.DateTime(), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('invitations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invitations_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_invitations_org_id'), ['org_id'], unique=False)

    op.create_table('invoices',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('number', sa.String(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('subscription_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('amount_ht', sa.Integer(), nullable=False),
    sa.Column('vat_rate', sa.Integer(), nullable=False),
    sa.Column('vat', sa.Integer(), nullable=False),
    sa.Column('amount_ttc', sa.Integer(), nullable=False),
    sa.Column('issued_on', sa.Date(), nullable=False),
    sa.Column('due_on', sa.Date(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('number')
    )
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invoices_due_on'), ['due_on'], unique=False)
        batch_op.create_index(batch_op.f('ix_invoices_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_invoices_status'), ['status'], unique=False)

    op.create_table('leads',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('phone', sa.String(), nullable=False),
    sa.Column('company', sa.String(), nullable=False),
    sa.Column('city', sa.String(), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('language', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('assigned_to', sa.String(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_leads_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_leads_status'), ['status'], unique=False)

    op.create_table('links',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('parent_doc', sa.String(), nullable=False),
    sa.Column('child_doc', sa.String(), nullable=False),
    sa.Column('confidence', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('links', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_links_child_doc'), ['child_doc'], unique=False)
        batch_op.create_index(batch_op.f('ix_links_parent_doc'), ['parent_doc'], unique=False)

    op.create_table('organizations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('city', sa.String(), nullable=False),
    sa.Column('ice', sa.String(), nullable=False),
    sa.Column('address', sa.String(), nullable=False),
    sa.Column('phone', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('language', sa.String(), nullable=False),
    sa.Column('account_manager', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_organizations_name'), ['name'], unique=False)

    op.create_table('password_resets',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('password_resets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_password_resets_user_id'), ['user_id'], unique=False)

    op.create_table('payments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('invoice_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('method', sa.String(), nullable=False),
    sa.Column('reference', sa.String(), nullable=False),
    sa.Column('paid_on', sa.Date(), nullable=False),
    sa.Column('recorded_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payments_invoice_id'), ['invoice_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_payments_paid_on'), ['paid_on'], unique=False)

    op.create_table('plans',
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('name_ar', sa.String(), nullable=False),
    sa.Column('name_fr', sa.String(), nullable=False),
    sa.Column('blurb_ar', sa.String(), nullable=False),
    sa.Column('blurb_fr', sa.String(), nullable=False),
    sa.Column('price', sa.Integer(), nullable=False),
    sa.Column('period', sa.String(), nullable=False),
    sa.Column('seats', sa.Integer(), nullable=False),
    sa.Column('daily_downloads', sa.Integer(), nullable=False),
    sa.Column('vat_rate', sa.Integer(), nullable=False),
    sa.Column('public', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    op.create_table('rate_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('bucket', sa.String(length=32), nullable=False),
    sa.Column('key', sa.String(length=320), nullable=False),
    sa.Column('at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rate_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rate_events_at'), ['at'], unique=False)
        batch_op.create_index(batch_op.f('ix_rate_events_bucket'), ['bucket'], unique=False)
        batch_op.create_index(batch_op.f('ix_rate_events_key'), ['key'], unique=False)

    op.create_table('reading_time',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('actor', sa.String(), nullable=False),
    sa.Column('doc_id', sa.String(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('lang', sa.String(), nullable=False),
    sa.Column('seconds', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('actor', 'doc_id', 'day', 'lang', name='uq_reading_time')
    )
    with op.batch_alter_table('reading_time', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reading_time_actor'), ['actor'], unique=False)
        batch_op.create_index(batch_op.f('ix_reading_time_day'), ['day'], unique=False)
        batch_op.create_index(batch_op.f('ix_reading_time_doc_id'), ['doc_id'], unique=False)

    op.create_table('reports',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('doc_id', sa.String(), nullable=False),
    sa.Column('reporter', sa.String(), nullable=False),
    sa.Column('quote', sa.Text(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_by', sa.String(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reports_doc_id'), ['doc_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reports_status'), ['status'], unique=False)

    op.create_table('subjects',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('label_ar', sa.String(), nullable=False),
    sa.Column('label_fr', sa.String(), nullable=False),
    sa.Column('model', sa.String(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('subscriptions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('plan_code', sa.String(), nullable=False),
    sa.Column('seats', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=False),
    sa.Column('ends_on', sa.Date(), nullable=False),
    sa.Column('auto_renew', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('monthly_price', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscriptions_ends_on'), ['ends_on'], unique=False)
        batch_op.create_index(batch_op.f('ix_subscriptions_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_subscriptions_status'), ['status'], unique=False)

    op.create_table('ticket_messages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('author', sa.String(), nullable=False),
    sa.Column('staff', sa.Integer(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ticket_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ticket_messages_ticket_id'), ['ticket_id'], unique=False)

    op.create_table('tickets',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=True),
    sa.Column('user_email', sa.String(), nullable=False),
    sa.Column('subject', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('priority', sa.String(), nullable=False),
    sa.Column('assigned_to', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tickets_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_user_email'), ['user_email'], unique=False)

    op.create_table('transfers',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('contract_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('paid_on', sa.Date(), nullable=False),
    sa.Column('bank', sa.String(), nullable=False),
    sa.Column('bank_ref', sa.String(), nullable=False),
    sa.Column('proof_key', sa.String(), nullable=False),
    sa.Column('proof_name', sa.String(), nullable=False),
    sa.Column('invoice_id', sa.Integer(), nullable=True),
    sa.Column('recorded_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('transfers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transfers_contract_id'), ['contract_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_transfers_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_transfers_paid_on'), ['paid_on'], unique=False)

    op.create_table('translations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('doc_id', sa.String(), nullable=False),
    sa.Column('lang', sa.String(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('model', sa.String(), nullable=False),
    sa.Column('source_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('doc_id', 'lang', name='uq_translation')
    )
    with op.batch_alter_table('translations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_translations_doc_id'), ['doc_id'], unique=False)

    op.create_table('user_notes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('author', sa.String(), nullable=False),
    sa.Column('at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user_notes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_notes_email'), ['email'], unique=False)

    op.create_table('user_sessions',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('ip', sa.String(), nullable=False),
    sa.Column('device', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('revoked_why', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('phone', sa.String(), nullable=False),
    sa.Column('language', sa.String(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=True),
    sa.Column('mfa_secret', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_org_id'), ['org_id'], unique=False)

    op.create_table('worker_state',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', sa.String(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )


def downgrade() -> None:
    op.drop_table('worker_state')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_org_id'))
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_sessions_user_id'))

    op.drop_table('user_sessions')
    with op.batch_alter_table('user_notes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_notes_email'))

    op.drop_table('user_notes')
    with op.batch_alter_table('translations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_translations_doc_id'))

    op.drop_table('translations')
    with op.batch_alter_table('transfers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transfers_paid_on'))
        batch_op.drop_index(batch_op.f('ix_transfers_org_id'))
        batch_op.drop_index(batch_op.f('ix_transfers_contract_id'))

    op.drop_table('transfers')
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tickets_user_email'))
        batch_op.drop_index(batch_op.f('ix_tickets_status'))
        batch_op.drop_index(batch_op.f('ix_tickets_org_id'))

    op.drop_table('tickets')
    with op.batch_alter_table('ticket_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ticket_messages_ticket_id'))

    op.drop_table('ticket_messages')
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscriptions_status'))
        batch_op.drop_index(batch_op.f('ix_subscriptions_org_id'))
        batch_op.drop_index(batch_op.f('ix_subscriptions_ends_on'))

    op.drop_table('subscriptions')
    op.drop_table('subjects')
    with op.batch_alter_table('reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reports_status'))
        batch_op.drop_index(batch_op.f('ix_reports_doc_id'))

    op.drop_table('reports')
    with op.batch_alter_table('reading_time', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reading_time_doc_id'))
        batch_op.drop_index(batch_op.f('ix_reading_time_day'))
        batch_op.drop_index(batch_op.f('ix_reading_time_actor'))

    op.drop_table('reading_time')
    with op.batch_alter_table('rate_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rate_events_key'))
        batch_op.drop_index(batch_op.f('ix_rate_events_bucket'))
        batch_op.drop_index(batch_op.f('ix_rate_events_at'))

    op.drop_table('rate_events')
    op.drop_table('plans')
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payments_paid_on'))
        batch_op.drop_index(batch_op.f('ix_payments_invoice_id'))

    op.drop_table('payments')
    with op.batch_alter_table('password_resets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_password_resets_user_id'))

    op.drop_table('password_resets')
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_organizations_name'))

    op.drop_table('organizations')
    with op.batch_alter_table('links', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_links_parent_doc'))
        batch_op.drop_index(batch_op.f('ix_links_child_doc'))

    op.drop_table('links')
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_leads_status'))
        batch_op.drop_index(batch_op.f('ix_leads_email'))

    op.drop_table('leads')
    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invoices_status'))
        batch_op.drop_index(batch_op.f('ix_invoices_org_id'))
        batch_op.drop_index(batch_op.f('ix_invoices_due_on'))

    op.drop_table('invoices')
    with op.batch_alter_table('invitations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invitations_org_id'))
        batch_op.drop_index(batch_op.f('ix_invitations_email'))

    op.drop_table('invitations')
    with op.batch_alter_table('import_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_import_jobs_status'))

    op.drop_table('import_jobs')
    with op.batch_alter_table('folders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_folders_owner'))
        batch_op.drop_index(batch_op.f('ix_folders_org_id'))

    op.drop_table('folders')
    with op.batch_alter_table('folder_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_folder_items_folder_id'))
        batch_op.drop_index(batch_op.f('ix_folder_items_doc_id'))

    op.drop_table('folder_items')
    with op.batch_alter_table('email_outbox', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_outbox_to_addr'))
        batch_op.drop_index(batch_op.f('ix_email_outbox_status'))

    op.drop_table('email_outbox')
    with op.batch_alter_table('downloads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_downloads_user_email'))
        batch_op.drop_index(batch_op.f('ix_downloads_org_id'))
        batch_op.drop_index(batch_op.f('ix_downloads_at'))

    op.drop_table('downloads')
    with op.batch_alter_table('decisions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_decisions_year'))
        batch_op.drop_index(batch_op.f('ix_decisions_theme_source'))
        batch_op.drop_index(batch_op.f('ix_decisions_theme_key'))
        batch_op.drop_index(batch_op.f('ix_decisions_theme'))
        batch_op.drop_index(batch_op.f('ix_decisions_state'))
        batch_op.drop_index(batch_op.f('ix_decisions_sort_key'))
        batch_op.drop_index(batch_op.f('ix_decisions_level'))
        batch_op.drop_index(batch_op.f('ix_decisions_city'))
        batch_op.drop_index(batch_op.f('ix_decisions_category'))
        batch_op.drop_index(batch_op.f('ix_decisions_case_id'))

    op.drop_table('decisions')
    with op.batch_alter_table('decision_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_decision_versions_status'))
        batch_op.drop_index(batch_op.f('ix_decision_versions_doc_id'))

    op.drop_table('decision_versions')
    with op.batch_alter_table('decision_i18n', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_decision_i18n_doc_id'))

    op.drop_table('decision_i18n')
    with op.batch_alter_table('contracts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contracts_org_id'))
        batch_op.drop_index(batch_op.f('ix_contracts_ends_on'))

    op.drop_table('contracts')
    with op.batch_alter_table('client_activity', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_client_activity_actor'))

    op.drop_table('client_activity')
    op.drop_table('audit_log')
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_alerts_user_email'))

    op.drop_table('alerts')

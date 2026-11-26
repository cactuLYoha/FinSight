"""Add shared expense categories and preserve existing transaction labels."""
from alembic import op
import sqlalchemy as sa


revision = 'b72c41d8e903'
down_revision = 'a18e2c7d9b04'
branch_labels = None
depends_on = None

# Keep this migration independent of future changes to application models.
DEFAULT_CATEGORY_NAMES = (
    'Продукти',
    'Кафе та ресторани',
    'Житло та комунальні послуги',
    'Побут і товари для дому',
    'Транспорт',
    'Здоров’я',
    'Особистий догляд',
    'Одяг та взуття',
    'Зв’язок та інтернет',
    'Підписки та цифрові сервіси',
    'Освіта',
    'Дозвілля та спорт',
    'Подорожі',
    'Сім’я та діти',
    'Домашні тварини',
    'Подарунки та благодійність',
    'Податки та банківські комісії',
    'Інше',
)

CATEGORY_FK = 'fk_transaction_category_id_category'
EXPENSE_CATEGORY_CHECK = 'check_transaction_expense_category_required'


def _tables():
    categories = sa.table(
        'category',
        sa.column('id', sa.Integer()),
        sa.column('name', sa.String(100)),
    )
    transactions = sa.table(
        'transaction',
        sa.column('category', sa.String(100)),
        sa.column('category_id', sa.Integer()),
    )
    return categories, transactions


def upgrade():
    op.create_table(
        'category',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.UniqueConstraint('name'),
    )
    connection = op.get_bind()
    categories, transactions = _tables()
    legacy_names = connection.execute(
        sa.select(transactions.c.category).distinct()
    ).scalars().all()
    extra_names = sorted({
        name for name in legacy_names
        if name and name.strip() and name not in DEFAULT_CATEGORY_NAMES
    })
    op.bulk_insert(
        categories,
        [{'name': name} for name in (*DEFAULT_CATEGORY_NAMES, *extra_names)],
    )
    op.add_column('transaction', sa.Column('category_id', sa.Integer(), nullable=True))
    category_ids = dict(connection.execute(
        sa.select(categories.c.name, categories.c.id)
    ).all())
    for legacy_name in legacy_names:
        name = legacy_name if legacy_name and legacy_name.strip() else 'Інше'
        connection.execute(
            transactions.update()
            .where(transactions.c.category == legacy_name)
            .values(category_id=category_ids[name])
        )

    missing_categories = connection.scalar(
        sa.select(sa.func.count())
        .select_from(transactions)
        .where(transactions.c.category_id.is_(None))
    )
    if missing_categories:
        raise RuntimeError('Some existing transactions could not be assigned a category.')

    with op.batch_alter_table('transaction') as batch_op:
        batch_op.create_foreign_key(
            CATEGORY_FK, 'category', ['category_id'], ['id'], ondelete='RESTRICT'
        )
        batch_op.create_index('ix_transaction_category_id', ['category_id'])
        batch_op.create_check_constraint(
            EXPENSE_CATEGORY_CHECK,
            "transaction_type != 'expense' OR category_id IS NOT NULL",
        )
        batch_op.drop_column('category')


def downgrade():
    connection = op.get_bind()
    categories, transactions = _tables()
    op.add_column('transaction', sa.Column('category', sa.String(100), nullable=True))
    category_name = (
        sa.select(categories.c.name)
        .where(categories.c.id == transactions.c.category_id)
        .scalar_subquery()
    )
    connection.execute(
        transactions.update().values(category=sa.func.coalesce(category_name, 'Інше'))
    )
    with op.batch_alter_table('transaction') as batch_op:
        batch_op.drop_constraint(EXPENSE_CATEGORY_CHECK, type_='check')
        batch_op.drop_constraint(CATEGORY_FK, type_='foreignkey')
        batch_op.drop_index('ix_transaction_category_id')
        batch_op.drop_column('category_id')
        batch_op.alter_column('category', existing_type=sa.String(100), nullable=False)
    op.drop_table('category')

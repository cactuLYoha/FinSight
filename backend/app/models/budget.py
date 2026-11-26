from dataclasses import dataclass
from decimal import Decimal

from app.services.analytics_service import get_monthly_totals


@dataclass(frozen=True)
class Budget:
    """A snapshot of a user's monthly income, calculated in one currency."""

    user_id: int
    year: int
    month: int
    currency: str
    income_total: Decimal

    @classmethod
    def for_month(
        cls, user_id: int, year: int, month: int, currency: str
    ) -> 'Budget':
        """Calculate income recorded in the requested UTC calendar month.

        Invalid arguments raise ValueError. An empty period returns
        Decimal('0.00'); every call calculates a new snapshot.
        """
        totals = get_monthly_totals(user_id, year, month, currency)
        return cls(
            user_id=totals.user_id, year=totals.year, month=totals.month,
            currency=totals.currency, income_total=totals.income_total,
        )

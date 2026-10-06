from __future__ import annotations

from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from investment_gini.models import Instrument, Universe, UniverseMembership


class UniverseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def members_as_of(self, universe_name: str, as_of: date) -> list[Instrument]:
        statement = (
            select(Instrument).distinct()
            .join(UniverseMembership, UniverseMembership.instrument_id == Instrument.id)
            .join(Universe, Universe.id == UniverseMembership.universe_id)
            .where(
                Universe.name == universe_name,
                UniverseMembership.effective_from <= as_of,
                or_(
                    UniverseMembership.effective_to.is_(None),
                    UniverseMembership.effective_to >= as_of,
                ),
            )
            .order_by(Instrument.company_name)
        )
        return list(self._session.scalars(statement).all())

    def has_overlapping_membership(
        self,
        universe_id: int,
        instrument_id: int,
        effective_from: date,
        effective_to: date | None,
    ) -> bool:
        new_end = effective_to or date.max
        statement = select(UniverseMembership.id).where(
            UniverseMembership.universe_id == universe_id,
            UniverseMembership.instrument_id == instrument_id,
            UniverseMembership.effective_from <= new_end,
            or_(
                UniverseMembership.effective_to.is_(None),
                and_(UniverseMembership.effective_to >= effective_from),
            ),
        )
        return self._session.scalar(statement.limit(1)) is not None
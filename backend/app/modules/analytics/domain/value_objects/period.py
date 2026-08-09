from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.shared.presentation.errors import DomainError


@dataclass(frozen=True, slots=True)
class AnalyticsPeriod:
    start: date
    end: date

    @classmethod
    def parse(cls, start: str | None, end: str | None) -> "AnalyticsPeriod":
        today = datetime.now(UTC).date()
        try:
            parsed_end = date.fromisoformat(end) if end else today
            parsed_start = date.fromisoformat(start) if start else parsed_end - timedelta(days=29)
        except ValueError as exc:
            raise DomainError("ANALYTICS_INVALID_PERIOD", "Período analítico inválido. Use datas ISO 8601.", 422) from exc
        if parsed_start > parsed_end:
            raise DomainError("ANALYTICS_INVALID_PERIOD", "A data inicial não pode ser posterior à data final.", 422)
        if (parsed_end - parsed_start).days > 730:
            raise DomainError("ANALYTICS_PERIOD_TOO_LARGE", "O período analítico não pode exceder 731 dias.", 422)
        return cls(parsed_start, parsed_end)

    @property
    def start_text(self) -> str:
        return self.start.isoformat()

    @property
    def end_text(self) -> str:
        return self.end.isoformat()

    @property
    def start_timestamp(self) -> str:
        return f"{self.start.isoformat()}T00:00:00"

    @property
    def end_exclusive_timestamp(self) -> str:
        return f"{(self.end + timedelta(days=1)).isoformat()}T00:00:00"

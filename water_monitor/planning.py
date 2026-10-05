"""Validation for civilian observation labels and schedules."""
import math
from datetime import datetime, timezone


class InvalidInput(ValueError):
    pass


def text(value, field, maximum, required=True):
    if not isinstance(value, str):
        raise InvalidInput(f'{field} must be text')
    value = value.strip()
    if len(value) > maximum or (required and not value):
        raise InvalidInput(f'{field} must contain {1 if required else 0}–{maximum} characters')
    return value


def coordinate(value, field, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum or not math.isfinite(value):
        raise InvalidInput(f'{field} must be a finite number between {minimum} and {maximum}')
    return float(value)


def identifier(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 2**63 - 1:
        raise InvalidInput(f'{field} must be a positive integer')
    return value


def scheduled_time(value):
    if not isinstance(value, str) or len(value) > 40:
        raise InvalidInput('scheduled_for must be an ISO timestamp with a timezone')
    try:
        date = datetime.fromisoformat(value)
        if date.tzinfo is None:
            raise ValueError('Missing timezone')
        return date.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as error:
        raise InvalidInput('scheduled_for must be an ISO timestamp with a timezone') from error

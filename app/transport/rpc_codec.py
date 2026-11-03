"""Lossless JSON wire codec for datetime and Decimal across mock HTTP calls."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

_TAG = '__lab4_mock_type__'


def to_wire(value):
    if isinstance(value, datetime):
        return {_TAG: 'datetime', 'value': value.isoformat()}
    if isinstance(value, Decimal):
        return {_TAG: 'decimal', 'value': str(value)}
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_wire(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_wire(v) for v in value]
    if value is None or isinstance(value, (str, bool, float, int)):
        return value
    raise TypeError(f'Unsupported RPC value: {type(value).__name__}')


def from_wire(value):
    if isinstance(value, list):
        return [from_wire(v) for v in value]
    if isinstance(value, dict):
        if set(value) == {_TAG, 'value'}:
            if value[_TAG] == 'datetime':
                parsed = datetime.fromisoformat(value['value'])
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError('RPC datetime must include time zone')
                return parsed
            if value[_TAG] == 'decimal':
                return Decimal(value['value'])
            raise ValueError('Unknown RPC type tag')
        return {k: from_wire(v) for k, v in value.items()}
    return value

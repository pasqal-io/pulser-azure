from __future__ import annotations

from unittest.mock import MagicMock

from tests.conftest import (
    _DEFAULT_QPU_TARGET,
    _DEFAULT_QPU_DEVICE_TYPE_NAME,
    _make_device_spec,
)


def test_qpu_device_is_returned_when_name_is_in_map(connection):
    """A device whose name is in _QPU_DEVICE_NAME_TARGET_NAME_MAP is returned."""
    connection._get_device_specs = MagicMock(
        return_value=[_make_device_spec(_DEFAULT_QPU_DEVICE_TYPE_NAME)]
    )

    devices = connection.fetch_available_devices()

    assert _DEFAULT_QPU_TARGET in devices
    assert devices[_DEFAULT_QPU_TARGET].name == _DEFAULT_QPU_DEVICE_TYPE_NAME


def test_no_devices_when_specs_empty(connection):
    """No devices returned when _get_device_specs returns an empty list."""
    connection._get_device_specs = MagicMock(return_value=[])

    devices = connection.fetch_available_devices()

    assert devices == {}


def test_device_name_not_in_map_is_excluded(connection):
    """A device whose name is NOT in _QPU_DEVICE_NAME_TARGET_NAME_MAP is excluded."""
    connection._get_device_specs = MagicMock(
        return_value=[_make_device_spec("UNKNOWN_DEVICE")]
    )

    devices = connection.fetch_available_devices()

    assert devices == {}


def test_multiple_specs_only_mapped_ones_returned(connection):
    """Only devices whose names are in the map are returned."""
    connection._get_device_specs = MagicMock(
        return_value=[
            _make_device_spec(_DEFAULT_QPU_DEVICE_TYPE_NAME),
            _make_device_spec("OTHER_DEVICE"),
        ]
    )

    devices = connection.fetch_available_devices()

    assert len(devices) == 1
    assert _DEFAULT_QPU_TARGET in devices

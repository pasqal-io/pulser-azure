from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pulser import Register, Sequence
from pulser.devices import AnalogDevice
from pulser.pulse import Pulse

from pulser_azure.connection import AzureConnection


@pytest.fixture
def sequence() -> Sequence:
    register = Register.square(2, spacing=5, prefix="q").with_automatic_layout(
        AnalogDevice
    )
    seq = Sequence(register, AnalogDevice)
    seq.declare_channel("rydberg", "rydberg_global")
    seq.add(Pulse.ConstantPulse(100, 1.0, 0.0, 0.0), "rydberg")
    return seq


@pytest.fixture
def connection() -> AzureConnection:
    conn = AzureConnection.__new__(AzureConnection)
    conn._workspace = MagicMock()
    conn._target_name_device_map = {}
    conn._target_name_target_map = {}
    conn._device_name_target_map = {}
    return conn

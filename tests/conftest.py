from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from azure.quantum.target.pasqal import PasqalTarget
from pulser import Register, Sequence
from pulser.devices import AnalogDevice
from pulser.pulse import Pulse

from pulser_azure.connection import AzureConnection, _TARGETS


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


@pytest.fixture
def fake_pasqal_targets():
    targets = {}
    for target in _TARGETS:
        m = MagicMock()
        m.name = target.enum_value
        m.provider_id = "pasqal"
        m.submit.return_value = MagicMock(id=f"job-{target.enum_value}")
        targets[target.enum_value] = m
    return targets


@pytest.fixture
def wired_connection(connection, fake_pasqal_targets):
    connection._target_name_target_map = dict(fake_pasqal_targets)
    connection._device_name_target_map = {"AnalogDevice": PasqalTarget.QPU_FRESNEL}
    connection._workspace.list_session_jobs.return_value = []
    connection.update_sequence_device = MagicMock(side_effect=lambda s: s)
    connection._get_job_ids = MagicMock(
        side_effect=lambda batch_id: [f"job-{target.enum_value}" for target in _TARGETS]
    )
    return connection

from __future__ import annotations

import json
from unittest.mock import MagicMock

from azure.quantum.target.pasqal import PasqalTarget
import pytest
from pulser import Register, Sequence
from pulser.devices import AnalogDevice, Device
from pulser.pulse import Pulse

from pulser_azure.connection import AzureConnection

# The QPU target name used by default for AnalogDevice sequences
# (AnalogDevice.name is not in the map, but the test sequence uses a device
# whose name *is* mapped).  We use FRESNEL_CAN1 as the canonical QPU target.
_DEFAULT_QPU_TARGET = PasqalTarget.QPU_FRESNEL_CAN1.value
_DEFAULT_QPU_DEVICE_TYPE_NAME = "FRESNEL_CAN1"
_EMU_MPS_TARGET = PasqalTarget.SIM_EMU_MPS.value


@pytest.fixture
def sequence() -> Sequence:
    specs = json.loads(AnalogDevice.to_abstract_repr())
    specs["name"] = _DEFAULT_QPU_DEVICE_TYPE_NAME

    device = Device.from_abstract_repr(json.dumps(specs))

    register = Register.square(2, spacing=5, prefix="q").with_automatic_layout(device)
    seq = Sequence(register, device)
    seq.declare_channel("rydberg", "rydberg_global")
    seq.add(Pulse.ConstantPulse(100, 1.0, 0.0, 0.0), "rydberg")
    return seq


def _make_device_spec(name: str) -> dict:
    spec = json.loads(AnalogDevice.to_abstract_repr())
    spec["name"] = name
    return {"specs": json.dumps(spec)}


@pytest.fixture
def connection() -> AzureConnection:
    conn = AzureConnection.__new__(AzureConnection)
    conn._workspace = MagicMock()
    return conn


@pytest.fixture
def fake_pasqal_targets():
    """Create mock target objects for each known target name."""
    targets = {}
    for target in PasqalTarget:
        m = MagicMock()
        m.name = target.value
        m.provider_id = "pasqal"
        m.submit.return_value = MagicMock(id=f"job-{target.value}")
        targets[target.value] = m
    return targets


@pytest.fixture
def wired_connection(connection, fake_pasqal_targets):
    """Connection whose workspace.get_targets returns the right mock."""

    def _get_targets(name, provider_id=None):
        return fake_pasqal_targets.get(name)

    connection._workspace.get_targets.side_effect = _get_targets
    connection._workspace.list_session_jobs.return_value = []
    connection._get_device_specs = MagicMock(
        return_value=[_make_device_spec(_DEFAULT_QPU_DEVICE_TYPE_NAME)]
    )
    connection._get_job_ids = MagicMock(
        side_effect=lambda batch_id: [f"job-{target.value}" for target in PasqalTarget]
    )
    return connection

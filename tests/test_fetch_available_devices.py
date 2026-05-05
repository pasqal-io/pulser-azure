from __future__ import annotations

import json
from unittest.mock import MagicMock

from azure.quantum.target.pasqal import PasqalTarget
from pulser.devices import AnalogDevice


def _make_device_spec(name: str) -> dict:
    spec = json.loads(AnalogDevice.to_abstract_repr())
    spec["name"] = name
    return {"specs": json.dumps(spec)}


def test_qpu_target_and_device_get_paired(connection):
    fresnel_target = MagicMock()
    fresnel_target.name = PasqalTarget.QPU_FRESNEL.value

    connection._workspace.get_targets.return_value = [fresnel_target]
    connection._get_device_specs = MagicMock(
        return_value=[_make_device_spec("FRESNEL")]
    )

    devices = connection.fetch_available_devices()

    assert PasqalTarget.QPU_FRESNEL in devices
    assert devices[PasqalTarget.QPU_FRESNEL].name == "FRESNEL"
    assert connection._device_name_target_map == {"FRESNEL": PasqalTarget.QPU_FRESNEL}
    assert (
        connection._target_name_target_map[PasqalTarget.QPU_FRESNEL] is fresnel_target
    )


def test_emulator_targets_have_no_device(connection):
    sim_target = MagicMock()
    sim_target.name = "pasqal.sim.emu-mps"

    connection._workspace.get_targets.return_value = [sim_target]
    connection._get_device_specs = MagicMock(return_value=[])

    devices = connection.fetch_available_devices()

    assert devices == {}
    assert connection._target_name_target_map["pasqal.sim.emu-mps"] is sim_target


def test_device_name_must_match_target_suffix(connection):
    fresnel_target = MagicMock()
    fresnel_target.name = PasqalTarget.QPU_FRESNEL.value

    connection._workspace.get_targets.return_value = [fresnel_target]
    connection._get_device_specs = MagicMock(
        return_value=[_make_device_spec("UNKNOWN_DEVICE")]
    )

    devices = connection.fetch_available_devices()

    assert devices == {}


def test_result_is_cached(connection):
    fresnel_target = MagicMock()
    fresnel_target.name = PasqalTarget.QPU_FRESNEL.value
    connection._workspace.get_targets.return_value = [fresnel_target]
    connection._get_device_specs = MagicMock(
        return_value=[_make_device_spec("FRESNEL")]
    )

    connection.fetch_available_devices()
    connection.fetch_available_devices()

    assert connection._get_device_specs.call_count == 1

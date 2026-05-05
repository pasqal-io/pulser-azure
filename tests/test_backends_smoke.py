from __future__ import annotations

from unittest.mock import patch

import pytest
from azure.quantum.target.pasqal import PasqalTarget
from pulser import QPUBackend

from pulser_azure import RemoteEmuMPSBackend


def test_emulator_backend_submits_to_emulator_target(
    sequence, wired_connection, fake_pasqal_targets
):
    backend = RemoteEmuMPSBackend(sequence=sequence, connection=wired_connection)

    with patch("pulser_azure.connection.Session") as session_cls:
        session_cls.return_value.id = "session-1"
        backend.run(job_params=[{"runs": 5}], wait=False)

    fake_pasqal_targets["pasqal.sim.emu-mps"].submit.assert_called_once()
    fake_pasqal_targets[PasqalTarget.QPU_FRESNEL].submit.assert_not_called()


def test_qpu_backend_submits_to_target_matching_sequence_device(
    sequence, wired_connection, fake_pasqal_targets
):
    backend = QPUBackend(sequence=sequence, connection=wired_connection)

    with patch("pulser_azure.connection.Session") as session_cls:
        session_cls.return_value.id = "session-1"
        backend.run(job_params=[{"runs": 5}], wait=False)

    fake_pasqal_targets[PasqalTarget.QPU_FRESNEL].submit.assert_called_once()
    fake_pasqal_targets["pasqal.sim.emu-mps"].submit.assert_not_called()


def test_unknown_workspace_target_raises(sequence, wired_connection):
    wired_connection._target_name_target_map.pop(PasqalTarget.QPU_FRESNEL)

    backend = QPUBackend(sequence=sequence, connection=wired_connection)

    with pytest.raises(RuntimeError, match="isn't available on your workspace"):
        backend.run(job_params=[{"runs": 5}], wait=False)

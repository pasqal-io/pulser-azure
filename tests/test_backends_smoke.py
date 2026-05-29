from __future__ import annotations

from unittest.mock import patch

import pytest
from pulser import QPUBackend

from pulser_azure import EmuMPSBackend
from tests.conftest import _DEFAULT_QPU_TARGET, _EMU_MPS_TARGET


def test_emulator_backend_submits_to_emulator_target(
    sequence, wired_connection, fake_pasqal_targets
):
    backend = EmuMPSBackend(sequence=sequence, connection=wired_connection)

    with patch("pulser_azure.connection.Session") as session_cls:
        session_cls.return_value.id = "session-1"
        backend.run(job_params=[{"runs": 5}], wait=False)

    fake_pasqal_targets[_EMU_MPS_TARGET].submit.assert_called_once()
    fake_pasqal_targets[_DEFAULT_QPU_TARGET].submit.assert_not_called()


def test_qpu_backend_submits_to_target_matching_sequence_device(
    sequence, wired_connection, fake_pasqal_targets
):
    backend = QPUBackend(sequence=sequence, connection=wired_connection)

    with patch("pulser_azure.connection.Session") as session_cls:
        session_cls.return_value.id = "session-1"
        backend.run(job_params=[{"runs": 5}], wait=False)

    fake_pasqal_targets[_DEFAULT_QPU_TARGET].submit.assert_called_once()
    fake_pasqal_targets[_EMU_MPS_TARGET].submit.assert_not_called()


def test_unknown_workspace_target_raises(sequence, wired_connection):
    # Make get_targets return None for the QPU target
    original_side_effect = wired_connection._workspace.get_targets.side_effect

    def _get_targets_no_qpu(name, provider_id=None):
        if name == _DEFAULT_QPU_TARGET:
            return None
        return original_side_effect(name, provider_id=provider_id)

    wired_connection._workspace.get_targets.side_effect = _get_targets_no_qpu

    backend = QPUBackend(sequence=sequence, connection=wired_connection)

    with pytest.raises(RuntimeError, match="isn't available on your workspace"):
        backend.run(job_params=[{"runs": 5}], wait=False)

# Copyright 2026 Pasqal Cloud Services development team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from typing import Any

from azure.quantum.target.pasqal import PasqalTarget
from pulser import Sequence
from pulser.backend import BitStrings, EmulationConfig
from pulser.backend.remote import RemoteBackend, RemoteConnection


class BaseRemoteEmulatorBackend(RemoteBackend):
    """Base class for Pasqal cloud emulator backends exposed via Azure.

    Subclasses must set:
        - `target_name`:     the ``PasqalTarget`` the backend should route to.
        - `_default_config`: the ``EmulationConfig`` used when the caller does
                             not explicitly pass ``config=...``.
    """

    target_name: PasqalTarget
    _default_config: EmulationConfig

    def __init__(
        self,
        sequence: Sequence,
        connection: RemoteConnection,
        mimic_qpu: bool = False,
        *,
        config: EmulationConfig | None = None,
    ) -> None:
        super().__init__(
            sequence,
            connection,
            mimic_qpu,
            config=config if config is not None else self._default_config,
        )

    def _submit_kwargs(self) -> dict[str, Any]:
        """Keyword arguments given to any call to RemoteConnection.submit()."""
        return {
            **super()._submit_kwargs(),
            "emulation_config": self._config,
            "target_name": self.target_name,
        }


class RemoteEmuSVBackend(BaseRemoteEmulatorBackend):
    target_name = "pasqal.sim.emu-sv"
    _default_config = EmulationConfig(observables=[BitStrings(evaluation_times=[1.0])])


class RemoteEmuMPSBackend(BaseRemoteEmulatorBackend):
    target_name = "pasqal.sim.emu-mps"
    _default_config = EmulationConfig(observables=[BitStrings(evaluation_times=[1.0])])


class RemoteEmuFreeBackend(BaseRemoteEmulatorBackend):
    target_name = "pasqal.sim.emu-free"
    _default_config = EmulationConfig(observables=[BitStrings()])

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

from dataclasses import dataclass
import json
import logging
import os
import typing
from typing import Any, Iterable, Mapping, cast

from pulser.backend import EmulationConfig
import urllib3
from azure.identity import DefaultAzureCredential
from azure.quantum import JobStatus as AzureJobStatus
from azure.quantum import SessionStatus
from azure.quantum.job import Job
from azure.quantum.job.session import Session
from azure.quantum.target import Target
from azure.quantum.target.pasqal import Pasqal, PasqalTarget
from azure.quantum.workspace import Workspace
from pulser import Sequence
from pulser.backend.remote import (
    BatchStatus,
    JobParams,
    JobStatus,
    RemoteConnection,
    RemoteResults,
    RemoteResultsError,
)
from pulser.backend.results import Results
from pulser.devices import Device
from pulser.json.utils import make_json_compatible
from pulser.result import SampledResult

_UNSET: Any = object()

_PASQAL_PROVIDER_ID = "pasqal"
_PASQAL_CLOUD_BASE_URL = os.getenv(
    "PASQAL_CLOUD_BASE_URL", "https://apis.pasqal.cloud/core-fast"
)

logger = logging.getLogger(__name__)

_AZURE_JOB_STATUS_MAP: dict[AzureJobStatus, JobStatus] = {
    AzureJobStatus.QUEUED: JobStatus.PENDING,
    AzureJobStatus.WAITING: JobStatus.PENDING,
    AzureJobStatus.EXECUTING: JobStatus.RUNNING,
    AzureJobStatus.SUCCEEDED: JobStatus.DONE,
    AzureJobStatus.COMPLETED: JobStatus.DONE,
    AzureJobStatus.FINISHING: JobStatus.RUNNING,
    AzureJobStatus.FAILED: JobStatus.ERROR,
    AzureJobStatus.CANCELLED: JobStatus.CANCELED,
    AzureJobStatus.CANCELLING: JobStatus.CANCELED,
    AzureJobStatus.CANCELLATION_REQUESTED: JobStatus.CANCELED,
}

_AZURE_SESSION_STATUS_MAP: dict[SessionStatus, BatchStatus] = {
    SessionStatus.WAITING: BatchStatus.PENDING,
    SessionStatus.EXECUTING: BatchStatus.RUNNING,
    SessionStatus.SUCCEEDED: BatchStatus.DONE,
    SessionStatus.FAILED: BatchStatus.ERROR,
    SessionStatus.FAILURE_S_: BatchStatus.ERROR,
    SessionStatus.TIMED_OUT: BatchStatus.TIMED_OUT,
}


@dataclass(frozen=True)
class _PasqalTarget:
    enum_name: str
    enum_value: str


_TARGETS = set(
    [_PasqalTarget(enum_name=pt.name, enum_value=pt.value) for pt in PasqalTarget]
    + [
        _PasqalTarget(enum_name="SIM_EMU_SV", enum_value="pasqal.sim.emu-sv"),
        _PasqalTarget(enum_name="SIM_EMU_MPS", enum_value="pasqal.sim.emu-mps"),
        _PasqalTarget(enum_name="SIM_EMU_FREE", enum_value="pasqal.sim.emu-free"),
        _PasqalTarget(
            enum_name="QPU_FRESNEL_CAN1", enum_value="pasqal.qpu.fresnel-can1"
        ),
    ]
)


class AzureConnection(RemoteConnection):
    """Azure Quantum connection bridge.

    :param resource_id: option resource ID of the Azure workspace, if the provided `resource_id` is None, the value is loaded from the `PULSER_AZURE_RESOURCE_ID` environment variable
    """

    def __init__(self, resource_id: str | None = None):
        credential = DefaultAzureCredential(
            exclude_interactive_browser_credential=False
        )
        self._workspace = Workspace(
            resource_id=resource_id or os.getenv("PULSER_AZURE_RESOURCE_ID"),
            credential=credential,
        )
        self._target_name_device_map: dict[str, Device] = {}
        self._target_name_target_map: dict[str, Pasqal] = {}
        self._device_name_target_map: dict[str, str] = {}

    def submit(
        self,
        sequence: Sequence,
        wait: bool = False,
        open: bool = _UNSET,
        batch_id: str | None = None,
        emulation_config: EmulationConfig | None = None,
        target_name: str | None = None,
        **kwargs: Any,
    ) -> RemoteResults:
        """Submit a job for execution."""
        open_explicit = open is not _UNSET
        open = True if open is _UNSET else open

        if target_name is None:
            target_name = self._device_name_target_map[sequence.device.name]

        target = self._target_name_target_map.get(target_name)
        if target is None:
            raise RuntimeError(
                f"The target {target_name} isn't available on your workspace"
            )

        job_params = make_json_compatible(kwargs.get("job_params", []))

        # Context manager use case (eg: with backend.open_batch()), even
        # if connection had a session, create a new one as we're supposed to
        # be in another context now.
        if open_explicit is True and open:
            batch_id = self._setup_session(target)

            return RemoteResults(batch_id=batch_id, connection=self)

        # Present when running backend.run() inside context manager
        if batch_id:
            job_ids = self._submit_jobs(
                target=target,
                sequence=sequence,
                job_params=job_params,
                emulation_config=emulation_config,
            )
        # Classic backend.run() call
        else:
            batch_id = self._setup_session(target)

            job_ids = self._submit_jobs(
                target=target,
                sequence=sequence,
                job_params=job_params,
                emulation_config=emulation_config,
            )

        if wait:
            for job_id in job_ids:
                job = self._workspace.get_job(job_id)
                job.wait_until_completed()

        if not open:
            self._close_batch(batch_id)

        return RemoteResults(batch_id=batch_id, connection=self, job_ids=job_ids)

    def _setup_session(self, target: Pasqal) -> str:
        session = Session(
            workspace=self._workspace,
            target=target.name,
            provider_id=target.provider_id,
        )
        self._workspace.open_session(session)
        target.latest_session = session

        return session.id

    def _submit_jobs(
        self,
        target: Pasqal,
        sequence: Sequence,
        job_params: list[JobParams],
        emulation_config: EmulationConfig | None = None,
    ) -> list[str]:
        sequence = self._add_measurement_to_sequence(sequence)

        if sequence.is_parametrized() or sequence.is_register_mappable():
            for params in job_params:
                vars = params.get("variables", {})
                sequence.build(**vars)

        input_data = {"sequence_builder": sequence.to_abstract_repr()}

        if emulation_config:
            input_data["emulation_config"] = emulation_config.to_abstract_repr()

        job_ids: list[str] = []

        if job_params:
            for params in job_params:
                job = target.submit(input_data=input_data, input_params={**params})
                job_ids.append(job.id)
        else:
            job = target.submit(input_data=input_data)
            job_ids.append(job.id)

        return job_ids

    def _fetch_result(
        self, batch_id: str, job_ids: list[str] | None
    ) -> typing.Sequence[Results]:
        """Fetches the results of a completed batch."""
        jobs = self._query_job_progress(batch_id)

        if job_ids is None:
            job_ids = list(jobs.keys())

        results: list[Results] = []
        for id in job_ids:
            status, result = jobs[id]
            if status in [JobStatus.PENDING, JobStatus.RUNNING]:
                raise RemoteResultsError(
                    f"The results are not yet available, job {id} status is {status}."
                )

            if result is None:
                raise RemoteResultsError(f"No results found for job {id}.")

            results.append(result)

        return results

    def _query_job_progress(
        self, batch_id: str
    ) -> Mapping[str, tuple[JobStatus, Results | None]]:
        """Fetches the status and results of all the jobs in a batch.

        Unlike `_fetch_result`, this method does not raise an error if some
        jobs in the batch do not have results.

        It returns a dictionary mapping the job ID to its status and results.
        """
        jobs = self._workspace.list_session_jobs(session_id=batch_id)

        progress: dict[str, tuple[JobStatus, Results | None]] = {}

        for job in jobs:
            job.refresh()

            status = _AZURE_JOB_STATUS_MAP.get(  # ty: ignore[no-matching-overload]
                job.details.status, JobStatus.ERROR
            )

            result: Results | None = None
            if status == JobStatus.DONE:
                try:
                    raw_results = job.get_results()
                    result = self._parse_job_result(raw_results, job)
                except Exception:
                    logger.warning(
                        "Failed to parse results for job %s",
                        job.id,
                        exc_info=True,
                    )

            progress[job.id] = (status, result)

        return progress

    def _parse_job_result(
        self,
        raw_results: Any,
        job: Job,
    ) -> SampledResult:
        input_data_uri = job.details.input_data_uri
        if not input_data_uri:
            raise ValueError(f"Job {job.id} has no input data URI")
        input_payload: Any = job.download_data(input_data_uri)

        sequence = None

        try:
            if isinstance(input_payload, (bytes, bytearray)):
                input_json = json.loads(input_payload.decode("utf8"))
            elif isinstance(input_payload, str):
                input_json = json.loads(input_payload)
            else:
                input_json = input_payload
            sequence = Sequence.from_abstract_repr(input_json["sequence_builder"])
        except Exception:
            pass

        if sequence is None:
            raise ValueError(f"Cannot reconstruct sequence for job {job.id}")

        reg = sequence.get_register(include_mappable=True)
        meas_basis = sequence.get_measurement_basis()
        all_qubit_ids = reg.qubit_ids

        counter = raw_results.get("counter", raw_results)
        if not isinstance(counter, dict):
            counter = raw_results

        size = None
        input_params = job.details.input_params or {}
        vars = input_params.get("variables") if isinstance(input_params, dict) else None

        if vars and "qubits" in vars:
            size = len(vars["qubits"])

        return SampledResult(
            atom_order=all_qubit_ids[slice(size)],
            meas_basis=meas_basis,
            bitstring_counts=counter,
        )

    def _get_batch_status(self, batch_id: str) -> BatchStatus:
        """Gets the status of a batch from its ID."""
        session = self._workspace.get_session(session_id=batch_id)
        return _AZURE_SESSION_STATUS_MAP.get(  # ty: ignore[no-matching-overload]
            session.details.status, BatchStatus.ERROR
        )

    def _get_job_ids(self, batch_id: str) -> list[str]:
        """Gets all the job IDs within a batch."""
        jobs = self._workspace.list_session_jobs(session_id=batch_id)
        return [job.id for job in jobs]

    def fetch_available_devices(self) -> dict[str, Device]:
        """Fetches the devices available through this connection."""

        if not self._target_name_device_map:
            # Only retrieve targets available through current workspace provider's plan
            raw_targets = self._workspace.get_targets(provider_id=_PASQAL_PROVIDER_ID)
            if isinstance(raw_targets, Target):
                targets: list[Target] = [raw_targets]
            else:
                targets = list(cast(Iterable[Target], raw_targets))

            # Only build real QPU devices
            devices = [
                Device.from_abstract_repr(spec["specs"])
                for spec in self._get_device_specs()
            ]

            # Iterate over all PasqalTarget values rather than only workspace
            # targets: free-plan users need real Device objects to author and
            # validate sequences locally even when their workspace only exposes
            # an emulator target (e.g. SIM_EMU_FREE).
            for _target in _TARGETS:
                target = next(
                    (t for t in targets if t.name == _target.enum_value), None
                )

                device = next(
                    (
                        d
                        for d in devices
                        if d.name == _target.enum_name.removeprefix("QPU_")
                    ),
                    None,
                )

                if device:
                    self._target_name_device_map[_target.enum_value] = device
                    self._device_name_target_map[device.name] = _target.enum_value

                if target:
                    # Targets returned from the pasqal provider are Pasqal
                    # instances at runtime; cast for the type checker.
                    self._target_name_target_map[_target.enum_value] = cast(
                        Pasqal, target
                    )

        return {k: v for k, v in self._target_name_device_map.items()}

    def _get_device_specs(self) -> dict:
        response = urllib3.request(
            "GET",
            f"{_PASQAL_CLOUD_BASE_URL}/api/v1/devices/public-specs",
            timeout=5,
            retries=urllib3.Retry(10, backoff_factor=0.5),
        )

        return response.json()["data"]

    def _close_batch(self, batch_id: str) -> None:
        """Closes a batch using its ID."""
        session = self._workspace.get_session(session_id=batch_id)

        self._workspace.close_session(session)

    def supports_open_batch(self) -> bool:
        """Flag to confirm this class can support creating an open batch."""
        return True

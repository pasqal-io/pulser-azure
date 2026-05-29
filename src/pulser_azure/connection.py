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

import json
import logging
import os
import typing
from typing import Any, Mapping

from pulser.backend import EmulationConfig
import urllib3
from azure.identity import DefaultAzureCredential
from azure.quantum import JobStatus as AzureJobStatus
from azure.quantum import SessionStatus
from azure.quantum.job import Job
from azure.quantum.job.session import Session
from azure.quantum.target.pasqal import Pasqal
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

_QPU_DEVICE_NAME_TARGET_NAME_MAP: dict[str, str] = {
    "FRESNEL_CAN1": "pasqal.qpu.fresnel-can1"
}

# Reversed map to get the Azure target name from Pasqal's device type name
_TARGET_NAME_QPU_DEVICE_NAME_MAP: dict[str, str] = {
    v: k for k, v in _QPU_DEVICE_NAME_TARGET_NAME_MAP.items()
}


class AzureConnection(RemoteConnection):
    """Azure Quantum connection bridge.

    Args:
        resource_id: option resource ID of the Azure workspace, if the provided `resource_id` is `None`, the value is loaded from the `PULSER_AZURE_RESOURCE_ID` environment variable.
    """

    def __init__(self, resource_id: str | None = None):
        credential = DefaultAzureCredential(
            exclude_interactive_browser_credential=False
        )
        self._workspace = Workspace(
            resource_id=resource_id or os.getenv("PULSER_AZURE_RESOURCE_ID"),
            credential=credential,
        )

    def submit(
        self,
        sequence: Sequence,
        wait: bool = False,
        open: bool = False,
        batch_id: str | None = None,
        emulation_config: EmulationConfig | None = None,
        target_name: str | None = None,
        **kwargs: Any,
    ) -> RemoteResults:

        # target_name is set only when using BaseRemoteEmulatorBackend
        if target_name is None:
            target_name = _QPU_DEVICE_NAME_TARGET_NAME_MAP[sequence.device.name]

        target: Pasqal | None = self._workspace.get_targets(  # ty: ignore[invalid-assignment]
            name=target_name, provider_id=_PASQAL_PROVIDER_ID
        )

        if target is None:
            raise RuntimeError(
                f"The target {target_name} isn't available on your workspace"
            )

        job_params = make_json_compatible(kwargs.get("job_params", []))

        # Context manager use case (eg: with backend.open_batch()): open a new
        # session and return immediately. The caller (the open_batch context
        # manager) owns this session and must close it on __exit__.
        if open:
            batch_id = self._setup_session(target)

            return RemoteResults(batch_id=batch_id, connection=self)

        owns_session = False

        if batch_id:
            # when fetching the target from azure, the session isn't attached
            # to it even if it is still open
            session = self._workspace.get_session(batch_id)
            target.latest_session = session

            job_ids = self._submit_jobs(
                target=target,
                sequence=sequence,
                job_params=job_params,
                emulation_config=emulation_config,
            )
        else:
            batch_id = self._setup_session(target)
            owns_session = True

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

        if owns_session:
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

        # Only build real QPU devices
        devices = [
            Device.from_abstract_repr(spec["specs"])
            for spec in self._get_device_specs()
        ]

        return {
            _QPU_DEVICE_NAME_TARGET_NAME_MAP[d.name]: d
            for d in devices
            if d.name in _QPU_DEVICE_NAME_TARGET_NAME_MAP
        }

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

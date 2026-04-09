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

from typing import Any, Mapping

from pulser import Sequence
from pulser.backend.remote import (
    BatchStatus,
    JobStatus,
    RemoteConnection,
    RemoteResults,
)
from pulser.backend.results import Results
from pulser.devices import Device


class AzureConnection(RemoteConnection):
    def submit(
        self,
        sequence: Sequence,
        wait: bool = False,
        open: bool = True,
        batch_id: str | None = None,
        **kwargs: Any,
    ) -> RemoteResults:
        """Submit a job for execution."""
        pass

    def _fetch_result(
        self, batch_id: str, job_ids: list[str] | None
    ) -> Sequence[Results]:
        """Fetches the results of a completed batch."""
        pass

    def _query_job_progress(
        self, batch_id: str
    ) -> Mapping[str, tuple[JobStatus, Results | None]]:
        """Fetches the status and results of all the jobs in a batch.

        Unlike `_fetch_result`, this method does not raise an error if some
        jobs in the batch do not have results.

        It returns a dictionary mapping the job ID to its status and results.
        """
        pass

    def _get_batch_status(self, batch_id: str) -> BatchStatus:
        """Gets the status of a batch from its ID."""
        pass

    def _get_job_ids(self, batch_id: str) -> list[str]:
        """Gets all the job IDs within a batch."""
        pass

    def fetch_available_devices(self) -> dict[str, Device]:
        """Fetches the devices available through this connection."""
        pass

    def _close_batch(self, batch_id: str) -> None:
        """Closes a batch using its ID."""
        pass

    def supports_open_batch(self) -> bool:
        """Flag to confirm this class can support creating an open batch."""
        pass

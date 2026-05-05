# Pulser Azure

**Pulser Azure** is a Python package to run quantum sequences on
[Azure Quantum](https://azure.microsoft.com/en-us/solutions/quantum-computing/) infrastructure,
providing access to [Pasqal](https://www.pasqal.com/) neutral atom quantum computers.

It implements the Pulser
[`RemoteConnection`](https://docs.pasqal.com/pulser/) interface so any sequence
written with [Pulser](https://github.com/pasqal-io/Pulser) can be submitted to
Pasqal QPUs and emulators hosted on Azure Quantum.

## Installation

```bash
pip install pulser-azure
```

## At a glance

```python
from pulser_azure import AzureConnection

connection = AzureConnection(
    resource_id="/subscriptions/<id>/resourceGroups/<rg>/providers/Microsoft.Quantum/Workspaces/<ws>",
)

devices = connection.fetch_available_devices()
```

## Where to next?

- [Getting started](getting-started.md) — full end-to-end example
- [API reference](reference/index.md) — auto-generated from the source

## License

Apache 2.0 — see [LICENSE](https://github.com/pasqal-io/pulser-azure/blob/main/LICENSE).

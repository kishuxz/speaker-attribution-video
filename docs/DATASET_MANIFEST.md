# Dataset manifests (D1C)

A `DatasetManifest` is a catalog of referenced artifacts. It does **not** bundle
media bytes. Entries may point at external logical URIs without copying files
into the package or git tree.

## Splits

`TRAIN`, `VALIDATION`, `TEST`, `DEMO`, `UNASSIGNED`.

Rules:

* Duplicate content hashes are detected.
* The same bytes must not appear in training and evaluation splits under
  different filenames without detection.
* Evaluation fixtures must not silently enter training.
* Restricted or research-only data cannot be copied into a synthetic or public
  dataset.
* Historical television research data is not part of this repository.

## Snapshots

An `IngestionSnapshot` records per-entry outcomes. Only `ACCEPTED` means
complete ingestion success. `PARTIAL`, `DEGRADED`, `REJECTED`,
`FAILED_VALIDATION`, and `FAILED_POLICY` are not success. Failed entries remain
visible. Snapshot identity is stable for equivalent inputs; observation
timestamps are excluded. Snapshots contain manifests, not media.

This is not license verification and not legal advice.

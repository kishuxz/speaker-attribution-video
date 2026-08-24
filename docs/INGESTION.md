# Ingestion contracts (D1)

D1 is a **source-neutral ingestion boundary**. It describes and snapshots
user-supplied or synthetic media **without processing audio or video**.

This phase answers:

* What is this artifact?
* Where did it come from?
* Is its use permitted as *declared*?
* Has it changed (content digest)?
* What sensitivity does it carry?
* Can it be redistributed as *declared*?
* Which immutable snapshot was ingested? (D1G)
* Was ingestion complete, degraded, or rejected? (D1C)

D1 does **not** determine speakers, transcribe media, download datasets,
validate model accuracy, decode audio/video, or grant legal rights.

## Supported sources in this repository

Only **synthetic fixtures** and **user-supplied local files** are intended for
runtime connectors (D1E/D1F). `PUBLIC_DATASET_REFERENCE` is a declared catalog
pointer. There is **no** network dataset connector, Hugging Face loader, S3
client, or CourtListener live connector.

Historical television research data is **not** part of this repository.

## Identity

Three identifiers are distinct:

| Identity | Derived from | Changes when |
|---|---|---|
| **Content / artifact** | SHA-256 of source bytes | The bytes change |
| **Manifest** | Canonical identity fields excluding observation timestamps and warnings | Provenance, rights, sensitivity, logical filename, or other identity fields change |
| **Ingestion event** | Manifest identity plus `ingested_at` and connector | The same artifact is ingested at a different observation time |

Changing a display/logical filename does **not** claim new media content.
Observation timestamps must not make content identity nondeterministic.
Equivalent identity payloads serialize byte-identically.

Manifests never serialize absolute local paths by default and never serialize
file contents. Duration is integer microseconds. Negative size or duration,
malformed hashes, and unsupported schema versions are rejected.

## Rights and sensitivity (not legal advice)

Unknown or missing license fields are **not** permission. User attestation is
**not** independent verification. The application does not automate acceptance
of third-party terms. Prohibited data fails closed. Research-only data cannot
be marked redistributable or emitted as public/synthetic fixtures.

Local ingestion is **not** license verification. A later deterministic policy
engine (D1H) evaluates declared source/rights/sensitivity for operations; it is
**not** legal advice.

Sensitivity cannot be silently downgraded. Voiceprints, face embeddings, and
identity mappings are classifiable as `BIOMETRIC_DATA` even though D1 does not
generate them.

## Current implementation (D1A/D1B)

Versioned contracts:

* `SourceDescriptor` (`d1.source.v1`)
* `RightsRecord` (`d1.rights.v1`)
* `MediaManifest` (`d1.manifest.v1`)

JSON Schema: `speaker_attribution_video/data/schemas/media_manifest.d1.v1.json`.

Connectors, snapshot storage, the policy engine, and G1 graph projection are
later D1 nodes except as follows:

* D1C defines `DatasetManifest`, `IngestionSnapshot`, and findings.
* D1D defines the source-neutral `DataConnector` protocol. There is still **no**
  HTTP, S3, Hugging Face, or database connector, and no media decode.
* D1E `LocalFileConnector` hashes user files inside an allowed root. It does not
  decode media, invoke ffmpeg, copy files into the package, or treat a file
  extension as an authoritative MIME type.
* D1F `SyntheticFixtureConnector` generates original-project silence/tone/noise
  WAV bytes with Python’s standard library. Those tones are not accuracy
  benchmarks.

JSON Schema: `speaker_attribution_video/data/schemas/media_manifest.d1.v1.json`,
`dataset_manifest.d1.v1.json`, and `ingestion_snapshot.d1.v1.json`.

## Local-file connector (D1E)

`LocalFileConnector` requires an explicit allowed root. Requested paths must stay
inside that root. Path traversal, absolute paths, and symlink escape are
rejected. Devices, sockets, FIFOs, and directories are rejected when a regular
file is required. Hard links are hashed; a warning records that path uniqueness
is not content uniqueness.

The connector may hash bytes in bounded chunks and sniff a short magic header.
It does **not** decode audio/video, infer duration, invoke ffmpeg, or copy the
file into the package. Container type is `declared`, `detected` from that
header, or `unknown`. A file extension is never authoritative.

Errors and manifests must not include absolute paths. Display names are safe
logical slugs. A configurable maximum size is enforced before hashing. If the
file changes during hashing, ingestion fails closed. Missing rights metadata is
rejected when policy requires it.

## Synthetic fixture connector (D1F)

`SyntheticFixtureConnector` generates only original-project content:

* silence WAV
* 440 Hz tone WAV
* deterministic non-speech noise WAV
* manifest-only synthetic transcript note `speaker-alpha-synthetic-sentence-one`

Every synthetic artifact declares `source_type=SYNTHETIC`, `sensitivity=SYNTHETIC`,
an explicit project fixture license, a deterministic seed, and an expected
SHA-256. These tones prove ingestion behavior. They are **not** diarization or
transcription benchmarks and must not include celebrity names, television
dialogue, cloned voices, or private audio.

Snapshot storage, the policy engine, and G1 graph projection remain later D1
nodes.

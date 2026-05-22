#!/usr/bin/env python3

from __future__ import annotations

from typing import Any


MSA_METADATA_COLUMNS = [
    "msa_used",
    "msa_source",
    "msa_mode",
    "msa_database",
    "msa_database_path",
    "msa_generation_included_in_timing",
    "msa_generation_included_in_carbon",
    "msa_reused",
    "shared_msa_metadata_file",
    "shared_msa_dir",
    "shared_msa_a3m_file",
    "msa_generation_time_sec",
    "msa_notes",
]

COLABFOLD_DB_PATH = "/data/chen/protein_folding_databases/colabfold"


def _bool(value: bool) -> str:
    return str(bool(value)).lower()


def _base(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "msa_used": "unknown",
        "msa_source": "unknown",
        "msa_mode": "model_default_unknown",
        "msa_database": "unknown",
        "msa_database_path": "",
        "msa_generation_included_in_timing": "unknown",
        "msa_generation_included_in_carbon": "unknown",
        "msa_reused": "unknown",
        "shared_msa_metadata_file": "",
        "shared_msa_dir": "",
        "shared_msa_a3m_file": "",
        "msa_generation_time_sec": "",
        "msa_notes": "MSA usage not confirmed from runner/config",
    }
    row.update(overrides)
    return row


def _stringify(value: Any) -> Any:
    if isinstance(value, bool):
        return _bool(value)
    return value


def _no_msa(mode: str, notes: str) -> dict[str, Any]:
    return _base(
        msa_used="false",
        msa_source="none",
        msa_mode=mode,
        msa_database="none",
        msa_database_path="",
        msa_generation_included_in_timing="false",
        msa_generation_included_in_carbon="false",
        msa_reused="false",
        shared_msa_metadata_file="",
        shared_msa_dir="",
        shared_msa_a3m_file="",
        msa_generation_time_sec="",
        msa_notes=notes,
    )


def _colabfold_msa(mode: str, notes: str) -> dict[str, Any]:
    return _base(
        msa_used="true",
        msa_source="colabfold_mmseqs2",
        msa_mode=mode,
        msa_database="colabfold",
        msa_database_path=COLABFOLD_DB_PATH,
        msa_generation_included_in_timing="true",
        msa_generation_included_in_carbon="true",
        msa_reused="false",
        shared_msa_metadata_file="",
        shared_msa_dir="",
        shared_msa_a3m_file="",
        msa_generation_time_sec="",
        msa_notes=notes,
    )



def shared_msa_metadata(
    metadata_file: str,
    msa_dir: str,
    a3m_file: str,
    generation_time_sec: str = "",
) -> dict[str, Any]:
    return _base(
        msa_used="true",
        msa_source="colabfold_mmseqs2",
        msa_mode="shared_precomputed_msa",
        msa_database="colabfold",
        msa_database_path=COLABFOLD_DB_PATH,
        msa_generation_included_in_timing="false",
        msa_generation_included_in_carbon="false",
        msa_reused="true",
        shared_msa_metadata_file=metadata_file,
        shared_msa_dir=msa_dir,
        shared_msa_a3m_file=a3m_file,
        msa_generation_time_sec=generation_time_sec,
        msa_notes="Shared ColabFold/MMseqs MSA generated once per target; MSA cost tracked separately",
    )


def infer_msa_metadata(model_name: str, model_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    model_cfg = model_cfg or {}
    explicit = {column: _stringify(model_cfg[column]) for column in MSA_METADATA_COLUMNS if column in model_cfg}

    if model_name in {"esmfold", "omegafold"}:
        metadata = _no_msa("native_single_sequence", "Native no-MSA model")
    elif model_name == "boltz2":
        metadata = _no_msa("model_default_no_msa", "Boltz-2 runner provides an explicit empty MSA and runs single-sequence mode")
    elif model_name == "chai1":
        metadata = _no_msa(
            "native_embedding_no_msa",
            "Chai-1 default CLI uses embeddings without MSAs/templates; external MSAs are optional",
        )
    elif model_name == "colabfold":
        metadata = _colabfold_msa("default_msa", "Default ColabFold MSA mode; MSA search included in timing/carbon")
    elif model_name == "openfold":
        metadata = _colabfold_msa("default_msa", "OpenFold with freshly generated ColabFold/MMseqs MSA; MSA search included in timing/carbon")
    elif model_name == "colabfold_single":
        metadata = _no_msa("forced_single_sequence_ablation", "Ablation: ColabFold forced to single-sequence mode")
    elif model_name == "colabfold_msa":
        metadata = _colabfold_msa("msa_ablation", "Ablation: ColabFold MSA mode; MSA search rerun per inference")
    elif model_name == "openfold_single":
        metadata = _no_msa("forced_single_sequence_ablation", "Ablation: OpenFold single-sequence/dummy-MSA smoke mode")
    elif model_name == "openfold_msa":
        metadata = _colabfold_msa("msa_ablation", "Ablation: OpenFold with freshly generated ColabFold/MMseqs MSA; MSA search rerun per inference")
    else:
        metadata = _base()

    metadata.update(explicit)
    return {column: metadata.get(column, "") for column in MSA_METADATA_COLUMNS}

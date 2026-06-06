#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
import random
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
ALPHAFOLD_REPO = REPO_ROOT / "models" / "alphafold"
sys.path.insert(0, str(ALPHAFOLD_REPO))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import numpy as np
from alphafold.common import confidence
from alphafold.common import protein
from alphafold.common import residue_constants
from alphafold.data import pipeline
from alphafold.data import templates
from alphafold.data.tools import hhsearch
from alphafold.model import config
from alphafold.model import data
from alphafold.model import model
from carbon_tracking import CarbonRunTracker, empty_carbon_metadata
import jax.numpy as jnp


STAGE_COLUMNS = [
    "target_id",
    "pdb_id",
    "chain",
    "sequence_length",
    "model",
    "stage",
    "stage_status",
    "stage_exit_code",
    "stage_runtime_sec",
    "stage_carbon_emissions_kg",
    "stage_carbon_emissions_g",
    "stage_energy_consumed_kwh",
    "stage_carbon_country_iso_code",
    "stage_carbon_intensity_mode",
    "stage_carbon_intensity_g_per_kwh",
    "stage_log_file",
    "stage_output_dir",
    "stage_command",
    "notes",
]

AF2_METADATA_COLUMNS = [
    "msa_feature_runtime_sec",
    "msa_feature_carbon_emissions_g",
    "msa_feature_energy_consumed_kwh",
    "af2_inference_runtime_sec",
    "af2_inference_carbon_emissions_g",
    "af2_inference_energy_consumed_kwh",
    "total_runtime_sec",
    "total_carbon_emissions_g",
    "total_energy_consumed_kwh",
    "af2_db_preset",
    "af2_model_preset",
    "af2_params_dir",
    "af2_data_dir",
    "af2_features_dir",
]


def read_fasta(path: Path) -> tuple[str, str]:
    name = path.stem
    sequence_parts: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            name = line[1:].split()[0] or name
        else:
            sequence_parts.append(line)
    sequence = "".join(sequence_parts).upper()
    if not sequence:
        raise SystemExit(f"No sequence found in FASTA: {path}")
    return name, sequence


def jnp_to_np(output: dict[str, Any]) -> dict[str, Any]:
    for key, value in output.items():
        if isinstance(value, dict):
            output[key] = jnp_to_np(value)
        elif isinstance(value, jnp.ndarray):
            output[key] = np.array(value)
    return output


def default_db_paths(data_dir: Path) -> dict[str, str]:
    return {
        "uniref90_database_path": str(data_dir / "uniref90" / "uniref90.fasta"),
        "mgnify_database_path": str(data_dir / "mgnify" / "mgy_clusters_2022_05.fa"),
        "bfd_database_path": str(
            data_dir / "bfd" / "bfd_metaclust_clu_complete_id30_c90_final_seq.sorted_opt"
        ),
        "uniref30_database_path": str(data_dir / "uniref30" / "UniRef30_2021_03"),
        "small_bfd_database_path": str(data_dir / "small_bfd" / "bfd-first_non_consensus_sequences.fasta"),
        "pdb70_database_path": str(data_dir / "pdb70" / "pdb70"),
        "template_mmcif_dir": str(data_dir / "pdb_mmcif" / "mmcif_files"),
        "obsolete_pdbs_path": str(data_dir / "pdb_mmcif" / "obsolete.dat"),
    }


def require_path(path: str, label: str) -> None:
    candidate = Path(path)
    if candidate.exists():
        return
    if list(candidate.parent.glob(candidate.name + "*")):
        return
    raise FileNotFoundError(f"Required AF2 {label} path does not exist: {path}")


def make_data_pipeline(args: argparse.Namespace) -> pipeline.DataPipeline:
    db_paths = default_db_paths(args.data_dir)
    required_labels = [
        "uniref90_database_path",
        "mgnify_database_path",
        "pdb70_database_path",
        "template_mmcif_dir",
        "obsolete_pdbs_path",
    ]
    if args.db_preset == "reduced_dbs":
        required_labels.append("small_bfd_database_path")
    else:
        required_labels.extend(["bfd_database_path", "uniref30_database_path"])
    for label in required_labels:
        require_path(db_paths[label], label)
    template_searcher = hhsearch.HHSearch(
        binary_path=args.hhsearch_binary_path,
        databases=[db_paths["pdb70_database_path"]],
        cpu=args.hhsearch_n_cpu,
    )
    template_featurizer = templates.HhsearchHitFeaturizer(
        mmcif_dir=db_paths["template_mmcif_dir"],
        max_template_date=args.max_template_date,
        max_hits=20,
        kalign_binary_path=args.kalign_binary_path,
        release_dates_path=None,
        obsolete_pdbs_path=db_paths["obsolete_pdbs_path"],
    )
    return pipeline.DataPipeline(
        jackhmmer_binary_path=args.jackhmmer_binary_path,
        hhblits_binary_path=args.hhblits_binary_path,
        uniref90_database_path=db_paths["uniref90_database_path"],
        mgnify_database_path=db_paths["mgnify_database_path"],
        bfd_database_path=None if args.db_preset == "reduced_dbs" else db_paths["bfd_database_path"],
        uniref30_database_path=None if args.db_preset == "reduced_dbs" else db_paths["uniref30_database_path"],
        small_bfd_database_path=db_paths["small_bfd_database_path"] if args.db_preset == "reduced_dbs" else None,
        template_searcher=template_searcher,
        template_featurizer=template_featurizer,
        use_small_bfd=args.db_preset == "reduced_dbs",
        use_precomputed_msas=args.use_precomputed_msas or args.db_preset == "full_dbs_query_only_bfd",
        msa_tools_n_cpu=args.msa_tools_n_cpu,
    )


def write_query_only_bfd_a3m(msa_output_dir: Path, target_id: str, sequence: str) -> Path:
    bfd_out_path = msa_output_dir / "bfd_uniref_hits.a3m"
    safe_target_id = target_id.replace("\n", "_").replace("\r", "_")
    bfd_out_path.write_text(f">{safe_target_id} query_only_bfd_fallback\n{sequence}\n")
    return bfd_out_path


def msa_mode_for_preset(db_preset: str) -> str:
    if db_preset == "reduced_dbs":
        return "official_af2_reduced_dbs_small_bfd"
    if db_preset == "full_dbs_query_only_bfd":
        return "official_af2_full_dbs_query_only_bfd_fallback"
    return "official_af2_database_search"


def stage_row(
    args: argparse.Namespace,
    target_id: str,
    sequence: str,
    stage: str,
    status: str,
    exit_code: int,
    runtime_sec: float,
    carbon: dict[str, Any],
    output_dir: Path,
    notes: str,
) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "pdb_id": args.pdb_id,
        "chain": args.chain_id,
        "sequence_length": len(sequence),
        "model": "af2",
        "stage": stage,
        "stage_status": status,
        "stage_exit_code": exit_code,
        "stage_runtime_sec": f"{runtime_sec:.6f}",
        "stage_carbon_emissions_kg": carbon.get("carbon_emissions_kg", ""),
        "stage_carbon_emissions_g": carbon.get("carbon_emissions_g", ""),
        "stage_energy_consumed_kwh": carbon.get("carbon_energy_consumed_kwh", ""),
        "stage_carbon_country_iso_code": carbon.get("carbon_country_iso_code", ""),
        "stage_carbon_intensity_mode": carbon.get("carbon_intensity_mode", ""),
        "stage_carbon_intensity_g_per_kwh": carbon.get("carbon_intensity_g_per_kwh", ""),
        "stage_log_file": args.stage_log_file,
        "stage_output_dir": str(output_dir),
        "stage_command": " ".join(sys.argv),
        "notes": notes,
    }


def append_stage_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STAGE_COLUMNS)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in STAGE_COLUMNS})


def run_stage(
    args: argparse.Namespace,
    target_id: str,
    sequence: str,
    stage: str,
    output_dir: Path,
    action: Callable[[], Any],
    notes: str,
) -> tuple[Any, dict[str, Any]]:
    tracker = CarbonRunTracker(
        enabled=args.track_carbon,
        output_dir=args.carbon_output_dir,
        country_iso_code=args.carbon_country_iso_code,
        project_name=args.carbon_project_name,
        measure_power_secs=args.carbon_measure_power_secs,
        run_label=f"{target_id}_af2_{stage}",
    )
    start = time.perf_counter()
    tracker.start()
    status = "success"
    exit_code = 0
    result = None
    try:
        result = action()
    except BaseException:
        status = "failed"
        exit_code = 1
        raise
    finally:
        runtime_sec = time.perf_counter() - start
        carbon = tracker.stop() if args.track_carbon else empty_carbon_metadata(False, args.carbon_country_iso_code)
        row = stage_row(args, target_id, sequence, stage, status, exit_code, runtime_sec, carbon, output_dir, notes)
        append_stage_rows(args.stage_metadata_csv, [row])
        append_stage_rows(args.output_dir / "af2_stage_metadata.csv", [row])
    return result, row


def run_feature_stage(
    args: argparse.Namespace,
    fasta_path: Path,
    features_dir: Path,
) -> dict[str, Any]:
    features_dir.mkdir(parents=True, exist_ok=True)
    msa_output_dir = features_dir / "msas"
    msa_output_dir.mkdir(parents=True, exist_ok=True)
    if args.db_preset == "full_dbs_query_only_bfd":
        target_id, sequence = read_fasta(fasta_path)
        write_query_only_bfd_a3m(msa_output_dir, target_id, sequence)
    data_pipeline = make_data_pipeline(args)
    feature_dict = data_pipeline.process(input_fasta_path=str(fasta_path), msa_output_dir=str(msa_output_dir))
    with (features_dir / "features.pkl").open("wb") as f:
        pickle.dump(feature_dict, f, protocol=4)
    return feature_dict


def run_inference_stage(
    args: argparse.Namespace,
    target_id: str,
    sequence: str,
    feature_dict: dict[str, Any],
    inference_dir: Path,
) -> list[dict[str, Any]]:
    inference_dir.mkdir(parents=True, exist_ok=True)
    model_names = config.MODEL_PRESETS[args.model_preset][: args.top_k]
    if not model_names:
        raise SystemExit(f"No AF2 model names found for preset {args.model_preset}")
    predictions: list[dict[str, Any]] = []
    ranking_confidences: dict[str, float] = {}
    random_seed = args.random_seed if args.random_seed is not None else random.randrange(sys.maxsize // len(model_names))
    for model_index, model_name in enumerate(model_names):
        model_config = config.model_config(model_name)
        model_config.data.eval.num_ensemble = 1
        model_params = data.get_model_haiku_params(model_name=model_name, data_dir=str(args.data_dir))
        model_runner = model.RunModel(model_config, model_params)
        model_random_seed = model_index + random_seed * len(model_names)
        processed_feature_dict = model_runner.process_features(feature_dict, random_seed=model_random_seed)
        prediction_result = model_runner.predict(processed_feature_dict, random_seed=model_random_seed)
        ranking_confidence = float(prediction_result["ranking_confidence"])
        ranking_confidences[model_name] = ranking_confidence

        plddt = prediction_result["plddt"]
        (inference_dir / f"confidence_{model_name}.json").write_text(confidence.confidence_json(plddt))
        if "predicted_aligned_error" in prediction_result and "max_predicted_aligned_error" in prediction_result:
            pae = prediction_result["predicted_aligned_error"]
            max_pae = float(prediction_result["max_predicted_aligned_error"])
            (inference_dir / f"pae_{model_name}.json").write_text(confidence.pae_json(pae, max_pae))

        np_prediction_result = jnp_to_np(dict(prediction_result))
        with (inference_dir / f"result_{model_name}.pkl").open("wb") as f:
            pickle.dump(np_prediction_result, f, protocol=4)

        plddt_b_factors = np.repeat(plddt[:, None], residue_constants.atom_type_num, axis=-1)
        unrelaxed_protein = protein.from_prediction(
            features=processed_feature_dict,
            result=prediction_result,
            b_factors=plddt_b_factors,
            remove_leading_feature_dimension=True,
        )
        pdb_string = protein.to_pdb(unrelaxed_protein)
        pdb_path = inference_dir / f"unrelaxed_{model_name}.pdb"
        pdb_path.write_text(pdb_string)
        predictions.append(
            {
                "model_name": model_name,
                "ranking_confidence": ranking_confidence,
                "pdb_path": str(pdb_path),
                "pdb_string": pdb_string,
            }
        )

    ranked = sorted(predictions, key=lambda item: item["ranking_confidence"], reverse=True)
    (inference_dir / "ranking_debug.json").write_text(
        json.dumps({"plddts": ranking_confidences, "order": [item["model_name"] for item in ranked]}, indent=2) + "\n"
    )
    for index, item in enumerate(ranked, start=1):
        rank_path = args.output_dir / f"rank_{index:03d}.pdb"
        rank_path.write_text(item["pdb_string"])
        shutil.copy2(item["pdb_path"], inference_dir / f"ranked_{index - 1}.pdb")
    return ranked


def float_value(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key, "") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def write_metadata(
    args: argparse.Namespace,
    target_id: str,
    sequence: str,
    feature_row: dict[str, Any],
    inference_row: dict[str, Any],
    ranked: list[dict[str, Any]],
) -> None:
    feature_runtime = float_value(feature_row, "stage_runtime_sec")
    inference_runtime = float_value(inference_row, "stage_runtime_sec")
    feature_carbon_g = float_value(feature_row, "stage_carbon_emissions_g")
    inference_carbon_g = float_value(inference_row, "stage_carbon_emissions_g")
    feature_energy = float_value(feature_row, "stage_energy_consumed_kwh")
    inference_energy = float_value(inference_row, "stage_energy_consumed_kwh")
    metadata = {
        "target_id": target_id,
        "model": "af2",
        "environment": "af2",
        "status": "success",
        "sequence_length": len(sequence),
        "top_k_requested": args.top_k,
        "top_k_generated": len(ranked),
        "top_k_policy": "official AlphaFold2 monomer models, truncated to requested top_k; relaxation disabled",
        "source_files": [item["pdb_path"] for item in ranked],
        "msa_used": "true",
        "msa_source": "alphafold2_default",
        "msa_mode": msa_mode_for_preset(args.db_preset),
        "msa_database": "alphafold",
        "msa_database_path": str(args.data_dir),
        "msa_generation_included_in_timing": "true",
        "msa_generation_included_in_carbon": "true",
        "msa_reused": "false",
        "msa_feature_runtime_sec": f"{feature_runtime:.6f}",
        "msa_feature_carbon_emissions_g": feature_carbon_g,
        "msa_feature_energy_consumed_kwh": feature_energy,
        "af2_inference_runtime_sec": f"{inference_runtime:.6f}",
        "af2_inference_carbon_emissions_g": inference_carbon_g,
        "af2_inference_energy_consumed_kwh": inference_energy,
        "total_runtime_sec": f"{feature_runtime + inference_runtime:.6f}",
        "total_carbon_emissions_g": feature_carbon_g + inference_carbon_g,
        "total_energy_consumed_kwh": feature_energy + inference_energy,
        "af2_db_preset": args.db_preset,
        "af2_model_preset": args.model_preset,
        "af2_params_dir": str(args.data_dir / "params"),
        "af2_data_dir": str(args.data_dir),
        "af2_features_dir": str(args.features_dir),
        "af2_model_names": [item["model_name"] for item in ranked],
        "af2_stage_metadata_csv": str(args.stage_metadata_csv),
        "af2_feature_stage": feature_row,
        "af2_inference_stage": inference_row,
    }
    (args.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run official AlphaFold2 with split MSA/features and inference tracking.")
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--data-dir", default=os.environ.get("AF2_DATA_DIR", "/data/chen/protein_folding_databases/alphafold"))
    parser.add_argument("--model-preset", default=os.environ.get("AF2_MODEL_PRESET", "monomer"), choices=["monomer", "monomer_casp14", "monomer_ptm"])
    parser.add_argument(
        "--db-preset",
        default=os.environ.get("AF2_DB_PRESET", "full_dbs"),
        choices=["full_dbs", "reduced_dbs", "full_dbs_query_only_bfd"],
    )
    parser.add_argument("--max-template-date", default=os.environ.get("AF2_MAX_TEMPLATE_DATE", "2026-05-26"))
    parser.add_argument("--random-seed", type=int, default=int(os.environ["AF2_RANDOM_SEED"]) if os.environ.get("AF2_RANDOM_SEED") else None)
    parser.add_argument("--pdb-id", default=os.environ.get("AF2_TARGET_PDB_ID", ""))
    parser.add_argument("--chain-id", default=os.environ.get("AF2_TARGET_CHAIN_ID", ""))
    parser.add_argument("--features-dir", default=os.environ.get("AF2_FEATURES_DIR", ""))
    parser.add_argument("--stage-metadata-csv", default=os.environ.get("AF2_STAGE_METADATA_CSV", ""))
    parser.add_argument("--stage-log-file", default=os.environ.get("AF2_STAGE_LOG_FILE", ""))
    parser.add_argument("--use-precomputed-msas", action="store_true")
    parser.add_argument("--track-carbon", action="store_true")
    parser.add_argument("--carbon-country-iso-code", default=os.environ.get("AF2_CARBON_COUNTRY_ISO_CODE", "WORLD"))
    parser.add_argument("--carbon-output-dir", default=os.environ.get("AF2_CARBON_OUTPUT_DIR", ""))
    parser.add_argument("--carbon-project-name", default=os.environ.get("AF2_CARBON_PROJECT_NAME", "protein_folding_benchmark"))
    parser.add_argument("--carbon-measure-power-secs", type=float, default=float(os.environ.get("AF2_CARBON_MEASURE_POWER_SECS", "1.0")))
    parser.add_argument("--jackhmmer-binary-path", default=os.environ.get("AF2_JACKHMMER_BINARY", shutil.which("jackhmmer") or "jackhmmer"))
    parser.add_argument("--hhblits-binary-path", default=os.environ.get("AF2_HHBLITS_BINARY", shutil.which("hhblits") or "hhblits"))
    parser.add_argument("--hhsearch-binary-path", default=os.environ.get("AF2_HHSEARCH_BINARY", shutil.which("hhsearch") or "hhsearch"))
    parser.add_argument("--kalign-binary-path", default=os.environ.get("AF2_KALIGN_BINARY", shutil.which("kalign") or "kalign"))
    parser.add_argument("--msa-tools-n-cpu", type=int, default=int(os.environ.get("AF2_MSA_TOOLS_N_CPU", "8")))
    parser.add_argument("--hhsearch-n-cpu", type=int, default=int(os.environ.get("AF2_HHSEARCH_N_CPU", "8")))
    args = parser.parse_args()

    args.output_dir = Path(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.data_dir = Path(args.data_dir)
    args.features_dir = Path(args.features_dir) if args.features_dir else args.output_dir / "af2_features"
    args.stage_metadata_csv = Path(args.stage_metadata_csv) if args.stage_metadata_csv else args.output_dir / "af2_stage_metadata.csv"
    args.carbon_output_dir = Path(args.carbon_output_dir) if args.carbon_output_dir else args.output_dir / "carbon"
    args.stage_log_file = args.stage_log_file or str(args.output_dir / "af2.log")
    if args.top_k < 1:
        raise SystemExit("--top-k must be >= 1")

    fasta_path = Path(args.fasta)
    target_id, sequence = read_fasta(fasta_path)
    inference_dir = args.output_dir / "af2_inference"

    try:
        feature_dict, feature_row = run_stage(
            args,
            target_id,
            sequence,
            "msa_features",
            args.features_dir,
            lambda: run_feature_stage(args, fasta_path, args.features_dir),
            "Official AlphaFold2 database search and feature/template generation.",
        )
        ranked, inference_row = run_stage(
            args,
            target_id,
            sequence,
            "inference",
            inference_dir,
            lambda: run_inference_stage(args, target_id, sequence, feature_dict, inference_dir),
            "Official AlphaFold2 JAX model inference; Amber relaxation disabled.",
        )
        write_metadata(args, target_id, sequence, feature_row, inference_row, ranked)
    except Exception as exc:
        error_metadata = {
            "target_id": target_id,
            "model": "af2",
            "environment": "af2",
            "status": "failed",
            "error": repr(exc),
            "traceback": traceback.format_exc(),
        }
        (args.output_dir / "metadata.json").write_text(json.dumps(error_metadata, indent=2) + "\n")
        raise


if __name__ == "__main__":
    main()

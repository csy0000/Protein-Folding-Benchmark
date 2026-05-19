#!/usr/bin/env python3

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CARBON_METADATA_COLUMNS = [
    "carbon_tracking_enabled",
    "carbon_method",
    "carbon_country_iso_code",
    "carbon_emissions_kg",
    "carbon_emissions_g",
    "carbon_energy_consumed_kwh",
    "carbon_cpu_power_w",
    "carbon_gpu_power_w",
    "carbon_ram_power_w",
    "carbon_cpu_energy_kwh",
    "carbon_gpu_energy_kwh",
    "carbon_ram_energy_kwh",
    "carbon_duration_sec",
    "carbon_output_file",
    "carbon_error",
]


def empty_carbon_metadata(enabled: bool = False, country_iso_code: str = "", error: str = "") -> dict[str, Any]:
    return {
        "carbon_tracking_enabled": str(bool(enabled)).lower(),
        "carbon_method": "codecarbon_offline" if enabled else "",
        "carbon_country_iso_code": country_iso_code,
        "carbon_emissions_kg": "",
        "carbon_emissions_g": "",
        "carbon_energy_consumed_kwh": "",
        "carbon_cpu_power_w": "",
        "carbon_gpu_power_w": "",
        "carbon_ram_power_w": "",
        "carbon_cpu_energy_kwh": "",
        "carbon_gpu_energy_kwh": "",
        "carbon_ram_energy_kwh": "",
        "carbon_duration_sec": "",
        "carbon_output_file": "",
        "carbon_error": error,
    }


def safe_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return label.strip("._") or "run"


def first_present(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = row.get(name, "")
        if value not in ("", None):
            return value
    return ""


@dataclass
class CarbonRunTracker:
    enabled: bool
    output_dir: Path
    country_iso_code: str
    project_name: str
    measure_power_secs: float
    run_label: str

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        self.output_file = f"{safe_label(self.run_label)}_emissions.csv"
        self.output_path = self.output_dir / self.output_file
        self._tracker = None
        self._start_error = ""

    def start(self) -> None:
        if not self.enabled:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            from codecarbon import OfflineEmissionsTracker

            self._tracker = OfflineEmissionsTracker(
                country_iso_code=self.country_iso_code,
                output_dir=str(self.output_dir),
                output_file=self.output_file,
                project_name=f"{self.project_name}_{self.run_label}",
                measure_power_secs=self.measure_power_secs,
                log_level="error",
            )
            self._tracker.start()
        except Exception as exc:  # pragma: no cover - depends on local hardware/codecarbon
            self._tracker = None
            self._start_error = repr(exc)

    def stop(self) -> dict[str, Any]:
        if not self.enabled:
            return empty_carbon_metadata(False, self.country_iso_code)

        metadata = empty_carbon_metadata(True, self.country_iso_code, self._start_error)
        metadata["carbon_output_file"] = str(self.output_path)
        if self._tracker is not None:
            try:
                emissions_kg = self._tracker.stop()
                if emissions_kg is not None:
                    metadata["carbon_emissions_kg"] = emissions_kg
                    metadata["carbon_emissions_g"] = emissions_kg * 1000.0
            except Exception as exc:  # pragma: no cover - depends on local hardware/codecarbon
                metadata["carbon_error"] = "; ".join(part for part in [metadata["carbon_error"], repr(exc)] if part)

        if self.output_path.exists():
            metadata.update(read_codecarbon_csv(self.output_path))
        return metadata


def read_codecarbon_csv(path: Path) -> dict[str, Any]:
    try:
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception as exc:  # pragma: no cover - defensive for partial files
        return {"carbon_error": f"failed to read CodeCarbon CSV: {exc!r}"}

    if not rows:
        return {}
    row = rows[-1]
    result: dict[str, Any] = {}

    emissions = first_present(row, ("emissions", "emissions_kg", "emissions_kg_co2"))
    if emissions:
        result["carbon_emissions_kg"] = emissions
        try:
            result["carbon_emissions_g"] = float(emissions) * 1000.0
        except ValueError:
            pass

    mappings = {
        "carbon_energy_consumed_kwh": ("energy_consumed", "energy_consumed_kwh"),
        "carbon_cpu_power_w": ("cpu_power", "cpu_power_w"),
        "carbon_gpu_power_w": ("gpu_power", "gpu_power_w"),
        "carbon_ram_power_w": ("ram_power", "ram_power_w"),
        "carbon_cpu_energy_kwh": ("cpu_energy", "cpu_energy_kwh"),
        "carbon_gpu_energy_kwh": ("gpu_energy", "gpu_energy_kwh"),
        "carbon_ram_energy_kwh": ("ram_energy", "ram_energy_kwh"),
        "carbon_duration_sec": ("duration", "duration_sec", "duration_seconds"),
    }
    for output_name, candidates in mappings.items():
        value = first_present(row, candidates)
        if value:
            result[output_name] = value
    return result

# Project Scope

This repository provides a local benchmark harness for protein folding models. It standardizes protein sequence inputs, model runner calls, prediction outputs, and reference-based scoring so different backends can be compared with the same driver.

The benchmark convention is to request up to the top 5 predicted structures per model. Models that produce a single deterministic structure should still write a standardized `rank_001.pdb` file and document the limitation in `metadata.json`.

The first target is Chignolin / `1UAO`, using sequence `GYDPETGTWG` and reference structure `data/references/1UAO_model1_chainA.pdb`.

Future extensions should add runtime, GPU memory, and carbon-emission benchmarking alongside structural quality metrics.

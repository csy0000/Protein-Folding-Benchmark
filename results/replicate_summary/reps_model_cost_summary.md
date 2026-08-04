# Cross-replicate cost summary

Replicates (n=3): rep1, rep2, rep3

- `rep1` -> `/home/chen/projects/Protein-Folding-Benchmark/results/2026-06-09-combine-8models-gpu`
- `rep2` -> `/home/chen/projects/Protein-Folding-Benchmark/results/20260802_082154_combine-8models-gpu_rep2`
- `rep3` -> `/home/chen/projects/Protein-Folding-Benchmark/results/20260803_005751_combine-8models-gpu_rep3`

All mean ± std below are **across replicates**, not across targets.

## Per-model cost

Per-model cost is *attributed* cost: correct for comparing models to each other, but **not additive across models**, because the shared ColabFold/MMseqs2 MSA is built once and re-charged to every model that reuses it. For a whole-benchmark figure use `benchmark_incremental_*` in the next section.

| model | n_reps | msa_role | total runtime (h) | inference runtime (h) | energy (kWh) | CO2 (g) | runtime CV |
| --- | --- | --- | --- | --- | --- | --- | --- |
| colabfold | 3 | builder | 8.36 ± 0.18 | 1.81 ± 0.04 | 0.8266 ± 0.2365 | 392.7 ± 112.4 | 0.0212 |
| af2 | 3 | reuser | not comparable † | 1.75 ± 0.04 | not comparable † | not comparable † | not comparable † |
| protenix | 3 | reuser | 7.72 ± 0.19 | 1.17 ± 0.03 | 0.7954 ± 0.1196 | 377.8 ± 56.8 | 0.0240 |
| openfold | 3 | reuser | 7.43 ± 0.17 | 0.88 ± 0.06 | 0.8433 ± 0.1416 | 400.6 ± 67.2 | 0.0230 |
| boltz2 | 3 | reuser | 7.38 ± 0.17 | 0.82 ± 0.01 | 0.7624 ± 0.1222 | 362.1 ± 58.1 | 0.0231 |
| chai1 | 3 | none | 1.67 ± 0.30 | 1.67 ± 0.30 | 0.4376 ± 0.0431 | 207.9 ± 20.5 | 0.1819 |
| omegafold | 3 | none | 1.42 ± 0.10 | 1.42 ± 0.10 | 0.4419 ± 0.0544 | 209.9 ± 25.8 | 0.0721 |
| esmfold | 3 | none | 0.78 ± 0.10 | 0.78 ± 0.10 | 0.1669 ± 0.0146 | 79.3 ± 6.9 | 0.1256 |

† af2: the shared MSA is charged in some replicates but not others (deliberate MSA reuse), so the *total* cost mixes accounting with machine variance and no mean ± std over reps is meaningful. The **inference** column is unaffected and is the comparable quantity for these models. Per-rep totals are in reps_per_rep_model_cost.csv.

## Whole-benchmark cost per replicate (shared MSA counted once)

| rep | inference (h) | MSA dedup (h) | incremental total (h) | naive sum (h) | overcount (h) | CO2 incremental (g) |
| --- | --- | --- | --- | --- | --- | --- |
| rep1 | 11.030 | 26.343 | 37.374 | 56.906 | 19.533 | 3300.6 |
| rep2 | 9.928 | 6.407 | 16.335 | 35.555 | 19.221 | 1404.0 |
| rep3 | 9.977 | 6.740 | 16.717 | 36.937 | 20.220 | 1455.8 |

## Energy by device (CPU / GPU / RAM)

From the per-(target, model, stage) CodeCarbon CSVs -- the only device-resolved measurement in the pipeline, since the prediction manifest records no device. This splits **energy, not wall time**: a stage occupies wall-clock while both CPU and GPU are partly busy, so there is no meaningful per-device wall time.

| model | n_reps | CPU (kWh) | GPU (kWh) | RAM (kWh) | measured total (kWh) | GPU share (%) | stage wall time (h) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| af2 | 3 | 0.3731 ± 0.5204 | 0.6755 ± 0.7802 | 0.8115 ± 1.1515 | 1.8602 ± 2.4519 | 44.9 ± 10.0 | 8.78 ± 12.24 |
| colabfold | 3 | 0.0824 ± 0.0018 | 0.4571 ± 0.2356 | 0.2871 ± 0.0063 | 0.8266 ± 0.2365 | 53.1 ± 11.4 | 8.31 ± 0.18 |
| omegafold | 3 | 0.0422 ± 0.0256 | 0.2981 ± 0.0133 | 0.1016 ± 0.0421 | 0.4419 ± 0.0544 | 68.5 ± 12.3 | 1.40 ± 0.10 |
| chai1 | 3 | 0.0474 ± 0.0266 | 0.2745 ± 0.0233 | 0.1158 ± 0.0398 | 0.4376 ± 0.0431 | 63.5 ± 12.3 | 1.65 ± 0.30 |
| openfold | 3 | 0.0262 ± 0.0156 | 0.1800 ± 0.0082 | 0.0628 ± 0.0260 | 0.2689 ± 0.0363 | 68.0 ± 12.2 | 0.86 ± 0.06 |
| boltz2 | 3 | 0.0250 ± 0.0152 | 0.1035 ± 0.0149 | 0.0594 ± 0.0265 | 0.1879 ± 0.0556 | 57.3 ± 11.7 | 0.80 ± 0.01 |
| protenix | 3 | 0.0362 ± 0.0232 | 0.0986 ± 0.0106 | 0.0862 ± 0.0405 | 0.2210 ± 0.0596 | 47.7 ± 17.8 | 1.15 ± 0.03 |
| esmfold | 3 | 0.0229 ± 0.0124 | 0.0893 ± 0.0182 | 0.0547 ± 0.0204 | 0.1669 ± 0.0146 | 54.4 ± 16.5 | 0.76 ± 0.10 |

Stages present: inference, msa_build, msa_features. Per-stage and per-replicate breakdowns are in reps_device_energy_by_stage.csv and reps_device_energy_per_rep.csv.

## Accuracy consistency across replicates

Tolerance on lDDT-Ca: 0.001. Fixed-seed GPU nondeterminism alone moves lDDT by ~1e-4.

- **af2**: OK, max deviation 0.301579 (exempt: nondeterministic by design)
- **boltz2**: 45 VIOLATION(S), max deviation 0.104716
- **chai1**: 44 VIOLATION(S), max deviation 0.081816
- **colabfold**: 8 VIOLATION(S), max deviation 0.005486
- **esmfold**: OK, max deviation 0.000000
- **omegafold**: OK, max deviation 0.000000
- **openfold**: 39 VIOLATION(S), max deviation 0.088642
- **protenix**: 16 VIOLATION(S), max deviation 0.061623

Violations:

  - boltz2 / T1104: spread 0.016022 (rep1=0.933637|rep2=0.923872|rep3=0.939894)
  - boltz2 / T1106s1: spread 0.010660 (rep1=0.889271|rep2=0.882737|rep3=0.878611)
  - boltz2 / T1106s2: spread 0.001757 (rep1=0.947738|rep2=0.947958|rep3=0.946201)
  - boltz2 / T1112: spread 0.004969 (rep1=0.878679|rep2=0.876141|rep3=0.873710)
  - boltz2 / T1114s1: spread 0.038942 (rep1=0.754808|rep2=0.733173|rep3=0.715865)
  - boltz2 / T1114s2: spread 0.009878 (rep1=0.954138|rep2=0.953855|rep3=0.944259)
  - boltz2 / T1114s3: spread 0.005785 (rep1=0.974109|rep2=0.969023|rep3=0.968324)
  - boltz2 / T1120: spread 0.009356 (rep1=0.921229|rep2=0.914299|rep3=0.923654)
  - boltz2 / T1122: spread 0.044683 (rep1=0.435577|rep2=0.480260|rep3=0.454638)
  - boltz2 / T1129s2: spread 0.010995 (rep1=0.799392|rep2=0.788397|rep3=0.795139)
  - boltz2 / T1133: spread 0.002755 (rep1=0.918557|rep2=0.921311|rep3=0.918970)
  - boltz2 / T1134s1: spread 0.005290 (rep1=0.977473|rep2=0.980735|rep3=0.975445)
  - boltz2 / T1134s2: spread 0.002664 (rep1=0.836148|rep2=0.838812|rep3=0.837168)
  - boltz2 / T1137s1: spread 0.035972 (rep1=0.812512|rep2=0.804455|rep3=0.840427)
  - boltz2 / T1137s2: spread 0.016410 (rep1=0.890062|rep2=0.884955|rep3=0.873652)
  - boltz2 / T1137s3: spread 0.027785 (rep1=0.881915|rep2=0.854130|rep3=0.855433)
  - boltz2 / T1137s4: spread 0.015275 (rep1=0.824556|rep2=0.809281|rep3=0.821758)
  - boltz2 / T1137s5: spread 0.028618 (rep1=0.825129|rep2=0.853747|rep3=0.838029)
  - boltz2 / T1137s6: spread 0.021660 (rep1=0.817926|rep2=0.839587|rep3=0.831747)
  - boltz2 / T1137s7: spread 0.006492 (rep1=0.896516|rep2=0.902943|rep3=0.896450)
  - boltz2 / T1137s8: spread 0.007806 (rep1=0.952807|rep2=0.958800|rep3=0.950994)
  - boltz2 / T1137s9: spread 0.007035 (rep1=0.942757|rep2=0.935722|rep3=0.939780)
  - boltz2 / T1145: spread 0.004412 (rep1=0.930134|rep2=0.928395|rep3=0.925722)
  - boltz2 / T1147: spread 0.006260 (rep1=0.976239|rep2=0.978155|rep3=0.982499)
  - boltz2 / T1151s2: spread 0.016656 (rep1=0.880915|rep2=0.864259|rep3=0.870330)
  - boltz2 / T1155: spread 0.053332 (rep1=0.643553|rep2=0.611315|rep3=0.590221)
  - boltz2 / T1157s2: spread 0.011888 (rep1=0.916783|rep2=0.908508|rep3=0.920396)
  - boltz2 / T1159: spread 0.001861 (rep1=0.970658|rep2=0.971774|rep3=0.969913)
  - boltz2 / T1183: spread 0.008115 (rep1=0.946506|rep2=0.951985|rep3=0.954621)
  - boltz2 / T1185s1: spread 0.001440 (rep1=0.862044|rep2=0.861324|rep3=0.860605)
  - boltz2 / T1185s2: spread 0.010083 (rep1=0.822854|rep2=0.827510|rep3=0.832937)
  - boltz2 / T1185s4: spread 0.005361 (rep1=0.876502|rep2=0.873405|rep3=0.871141)
  - boltz2 / T1194: spread 0.015457 (rep1=0.961583|rep2=0.949654|rep3=0.965110)
  - boltz2 / T1212: spread 0.003851 (rep1=0.914376|rep2=0.910525|rep3=0.912716)
  - boltz2 / T1227s1: spread 0.002394 (rep1=0.899943|rep2=0.897884|rep3=0.897549)
  - boltz2 / T1266: spread 0.008982 (rep1=0.956621|rep2=0.947639|rep3=0.954477)
  - boltz2 / T1272s2: spread 0.025220 (rep1=0.838743|rep2=0.857580|rep3=0.863963)
  - boltz2 / T1272s3: spread 0.003917 (rep1=0.664223|rep2=0.668140|rep3=0.667135)
  - boltz2 / T1272s4: spread 0.022298 (rep1=0.760346|rep2=0.780735|rep3=0.782644)
  - boltz2 / T1272s5: spread 0.104716 (rep1=0.706335|rep2=0.683653|rep3=0.601619)
  - boltz2 / T1272s6: spread 0.011399 (rep1=0.867503|rep2=0.856104|rep3=0.861186)
  - boltz2 / T1272s7: spread 0.032659 (rep1=0.760113|rep2=0.727454|rep3=0.738727)
  - boltz2 / T1272s9: spread 0.025687 (rep1=0.815719|rep2=0.836136|rep3=0.841406)
  - boltz2 / T1280: spread 0.016075 (rep1=0.952426|rep2=0.956088|rep3=0.940013)
  - boltz2 / T1299: spread 0.007218 (rep1=0.912777|rep2=0.919995|rep3=0.913114)
  - chai1 / T1104: spread 0.081816 (rep1=0.580868|rep2=0.575749|rep3=0.499052)
  - chai1 / T1106s1: spread 0.062586 (rep1=0.781637|rep2=0.723177|rep3=0.785763)
  - chai1 / T1106s2: spread 0.006478 (rep1=0.955314|rep2=0.948836|rep3=0.955204)
  - chai1 / T1112: spread 0.007613 (rep1=0.861213|rep2=0.865905|rep3=0.868826)
  - chai1 / T1114s1: spread 0.033654 (rep1=0.762019|rep2=0.795673|rep3=0.775962)
  - chai1 / T1114s2: spread 0.013773 (rep1=0.721495|rep2=0.728071|rep3=0.735268)
  - chai1 / T1114s3: spread 0.023660 (rep1=0.889403|rep2=0.865743|rep3=0.877967)
  - chai1 / T1120: spread 0.007565 (rep1=0.850427|rep2=0.852795|rep3=0.845230)
  - chai1 / T1122: spread 0.028959 (rep1=0.514480|rep2=0.495814|rep3=0.524774)
  - chai1 / T1129s2: spread 0.036502 (rep1=0.172483|rep2=0.208984|rep3=0.190625)
  - chai1 / T1133: spread 0.001171 (rep1=0.920278|rep2=0.921449|rep3=0.920829)
  - chai1 / T1134s1: spread 0.021337 (rep1=0.913948|rep2=0.935285|rep3=0.917254)
  - chai1 / T1134s2: spread 0.001077 (rep1=0.827703|rep2=0.827080|rep3=0.828157)
  - chai1 / T1137s1: spread 0.008389 (rep1=0.796919|rep2=0.804929|rep3=0.805308)
  - chai1 / T1137s2: spread 0.021574 (rep1=0.866135|rep2=0.887709|rep3=0.878758)
  - chai1 / T1137s3: spread 0.029397 (rep1=0.873791|rep2=0.880365|rep3=0.903188)
  - chai1 / T1137s4: spread 0.014609 (rep1=0.729751|rep2=0.723845|rep3=0.738455)
  - chai1 / T1137s5: spread 0.018090 (rep1=0.828737|rep2=0.846827|rep3=0.840451)
  - chai1 / T1137s6: spread 0.019666 (rep1=0.798486|rep2=0.818153|rep3=0.808093)
  - chai1 / T1137s7: spread 0.004143 (rep1=0.829505|rep2=0.825884|rep3=0.825362)
  - chai1 / T1137s9: spread 0.004793 (rep1=0.863173|rep2=0.865608|rep3=0.867965)
  - chai1 / T1145: spread 0.003478 (rep1=0.611777|rep2=0.608299|rep3=0.608543)
  - chai1 / T1147: spread 0.020184 (rep1=0.921180|rep2=0.941364|rep3=0.922458)
  - chai1 / T1151s2: spread 0.028176 (rep1=0.815691|rep2=0.787516|rep3=0.794676)
  - chai1 / T1155: spread 0.036997 (rep1=0.592276|rep2=0.579727|rep3=0.555279)
  - chai1 / T1157s2: spread 0.023124 (rep1=0.895524|rep2=0.918648|rep3=0.901632)
  - chai1 / T1159: spread 0.033251 (rep1=0.670037|rep2=0.655645|rep3=0.636787)
  - chai1 / T1183: spread 0.007856 (rep1=0.940097|rep2=0.946351|rep3=0.938495)
  - chai1 / T1185s1: spread 0.026871 (rep1=0.852927|rep2=0.836372|rep3=0.863244)
  - chai1 / T1185s2: spread 0.007352 (rep1=0.830451|rep2=0.837803|rep3=0.830661)
  - chai1 / T1185s4: spread 0.004391 (rep1=0.847245|rep2=0.849926|rep3=0.851636)
  - chai1 / T1194: spread 0.060287 (rep1=0.866149|rep2=0.805862|rep3=0.822601)
  - chai1 / T1212: spread 0.008486 (rep1=0.746518|rep2=0.754935|rep3=0.755004)
  - chai1 / T1227s1: spread 0.016140 (rep1=0.885065|rep2=0.875824|rep3=0.891964)
  - chai1 / T1266: spread 0.015514 (rep1=0.717610|rep2=0.730709|rep3=0.715195)
  - chai1 / T1272s2: spread 0.014566 (rep1=0.844992|rep2=0.845891|rep3=0.831325)
  - chai1 / T1272s3: spread 0.036360 (rep1=0.791382|rep2=0.757935|rep3=0.794295)
  - chai1 / T1272s4: spread 0.011752 (rep1=0.851848|rep2=0.863600|rep3=0.861691)
  - chai1 / T1272s5: spread 0.019484 (rep1=0.848221|rep2=0.851719|rep3=0.867706)
  - chai1 / T1272s6: spread 0.012045 (rep1=0.808232|rep2=0.796187|rep3=0.801409)
  - chai1 / T1272s7: spread 0.012931 (rep1=0.628150|rep2=0.623176|rep3=0.636107)
  - chai1 / T1272s9: spread 0.015546 (rep1=0.827395|rep2=0.811849|rep3=0.815919)
  - chai1 / T1280: spread 0.011151 (rep1=0.960077|rep2=0.956739|rep3=0.967890)
  - chai1 / T1299: spread 0.026376 (rep1=0.951228|rep2=0.929034|rep3=0.955410)
  - colabfold / T1104: spread 0.001043 (rep1=0.879314|rep2=0.880356|rep3=0.879314)
  - colabfold / T1106s1: spread 0.001032 (rep1=0.877579|rep2=0.877235|rep3=0.876547)
  - colabfold / T1122: spread 0.005486 (rep1=0.457127|rep2=0.462613|rep3=0.457410)
  - colabfold / T1151s2: spread 0.001245 (rep1=0.890411|rep2=0.891656|rep3=0.891656)
  - colabfold / T1212: spread 0.003551 (rep1=0.919749|rep2=0.923231|rep3=0.923300)
  - colabfold / T1272s3: spread 0.001406 (rep1=0.809060|rep2=0.810165|rep3=0.808759)
  - colabfold / T1272s4: spread 0.001607 (rep1=0.839494|rep2=0.841101|rep3=0.840599)
  - colabfold / T1272s5: spread 0.005196 (rep1=0.843125|rep2=0.846922|rep3=0.841727)
  - openfold / T1104: spread 0.088642 (rep1=0.875427|rep2=0.893250|rep3=0.804608)
  - openfold / T1106s1: spread 0.008253 (rep1=0.872765|rep2=0.878611|rep3=0.870358)
  - openfold / T1106s2: spread 0.001537 (rep1=0.945982|rep2=0.947519|rep3=0.946970)
  - openfold / T1114s1: spread 0.002404 (rep1=0.866827|rep2=0.865865|rep3=0.864423)
  - openfold / T1114s2: spread 0.001185 (rep1=0.910110|rep2=0.909009|rep3=0.908924)
  - openfold / T1114s3: spread 0.003733 (rep1=0.937541|rep2=0.933808|rep3=0.934150)
  - openfold / T1120: spread 0.011435 (rep1=0.886406|rep2=0.895588|rep3=0.897840)
  - openfold / T1122: spread 0.022398 (rep1=0.400339|rep2=0.417251|rep3=0.394853)
  - openfold / T1129s2: spread 0.047512 (rep1=0.690422|rep2=0.712587|rep3=0.665075)
  - openfold / T1134s1: spread 0.002425 (rep1=0.938944|rep2=0.940443|rep3=0.941368)
  - openfold / T1137s1: spread 0.023507 (rep1=0.900142|rep2=0.876635|rep3=0.897725)
  - openfold / T1137s2: spread 0.013541 (rep1=0.938260|rep2=0.924719|rep3=0.936137)
  - openfold / T1137s3: spread 0.007256 (rep1=0.896428|rep2=0.903684|rep3=0.896862)
  - openfold / T1137s4: spread 0.005995 (rep1=0.855240|rep2=0.849245|rep3=0.854130)
  - openfold / T1137s5: spread 0.001137 (rep1=0.922845|rep2=0.921708|rep3=0.922202)
  - openfold / T1137s6: spread 0.001178 (rep1=0.902211|rep2=0.903390|rep3=0.902800)
  - openfold / T1137s7: spread 0.003817 (rep1=0.875408|rep2=0.878735|rep3=0.879225)
  - openfold / T1145: spread 0.001667 (rep1=0.919814|rep2=0.918147|rep3=0.918420)
  - openfold / T1147: spread 0.001788 (rep1=0.958099|rep2=0.956311|rep3=0.957971)
  - openfold / T1151s2: spread 0.002958 (rep1=0.886675|rep2=0.884496|rep3=0.887453)
  - openfold / T1155: spread 0.003462 (rep1=0.611856|rep2=0.615318|rep3=0.612830)
  - openfold / T1157s2: spread 0.010559 (rep1=0.905664|rep2=0.907249|rep3=0.916224)
  - openfold / T1159: spread 0.001117 (rep1=0.961228|rep2=0.961352|rep3=0.960236)
  - openfold / T1183: spread 0.010492 (rep1=0.950382|rep2=0.960203|rep3=0.949711)
  - openfold / T1185s1: spread 0.001679 (rep1=0.864683|rep2=0.863964|rep3=0.865643)
  - openfold / T1185s2: spread 0.003501 (rep1=0.852437|rep2=0.855938|rep3=0.852892)
  - openfold / T1185s4: spread 0.001387 (rep1=0.875716|rep2=0.874515|rep3=0.875901)
  - openfold / T1194: spread 0.006862 (rep1=0.964726|rep2=0.967034|rep3=0.960172)
  - openfold / T1212: spread 0.003644 (rep1=0.930749|rep2=0.931879|rep3=0.928235)
  - openfold / T1227s1: spread 0.001133 (rep1=0.909880|rep2=0.908773|rep3=0.909905)
  - openfold / T1272s2: spread 0.011913 (rep1=0.860592|rep2=0.871606|rep3=0.859693)
  - openfold / T1272s3: spread 0.019586 (rep1=0.796103|rep2=0.815689|rep3=0.799217)
  - openfold / T1272s4: spread 0.009140 (rep1=0.858076|rep2=0.854058|rep3=0.848935)
  - openfold / T1272s5: spread 0.005096 (rep1=0.840627|rep2=0.843225|rep3=0.845723)
  - openfold / T1272s6: spread 0.001320 (rep1=0.863348|rep2=0.864668|rep3=0.864359)
  - openfold / T1272s7: spread 0.002818 (rep1=0.760610|rep2=0.759118|rep3=0.761936)
  - openfold / T1272s9: spread 0.007673 (rep1=0.879637|rep2=0.871964|rep3=0.878436)
  - openfold / T1280: spread 0.012657 (rep1=0.924426|rep2=0.932688|rep3=0.937083)
  - openfold / T1299: spread 0.001147 (rep1=0.950216|rep2=0.950958|rep3=0.949811)
  - protenix / T1104: spread 0.061623 (rep1=0.791619|rep2=0.830774|rep3=0.769151)
  - protenix / T1114s1: spread 0.001442 (rep1=0.830288|rep2=0.831731|rep3=0.830288)
  - protenix / T1122: spread 0.013122 (rep1=0.448982|rep2=0.454977|rep3=0.441855)
  - protenix / T1129s2: spread 0.007031 (rep1=0.663701|rep2=0.660475|rep3=0.667506)
  - protenix / T1137s3: spread 0.004403 (rep1=0.878814|rep2=0.883218|rep3=0.881915)
  - protenix / T1137s4: spread 0.003153 (rep1=0.846226|rep2=0.846403|rep3=0.843250)
  - protenix / T1137s5: spread 0.006079 (rep1=0.889037|rep2=0.895117|rep3=0.891212)
  - protenix / T1137s6: spread 0.001541 (rep1=0.890973|rep2=0.890203|rep3=0.891744)
  - protenix / T1137s7: spread 0.001533 (rep1=0.878279|rep2=0.876778|rep3=0.878311)
  - protenix / T1145: spread 0.001480 (rep1=0.940770|rep2=0.942250|rep3=0.942221)
  - protenix / T1183: spread 0.001189 (rep1=0.961650|rep2=0.962839|rep3=0.961857)
  - protenix / T1272s2: spread 0.008901 (rep1=0.860951|rep2=0.869808|rep3=0.869853)
  - protenix / T1272s3: spread 0.004821 (rep1=0.764665|rep2=0.760647|rep3=0.759843)
  - protenix / T1272s4: spread 0.001607 (rep1=0.817497|rep2=0.817296|rep3=0.815890)
  - protenix / T1272s5: spread 0.003697 (rep1=0.772982|rep2=0.769984|rep3=0.773681)
  - protenix / T1272s7: spread 0.001658 (rep1=0.736737|rep2=0.735908|rep3=0.737566)

## MSA attribution drift

- **note** af2: charged in [rep1], uncharged in [rep2|rep3]

## Dropped (target, model) pairs

None: every pair succeeded in every replicate.

# Chignolin Example

```bash
mkdir -p data/sequences data/references data/predictions data/scores logs

cat > data/sequences/1UAO_chignolin.fasta << 'EOF_FASTA'
>1UAO_chignolin
GYDPETGTWG
EOF_FASTA

wget https://files.rcsb.org/download/1UAO.pdb -O data/references/1UAO_raw.pdb

python scripts/prepare_reference_model1.py \
  --input data/references/1UAO_raw.pdb \
  --output data/references/1UAO_model1_chainA.pdb \
  --chain A

python scripts/01_predict_top5.py \
  --target-id 1UAO_chignolin \
  --fasta data/sequences/1UAO_chignolin.fasta \
  --top-k 5

python scripts/02_score_predictions.py \
  --target-id 1UAO_chignolin \
  --reference data/references/1UAO_model1_chainA.pdb \
  --ref-chain A \
  --pred-chain A
```

# Shared AF2/OpenFold Database Notes

Full local MSA/template protocols for AlphaFold2-style backends need a database
root outside this Git repository. Do not download these databases into
`models/`, `data/`, or any other tracked project path.

Example database root:

```bash
export AF2_OPENFOLD_DB_ROOT=/media/$USER/AFDB/alphafold_databases
# or
export AF2_OPENFOLD_DB_ROOT=$HOME/databases/alphafold
```

Expected database types for full or reduced AF2/OpenFold protocols include:

- UniRef90
- MGnify
- BFD or small_BFD
- UniRef30 or Uniclust30
- PDB70
- PDB mmCIF templates
- obsolete PDBs file

Approximate storage requirements:

| Setup | Rough size |
|---|---:|
| Reduced AF2/OpenFold databases | hundreds of GB, roughly 600 GB |
| Full AF2/OpenFold databases | roughly 2 TB or more |

Current status:

- The current local machine has insufficient free disk space for these database
  trees.
- MSA-heavy protocols are paused until external storage is available.
- OpenFold is installed and can run single-sequence smoke mode, but true MSA
  mode needs these database paths.
- AlphaFold2, OpenFold3, and AlphaFold3 remain disabled/future backends.

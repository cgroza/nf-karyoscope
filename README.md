# nf-karyoscope

A Nextflow DSL2 pipeline for annotating **haplotype-resolved assemblies** with
[KaryoScope](https://github.com/barthel-lab/KaryoScope). Each sample/haplotype is
an independent task; contig names and input sequence order are preserved. The
pipeline annotates assemblies, not reads, and does not phase, scaffold, or render
karyotypes.

```text
samplesheet -> validate all rows -> annotate each haplotype -> BED tracks
                                   ^
                     existing database OR one shared download
```

## Requirements

- Nextflow >=25.10.0 and a compatible Java runtime, installed on the host.
- Docker, Apptainer, or a local KaryoScope installation.
- A FASTA (`.fa`, `.fasta`, `.fna`, optionally `.gz`) per haplotype.
- Storage for the database, task outputs, and published result copies.

The Dockerfile includes Python 3.12, KaryoScope 2.3.0 and its Python dependencies,
HKS 0.4.0 (pinned to a source commit, built with its submodules and Cargo lockfile),
the compiled C++20 KMC query helper, KMC, samtools, bgzip/tabix, seqtk, Cairo,
and the required system libraries and utilities. **It does not include Nextflow
or Java.** No reference database is baked into the image.

KaryoScope and HKS source versions are pinned; the base-image tags, Debian
packages, and Python transitive dependencies are not fully locked. For production,
publish the image and supply its immutable digest with `--container`.
The image has not been built or validated yet.

## Samplesheet

Use the following CSV columns:

```csv
sample,haplotype,assembly
HG002,hap1,/data/assemblies/HG002.hap1.fasta.gz
HG002,hap2,/data/assemblies/HG002.hap2.fasta.gz
HG003,mat,/data/assemblies/HG003.mat.fasta.gz
HG003,pat,/data/assemblies/HG003.pat.fasta.gz
```

See [`assets/samplesheet.csv`](assets/samplesheet.csv). Paths may be absolute,
relative to the samplesheet directory, or Nextflow-supported remote URIs.
CSV quoting is supported. Sample and haplotype identifiers must start with a
letter or digit and contain only letters, digits, `_`, or `-`; pairs must be
unique. Haplotype labels are user-defined, and any number per sample is allowed.
Use separate FASTAs, rather than a concatenated diploid assembly, to retain
haplotype identity in published results.

## Running

The default image name is `nf-karyoscope:0.1.0`. The Dockerfile is provided, but
**no image has been built or published**. Once an image is available:

```bash
nextflow run main.nf \
    -profile docker \
    --input samplesheet.csv \
    --container your-registry/nf-karyoscope:0.1.0 \
    --db HKS_human_CHM13_v2 \
    --outdir results \
    -resume
```

Without `--db_dir`, the pipeline downloads the explicitly selected database
**once**, using KaryoScope's checksum verification, into the Nextflow work
directory. Keep that work directory to reuse the download with `-resume`.
It deliberately selects HKS instead of KaryoScope's current KMC default.

To reuse an extracted local database without downloading:

```bash
nextflow run main.nf \
    -profile docker \
    --input samplesheet.csv \
    --db HKS_human_CHM13_v2 \
    --db_dir /references/karyoscope/HKS_human_CHM13_v2 \
    --feature_sets chromosome,region,repeat \
    --outdir results \
    -resume
```

`--db_dir` is the directory **containing `manifest.yaml`**, not its parent
database root and not a tarball. Its manifest ID must match `--db`. Each task
validates the database layout and requested feature sets, then creates a private
registry pointing to the staged read-only index. The shared database and its
original registry are never modified, and the index is not copied per haplotype.

Use `-profile apptainer` with a published registry image, or `-profile local`
when KaryoScope and its backend helpers are installed on the host. For a cluster,
override `process.executor` and scheduler options in a site-specific config:

```bash
nextflow run main.nf -profile apptainer -c cluster.config \
    --input samplesheet.csv \
    --container your-registry/nf-karyoscope:0.1.0 \
    --db_dir /references/karyoscope/HKS_human_CHM13_v2 -resume
```

For remote execution, the executor must support directory staging and all
workers must be able to access the database. The local/shared-filesystem model
avoids copying the large index; object-storage executors may transfer it per task.

## Parameters and resource planning

| Parameter | Default | Purpose |
|---|---|---|
| `--input` | required | Samplesheet CSV |
| `--db` | `HKS_human_CHM13_v2` | Explicit database ID |
| `--db_dir` | unset | Existing extracted database; otherwise download once |
| `--feature_sets` | all | Comma-separated feature sets |
| `--smooth` | `true` | Produce hierarchy-smoothed tracks |
| `--keep_presmoothed` | `true` | Also retain raw tracks |
| `--bgzip` | `true` | Compress output BEDs |
| `--outdir` | `results` | Published results |
| `--cpus` | `16` | CPUs per haplotype task |
| `--memory` | `16 GB` | Memory per haplotype task |
| `--time` | `4h` | Scheduler time limit per haplotype task |
| `--max_parallel` | `2` | Maximum concurrent annotation tasks |
| `--container` | `nf-karyoscope:0.1.0` | Image reference |

Pass boolean values explicitly, e.g. `--keep_presmoothed false`. At least one
output variant must be enabled. KaryoScope's resource checks remain enabled;
failures terminate the run rather than silently skipping a haplotype.

The upstream README reports approximately 7-9 minutes at 16 threads and a 10 GB
memory peak for a human haplotype with HKS. The defaults request 16 GB **per
task**, so two concurrent tasks require about 32 GB and 32 CPUs. Actual runtimes
depend on storage and hardware. For the legacy `KS_human_CHM13_v2` KMC database,
set `--memory '96 GB'` or more; the pipeline does not automatically infer memory
from the database.

Allow approximately **36 GB free to install the HKS human database** and
**15 GB of uncompressed BED output per haplotype** for six feature sets, with
additional headroom for temporary files. Compression happens after BEDs are
written and does not eliminate peak disk usage. Published files are copied from
the work directory, so budget for both work files and result copies. Reduce output
with `--feature_sets` or `--keep_presmoothed false`.

## Outputs

```text
results/
  annotations/
    HG002/
      hap1/
        annotation/
          <assembly>.<database>.<feature_set>.presmoothed.bed.gz
          <assembly>.<database>.<feature_set>.smoothed.bed.gz
        database_manifest.yaml
        versions.txt
        karyoscope.log
      hap2/
        ...
  pipeline_info/
    report.html
    timeline.html
    trace.tsv
    dag.html
```

BED names follow KaryoScope's input-basename convention, while the containing
directories identify the sample and haplotype. Coordinates refer to the original
assembly contigs, not reference chromosome coordinates; the fourth column is the
feature label. These are k-mer interval tracks: do not assume every contig's last
`k-1` bases are represented. No tabix index is promised by this pipeline.
When `--bgzip false` is used, the BEDs are plain `.bed` files.

Nextflow keeps process commands, logs, and downloaded databases in `work/`.
An annotation failure is reported by Nextflow; inspect the failing task's
`.command.log` and `karyoscope.log`. The download log stays in its work task.
Do not clean the work directory before a resumed run. Use separate output and
work directories for simultaneous runs to avoid overwriting reports/results.
Treat assembly and database files as immutable when resuming: use a new database
directory/version after rebuilding an index rather than modifying cached inputs
in place.

## Development

No container is needed for the stub checks:

```bash
python -m unittest discover -s tests -v
# Or: NEXTFLOW=/path/to/nextflow python -m unittest discover -s tests -v
```

They exercise two-haplotype wiring, single database download, publication,
output switches, and invalid samplesheets. Stub BEDs are empty placeholders,
not biological annotation.

Optional real integration tests use KaryoScope's tiny bundled synthetic KMC
database; they check exact smoothed BED content, resumption, gzip inputs,
output switches, and read-only database reuse:

```bash
# With KaryoScope, its compiled KMC helper, and bgzip installed:
# Extract KaryoScope's tests/data/dummy_db.tar.gz into a temporary directory.
export KARYOSCOPE_TEST_DB=/path/to/extracted/KS_dummy_test_v1
python -m unittest discover -s tests -v
```

CI runs both stub and real synthetic-database tests without building a Docker
image. The HKS backend and container require separate production validation.

## License and citation

The pipeline code is MIT licensed. KaryoScope 2.3.0 and the KMC helper are
GPL-3.0-or-later; HKS is MIT licensed. Their licenses continue to apply to the
software distributed in the container.

Cite KaryoScope when using these annotations:
[Ranallo-Benavidez et al., bioRxiv (2026)](https://doi.org/10.64898/2026.05.15.725544),
and [Nextflow](https://doi.org/10.1038/nbt.3820) for workflow execution.

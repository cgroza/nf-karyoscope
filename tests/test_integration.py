"""Optional real KMC smoke test against the upstream synthetic database."""

import csv
import gzip
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXTFLOW = os.environ.get("NEXTFLOW", shutil.which("nextflow"))
DATABASE = os.environ.get("KARYOSCOPE_TEST_DB")


@unittest.skipUnless(NEXTFLOW and DATABASE, "Set NEXTFLOW and KARYOSCOPE_TEST_DB for real annotation.")
class IntegrationTests(unittest.TestCase):
    def test_annotation_and_resume(self):
        with tempfile.TemporaryDirectory(prefix="nf-karyoscope-integration-") as directory:
            output = Path(directory) / "results"
            command = [
                NEXTFLOW, "run", str(ROOT / "main.nf"),
                "-profile", "local", "-ansi-log", "false",
                "--input", str(ROOT / "tests/data/samplesheet.csv"),
                "--db", "KS_dummy_test_v1", "--db_dir", DATABASE,
                "--cpus", "1", "--memory", "1 GB", "--outdir", str(output),
            ]
            original_files = sorted(str(path) for path in Path(DATABASE).rglob("*"))
            for resume in (False, True):
                result = subprocess.run(
                    command + (["-resume"] if resume else []),
                    cwd=directory, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, timeout=180, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                if resume:
                    trace = (output / "pipeline_info/trace.tsv").read_text()
                    self.assertEqual(trace.count("CACHED"), 2)

            expected = {
                "chromosome": (
                    "contig_with_features\t0\t2\tchr1\n"
                    "contig_with_features\t2\t3\tchr2\n"
                    "contig_novel\t0\t10\tnovel\n"
                ),
                "region": (
                    "contig_with_features\t0\t1\trA\n"
                    "contig_with_features\t1\t2\trB\n"
                    "contig_with_features\t2\t3\trC\n"
                    "contig_novel\t0\t10\tnovel\n"
                ),
            }
            for haplotype in ("hap1", "hap2"):
                beds = output / "annotations/TEST" / haplotype / "annotation"
                self.assertEqual(len(list(beds.glob("*.bed.gz"))), 4)
                for feature, text in expected.items():
                    bed = next(beds.glob(f"*.{feature}.smoothed.bed.gz"))
                    with gzip.open(bed, "rt") as handle:
                        self.assertEqual(handle.read(), text)
            self.assertEqual(original_files, sorted(str(path) for path in Path(DATABASE).rglob("*")))

    def test_manifest_and_features_are_checked(self):
        for db_id, features, message in (
            ("wrong_id", [], "manifest declares"),
            ("KS_dummy_test_v1", ["--feature-set", "missing"], "Feature sets absent"),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(
                    [
                        sys.executable, str(ROOT / "bin/prepare_database.py"),
                        "--source", DATABASE, "--root", str(Path(directory) / "registry"),
                        "--db", db_id, *features,
                    ],
                    cwd=directory, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, timeout=30, check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout)

    def test_gzipped_input_and_output_switches(self):
        for arguments, suffix in (
            (["--keep_presmoothed", "false", "--bgzip", "false"], "smoothed.bed"),
            (["--smooth", "false"], "presmoothed.bed.gz"),
        ):
            with self.subTest(arguments=arguments), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                assembly = directory / "assembly with quote's.fa.gz"
                with gzip.open(assembly, "wt") as handle:
                    handle.write((ROOT / "tests/data/hap1.fa").read_text())
                sheet = directory / "samplesheet.csv"
                with sheet.open("w", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(["sample", "haplotype", "assembly"])
                    writer.writerow(["TEST", "hap1", assembly.name])
                result = subprocess.run(
                    [
                        NEXTFLOW, "run", str(ROOT / "main.nf"),
                        "-profile", "local", "-ansi-log", "false",
                        "--input", str(sheet), "--db", "KS_dummy_test_v1",
                        "--db_dir", DATABASE, "--feature_sets", "chromosome",
                        "--cpus", "1", "--memory", "1 GB",
                        "--outdir", str(directory / "results"), *arguments,
                    ],
                    cwd=directory, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, timeout=180, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout)
                beds = list((directory / "results/annotations").rglob("*.bed*"))
                self.assertEqual(len(beds), 1)
                self.assertTrue(beds[0].name.endswith(suffix))
                if suffix.endswith(".gz"):
                    with gzip.open(beds[0], "rt") as handle:
                        text = handle.read()
                else:
                    text = beds[0].read_text()
                self.assertIn("contig_with_features\t0\t2\tchr1\n", text)

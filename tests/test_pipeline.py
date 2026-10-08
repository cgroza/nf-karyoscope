"""Exercise Nextflow wiring and input validation without building a container."""

import csv
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXTFLOW = os.environ.get("NEXTFLOW", shutil.which("nextflow"))


@unittest.skipUnless(NEXTFLOW, "Install Nextflow or set NEXTFLOW to its executable.")
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nf-karyoscope-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def run_pipeline(self, *arguments):
        return subprocess.run(
            [
                NEXTFLOW, "run", str(ROOT / "main.nf"),
                "-profile", "local", "-stub-run", "-ansi-log", "false",
                "--cpus", "1", "--memory", "1 GB",
                "--outdir", str(self.directory / "results"),
                *arguments,
            ],
            cwd=self.directory,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )

    def sheet(self, rows, header=("sample", "haplotype", "assembly")):
        sheet = self.directory / "samplesheet.csv"
        with sheet.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        return sheet

    def test_local_database_two_haplotypes(self):
        result = self.run_pipeline(
            "--input", str(ROOT / "tests/data/samplesheet.csv"),
            "--db_dir", str(ROOT / "tests/data"),
            "--feature_sets", "chromosome,region",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        for haplotype in ("hap1", "hap2"):
            output = self.directory / "results/annotations/TEST" / haplotype
            self.assertEqual(len(list(output.rglob("*.bed.gz"))), 4)
            self.assertTrue((output / "database_manifest.yaml").is_file())
            self.assertTrue((output / "versions.txt").is_file())
        self.assertNotIn("process > DOWNLOAD_DATABASE", result.stdout)

    def test_download_once_and_smoothed_only(self):
        result = self.run_pipeline(
            "--input", str(ROOT / "tests/data/samplesheet.csv"),
            "--keep_presmoothed", "false", "--bgzip", "false",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        beds = list((self.directory / "results/annotations").rglob("*.bed"))
        self.assertEqual(len(beds), 2)
        self.assertTrue(all(".smoothed.bed" in bed.name for bed in beds))
        trace = (self.directory / "results/pipeline_info/trace.tsv").read_text()
        self.assertEqual(trace.count("DOWNLOAD_DATABASE ("), 1)

    def test_invalid_samplesheets(self):
        assembly = str(ROOT / "tests/data/hap1.fa")
        cases = [
            ([("TEST", "hap1", assembly), ("TEST", "hap1", assembly)],
             ("sample", "haplotype", "assembly"), "Duplicate sample/haplotype"),
            ([("bad/sample", "hap1", assembly)],
             ("sample", "haplotype", "assembly"), "Sample and haplotype identifiers"),
            ([("TEST", "hap1", "missing.fa")],
             ("sample", "haplotype", "assembly"), "missing.fa"),
            ([("TEST", "hap1", assembly)],
             ("sample", "phase", "assembly"), "must have columns"),
            ([], ("sample", "haplotype", "assembly"), "at least one assembly"),
        ]
        for rows, header, message in cases:
            with self.subTest(message=message):
                result = self.run_pipeline("--input", str(self.sheet(rows, header)))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(message, result.stdout)
                self.assertNotIn("process > DOWNLOAD_DATABASE", result.stdout)

    def test_no_output_variant_is_rejected(self):
        result = self.run_pipeline(
            "--input", str(ROOT / "tests/data/samplesheet.csv"),
            "--smooth", "false", "--keep_presmoothed", "false",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("At least one", result.stdout)

    def test_invalid_options_are_rejected(self):
        for arguments, message in (
            (["--bgzip", "maybe"], "--bgzip must be true or false"),
            (["--feature_sets", "chromosome,chromosome"], "unique, nonempty"),
            (["--feature_sets", "chromosome,"], "unique, nonempty"),
            (["--cpus", "0"], "positive integers"),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_pipeline(
                    "--input", str(ROOT / "tests/data/samplesheet.csv"), *arguments,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(message, result.stdout)


if __name__ == "__main__":
    unittest.main()

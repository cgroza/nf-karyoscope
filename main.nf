nextflow.enable.dsl = 2

include { DOWNLOAD_DATABASE } from './modules/download_database'
include { ANNOTATE } from './modules/annotate'

def usage() {
    return '''
nf-karyoscope: annotate haplotype-resolved assemblies with KaryoScope

Usage:
  nextflow run main.nf --input samplesheet.csv -profile docker

Required:
  --input                 CSV with sample,haplotype,assembly columns

Database:
  --db                    Database ID (default: HKS_human_CHM13_v2)
  --db_dir                Existing database directory containing manifest.yaml;
                          omit to download --db once into the work directory

Annotation:
  --feature_sets          Comma-separated feature sets (default: all)
  --smooth                Produce smoothed tracks (default: true)
  --keep_presmoothed      Keep raw tracks (default: true)
  --bgzip                 Compress BED tracks (default: true)
  --outdir                Results directory (default: results)

Resources:
  --cpus                  CPUs per annotation task (default: 16)
  --memory                Memory per annotation task (default: 16 GB; use
                          96 GB or more for the legacy KMC human database)
  --time                  Time limit per annotation task (default: 4h)
  --max_parallel          Concurrent annotation tasks (default: 2)
  --container             Container image (default: nf-karyoscope:0.1.0)

Profiles: docker, apptainer, local (preinstalled dependencies)
Use -resume to reuse completed tasks. See README.md for storage requirements.
'''
}

def readAssemblies(sheet) {
    Channel.fromPath(sheet.toString(), checkIfExists: true)
        .splitCsv(header: true, strip: true)
        .toList()
        .map { rows ->
            if (!rows) {
                error 'The samplesheet must contain at least one assembly.'
            }
            def required = ['sample', 'haplotype', 'assembly']
            if (!rows[0].keySet().containsAll(required)) {
                error "The samplesheet must have columns: ${required.join(',')}."
            }
            def seen = [] as Set
            rows.collect { row ->
                def sample = row.sample?.trim()
                def haplotype = row.haplotype?.trim()
                if (!(sample ==~ /[A-Za-z0-9][A-Za-z0-9_-]*/) ||
                    !(haplotype ==~ /[A-Za-z0-9][A-Za-z0-9_-]*/)) {
                    error 'Sample and haplotype identifiers must start with a letter or digit and contain only letters, digits, underscores, or hyphens.'
                }
                if (!seen.add([sample, haplotype])) {
                    error "Duplicate sample/haplotype: ${sample}/${haplotype}."
                }
                if (!row.assembly?.trim()) {
                    error "Missing assembly for ${sample}/${haplotype}."
                }
                def assemblyName = row.assembly.trim()
                if (!(assemblyName ==~ /(?i).*\.(fa|fasta|fna)(\.gz)?/)) {
                    error "Assembly must be FASTA (.fa, .fasta, .fna, optionally .gz): ${assemblyName}."
                }
                def assembly = assemblyName.contains('://') ?
                    file(assemblyName, checkIfExists: true) :
                    file(sheet.parent.resolve(assemblyName).toString(), checkIfExists: true)
                if (!assembly.isFile()) {
                    error "Assembly is not a file: ${assembly}."
                }
                tuple([sample: sample, haplotype: haplotype], assembly)
            }
        }
        .flatMap { it }
}

def booleanParam(name, value) {
    if (value instanceof Boolean) {
        return value
    }
    if (value?.toString()?.toLowerCase() in ['true', 'false']) {
        return value.toString().equalsIgnoreCase('true')
    }
    error "--${name} must be true or false."
}

workflow {
    if (booleanParam('help', params.help)) {
        log.info usage()
        return
    }
    if (!params.input) {
        error 'Provide --input samplesheet.csv. Use --help for usage.'
    }
    if (!(params.db ==~ /[A-Za-z0-9][A-Za-z0-9_.-]*/)) {
        error 'Provide a valid database ID with --db.'
    }
    def options = [
        smooth: booleanParam('smooth', params.smooth),
        keep_presmoothed: booleanParam('keep_presmoothed', params.keep_presmoothed),
        bgzip: booleanParam('bgzip', params.bgzip),
    ]
    if (!options.smooth && !options.keep_presmoothed) {
        error 'At least one of --smooth or --keep_presmoothed must be true.'
    }
    if (!(params.cpus.toString() ==~ /[1-9][0-9]*/) ||
        !(params.max_parallel.toString() ==~ /[1-9][0-9]*/)) {
        error '--cpus and --max_parallel must be positive integers.'
    }
    def features = params.feature_sets ?
        params.feature_sets.toString().split(',', -1).collect { it.trim() } : []
    if (features.any { !(it ==~ /[A-Za-z0-9][A-Za-z0-9_.-]*/) } ||
        features.unique(false).size() != features.size()) {
        error '--feature_sets must contain unique, nonempty, comma-separated feature-set names.'
    }

    def sheet = file(params.input, checkIfExists: true)
    def assemblies = readAssemblies(sheet)
    def database
    if (params.db_dir) {
        def existing = file(params.db_dir, checkIfExists: true)
        if (!existing.isDirectory()) {
            error '--db_dir must be a database directory, not an archive or database root.'
        }
        database = Channel.value(existing)
    } else {
        // Validate the whole samplesheet before starting a large download.
        DOWNLOAD_DATABASE(assemblies.toList().map { params.db })
        database = DOWNLOAD_DATABASE.out.database
    }

    ANNOTATE(assemblies, database, params.db, features, options)
}

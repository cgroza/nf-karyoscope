process ANNOTATE {
    tag "${meta.sample}/${meta.haplotype}"
    cpus params.cpus
    memory params.memory
    time params.time
    maxForks params.max_parallel

    input:
    tuple val(meta), path(assembly)
    path reference, stageAs: 'reference'
    val db_id
    val features
    val options

    output:
    tuple val(meta), path('annotation/*.bed*'), emit: beds
    tuple val(meta), path('database_manifest.yaml'), emit: manifest
    tuple val(meta), path('versions.txt'), emit: versions
    tuple val(meta), path('karyoscope.log'), emit: log

    script:
    def featureArgs = features.collect { "--feature-set '${it}'" }.join(' ')
    def smoothArg = options.smooth ? '--smooth' : '--no-smooth'
    def rawArg = options.keep_presmoothed ? '--keep-presmoothed' : '--no-keep-presmoothed'
    def compressionArg = options.bgzip ? '--bgzip' : '--no-bgzip'
    """
    prepare_database.py \\
        --source '${reference}' --root task_db --db '${db_id}' ${featureArgs}
    karyoscope version > versions.txt
    karyoscope annotate \\
        --input '${assembly.toString().replace("'", "'\\''")}' \\
        --outdir annotation \\
        --db '${db_id}' --db-root task_db \\
        --threads ${task.cpus} \\
        --query-names --preserve-order \\
        ${smoothArg} ${rawArg} ${compressionArg} ${featureArgs} \\
        2>&1 | tee karyoscope.log
    """

    stub:
    def suffix = options.bgzip ? '.bed.gz' : '.bed'
    def stubFeatures = features ?: ['chromosome']
    def variants = (options.keep_presmoothed ? ['presmoothed'] : []) + (options.smooth ? ['smoothed'] : [])
    def files = stubFeatures.collectMany { feature ->
        variants.collect { variant ->
            "'annotation/${meta.sample}.${meta.haplotype}.${db_id}.${feature}.${variant}${suffix}'"
        }
    }.join(' ')
    """
    mkdir -p annotation
    touch ${files}
    printf 'id: ${db_id}\\n' > database_manifest.yaml
    printf 'Stub execution; no biological annotation performed.\\n' > versions.txt
    touch karyoscope.log
    """
}

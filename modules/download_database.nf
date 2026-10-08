process DOWNLOAD_DATABASE {
    tag "${db_id}"
    cpus 1
    memory '2 GB'
    time '12h'

    input:
    val db_id

    output:
    path "database/${db_id}", emit: database
    path 'download.log', emit: log

    script:
    """
    karyoscope download '${db_id}' --db-root database 2>&1 | tee download.log
    """

    stub:
    """
    mkdir -p 'database/${db_id}'
    touch 'database/${db_id}/manifest.yaml' download.log
    """
}

FROM rust:1.90.0-bookworm AS hks_builder

ARG HKS_COMMIT=04bbc5260e37ff8874ffd13f4dfe77a52fedd331

RUN apt-get update \
    && apt-get install -y --no-install-recommends cmake libbz2-dev zlib1g-dev \
    && git clone https://github.com/jnalanko/HKS.git /opt/HKS \
    && git -C /opt/HKS checkout "${HKS_COMMIT}" \
    && git -C /opt/HKS submodule update --init --recursive \
    && cargo install --locked --path /opt/HKS --root /opt/hks

FROM python:3.12-slim-bookworm

ARG KARYOSCOPE_REF=v2.3.0
LABEL org.opencontainers.image.title="nf-karyoscope" \
      org.opencontainers.image.description="KaryoScope 2.3.0 with HKS 0.4.0 and the legacy KMC helper; no Nextflow" \
      org.opencontainers.image.source="https://github.com/cgroza/nf-karyoscope"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    KARYOSCOPE_GET_FEATUREIDS=/opt/KaryoScope/native/get_featureIDs/build/get_featureIDs \
    KARYOSCOPE_HKS=/usr/local/bin/hks

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash build-essential ca-certificates git pkg-config procps \
        gzip tar \
        zlib1g-dev libbz2-1.0 liblzma5 libcairo2 libffi8 \
        samtools tabix seqtk kmc \
    && git clone --depth 1 --branch "${KARYOSCOPE_REF}" \
        https://github.com/barthel-lab/KaryoScope.git /opt/KaryoScope \
    && make -C /opt/KaryoScope/native/get_featureIDs -j2 \
    && python -m pip install /opt/KaryoScope

COPY --from=hks_builder /opt/hks/bin/hks /usr/local/bin/hks
COPY --from=hks_builder /opt/HKS/LICENSE /usr/local/share/licenses/hks/LICENSE

WORKDIR /data
CMD ["karyoscope", "--help"]

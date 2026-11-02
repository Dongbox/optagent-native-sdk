# GCC 10.2.1 / glibc 2.17; tool upgrades are explicit source changes.
FROM quay.io/pypa/manylinux2014_x86_64@sha256:3132b11674b649393fb3de60cc88a3788509e65b90b7984f7e2f6eb491102ca3
ENV PATH=/opt/python/cp312-cp312/bin:$PATH
COPY requirements-producer.lock /tmp/requirements-producer.lock
RUN python -m pip install --require-hashes -r /tmp/requirements-producer.lock
WORKDIR /workspace

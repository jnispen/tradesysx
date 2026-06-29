# Test harness for the exported tradesysx package.
#
# Builds an image that unzips a tradesysx-*.zip (as produced by
# scripts/export_package.sh), installs requirements.txt, and lets you
# run the pipeline in isolation.
#
# Usage:
#   scripts/export_package.sh test
#   docker build -t tradesysx-test -f scripts/Dockerfile \
#       --build-arg ZIP_FILE=tradesysx-test.zip dist/
#   docker run --rm -it tradesysx-test
#
# To inspect the generated out/ directory after the run, mount it to
# the host (otherwise it's removed with the container on exit):
#   docker run --rm -v /tmp/tradesysx-out:/app/tradesysx/out tradesysx-test
#
# To edit config files, run the pipeline manually, and inspect files
# from a shell inside the container:
#   docker run --rm -it --entrypoint bash tradesysx-test
#   # edit config/system_conf.json, then:
#   python tradesysx.py
#   ls out/

FROM python:3.12-slim

# Build tools for TA-Lib, runtime libs for WeasyPrint, unzip for the export
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    unzip \
    vim \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# TA-Lib C library (required by the TA-Lib pip package)
RUN wget -q https://github.com/ta-lib/ta-lib/releases/download/v0.4.0/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib \
    && ./configure --prefix=/usr \
    && make \
    && make install \
    && cd .. \
    && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

WORKDIR /app

ARG ZIP_FILE
COPY ${ZIP_FILE} /tmp/tradesysx.zip
# Unzips to /app/tradesysx/ (the zip's tradesysx/ prefix), kept as a
# subdirectory so `tradesysx.py`'s `from tradesysx import utils` absolute
# imports resolve `tradesysx` to this package directory.
RUN unzip /tmp/tradesysx.zip -d . \
    && rm -f /tmp/tradesysx.zip

WORKDIR /app/tradesysx

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "tradesysx.py"]

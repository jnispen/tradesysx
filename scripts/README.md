##  Running `tradesysx` from a Docker container

Below is a description on how to package and run `tradesysx` from a Docker container. It was added as a simple way to test or try-out the software.

### export_package.sh

Packages the current `HEAD` commit into a zip archive for sharing with a collaborator.

```sh
scripts/export_package.sh <label>
```

- `<label>` is a free-text version label used in the output filename, e.g. `scripts/export_package.sh v0.1` produces `dist/tradesysx-v0.1.zip`.
- The archive extracts into a top-level `tradesysx/` directory.
- Only files committed to `HEAD` are included. Files marked `export-ignore` in `.gitattributes` are excluded.
- If the working tree has uncommitted changes, the script prints a warning (via `git status --porcelain`) but still archives `HEAD` — commit first if those changes should be included.

The recipient should unzip the archive and follow the setup steps in `tradesysx/README.md` (`pip install -r requirements.txt`, etc.).

### Dockerfile

Tests an exported zip in isolation: builds the TA-Lib C library and
WeasyPrint runtime deps, unzips the package, installs `requirements.txt`,
and runs the pipeline.

```sh
scripts/export_package.sh test
docker build -t tradesysx-test -f scripts/Dockerfile \
    --build-arg ZIP_FILE=tradesysx-test.zip dist/
docker run --rm -it tradesysx-test
```

To persist the generated plots and reports in the `out/` directory after the run, mount it to the
host:

```sh
docker run --rm -v /tmp/tradesysx-out:/app/tradesysx/out tradesysx-test
```

Or, edit the system configuration outside of the container and persist the generated plots and reports in the `out/` directory after the run:

```sh
docker run --rm -v /tmp/tradesysx-out:/app/tradesysx/out -v /tmp/tradesysx-config:/app/tradesysx/config tradesysx-test
```

Please read the Docker documentation for any other usescase(s) that would suit your need.

##  Running `tradesysx` from a single executable

The `build_binary.sh` script was added to compile everything into a single executable, which bypasses the need to create a separate Python virtual environment.

### build_binary.sh

Builds a standalone executable with [PyInstaller](https://pyinstaller.org/).

```sh
scripts/build_binary.sh
```

- Runs `pyinstaller --clean --noconfirm tradesysx.spec`.
- Copies `config/`, `quotes/` and an empty `out/` into `dist/` alongside the
  binary, since the app reads these relative to its working directory
  (`--basedir`) rather than from the PyInstaller bundle.
- Run it from `dist/` (`./tradesysx [--basedir <path>] [--loglevel <level>]`),
  or copy the whole `dist/` directory elsewhere first.

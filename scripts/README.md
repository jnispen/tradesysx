# Exporting `tradesysx` and running from a Docker container

Below is a description on how to package and run `tradesysx` from a Docker container. It was added as a quick way to test or try-out the software. The `build_binary.sh` script was added to compile everything into a single executable, which might also be conveniant in some cases.

## export_package.sh

Packages the current `HEAD` commit into a zip archive for sharing with a collaborator.

```sh
scripts/export_package.sh <label>
```

- `<label>` is a free-text version label used in the output filename, e.g. `scripts/export_package.sh v0.1` produces `dist/tradesysx-v0.1.zip`.
- The archive extracts into a top-level `tradesysx/` directory.
- Only files committed to `HEAD` are included. Files marked `export-ignore` in `.gitattributes` are excluded.
- If the working tree has uncommitted changes, the script prints a warning (via `git status --porcelain`) but still archives `HEAD` — commit first if those changes should be included.

The recipient should unzip the archive and follow the setup steps in `tradesysx/README.md` (`pip install -r requirements.txt`, etc.).

## Dockerfile

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

To edit config files inside the container, run the pipeline manually and to view the plots and
reports from the host:

```sh
docker run --rm -it -v /tmp/tradesysx-out:/app/tradesysx/out --entrypoint bash tradesysx-test
# edit config/system_conf.json, then:
python tradesysx.py
ls out/
```

## build_binary.sh

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

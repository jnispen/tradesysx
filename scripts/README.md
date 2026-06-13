## export_package.sh

Packages the current `HEAD` commit into a zip archive for sharing with a collaborator.

```sh
scripts/export_package.sh <label>
```

- `<label>` is a free-text version label used in the output filename, e.g. `scripts/export_package.sh v0.1` produces `dist/getquotes-v0.1.zip`.
- The archive extracts into a top-level `getquotes/` directory.
- Only files committed to `HEAD` are included. Files marked `export-ignore` in `.gitattributes` are excluded.
- If the working tree has uncommitted changes, the script prints a warning (via `git status --porcelain`) but still archives `HEAD` — commit first if those changes should be included.

The recipient should unzip the archive and follow the setup steps in `getquotes/README.md` (`pip install -r requirements.txt`, etc.).

## generate_docs.sh

Generates browsable API documentation from the Python source using `pdoc`.

```sh
scripts/generate_docs.sh
```

- Regenerates `docs/` from scratch.
- Open `docs/index.html` directly in a browser (e.g. Firefox).
- Rerun the script to refresh the docs after code changes.

## Dockerfile

Tests an exported zip in isolation: builds the TA-Lib C library and
WeasyPrint runtime deps, unzips the package, installs `requirements.txt`,
and runs the pipeline.

```sh
scripts/export_package.sh test
docker build -t getquotes-test -f scripts/Dockerfile \
    --build-arg ZIP_FILE=getquotes-test.zip dist/
docker run --rm -it getquotes-test
```

See the comments at the top of `scripts/Dockerfile` for variants: mounting
`out/` to the host to inspect results, or dropping into a shell to edit
config files and run manually.

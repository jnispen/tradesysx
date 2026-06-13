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

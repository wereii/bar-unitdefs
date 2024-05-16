# unitdefs-reshaper

Reprocess raw unitdefs json export from game into something more _usable_

### Run

The script `unitdefs-reshaper.py` is single-file CLI that should run almost anywhere with fresh enough python version (
tested with py3.12).

```sh
> python unitdefs-reshaper.py
usage: unitdefs-reshaper [-h] [--debug] --unitdefs-dir UNITDEFS_DIR [--output-file OUTPUT_FILE]

options:
  -h, --help            show this help message and exit
  --debug, -d           Enable debug logging
  --unitdefs-dir UNITDEFS_DIR
                        Location of exported json unitdefs (usually "json_export/")
  --output-file OUTPUT_FILE
                        Path to directory where to output files, defaults to "./unitdefs.json"
```


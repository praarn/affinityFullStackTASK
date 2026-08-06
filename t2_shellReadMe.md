# t2.sh — S&P 500 Founding Year Report

A Bash/gawk script that downloads the S&P 500 constituents CSV from
GitHub and prints every company's **name**, **headquarters location**,
and **founding year**, sorted oldest → newest.

Source data:
`https://raw.githubusercontent.com/datasets/s-and-p-500-companies/refs/heads/main/data/constituents.csv`

---

## How it works

1. **Download** — `curl -sL` fetches the raw CSV.
2. **Parse** — piped into `gawk` using `FPAT='[^,]*|"[^"]*"'`, which
   splits fields correctly even when a field itself contains a comma
   (e.g. `"Saint Paul, Minnesota"`), something a naive `awk -F','` or
   `cut -d','` would break on.
3. **Extract columns**:
   - Column 2 → Company name (`Security`)
   - Column 5 → Headquarters location
   - Column 8 → `Founded` (messy — see note below)
4. **Clean the year** — the `Founded` field isn't a clean 4-digit
   number for every row (spinoffs, mergers, and predecessor companies
   are annotated), e.g.:
   - `"2013 (1888)"` → AbbVie, spun off from Abbott in 2013 but traces to 1888
   - `"1975/1977 (1997)"` → KLA Corporation, merger history
   - `"2020 (1853, United Technologies spinoff)"` → Otis Worldwide
   - The script uses a regex to grab the **first** 4-digit number in
     the field, which is generally the earliest/founding date.
5. **Sort** — `sort -n -k1,1` sorts numerically by year.
6. **Format** — a final `awk` pass pretty-prints the three columns
   with fixed-width alignment.

---

## Requirements

| Tool | Purpose |
|---|---|
| `bash` | run the script |
| `curl` | download the CSV |
| `gawk` | GNU awk — specifically needs `FPAT` support (not available in mawk/POSIX awk) |

### Windows setup (what actually worked)
Native PowerShell doesn't have `chmod`, `curl` (the real one), or
`gawk`, so the script needs to run inside **Git Bash** (MINGW64) or
WSL:

```powershell
# Open "Git Bash" instead of PowerShell
cd /d/Engineering/Tasks/affinityFullStack
chmod +x t2.sh
./t2.sh
```

Git Bash ships with `bash` and `curl`, but its default `awk` is
`busybox awk`/`mawk`, which does **not** support `FPAT`. If you hit an
`FPAT` or "gawk not found" style error, install gawk into Git Bash via
its package manager:

```bash
pacman -S gawk
```

(On this run it worked directly, so gawk was already present/resolved
in the environment — no extra install step was needed.)

---

## Usage

```bash
chmod +x t2.sh
./t2.sh                          # prints to terminal
./t2.sh > companies_by_year.tsv  # saves to a file
```

---

## Confirmed execution output

Ran successfully via Git Bash on Windows:

```
Dell@tinTon MINGW64 /d/Engineering/Tasks/affinityFullStack
$ ./t2.sh
Year   Company                                       Location
----   -------                                       --------
1784   BNY Mellon                                    New York City, New York
1792   State Street Corporation                      Boston, Massachusetts
1806   Colgate-Palmolive                             New York City, New York
...
2024   GE Vernova                                    Cambridge, Massachusetts
2025   Paramount Skydance Corporation                Los Angeles, California
2025   Qnity Electronics                             Wilmington, Delaware
```

- **502 companies** parsed and printed (out of 503 rows in the source
  file — the header row is skipped).
- **Oldest**: BNY Mellon, founded **1784**, New York City, New York.
- **Newest**: Paramount Skydance Corporation and Qnity Electronics,
  both founded **2025**.
- Output is a clean, evenly-aligned three-column table (`Year`,
  `Company`, `Location`), correctly sorted ascending by year, matching
  the expected behavior end-to-end.

---

## Known data quirks (from the source CSV, not the script)

These come straight from the dataset and show up as-is in the output:

- **Multi-HQ companies** use a semicolon to separate locations, e.g.
  `Huntington Bancshares → Columbus, Ohio; Detroit, Michigan`.
- **Wikipedia-style citation brackets** occasionally leak into the
  location field, e.g. `Northrop Grumman → West Falls Church,
  Virginia[2]`.
- **Missing location**: `Block, Inc.` shows `none` as its location in
  the source data.
- **Split business units**: "Honeywell Technologies" (1906) and
  "Honeywell Aerospace" (1914) appear as separate rows in the source
  dataset even though they're the same parent company — this is a
  quirk of the S&P 500 constituents list, not a script bug.

If you want these cleaned up further (e.g. stripping `[2]` citation
markers, normalizing multi-HQ entries), that's a quick follow-up
tweak to the `gsub()` calls in the script.

---

## Output columns

| Column | Source | Notes |
|---|---|---|
| `Year` | `Founded` (first 4-digit match) | Earliest year mentioned when the field has parenthetical/merger notes |
| `Company` | `Security` | Company display name |
| `Location` | `Headquarters Location` | As listed in the source CSV, including quirks above |

set -euo pipefail
 
URL="https://raw.githubusercontent.com/datasets/s-and-p-500-companies/refs/heads/main/data/constituents.csv"
 
if ! command -v gawk >/dev/null 2>&1; then
    echo "Error: gawk is required (uses FPAT for CSV parsing). Install with: sudo apt install gawk" >&2
    exit 1
fi
 
curl -sL "$URL" | gawk -v FPAT='[^,]*|"[^"]*"' '
    NR == 1 { next }  # skip header row
    {
        name     = $2
        location = $5
        founded  = $8
 
        gsub(/^"|"$/, "", name)
        gsub(/^"|"$/, "", location)
        gsub(/^"|"$/, "", founded)
 
        # Pull out the first 4-digit year in the Founded field
        if (match(founded, /[0-9]{4}/)) {
            year = substr(founded, RSTART, RLENGTH)
            print year "\t" name "\t" location
        }
    }
' | sort -n -k1,1 | awk -F'\t' '
    BEGIN {
        printf "%-6s %-45s %s\n", "Year", "Company", "Location"
        printf "%-6s %-45s %s\n", "----", "-------", "--------"
    }
    { printf "%-6s %-45s %s\n", $1, $2, $3 }
'
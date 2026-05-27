import os
import sys
import json
import urllib.request

DATA_DIR = "/app/data"
OUT_CSV = os.path.join(DATA_DIR, "htjm4_data.csv")
RESULT_JSON = os.path.join(DATA_DIR, "osf_download_result.json")

# Candidate direct download URLs (public view-only link may not expose raw). These are guesses and may need adjustment.
CANDIDATE_URLS = [
    # If the OSF project exposes a CSV named similar to the study
    "https://osf.io/download/vhmgc/",
]


def try_download(url):
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = resp.read()
        # Heuristic: if looks like zip or html, skip
        if data[:2] == b"PK" or data.lstrip().startswith(b"<"):
            return False, f"URL {url} returned a zip/html, not a raw CSV"
        # Save as CSV
        with open(OUT_CSV, "wb") as f:
            f.write(data)
        # Quick sanity: ensure header line has DSM5_Total or MiniK_Total
        with open(OUT_CSV, "r", encoding="utf-8", errors="replace") as f:
            header = f.readline()
        if ("DSM5_Total" in header) or ("MiniK_Total" in header) or ("HKSS_Total" in header):
            return True, "downloaded"
        else:
            return False, "Downloaded file does not appear to contain required columns"
    except Exception as e:
        return False, str(e)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for url in CANDIDATE_URLS:
        ok, msg = try_download(url)
        if ok:
            with open(RESULT_JSON, 'w') as f:
                json.dump({"status": "success", "url": url, "path": OUT_CSV}, f, indent=2)
            return 0
    with open(RESULT_JSON, 'w') as f:
        json.dump({"status": "failure", "tried": CANDIDATE_URLS}, f, indent=2)
    return 2


if __name__ == "__main__":
    sys.exit(main())

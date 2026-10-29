"""Upload a build_pages private bundle to a private Cloudflare R2 bucket.

Uploads run in parallel, and a manifest beside the bundle records what was uploaded, so a rerun only
sends files that are new or changed since the last successful upload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=8, help="Uploads to run at the same time")
    parser.add_argument("--all", action="store_true", help="Upload every file, ignoring the manifest")
    args = parser.parse_args()

    manifest_path = args.bundle.parent / f".uploaded-{args.bucket}.json"
    manifest = {} if args.all or not manifest_path.exists() else json.loads(manifest_path.read_text())
    files = {
        path.relative_to(args.bundle).as_posix(): path for path in sorted(args.bundle.rglob("*"))
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(args.bundle).parts)
    }
    hashes = {key: digest(path) for key, path in files.items()}
    pending = [key for key in files if manifest.get(key) != hashes[key]]
    print(f"{len(pending)} of {len(files)} files are new or changed; uploading with {args.jobs} at a time.")

    def upload(key: str) -> str:
        command = ["npx", "--yes", "wrangler", "r2", "object", "put", f"{args.bucket}/{key}",
                   "--file", str(files[key]), "--remote", "--config", str(args.config), "--force"]
        content_type = mimetypes.guess_type(key)[0]
        if content_type:
            command.extend(["--content-type", content_type])
        # A hung wrangler (e.g. waiting on an expired login) fails after 3 minutes instead of blocking forever.
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
        return key

    failed = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(upload, key): key for key in pending}
        for done, future in enumerate(as_completed(futures), 1):
            key = futures[future]
            try:
                future.result()
                manifest[key] = hashes[key]
                print(f"[{done}/{len(pending)}] {key}")
            except subprocess.CalledProcessError as error:
                failed.append(key)
                print(f"[{done}/{len(pending)}] FAILED {key}: {(error.stderr or error.stdout or '').strip()[-300:]}")
            except subprocess.TimeoutExpired:
                failed.append(key)
                print(f"[{done}/{len(pending)}] TIMED OUT {key} (check `npx wrangler whoami`; you may need `npx wrangler login`)")
            if done % 25 == 0:  # save progress so an interrupted run can resume
                manifest_path.write_text(json.dumps(manifest, indent=0))
    manifest_path.write_text(json.dumps(manifest, indent=0))
    if failed:
        raise SystemExit(f"{len(failed)} upload(s) failed; rerun the same command to retry only those.")
    print("Done.")


if __name__ == "__main__":
    main()

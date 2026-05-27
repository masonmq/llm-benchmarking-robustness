import os
import json
import urllib.parse
import urllib.request

OSF_API = "https://api.osf.io/v2"


def _add_view_only(url: str, token: str) -> str:
    if not token:
        return url
    sep = '&' if ('?' in url) else '?'
    return f"{url}{sep}view_only={token}"


def _http_get_json(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    return json.loads(data.decode('utf-8'))


def _http_download(url: str, out_path: str):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=300) as resp:
        with open(out_path, 'wb') as f:
            f.write(resp.read())


def _list_all(url: str):
    # Iterate OSF paginated endpoints
    results = []
    while url:
        js = _http_get_json(url)
        data = js.get('data', [])
        results.extend(data)
        links = js.get('links', {})
        url = links.get('next')
    return results


def _traverse_folder(folder_item: dict, token: str):
    files = []
    rel = folder_item.get('relationships', {})
    files_rel = rel.get('files', {})
    link = None
    if isinstance(files_rel, dict):
        links = files_rel.get('links', {})
        link = links.get('related', {}).get('href') or links.get('related')
    if not link:
        return files
    url = _add_view_only(link, token)
    items = _list_all(url)
    for it in items:
        kind = it.get('attributes', {}).get('kind')
        if kind == 'file':
            files.append(it)
        elif kind == 'folder':
            files.extend(_traverse_folder(it, token))
    return files


def osf_find_and_download_csv(node_id: str, view_only_token: str, dest_dir: str, required_columns=None):
    os.makedirs(dest_dir, exist_ok=True)
    root_url = f"{OSF_API}/nodes/{node_id}/files/osfstorage/"
    root_url = _add_view_only(root_url, view_only_token)
    try:
        roots = _list_all(root_url)
    except Exception as e:
        return None, f"OSF API error: {e}"

    all_files = []
    for it in roots:
        kind = it.get('attributes', {}).get('kind')
        if kind == 'file':
            all_files.append(it)
        elif kind == 'folder':
            all_files.extend(_traverse_folder(it, view_only_token))

    # Prefer CSV files
    csv_files = [f for f in all_files if f.get('attributes', {}).get('name', '').lower().endswith('.csv')]

    for fitem in csv_files:
        name = fitem.get('attributes', {}).get('name', 'download.csv')
        dl = fitem.get('links', {}).get('download') or fitem.get('links', {}).get('self')
        if not dl:
            continue
        url = _add_view_only(dl, view_only_token)
        out_path = os.path.join(dest_dir, name)
        try:
            _http_download(url, out_path)
            # Validate header if required
            if required_columns:
                with open(out_path, 'r', encoding='utf-8', errors='replace') as f:
                    header = f.readline()
                ok = all(col in header for col in required_columns)
                if not ok:
                    continue
            return out_path, None
        except Exception as e:
            err = str(e)
            continue

    return None, "No suitable CSV found with required columns"

import json, os

def write_execution_result(obj, fname="execution_result.json"):
    out_dir = "/app/data/outputs"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, fname)
    with open(path, "w") as f:
        json.dump(obj, f)
    print(json.dumps({"execution_result_path": path}))

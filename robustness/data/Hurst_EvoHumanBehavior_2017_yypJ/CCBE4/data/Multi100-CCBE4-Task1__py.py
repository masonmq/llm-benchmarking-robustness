import json
import os
import sys
import subprocess
import importlib

# Ensure required packages are available at runtime
REQUIRED_PY_PKGS = [
    "numpy==1.26.4",
    "pandas==2.2.2",
    "scipy==1.11.4",
    "scikit-learn==1.4.2",
    "requests==2.31.0"
]

def ensure_packages(packages):
    for spec in packages:
        name = spec.split("==")[0]
        try:
            importlib.import_module(name)
        except ImportError:
            print(f"Package {name} not found. Installing {spec}...", file=sys.stderr)
            subprocess.check_call([sys.executable, "-m", "pip", "install", spec])

ensure_packages(REQUIRED_PY_PKGS)

# Ensure user site-packages is on sys.path
import site
try:
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
except Exception as e:
    print(f"WARNING: Could not append user site-packages: {e}", file=sys.stderr)
# Also try default pip user dir as fallback
fallback_user_site = os.path.expanduser("~/.local/lib/python3.9/site-packages")
if os.path.isdir(fallback_user_site) and fallback_user_site not in sys.path:
    sys.path.append(fallback_user_site)

# Now import after ensuring availability
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import t as student_t
from sklearn.decomposition import PCA

INPUT_PATH = "/app/data/Dataset.csv"
RESULTS_JSON = "/app/data/Multi100-CCBE4-Task1_results.json"
DATA_OSF_URL = "https://osf.io/download/vhmgc/?view_only=5c6bedb36b2549a88ac137d6c746bcb8"


def partial_corr_resid(x, y, covars):
    """Compute partial correlation between x and y, controlling for covars, using residualization.
    Returns (r, p, n).
    """
    df = pd.concat([x, y, covars], axis=1).dropna()
    # Residualize via OLS using numpy lstsq
    X = np.column_stack([np.ones(len(df)), df[covars.columns].values])
    beta_x, *_ = np.linalg.lstsq(X, df[x.name].values, rcond=None)
    beta_y, *_ = np.linalg.lstsq(X, df[y.name].values, rcond=None)
    x_hat = X @ beta_x
    y_hat = X @ beta_y
    x_resid = df[x.name].values - x_hat
    y_resid = df[y.name].values - y_hat
    r, p = stats.pearsonr(x_resid, y_resid)
    return r, p, len(df)


def partial_corr_matrix(df):
    """Compute partial correlation matrix and p-values using precision matrix.
    Returns (pcorr, pvals) as DataFrames.
    """
    M = df.dropna().copy()
    M = (M - M.mean()) / M.std(ddof=0)
    n, p = M.shape
    S = np.cov(M.values, rowvar=False, ddof=0)
    # Regularization check: add small ridge if singular
    try:
        P = np.linalg.inv(S)
    except np.linalg.LinAlgError:
        ridge = 1e-6 * np.eye(S.shape[0])
        P = np.linalg.inv(S + ridge)
    pc = np.zeros_like(P)
    for i in range(p):
        for j in range(p):
            if i == j:
                pc[i, j] = 1.0
            else:
                pc[i, j] = -P[i, j] / np.sqrt(P[i, i] * P[j, j])
    # p-values for partial correlations controlling for p-2 variables
    dfree = n - p
    pvals = np.ones_like(pc)
    for i in range(p):
        for j in range(i + 1, p):
            r = pc[i, j]
            tval = r * np.sqrt(dfree / max(1e-12, (1.0 - r ** 2)))
            pv = 2.0 * (1.0 - student_t.cdf(abs(tval), df=dfree)) if dfree > 0 else np.nan
            pvals[i, j] = pvals[j, i] = pv
    pc_df = pd.DataFrame(pc, index=M.columns, columns=M.columns)
    pv_df = pd.DataFrame(pvals, index=M.columns, columns=M.columns)
    return pc_df, pv_df, n, p


def main():
    if not os.path.exists(INPUT_PATH):
        # Try to auto-download from OSF folder link if possible
        try:
            import requests
            print(f"Dataset not found locally. Attempting download from OSF: {DATA_OSF_URL}")
            r = requests.get(DATA_OSF_URL, allow_redirects=True, timeout=60)
            r.raise_for_status()
            # Write the content to INPUT_PATH
            with open(INPUT_PATH, "wb") as f:
                f.write(r.content)
            print(f"Downloaded dataset to {INPUT_PATH}")
        except Exception as e:
            print(f"ERROR: Expected dataset at {INPUT_PATH} but not found and auto-download failed: {e}", file=sys.stderr)
            sys.exit(1)
    dat = pd.read_csv(INPUT_PATH)

    results = {"task": "Task1", "input": INPUT_PATH, "outputs": {}}

    # Variables used
    needed_cols = ["MiniK_Total", "HKSS_Total", "DSM5_Total", "Age"]
    missing = [c for c in needed_cols if c not in dat.columns]
    if missing:
        print(f"ERROR: Missing required columns: {missing}", file=sys.stderr)
        sys.exit(1)

    # Original/Replicated partial correlations controlling for Age
    covars = dat[["Age"]]
    r_mini_dsm5, p_mini_dsm5, n1 = partial_corr_resid(dat["MiniK_Total"], dat["DSM5_Total"], covars)
    r_hkss_dsm5, p_hkss_dsm5, n2 = partial_corr_resid(dat["HKSS_Total"], dat["DSM5_Total"], covars)
    r_mini_hkss, p_mini_hkss, n3 = partial_corr_resid(dat["MiniK_Total"], dat["HKSS_Total"], covars)

    print("Main partial correlations controlling for Age:")
    print(f"MiniK_Total vs DSM5_Total: r = {r_mini_dsm5:.3f}, p = {p_mini_dsm5:.4g}, N = {n1}")
    print(f"HKSS_Total vs DSM5_Total: r = {r_hkss_dsm5:.3f}, p = {p_hkss_dsm5:.4g}, N = {n2}")
    print(f"MiniK_Total vs HKSS_Total: r = {r_mini_hkss:.3f}, p = {p_mini_hkss:.4g}, N = {n3}")

    results["outputs"]["partial_correlations_age_controlled"] = {
        "MiniK_Total__DSM5_Total": {"r": r_mini_dsm5, "p": p_mini_dsm5, "N": n1},
        "HKSS_Total__DSM5_Total": {"r": r_hkss_dsm5, "p": p_hkss_dsm5, "N": n2},
        "MiniK_Total__HKSS_Total": {"r": r_mini_hkss, "p": p_mini_hkss, "N": n3},
    }

    # Sensitivity 1: PCA on MiniK and HKSS
    X = dat[["MiniK_Total", "HKSS_Total"]].dropna().values
    pca = PCA(n_components=1)
    comps = pca.fit_transform((X - X.mean(axis=0)) / X.std(axis=0, ddof=0))
    # Align length to rows used
    pc_scores = pd.Series(np.nan, index=dat.index, name="compscores")
    non_na_idx = dat[["MiniK_Total", "HKSS_Total"]].dropna().index
    pc_scores.loc[non_na_idx] = comps[:, 0]
    dat["compscores"] = pc_scores

    # Loadings (correlation between component and original vars in standardized space)
    loadings = pca.components_[0]
    results["outputs"]["pca"] = {
        "explained_variance_ratio": float(pca.explained_variance_ratio_[0]),
        "loadings": {"MiniK_Total": float(loadings[0]), "HKSS_Total": float(loadings[1])}
    }

    # Partial corr between comp score and DSM5 controlling for Age
    r_comp_dsm5, p_comp_dsm5, ncomp = partial_corr_resid(dat["compscores"], dat["DSM5_Total"], dat[["Age"]])
    print("\nSensitivity Analysis (PCA component):")
    print(f"Component vs DSM5_Total (controlling Age): r = {r_comp_dsm5:.3f}, p = {p_comp_dsm5:.4g}, N = {ncomp}")

    results["outputs"]["pca_partial_corr"] = {
        "compscores__DSM5_Total": {"r": r_comp_dsm5, "p": p_comp_dsm5, "N": ncomp}
    }

    # Sensitivity 2: Partial correlation network
    net_vars = [
        "Age", "Bio_Sib", "Half_Sib", "Step_Sib", "Stepparent",
        "MiniK_Total", "HKSS_Total", "DSM5_Total", "SH_Total",
        "Attach_Total", "Aggresion_Total"
    ]
    present = [c for c in net_vars if c in dat.columns]
    if len(present) >= 4:  # need at least some variables
        pc_df, pv_df, n_net, p_net = partial_corr_matrix(dat[present])
        print("\nPartial Correlation Network (Bonferroni alpha = 0.05/55):")
        alpha_bonf = 0.05 / 55.0
        # Focus on key pairs
        pairs_of_interest = [
            ("MiniK_Total", "DSM5_Total"),
            ("HKSS_Total", "DSM5_Total"),
            ("MiniK_Total", "HKSS_Total"),
        ]
        net_out = {}
        for a, b in pairs_of_interest:
            if a in pc_df.columns and b in pc_df.columns:
                r = float(pc_df.loc[a, b])
                pval = float(pv_df.loc[a, b])
                sig = (pval < alpha_bonf)
                print(f"{a} vs {b}: r = {r:.3f}, p = {pval:.4g}, significant={sig}")
                net_out[f"{a}__{b}"] = {"r": r, "p": pval, "significant_bonf": sig}
        results["outputs"]["partial_corr_network"] = {
            "n": n_net, "p": p_net, "alpha_bonf": alpha_bonf, "pairs": net_out
        }
    else:
        print("\nPartial Correlation Network: insufficient variables present in dataset to compute network.")
        results["outputs"]["partial_corr_network"] = {"error": "insufficient_variables"}

    # Save JSON
    try:
        with open(RESULTS_JSON, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved results to {RESULTS_JSON}")
    except Exception as e:
        print(f"WARNING: Failed to save results JSON due to: {e}")


if __name__ == "__main__":
    main()

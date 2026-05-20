import json
import os
import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize
from scipy.special import gammaln

# IO paths inside container
DATA_PATH = "/app/data/final_data.dta"
ARTIFACTS_DIR = "/app/artifacts"
RESULTS_PATH = os.path.join(ARTIFACTS_DIR, "execution_result.json")


def load_data(path=DATA_PATH):
    dta = pd.read_stata(path)
    return dta


def add_constant(X):
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    const = np.ones((X.shape[0], 1))
    return np.hstack([const, X])


def poisson_loglike(beta, X, y):
    Xb = X @ beta
    mu = np.exp(Xb)
    # log-likelihood includes constant -log(y!) for fair comparison
    return np.sum(y * np.log(mu + 1e-12) - mu - gammaln(y + 1))


def fit_poisson_mle(X, y):
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n_params = X.shape[1]
    beta0 = np.zeros(n_params)

    def nll(beta):
        return -poisson_loglike(beta, X, y)

    res = minimize(nll, beta0, method="BFGS")
    beta_hat = res.x
    # Approximate covariance from inverse Hessian
    if hasattr(res, "hess_inv"):
        cov = res.hess_inv if isinstance(res.hess_inv, np.ndarray) else res.hess_inv.todense()
        cov = np.asarray(cov, dtype=float)
    else:
        # Fallback: numerical Hessian via finite differences (rough)
        eps = 1e-5
        H = np.zeros((n_params, n_params))
        f0 = nll(beta_hat)
        for i in range(n_params):
            e_i = np.zeros(n_params); e_i[i] = eps
            f_ip = nll(beta_hat + e_i)
            f_im = nll(beta_hat - e_i)
            H[i, i] = (f_ip - 2*f0 + f_im) / (eps**2)
        cov = np.linalg.pinv(H)
    se = np.sqrt(np.diag(cov))
    z = beta_hat / se
    p = 2 * stats.norm.sf(np.abs(z))

    # Deviance and GOF p-value
    mu = np.exp(X @ beta_hat)
    with np.errstate(divide='ignore', invalid='ignore'):
        term = np.where(y > 0, y * np.log((y + 1e-12) / (mu + 1e-12)), 0.0)
    deviance = 2 * np.sum(term - (y - mu))
    df_resid = max(int(len(y) - n_params), 1)
    gof_p = stats.chi2.sf(deviance, df_resid)

    llf = poisson_loglike(beta_hat, X, y)

    return {
        "params": beta_hat.tolist(),
        "se": se.tolist(),
        "z": z.tolist(),
        "p": p.tolist(),
        "llf": float(llf),
        "deviance": float(deviance),
        "df_resid": int(df_resid),
        "gof_p": float(gof_p)
    }


def nb2_loglike(params, X, y):
    # params: [beta..., log_alpha], NB2: Var(y) = mu + alpha*mu^2
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    beta = params[:-1]
    log_alpha = params[-1]
    alpha = np.exp(log_alpha)
    mu = np.exp(X @ beta)
    r = 1.0 / (alpha + 1e-12)  # size
    # log-likelihood per obs
    ll_i = (
        gammaln(y + r)
        - gammaln(r)
        - gammaln(y + 1)
        + r * (np.log(r) - np.log(r + mu))
        + y * (np.log(mu) - np.log(r + mu))
    )
    return np.sum(ll_i)


def fit_nb2_mle(X, y):
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n_params = X.shape[1] + 1  # + log_alpha

    # Initialize with Poisson estimates and small alpha
    pois = fit_poisson_mle(X, y)
    beta0 = np.array(pois["params"]) if isinstance(pois, dict) else np.zeros(X.shape[1])
    init = np.r_[beta0, np.log(0.1)]

    def nll(params):
        return -nb2_loglike(params, X, y)

    res = minimize(nll, init, method="BFGS")
    theta_hat = res.x
    if hasattr(res, "hess_inv"):
        cov = res.hess_inv if isinstance(res.hess_inv, np.ndarray) else res.hess_inv.todense()
        cov = np.asarray(cov, dtype=float)
    else:
        eps = 1e-5
        H = np.zeros((n_params, n_params))
        f0 = nll(theta_hat)
        for i in range(n_params):
            e_i = np.zeros(n_params); e_i[i] = eps
            f_ip = nll(theta_hat + e_i)
            f_im = nll(theta_hat - e_i)
            H[i, i] = (f_ip - 2*f0 + f_im) / (eps**2)
        cov = np.linalg.pinv(H)

    se = np.sqrt(np.diag(cov))
    beta_hat = theta_hat[:-1]
    se_beta = se[:-1]
    z = beta_hat / se_beta
    p = 2 * stats.norm.sf(np.abs(z))

    log_alpha_hat = theta_hat[-1]
    alpha_hat = float(np.exp(log_alpha_hat))
    se_log_alpha = float(se[-1])

    llf = nb2_loglike(theta_hat, X, y)

    return {
        "params": beta_hat.tolist(),
        "se": se_beta.tolist(),
        "z": z.tolist(),
        "p": p.tolist(),
        "alpha": alpha_hat,
        "se_log_alpha": se_log_alpha,
        "llf": float(llf)
    }


def chi_square_complaints_binary(dta):
    df = dta[["complaints_2008", "first_A"]].dropna().copy()
    df["complaints_binary"] = np.where(df["complaints_2008"] == 0, 0, 1)
    contingency = pd.crosstab(df["first_A"], df["complaints_binary"])  # rows: first_A
    chi2, p, dof, expected = stats.chi2_contingency(contingency.values)
    return contingency, chi2, p, dof


def t_test_complaints(dta):
    df = dta[["complaints_2008", "first_A"]].dropna()
    grp0 = df.loc[df["first_A"] == 0, "complaints_2008"].values
    grp1 = df.loc[df["first_A"] == 1, "complaints_2008"].values
    t_stat, p_val = stats.ttest_ind(grp1, grp0, equal_var=False, nan_policy='omit')
    return t_stat, p_val, float(np.nanmean(grp1)), float(np.nanmean(grp0)), int(len(grp1)), int(len(grp0))


def run_analysis():
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    dta = load_data()
    print(f"Loaded data with shape: {dta.shape}")

    # Chi-square on binary complaints
    contingency, chi2, p_chi, dof = chi_square_complaints_binary(dta)
    print(f"Chi-square test (complaints_binary ~ first_A): chi2={chi2:.3f}, df={dof}, p={p_chi:.6f}")
    print("Contingency table (rows=first_A, cols=complaints_binary):\n", contingency)

    # Poisson regression: complaints_2008 ~ const + first_A
    df_simple = dta[["complaints_2008", "first_A"]].dropna().copy()
    y_simple = df_simple["complaints_2008"].astype(float).values
    X_simple = add_constant(df_simple[["first_A"]].astype(float).values)
    pois = fit_poisson_mle(X_simple, y_simple)
    print("Poisson MLE results (complaints_2008 ~ first_A):")
    print({k: (v if not isinstance(v, list) else [round(x, 6) for x in v]) for k, v in pois.items() if k in ["params", "se", "z", "p", "llf", "deviance", "gof_p"]})

    # Negative Binomial regression (NB2): complaints_2008 ~ const + first_A
    nb_simple = fit_nb2_mle(X_simple, y_simple)
    print("NB2 MLE results (complaints_2008 ~ first_A):")
    print({k: (v if not isinstance(v, list) else [round(x, 6) for x in v]) for k, v in nb_simple.items() if k in ["params", "se", "z", "p", "alpha", "llf"]})

    # LLR: Poisson vs NB
    llr = 2 * (nb_simple["llf"] - pois["llf"])
    p_llr = stats.chi2.sf(llr, df=1)
    print(f"LR test Poisson vs NB: LLR={llr:.3f}, p={p_llr:.6f}")

    # NB with controls
    control_cols = [
        "first_A", "multiple_names", "on_google", "ad_spend_k", "firm_age", "chicago", "emp_size"
    ]
    cols = ["complaints_2008"] + control_cols
    df_ctrl = dta[cols].dropna().copy()
    y_ctrl = df_ctrl["complaints_2008"].astype(float).values
    X_ctrl = add_constant(df_ctrl[control_cols].astype(float).values)
    nb_ctrl = fit_nb2_mle(X_ctrl, y_ctrl)
    print("NB2 MLE with controls results (complaints_2008 ~ first_A + controls):")
    print({k: (v if not isinstance(v, list) else [round(x, 6) for x in v]) for k, v in nb_ctrl.items() if k in ["params", "se", "z", "p", "alpha", "llf"]})

    # Welch t-test
    t_stat, p_val, mean_A, mean_notA, n_A, n_notA = t_test_complaints(dta)
    print(f"t-test (complaints_2008 by first_A): t={t_stat:.3f}, p={p_val:.6f}")
    print(f"Means: first_A=1 -> {mean_A:.3f} (n={n_A}), first_A=0 -> {mean_notA:.3f} (n={n_notA})")

    # Prepare results JSON
    results = {
        "summary": {
            "n_simple": int(len(y_simple)),
            "n_controls": int(len(y_ctrl)),
            "chi_square": {
                "chi2": float(chi2),
                "df": int(dof),
                "p": float(p_chi)
            },
            "poisson": {
                "params": pois["params"],
                "se": pois["se"],
                "z": pois["z"],
                "p": pois["p"],
                "llf": float(pois["llf"]),
                "deviance": float(pois["deviance"]),
                "gof_p": float(pois["gof_p"])
            },
            "nb_simple": {
                "params": nb_simple["params"],
                "se": nb_simple["se"],
                "z": nb_simple["z"],
                "p": nb_simple["p"],
                "alpha": float(nb_simple["alpha"]),
                "llf": float(nb_simple["llf"])    
            },
            "llr_nb_vs_pois": {
                "llr": float(llr),
                "df": 1,
                "p": float(p_llr)
            },
            "nb_controls": {
                "params": nb_ctrl["params"],
                "se": nb_ctrl["se"],
                "z": nb_ctrl["z"],
                "p": nb_ctrl["p"],
                "alpha": float(nb_ctrl["alpha"]),
                "llf": float(nb_ctrl["llf"])    
            },
            "t_test": {
                "t": float(t_stat),
                "p": float(p_val),
                "mean_firstA": float(mean_A),
                "mean_not_firstA": float(mean_notA),
                "n_firstA": int(n_A),
                "n_not_firstA": int(n_notA)
            }
        },
        "notes": {
            "zero_inflated_models": "skipped (not required; optional)",
            "implementation": "MLE via SciPy; no statsmodels dependency"
        }
    }

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Saved results to {RESULTS_PATH}")


if __name__ == "__main__":
    run_analysis()

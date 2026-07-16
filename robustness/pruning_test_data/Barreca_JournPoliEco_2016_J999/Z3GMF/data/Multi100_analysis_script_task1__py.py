import os
import pandas as pd
import statsmodels.formula.api as smf
import matplotlib.pyplot as plt
import seaborn as sns

DATA_DIR = "/app/data"
OUT_DIR = DATA_DIR

DATA_1900_2004 = pd.read_stata(os.path.join(DATA_DIR, "DATA_1900_2004.dta"))
DATA_TABLE9 = pd.read_stata(os.path.join(DATA_DIR, "DATA_TABLE9.dta"))

# Compute variables used in the R analysis.
DATA_1900_2004["statemo"] = DATA_1900_2004["stfips"] * 1000 + DATA_1900_2004["month"]
DATA_1900_2004["yearmo"] = DATA_1900_2004["year"] * 1000 + DATA_1900_2004["month"]
DATA_1900_2004["year2"] = DATA_1900_2004["year"] ** 2
DATA_1900_2004["b10_b_4"] = DATA_1900_2004[["b10_1", "b10_2", "b10_3", "b10_4"]].sum(axis=1)

# Decade variables.
def assign_decade(year):
    if 1900 <= year < 1910:
        return 1
    if 1910 <= year < 1920:
        return 2
    if 1920 <= year < 1930:
        return 3
    if 1930 <= year < 1940:
        return 4
    if 1940 <= year < 1950:
        return 5
    if 1950 <= year < 1960:
        return 6
    if 1960 <= year < 1970:
        return 7
    if 1970 <= year < 1980:
        return 8
    if 1980 <= year < 1990:
        return 9
    if 1990 <= year < 2000:
        return 10
    if 2000 <= year < 2010:
        return 11
    return pd.NA

DATA_1900_2004["decade"] = DATA_1900_2004["year"].apply(assign_decade)
DATA_1900_2004["decade_two"] = DATA_1900_2004["year"].apply(lambda y: 1 if y <= 1959 else 2)

# Remove missing mortality rate and restrict to years from 1931 onward.
DATA_1931_2004_no_missing = DATA_1900_2004.dropna(subset=["lndrate"])
DATA_1931_2004_no_missing = DATA_1931_2004_no_missing[DATA_1931_2004_no_missing["year"] >= 1931].copy()

formulas = {
    "M1": "lndrate ~ b10_1 + b10_2 + b10_3 + b10_4 + b10_5 + b10_6 + b10_8 + b10_9 + b10_10 + (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month + lri * month + statemo + yearmo + year2 + devp25 + devp75",
    "M2": "lndrate ~ (b10_1 + b10_2 + b10_3 + b10_4 + b10_5 + b10_6 + b10_8 + b10_9 + b10_10) * C(decade_two) + (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month + lri * month + statemo + yearmo + year2 + devp25 + devp75",
    "M3": "lndrate ~ (b10_1 + b10_2 + b10_3 + b10_4 + b10_5 + b10_6 + b10_8 + b10_9 + b10_10) * C(decade) + (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month + lri * month + statemo + yearmo + year2 + devp25 + devp75",
    "M4": "lndrate ~ (b10_9 + b10_10 + b10_b_4) * C(decade_two) + (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month + lri * month + statemo + yearmo + year2 + devp25 + devp75",
    "M5": "lndrate ~ (b10_9 + b10_10 + b10_b_4) * C(decade) + (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month + lri * month + statemo + yearmo + year2 + devp25 + devp75",
}

with open(os.path.join(OUT_DIR, "task1_model_summaries.txt"), "w", encoding="utf-8") as f:
    for name, formula in formulas.items():
        model = smf.ols(formula=formula, data=DATA_1931_2004_no_missing).fit()
        f.write(f"\n\n{name}\n")
        f.write(model.summary().as_text())

# Save simple equivalents of the diagnostic interaction plots from the R script.
plot_specs = [
    ("b10_10", "decade_two", "task1_b10_10_decade_two.png"),
    ("b10_1", "decade_two", "task1_b10_1_decade_two.png"),
    ("b10_9", "decade_two", "task1_b10_9_decade_two.png"),
    ("b10_10", "decade", "task1_b10_10_decade.png"),
    ("b10_9", "decade", "task1_b10_9_decade.png"),
    ("b10_b_4", "decade_two", "task1_b10_b_4_decade_two.png"),
    ("b10_b_4", "decade", "task1_b10_b_4_decade.png"),
]
for xvar, huevar, fname in plot_specs:
    plt.figure(figsize=(8, 5))
    sns.scatterplot(data=DATA_1931_2004_no_missing, x=xvar, y="lndrate", hue=DATA_1931_2004_no_missing[huevar].astype(str), s=10, alpha=0.4)
    for value, group in DATA_1931_2004_no_missing.groupby(huevar):
        sns.regplot(data=group, x=xvar, y="lndrate", scatter=False, label=str(value))
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, fname), dpi=150)
    plt.close()

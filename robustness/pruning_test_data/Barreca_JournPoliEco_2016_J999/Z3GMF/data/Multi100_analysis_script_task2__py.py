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
DATA_1900_2004["decade_two"] = DATA_1900_2004["year"].apply(lambda y: 1 if y <= 1959 else 2)

# Remove missing mortality rate and restrict to years from 1931 onward.
DATA_1931_2004_no_missing = DATA_1900_2004.dropna(subset=["lndrate"])
DATA_1931_2004_no_missing = DATA_1931_2004_no_missing[DATA_1931_2004_no_missing["year"] >= 1931].copy()

# Task 2 model: use 90 F as the extreme-temperature threshold, compare 1931-1959 vs 1960-2004, and omit socioeconomic, geographical, and precipitation controls.
formula = "lndrate ~ b10_10 * C(decade_two) + (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month + yearmo + year2"
model = smf.ols(formula=formula, data=DATA_1931_2004_no_missing).fit()

with open(os.path.join(OUT_DIR, "task2_model_summary.txt"), "w", encoding="utf-8") as f:
    f.write(model.summary().as_text())

plt.figure(figsize=(8, 5))
sns.scatterplot(data=DATA_1931_2004_no_missing, x="b10_10", y="lndrate", hue=DATA_1931_2004_no_missing["decade_two"].astype(str), s=10, alpha=0.4)
for value, group in DATA_1931_2004_no_missing.groupby("decade_two"):
    sns.regplot(data=group, x="b10_10", y="lndrate", scatter=False, label=str(value))
plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "task2_b10_10_decade_two.png"), dpi=150)
plt.close()

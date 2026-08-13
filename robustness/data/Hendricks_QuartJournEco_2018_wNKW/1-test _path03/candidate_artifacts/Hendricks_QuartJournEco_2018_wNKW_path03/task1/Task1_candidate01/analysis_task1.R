# Task1 analysis script for Hendricks & Schoellman (QJE 2018)
# Conclusion-oriented reanalysis: compare log wage gains at migration for never-high-school vs college-degree immigrants
# Model: OLS with female, age, age^2, country fixed effects, and birth-cohort (decade) fixed effects; HC3 robust SEs

suppressPackageStartupMessages({
  library(readxl)
  library(sandwich)
  library(lmtest)
})

# Resolve paths relative to this script location
get_script_path <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) > 0) {
    normalizePath(sub("^--file=", "", file_arg))
  } else if (!is.null(sys.frames()[[1]]$ofile)) {
    normalizePath(sys.frames()[[1]]$ofile)
  } else {
    stop("Cannot determine script path; use Rscript to run this file.")
  }
}

script_path <- get_script_path()
script_dir <- dirname(script_path)
# test_dir is four levels up from candidate_artifacts/.../<task>/<candidate>
# <test>/candidate_artifacts/<path_id>/<task>/<candidate>
# so go up 4 to the test directory
test_dir <- normalizePath(file.path(script_dir, "..", "..", "..", ".."))

data_path <- file.path(test_dir, "data", "wage_gain_table.xlsx")

# Read data
stopifnot(file.exists(data_path))
df <- readxl::read_xlsx(data_path)

# Coerce expected columns
num_cols <- c("edyrs", "yearLastHomeJob", "yearLastUsJob", "sex", "yrborn", "lastHomeWage", "lastHomeWageAdjusted", "lastUsWage", "lastUsWageAdjusted")
for (cc in num_cols) {
  if (!cc %in% names(df)) stop(sprintf("Missing required column: %s", cc))
  df[[cc]] <- suppressWarnings(as.numeric(df[[cc]]))
}

# Verify other required columns
req_cols <- c("occGroupLastHomeJob", "occGroupLastUsJob", "country")
for (cc in req_cols) {
  if (!cc %in% names(df)) stop(sprintf("Missing required column: %s", cc))
}

# Sample flow tracking
n0 <- nrow(df)

# Keep rows with positive adjusted wages
df$keep_pos_wages <- is.finite(df$lastHomeWageAdjusted) & is.finite(df$lastUsWageAdjusted) & df$lastHomeWageAdjusted > 0 & df$lastUsWageAdjusted > 0
n_drop_nonpos <- sum(!df$keep_pos_wages)

df1 <- df[df$keep_pos_wages, , drop = FALSE]

# Construct variables
# Outcome: log wage gain = log(lastUsWageAdjusted) - log(lastHomeWageAdjusted)
df1$log_wage_gain <- log(df1$lastUsWageAdjusted) - log(df1$lastHomeWageAdjusted)

# Age at last US job
df1$age_at_us_job <- df1$yearLastUsJob - df1$yrborn

# Female indicator (1 if sex == 2, 0 if sex == 1)
df1$female <- ifelse(df1$sex == 2, 1L, ifelse(df1$sex == 1, 0L, NA_integer_))

# Education group: never_high_school (edyrs < 9), college_degree (edyrs >= 16), other
edu_group <- ifelse(df1$edyrs < 9, "never_high_school", ifelse(df1$edyrs >= 16, "college_degree", "other"))
df1$edu_group <- factor(edu_group, levels = c("college_degree", "never_high_school", "other"))

# Birth cohort decade
cohort_decade <- floor(df1$yrborn / 10) * 10
# Treat implausible years as NA
cohort_decade[!is.finite(cohort_decade)] <- NA
# Convert to factor (character labels like "1960s")
df1$cohort_decade <- factor(paste0(cohort_decade, "s"))

# Drop rows with missing in material variables
keep_complete <- is.finite(df1$log_wage_gain) & is.finite(df1$age_at_us_job) & !is.na(df1$female) & !is.na(df1$edu_group) & !is.na(df1$country) & !is.na(df1$cohort_decade)

n_drop_missing_material <- sum(!keep_complete)

df2 <- df1[keep_complete, , drop = FALSE]

# Restrict to focal education groups only (drop 'other')
keep_focal_edu <- df2$edu_group %in% c("college_degree", "never_high_school")

n_drop_nonfocal_edu <- sum(!keep_focal_edu)

df3 <- droplevels(df2[keep_focal_edu, , drop = FALSE])

# Relevel to set college_degree as reference
df3$edu_group <- relevel(df3$edu_group, ref = "college_degree")

n_final <- nrow(df3)

# Fit OLS with country and cohort FE, female, age and age^2
formula_t1 <- log_wage_gain ~ edu_group + female + age_at_us_job + I(age_at_us_job^2) + factor(country) + factor(cohort_decade)

model_t1 <- lm(formula_t1, data = df3)

# HC3 robust standard errors
vcov_hc3 <- sandwich::vcovHC(model_t1, type = "HC3")
coeftab <- lmtest::coeftest(model_t1, vcov. = vcov_hc3)

# Extract focal coefficient
coef_name <- "edu_groupnever_high_school"
if (!(coef_name %in% rownames(coeftab))) {
  stop(sprintf("Focal coefficient '%s' not found in model. Levels present: %s", coef_name, paste(rownames(coeftab), collapse = ", ")))
}

beta <- unname(coeftab[coef_name, "Estimate"]) 
se <- unname(coeftab[coef_name, "Std. Error"]) 
tval <- unname(coeftab[coef_name, "t value"]) 
pval <- unname(coeftab[coef_name, "Pr(>|t|)"])

# 95% CI using normal approximation with robust SE
ci_low <- beta - 1.96 * se
ci_high <- beta + 1.96 * se
percent_diff <- 100 * (exp(beta) - 1)

# Report sample flow
cat("Task1 Sample Flow (rows)\n")
cat(sprintf("  Starting rows: %d\n", n0))
cat(sprintf("  Removed non-positive/invalid adjusted wages: %d\n", n_drop_nonpos))
cat(sprintf("  Removed rows with missing material variables: %d\n", n_drop_missing_material))
cat(sprintf("  Removed non-focal education groups: %d\n", n_drop_nonfocal_edu))
cat(sprintf("  Final analytic rows: %d\n\n", n_final))

# Report focal result
cat("Task1 OLS with HC3 robust SEs: log_wage_gain ~ edu_group + female + age + age^2 + country FE + cohort FE\n")
cat(sprintf("  Coef (never_high_school vs college_degree): %.6f\n", beta))
cat(sprintf("  Robust SE: %.6f\n", se))
cat(sprintf("  t value: %.4f\n", tval))
cat(sprintf("  p value: %.6f\n", pval))
cat(sprintf("  95%% CI: [%.6f, %.6f]\n", ci_low, ci_high))
cat(sprintf("  Percent difference: %.2f%%%%\n", percent_diff))

# Column references (for preflight)
# Referenced columns: edyrs, yearLastHomeJob, yearLastUsJob, sex, yrborn, occGroupLastHomeJob, lastHomeWage, lastHomeWageAdjusted, occGroupLastUsJob, lastUsWage, lastUsWageAdjusted, country

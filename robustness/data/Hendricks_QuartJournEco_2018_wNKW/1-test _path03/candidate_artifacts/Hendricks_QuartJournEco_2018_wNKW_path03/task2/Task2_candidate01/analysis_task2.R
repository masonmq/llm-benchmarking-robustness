# Task2 analysis script for Hendricks & Schoellman (QJE 2018)
# Comparable-result reanalysis per instruction: pooled sample including Mexico; do NOT control for sector or region (rural/urban)
# Model: OLS of log_wage_gain on education group (never_high_school vs college_degree) with demographic controls (female, age, age^2). No sector/region or country FE.

suppressPackageStartupMessages({
  library(readxl)
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

# Verify presence of country (even if not used as control)
if (!("country" %in% names(df))) stop("Missing required column: country")

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

# Drop rows with missing in material variables
keep_complete <- is.finite(df1$log_wage_gain) & is.finite(df1$age_at_us_job) & !is.na(df1$female) & !is.na(df1$edu_group)

n_drop_missing_material <- sum(!keep_complete)

df2 <- df1[keep_complete, , drop = FALSE]

# Restrict to focal education groups only (drop 'other')
keep_focal_edu <- df2$edu_group %in% c("college_degree", "never_high_school")

n_drop_nonfocal_edu <- sum(!keep_focal_edu)

df3 <- droplevels(df2[keep_focal_edu, , drop = FALSE])

# Relevel to set college_degree as reference
df3$edu_group <- relevel(df3$edu_group, ref = "college_degree")

n_final <- nrow(df3)

# Fit OLS with demographic controls only (no sector, no region, no country FE)
formula_t2 <- log_wage_gain ~ edu_group + female + age_at_us_job + I(age_at_us_job^2)

model_t2 <- lm(formula_t2, data = df3)

sum_t2 <- summary(model_t2)
coef_row <- which(rownames(sum_t2$coefficients) == "edu_groupnever_high_school")
if (length(coef_row) != 1) {
  stop("Focal coefficient edu_groupnever_high_school not found in model.")
}

beta <- sum_t2$coefficients[coef_row, 1]
se <- sum_t2$coefficients[coef_row, 2]
tval <- sum_t2$coefficients[coef_row, 3]
pval <- sum_t2$coefficients[coef_row, 4]
ci_low <- beta - 1.96 * se
ci_high <- beta + 1.96 * se
percent_diff <- 100 * (exp(beta) - 1)

# Report sample flow
cat("Task2 Sample Flow (rows)\n")
cat(sprintf("  Starting rows: %d\n", n0))
cat(sprintf("  Removed non-positive/invalid adjusted wages: %d\n", n_drop_nonpos))
cat(sprintf("  Removed rows with missing material variables: %d\n", n_drop_missing_material))
cat(sprintf("  Removed non-focal education groups: %d\n", n_drop_nonfocal_edu))
cat(sprintf("  Final analytic rows: %d\n\n", n_final))

# Report focal result
cat("Task2 OLS (no sector/region, demographics only): log_wage_gain ~ edu_group + female + age + age^2\n")
cat(sprintf("  Coef (never_high_school vs college_degree): %.6f\n", beta))
cat(sprintf("  SE: %.6f\n", se))
cat(sprintf("  t value: %.4f\n", tval))
cat(sprintf("  p value: %.6f\n", pval))
cat(sprintf("  95%% CI: [%.6f, %.6f]\n", ci_low, ci_high))
cat(sprintf("  Percent difference: %.2f%%%%\n", percent_diff))

# Column references (for preflight)
# Referenced columns: edyrs, yearLastHomeJob, yearLastUsJob, sex, yrborn, lastHomeWage, lastHomeWageAdjusted, lastUsWage, lastUsWageAdjusted, country

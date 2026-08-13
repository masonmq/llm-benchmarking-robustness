#!/usr/bin/env Rscript
# Task1: Controlled OLS with country FE and cluster-robust SEs
suppressPackageStartupMessages({
  library(readxl)
  library(dplyr)
  library(lmtest)
  library(sandwich)
})

source("helpers_loader.R")

cat("Running Task1: controlled_log_wage_gain_with_sector_region_countryFE_clusteredSE\n\n")

# Load data
xls_path <- find_data_file()
cat("Data file:", xls_path, "\n\n")
df <- readxl::read_xlsx(xls_path)

# Fit model per plan (with available controls)
res <- fit_task1(df)

# Report controls used
cat("Controls used in Task1 model (RHS terms):\n")
print(res$used_controls)
cat("\n")

# Print analytic sample counts by edu_group
print_group_counts(res$data)
cat("\n")

# Print coefficient table with cluster-robust SEs
cat("OLS coefficients with cluster-robust (country) SEs:\n")
print(res$coef_table)
cat("\n")

# Extract and print focal result
focal <- report_focal(res$coef_table, which = "task1")
cat("Focal coefficient (never_high_school vs college_degree):\n")
cat(sprintf("  Estimate (log pts): %.6f\n  Std. Error: %.6f\n  p-value: %.6f\n  95%% CI: [%.6f, %.6f]\n  Percent difference: %.2f%%%%\n",
          focal$estimate, focal$std_error, focal$p_value, focal$ci_lower, focal$ci_upper, focal$percent_diff))

cat("\nTask1 completed.\n")

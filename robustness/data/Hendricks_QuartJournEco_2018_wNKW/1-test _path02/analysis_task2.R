#!/usr/bin/env Rscript
# Task2: OLS with country FE only (no sector/rural controls)
suppressPackageStartupMessages({
  library(readxl)
  library(dplyr)
})

source("helpers_loader.R")

cat("Running Task2: pooled_poor_country_countryFE_no_sector_region\n\n")

# Load data
xls_path <- find_data_file()
cat("Data file:", xls_path, "\n\n")
df <- readxl::read_xlsx(xls_path)

# Fit model per plan (country FE only)
res <- fit_task2(df)

# Report controls used
cat("Controls used in Task2 model (RHS terms):\n")
print(res$used_controls)
cat("\n")

# Print analytic sample counts by edu_group
print_group_counts(res$data)
cat("\n")

# Print coefficient table (conventional SEs)
cat("OLS coefficients (conventional SEs):\n")
print(res$coef_table)
cat("\n")

# Extract and print focal result
focal <- report_focal(res$coef_table, which = "task2")
cat("Focal coefficient (never_high_school vs college_degree):\n")
cat(sprintf("  Estimate (log pts): %.6f\n  Std. Error: %.6f\n  p-value: %.6f\n  95%% CI: [%.6f, %.6f]\n  Percent difference: %.2f%%%%\n",
          focal$estimate, focal$std_error, focal$p_value, focal$ci_lower, focal$ci_upper, focal$percent_diff))

cat("\nTask2 completed.\n")

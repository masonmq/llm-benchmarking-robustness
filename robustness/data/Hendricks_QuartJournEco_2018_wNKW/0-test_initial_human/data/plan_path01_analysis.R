# Planned analysis code for Hendricks_QuartJournEco_2018_wNKW_path01
# Do not run during planning. This script is intended for the execution agent.

suppressPackageStartupMessages({
  library(readxl)
  library(dplyr)
  library(broom)
  library(sandwich)
  library(lmtest)
  library(readr)
})

`%||%` <- function(a, b) if (!is.null(a)) a else b

input_file <- "data/wage_gain_table.xlsx"
if (!file.exists(input_file)) {
  input_file <- file.path(dirname(sys.frame(1)$ofile %||% "data/plan_path01_analysis.R"), "wage_gain_table.xlsx")
}
if (!file.exists(input_file)) {
  input_file <- "data/Hendricks_QuartJournEco_2018_wNKW/test/data/wage_gain_table.xlsx"
}

raw <- read_excel(input_file)

analysis_df <- raw %>%
  mutate(
    log_home_wage = log(lastHomeWageAdjusted),
    log_us_wage = log(lastUsWageAdjusted),
    log_wage_gain = log_us_wage - log_home_wage,
    wage_gain_ratio = lastUsWageAdjusted / lastHomeWageAdjusted,
    age_last_us_job = yearLastUsJob - yrborn,
    education_group = case_when(
      edyrs < 9 ~ "never_high_school",
      edyrs >= 9 & edyrs <= 11 ~ "some_high_school",
      edyrs == 12 ~ "high_school_degree",
      edyrs >= 13 & edyrs <= 15 ~ "some_college",
      edyrs >= 16 ~ "college_degree",
      TRUE ~ NA_character_
    ),
    education_group = factor(
      education_group,
      levels = c("college_degree", "some_college", "high_school_degree", "some_high_school", "never_high_school")
    ),
    country = factor(country),
    sex = factor(sex)
  ) %>%
  filter(
    is.finite(log_wage_gain),
    is.finite(wage_gain_ratio),
    !is.na(education_group),
    !is.na(country),
    !is.na(sex),
    is.finite(age_last_us_job)
  )

# Task 1: conclusion-oriented unrestricted reanalysis.
# Directly compare wage gains by schooling category, with college degree as reference,
# controlling for origin country fixed effects and basic demographic/job-timing covariates available in the file.
task1_model <- lm(log_wage_gain ~ education_group + country + sex + age_last_us_job + yearLastHomeJob + yearLastUsJob, data = analysis_df)
task1_vcov <- vcovHC(task1_model, type = "HC1")
task1_results <- tidy(coeftest(task1_model, vcov. = task1_vcov)) %>%
  mutate(task = "Task1", model = "M1_log_gain_country_demographic_controls")

# Task 2: comparable result-oriented reanalysis.
# Use the pooled available immigrant sample from poor countries in NIS/Migration Projects as represented by wage_gain_table.xlsx,
# include Mexico, and do not control for sector agriculture/nonagriculture or rural/urban region.
# The model gives the single comparable result for never_high_school relative to college_degree.
task2_model <- lm(log_wage_gain ~ education_group + country, data = analysis_df)
task2_vcov <- vcovHC(task2_model, type = "HC1")
task2_results <- tidy(coeftest(task2_model, vcov. = task2_vcov)) %>%
  mutate(task = "Task2", model = "M1_log_gain_country_fixed_effects_no_sector_region")

# Additional descriptive comparison of the focal groups for standardized reporting.
focal_descriptives <- analysis_df %>%
  filter(education_group %in% c("never_high_school", "college_degree")) %>%
  group_by(education_group) %>%
  summarise(
    n = n(),
    mean_log_wage_gain = mean(log_wage_gain, na.rm = TRUE),
    sd_log_wage_gain = sd(log_wage_gain, na.rm = TRUE),
    mean_wage_gain_ratio = mean(wage_gain_ratio, na.rm = TRUE),
    median_wage_gain_ratio = median(wage_gain_ratio, na.rm = TRUE),
    .groups = "drop"
  )

# Save outputs.
out_dir <- "results"
if (!dir.exists(out_dir)) dir.create(out_dir, recursive = TRUE)
write_csv(task1_results, file.path(out_dir, "task1_path01_results.csv"))
write_csv(task2_results, file.path(out_dir, "task2_path01_results.csv"))
write_csv(focal_descriptives, file.path(out_dir, "focal_group_descriptives_path01.csv"))

cat("Task1 focal coefficient (never_high_school vs college_degree):\n")
print(task1_results %>% filter(term == "education_groupnever_high_school"))
cat("Task2 focal coefficient (never_high_school vs college_degree):\n")
print(task2_results %>% filter(term == "education_groupnever_high_school"))
cat("Focal group descriptives:\n")
print(focal_descriptives)

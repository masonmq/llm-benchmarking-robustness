# Planned robustness analysis for Hendricks_QuartJournEco_2018_wNKW
# Focal claim: immigrants who have never been to high school gain more on migration to the United States than immigrants with a college degree.
# This script is intended for execution by the Execute Agent; it is not run during planning.

suppressPackageStartupMessages({
  library(readxl)
  library(dplyr)
  library(broom)
})

data_path <- file.path("data", "Hendricks_QuartJournEco_2018_wNKW", "test", "data", "wage_gain_table.xlsx")
if (!file.exists(data_path)) {
  data_path <- file.path("/app", "data", "wage_gain_table.xlsx")
}
if (!file.exists(data_path)) {
  data_path <- "data/wage_gain_table.xlsx"
}

raw <- read_excel(data_path)

make_analysis_data <- function(dat) {
  dat %>%
    mutate(
      edyrs = as.numeric(edyrs),
      lastHomeWageAdjusted = as.numeric(lastHomeWageAdjusted),
      lastUsWageAdjusted = as.numeric(lastUsWageAdjusted),
      age_at_us_job = as.numeric(yearLastUsJob) - as.numeric(yrborn),
      female = ifelse(sex == 2, 1, ifelse(sex == 1, 0, NA_real_)),
      log_home_wage = log(lastHomeWageAdjusted),
      log_us_wage = log(lastUsWageAdjusted),
      log_wage_gain = log_us_wage - log_home_wage,
      edu_group = case_when(
        edyrs < 9 ~ "never_high_school",
        edyrs >= 16 ~ "college_degree",
        TRUE ~ "other_education"
      ),
      never_high_school = ifelse(edu_group == "never_high_school", 1, 0),
      college_degree = ifelse(edu_group == "college_degree", 1, 0)
    ) %>%
    filter(is.finite(log_wage_gain), is.finite(edyrs), lastHomeWageAdjusted > 0, lastUsWageAdjusted > 0)
}

analysis_data <- make_analysis_data(raw)

# Task 1: unrestricted conclusion-oriented reanalysis.
# Estimate the education-gradient in log wage gains using all observations in the authorized wage_gain_table file.
# Controls are demographic and source-country controls available in the file; no sector or rural/urban controls are included because they are not in this data file.
task1_data <- analysis_data %>%
  filter(edu_group %in% c("never_high_school", "college_degree")) %>%
  mutate(edu_group = factor(edu_group, levels = c("college_degree", "never_high_school")))

task1_model <- lm(log_wage_gain ~ edu_group + female + age_at_us_job + I(age_at_us_job^2) + factor(country), data = task1_data)

task1_main <- tidy(task1_model, conf.int = TRUE) %>%
  filter(term == "edu_groupnever_high_school") %>%
  mutate(
    percent_difference = 100 * (exp(estimate) - 1),
    percent_conf_low = 100 * (exp(conf.low) - 1),
    percent_conf_high = 100 * (exp(conf.high) - 1),
    task = "Task1"
  )

# Task 2: comparable-result path under the assigned restriction.
# Use the pooled poor-country sample in the supplied file, including Mexico, and do not control for sector or region.
# Compare never-high-school immigrants with college-degree immigrants using a single no-sector/no-region OLS result.
task2_data <- analysis_data %>%
  filter(edu_group %in% c("never_high_school", "college_degree")) %>%
  mutate(edu_group = factor(edu_group, levels = c("college_degree", "never_high_school")))

task2_model <- lm(log_wage_gain ~ edu_group, data = task2_data)

task2_main <- tidy(task2_model, conf.int = TRUE) %>%
  filter(term == "edu_groupnever_high_school") %>%
  mutate(
    percent_difference = 100 * (exp(estimate) - 1),
    percent_conf_low = 100 * (exp(conf.low) - 1),
    percent_conf_high = 100 * (exp(conf.high) - 1),
    task = "Task2"
  )

summary_counts <- bind_rows(
  task1_data %>% count(edu_group) %>% mutate(task = "Task1"),
  task2_data %>% count(edu_group) %>% mutate(task = "Task2")
)

print("Task 1 main coefficient: never high school vs college degree on log wage gain")
print(task1_main)
print(summary(task1_model))
print("Task 2 main coefficient: never high school vs college degree on log wage gain")
print(task2_main)
print(summary(task2_model))
print("Analytic sample counts")
print(summary_counts)

# Execute Agent output extraction: print machine-readable summaries without changing analyses.
combined_main <- bind_rows(task1_main, task2_main)
cat("\nEXECUTE_AGENT_MAIN_RESULTS_CSV\n")
write.csv(as.data.frame(combined_main), stdout(), row.names = FALSE)
cat("EXECUTE_AGENT_SAMPLE_COUNTS_CSV\n")
write.csv(as.data.frame(summary_counts), stdout(), row.names = FALSE)

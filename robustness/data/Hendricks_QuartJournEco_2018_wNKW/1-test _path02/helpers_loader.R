# Helpers and data loader for Hendricks_QuartJournEco_2018_wNKW tasks
suppressPackageStartupMessages({
  library(readxl)
  library(dplyr)
  library(lmtest)
  library(sandwich)
})

# Find the data file path robustly
find_data_file <- function() {
  candidates <- c(
    "data/wage_gain_table.xlsx",
    "./data/wage_gain_table.xlsx",
    file.path(getwd(), "data", "wage_gain_table.xlsx"),
    "/home/mason/mygpu/llm-robustness/llm-benchmarking-robustness/robustness/data/Hendricks_QuartJournEco_2018_wNKW/test/data/wage_gain_table.xlsx"
  )
  for (p in candidates) {
    if (file.exists(p)) return(p)
  }
  stop("wage_gain_table.xlsx not found in expected locations.")
}

# Safe numeric coercion
as_numeric_safe <- function(x) {
  if (is.numeric(x)) return(x)
  suppressWarnings(as.numeric(x))
}

# Prepare common variables used by both tasks
prepare_common <- function(df) {
  # Coerce key columns if present
  for (nm in c("edyrs", "lastHomeWageAdjusted", "lastUsWageAdjusted", "yearLastUsJob", "yrborn")) {
    if (nm %in% names(df)) df[[nm]] <- as_numeric_safe(df[[nm]])
  }
  # Sex can be numeric 1/2 or string
  if ("sex" %in% names(df)) {
    if (is.numeric(df$sex)) {
      df$female <- ifelse(df$sex == 2, 1L, ifelse(df$sex == 1, 0L, NA_integer_))
    } else {
      sx <- tolower(trimws(as.character(df$sex)))
      df$female <- ifelse(sx %in% c("2", "f", "female"), 1L,
                          ifelse(sx %in% c("1", "m", "male"), 0L, NA_integer_))
    }
  } else {
    df$female <- NA_integer_
  }

  # Compute age at last US job if possible
  if (all(c("yearLastUsJob", "yrborn") %in% names(df))) {
    df$age_at_us_job <- df$yearLastUsJob - df$yrborn
  } else {
    df$age_at_us_job <- NA_real_
  }

  # Ensure adjusted wages exist and are positive; compute logs
  if (!all(c("lastHomeWageAdjusted", "lastUsWageAdjusted") %in% names(df))) {
    stop("Required columns lastHomeWageAdjusted and lastUsWageAdjusted are missing.")
  }
  df <- df %>%
    mutate(
      lastHomeWageAdjusted = as_numeric_safe(lastHomeWageAdjusted),
      lastUsWageAdjusted = as_numeric_safe(lastUsWageAdjusted),
      log_home_wage = ifelse(lastHomeWageAdjusted > 0, log(lastHomeWageAdjusted), NA_real_),
      log_us_wage = ifelse(lastUsWageAdjusted > 0, log(lastUsWageAdjusted), NA_real_),
      log_wage_gain = log_us_wage - log_home_wage
    ) %>%
    filter(is.finite(log_home_wage), is.finite(log_us_wage), is.finite(log_wage_gain))

  # Education group: never_high_school (<9) vs college_degree (>=16)
  if (!("edyrs" %in% names(df))) stop("Required column edyrs is missing.")
  df <- df %>%
    mutate(
      edyrs = as_numeric_safe(edyrs),
      edu_group = case_when(
        !is.na(edyrs) & edyrs < 9 ~ "never_high_school",
        !is.na(edyrs) & edyrs >= 16 ~ "college_degree",
        TRUE ~ NA_character_
      ),
      edu_group = factor(edu_group, levels = c("college_degree", "never_high_school"))
    ) %>%
    filter(!is.na(edu_group))

  # Derive sector_agriculture if we can detect agriculture in origin occupation group
  if ("occGroupLastHomeJob" %in% names(df)) {
    df$sector_agriculture <- ifelse(grepl("agri", tolower(as.character(df$occGroupLastHomeJob))), 1L, 0L)
  } else if ("occGroupLastUsJob" %in% names(df)) {
    df$sector_agriculture <- ifelse(grepl("agri", tolower(as.character(df$occGroupLastUsJob))), 1L, 0L)
  } else {
    df$sector_agriculture <- NA_integer_
  }

  # Grew up rural indicator not available in provided columns; attempt to detect any column containing 'rural'
  rural_cols <- grep("rural|urban", names(df), ignore.case = TRUE, value = TRUE)
  if (length(rural_cols) > 0) {
    # Use the first detected rural/urban column to create binary rural indicator
    rc <- rural_cols[1]
    vals <- tolower(as.character(df[[rc]]))
    df$grew_up_rural <- ifelse(grepl("rural", vals), 1L,
                          ifelse(grepl("urban", vals), 0L, NA_integer_))
  } else {
    df$grew_up_rural <- NA_integer_
  }

  # Country factor
  if (!("country" %in% names(df))) stop("Required column country is missing.")
  df$country <- as.factor(df$country)

  # Keep reasonable ages if available; otherwise retain all
  if ("age_at_us_job" %in% names(df) && any(!is.na(df$age_at_us_job))) {
    df <- df %>% filter(is.na(age_at_us_job) | (age_at_us_job >= 14 & age_at_us_job <= 80))
  }

  df
}

# Fit Task1 model: includes controls female, age, age^2, sector_agriculture, grew_up_rural, and country FE
fit_task1 <- function(df) {
  data <- prepare_common(df)

  # Determine availability of sector and rural controls
  include_sector <- ("sector_agriculture" %in% names(data)) && any(!is.na(data$sector_agriculture))
  include_rural  <- ("grew_up_rural" %in% names(data)) && any(!is.na(data$grew_up_rural))

  rhs_terms <- c(
    "edu_group",
    "female",
    "age_at_us_job",
    "I(age_at_us_job^2)",
    if (include_sector) "sector_agriculture" else NULL,
    if (include_rural)  "grew_up_rural" else NULL,
    "factor(country)"
  )
  fmla <- as.formula(paste("log_wage_gain ~", paste(rhs_terms, collapse = " + ")))

  # Drop rows with missing values in used variables (refer to underlying columns, not formula wrappers)
  vars_needed <- unique(c(
    "log_wage_gain",
    "edu_group",
    "female",
    "age_at_us_job",
    if (include_sector) "sector_agriculture" else NULL,
    if (include_rural)  "grew_up_rural" else NULL,
    "country"
  ))
  analysis_df <- data[complete.cases(data[, vars_needed, drop = FALSE]), ]

  if (nrow(analysis_df) == 0) stop("No complete cases available for Task1 model after applying required variables.")

  fit <- lm(fmla, data = analysis_df)

  # Cluster-robust SEs at the country level
  vc <- sandwich::vcovCL(fit, cluster = ~ country, type = "HC1")
  ct <- lmtest::coeftest(fit, vcov. = vc)

  list(
    data = analysis_df,
    fit = fit,
    coef_table = ct,
    used_controls = rhs_terms
  )
}# Fit Task2 model: only edu_group and country FE
fit_task2 <- function(df) {
  data <- prepare_common(df)
  rhs_terms <- c("edu_group", "factor(country)")
  fmla <- as.formula(paste("log_wage_gain ~", paste(rhs_terms, collapse = " + ")))
  analysis_df <- data[complete.cases(data[, c("log_wage_gain", "edu_group", "country"), drop = FALSE]), ]
  if (nrow(analysis_df) == 0) stop("No complete cases available for Task2 model after applying required variables.")
  fit <- lm(fmla, data = analysis_df)
  sm <- summary(fit)
  list(
    data = analysis_df,
    fit = fit,
    coef_table = sm$coefficients,
    used_controls = rhs_terms
  )
}

# Extract and print focal result
report_focal <- function(coef_table, which = c("task1", "task2")) {
  which <- match.arg(which)
  coef_name <- "edu_groupnever_high_school"

  if (which == "task1") {
    # coef_table is a matrix from coeftest with columns: Estimate, Std. Error, z value, Pr(>|z|)
    rn <- rownames(coef_table)
    if (!(coef_name %in% rn)) stop(paste0("Focal coefficient ", coef_name, " not found in model."))
    est <- as.numeric(coef_table[coef_name, 1])
    se  <- as.numeric(coef_table[coef_name, 2])
    z   <- as.numeric(coef_table[coef_name, 3])
    p   <- as.numeric(coef_table[coef_name, 4])
    ci  <- est + c(-1, 1) * 1.96 * se
  } else {
    # task2: coef_table is summary coefficients with columns: Estimate, Std. Error, t value, Pr(>|t|)
    rn <- rownames(coef_table)
    if (!(coef_name %in% rn)) stop(paste0("Focal coefficient ", coef_name, " not found in model."))
    est <- as.numeric(coef_table[coef_name, 1])
    se  <- as.numeric(coef_table[coef_name, 2])
    t   <- as.numeric(coef_table[coef_name, 3])
    p   <- as.numeric(coef_table[coef_name, 4])
    ci  <- est + c(-1, 1) * 1.96 * se
  }
  pct <- 100 * (exp(est) - 1)

  list(
    estimate = est,
    std_error = se,
    p_value = p,
    ci_lower = ci[1],
    ci_upper = ci[2],
    percent_diff = pct
  )
}

# Utility to pretty print counts by edu_group
print_group_counts <- function(df) {
  cat("Analytic sample counts by education group:\n")
  print(df %>% count(edu_group))
}

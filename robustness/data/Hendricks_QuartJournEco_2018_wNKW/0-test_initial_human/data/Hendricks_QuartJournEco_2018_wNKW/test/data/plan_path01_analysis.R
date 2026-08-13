# Compatibility wrapper for orchestrator path resolution.
args <- commandArgs(trailingOnly = FALSE)
file_arg <- args[grepl("^--file=", args)]
this_file <- sub("^--file=", "", file_arg[1])
study_root <- normalizePath(file.path(dirname(this_file), "../../../.."), mustWork = TRUE)
setwd(study_root)
source("data/plan_path01_analysis.R", chdir = FALSE)

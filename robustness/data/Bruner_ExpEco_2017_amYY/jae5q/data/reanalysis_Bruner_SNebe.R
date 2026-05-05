#!/usr/bin/env Rscript
# Wrapper script to invoke the Python analysis entrypoint.
# This preserves the orchestrator's R-based entry while running the actual analysis in Python.

# Ensure required directories and data placement expected by the Python script
try({
  dir.create("/app/data", recursive=TRUE, showWarnings=FALSE)
  file.copy("data/RiskData.dta", "/app/data/RiskData.dta", overwrite=TRUE)
  dir.create("/app/artifacts", recursive=TRUE, showWarnings=FALSE)
}, silent=TRUE)

cmd <- "python3 /workspace/data/analysis_entrypoint.py"
status <- system(cmd, intern=FALSE, ignore.stdout=FALSE, ignore.stderr=FALSE)
if (status != 0) {
  stop(paste("Python analysis failed with status", status))
}
cat("Python analysis executed successfully via R wrapper.\n")

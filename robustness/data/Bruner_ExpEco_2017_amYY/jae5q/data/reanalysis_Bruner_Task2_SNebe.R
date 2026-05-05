# Analysis Code Multi100 Project
# Reanalysis of Bruner (2017; https://doi.org/10.1007/s10683-016-9484-1 )
# S. Nebe, Zurich, May|2022 

# Claim: the likelihood ... [of decision error] should decrease with the degree of risk aversion (p. 269.)
# Hypothesis: Higher risk aversion is associated with fewer decision errors.
# Operational hypothesis: More frequent choices of safe options in both the risk and probability variation tasks
#                         are associated with fewer violations of stochastic dominance in the lottery variation task.
# Statistical hypothesis: Average number of safe choices in RV and PV tasks are negatively correlated with 
#                         number of violations of stochastic dominance in LV task.

# Libraries
if (!require("pacman")) install.packages("pacman") #requires R v3.5 or newer
p_load(data.table,stats,psych,dplyr,readstata13,ggplot2)
# p_load(R.matlab, qdapTools,lme4,ggplot2,pastecs,car,MASS,optimx,tidyr,lmerTest,MCMCglmm,tibble,
       # fitdistrplus,h5,dfoptim,boot,interactions,simr,reghelper,rmcorr,r2mlm,boot,patchwork) 


# load data (Stata 13 data file) & convert to data table
bru_dat <- read.dta13("RiskData.dta")
bru_dat <- data.table(bru_dat)

# exclude 2 "participants", which were not participants but the experimenter 
# (evident at their age of 99 years, info found in analysis code of original authors:
# //In 2 sessions an extra subject station was started in ZTREE.
# //These data were not are not entered by subjects and are not
# //used in the analysis.
# drop if age==99)
bru_dat <- bru_dat[age!=99]
# sample size = 106 now (consistent with paper)

# calculate the sum of safe choices (i.e., option B) for probability variation task (PV, experiment 1) 
# and risk variation task (RV, experiment 2)
# Risk1x and Risk2x variables are 1 when choosing the safe option, 0 when choosing the gamble (I guess, but without a code book I can't be certain)
bru_dat[,risk1_sum := Risk11+Risk12+Risk13+Risk14+Risk15+Risk16+Risk17+Risk18+Risk19+Risk110]
bru_dat[,risk2_sum := Risk21+Risk22+Risk23+Risk24+Risk25+Risk26+Risk27+Risk28+Risk29+Risk210]

# calculate average number of safe choices for both PV and RV
bru_dat[,risk_avg_safe := (risk1_sum+risk2_sum)/2]

# calculate number of stochastically dominant choices in lottery variation task (LV, experiment 3)
# stochastically dominant = choosing the safer option
# p. 265: "The RV lottery is safer for the first four decisions and the PV lottery is safer for the last five decisions."
# Risk3x variables are 1 when choosing the RV lottery, 0 when choosing the PV lottery (I guess, but without a code book I can't be certain)
# choice in 5th item of LV task is always correct b/c both options are the same
bru_dat[,risk3_sum_dom := Risk31+Risk32+Risk33+Risk34+1+abs(Risk36-1)+abs(Risk37-1)+abs(Risk38-1)+abs(Risk39-1)+abs(Risk310-1)]

# define decision errors (i.e., violation of stochastic dominance in LV task)
# violation = choosing the less safe option 
bru_dat[,risk3_sum_errors:= abs(Risk31-1)+abs(Risk32-1)+abs(Risk33-1)+abs(Risk34-1)+Risk36+Risk37+Risk38+Risk39+Risk310]

# Hypothesis test: correlation of average number of safe choices in RV and PV w/ number of violations in LV
describe(bru_dat$risk_avg_safe)
hist(bru_dat$risk_avg_safe)
describe(bru_dat$risk3_sum_errors)
hist(bru_dat$risk3_sum_errors)
# scale and distribution of variables make Pearson's correlation a suboptimal choice

# look at number of ties (i.e., number of participants w/ same values in both variables)
table(bru_dat$risk_avg_safe,bru_dat$risk3_sum_errors)
# rather many ties makes Spearman's correlation a suboptimal choice 

# compute Kendall's tau correlation
result <- corr.test(bru_dat$risk_avg_safe,bru_dat$risk3_sum_errors,method="pearson",ci=TRUE)
print(result,short=FALSE)

# scatter plot of correlation w/ a loess curve for visualization
ggplot(data=bru_dat,aes(x=risk_avg_safe,y=risk3_sum_errors)) +
  geom_count(na.rm=T) +
  geom_smooth(method="loess") +
  scale_x_continuous(breaks=c(1,2,3,4,5,6,7,8,9,10),limits=c(0,10)) +
  scale_y_continuous(breaks=c(1,2,3,4,5,6,7,8,9,10),limits=c(0,10)) +
  xlab("Average number of safe choices in RV and PV") +
  ylab("Number of decision errors in LV") +
  labs(size="number of \nparticipants") +
  theme_classic()

# 1. library required -------

library(foreign) # for reading stata data
library(dplyr)
library(ggplot2)
library(tidyr)

# 2. setting working directory ------

setwd('D:/multi100/R_analysis')

# 3. reading the stata data into the working directory ------
DATA_1900_2004 <- read.dta("DATA_1900_2004.dta") 
DATA_TABLE9<-read.dta("DATA_TABLE9.dta")

# 4. compute a few variables that are needed for the analysis ----

# compute state-month interaction #
DATA_1900_2004 <- DATA_1900_2004 %>% mutate(statemo = stfips * 1000 + month)
# compute year-month interaction #
DATA_1900_2004 <- DATA_1900_2004 %>% mutate(yearmo = year * 1000 + month)
# compute quadratic time #
DATA_1900_2004 <- DATA_1900_2004 %>% mutate(year2 = year^2)

# get the sum of the days of below 40 degrees, and coded this variable as "b10_b_4"
DATA_1900_2004 <- DATA_1900_2004 %>% mutate(b10_b_4 = b10_1 + b10_2 + b10_3 + b10_4)

# 5. Add "decade" variable to test for the hypothesis ------

# 5.1 Add "decade" with 11 levels (one level every ten years)------------
DATA_1900_2004 <-DATA_1900_2004 %>% mutate(decade = case_when(year >= 1900 & year < 1910 ~ 1,
                                                              year >= 1910 & year < 1920 ~ 2,
                                                              year >= 1920 & year < 1930 ~ 3,
                                                              year >= 1930 & year < 1940 ~ 4,
                                                              year >= 1940 & year < 1950 ~ 5,
                                                              year >= 1950 & year < 1960 ~ 6,
                                                              year >= 1960 & year < 1970 ~ 7,
                                                              year >= 1970 & year < 1980 ~ 8,
                                                              year >= 1980 & year < 1990 ~ 9,
                                                              year >= 1990 & year < 2000 ~ 10,
                                                              year >= 2000 & year < 2010 ~ 11)) # only until 2004 for the last decade 

# 5.2 Add "decade_two" variable with two levels (before/after the year 1959) -------
# This is done according to what is shown in Table 3, where the claim was drawn from
DATA_1900_2004 <-DATA_1900_2004 %>% mutate(decade_two = case_when(year <= 1959 ~ 1,
                                                                  year >  1959 ~ 2)) 

# 6 Data cleaning -----
# remove the missing data - according to the mortality rate #
DATA_1900_2004_no_missing <- DATA_1900_2004[!is.na(DATA_1900_2004$lndrate),]

# Get the data from year 1931 on since the paper only reported data from the year 1931 on 
DATA_1931_2004_no_missing <- subset (DATA_1900_2004_no_missing, DATA_1900_2004_no_missing$year >= 1931)
# This dataset (DATA_1931_2004_no_missing) is to be used for the modelling and plotting 

# 7.Models & Plots 
# Regression with all the bins except for [60-70)° F (b_10_7) + all control variables specified in the paper
# Control variables include: share of state population (four categories), interacting with month; log per capta income, interacting with month;
# state-month and year-month fixed effects; quadratic term of the year; unusually high or low amounts of precipitation 
M1 <- lm(data = DATA_1931_2004_no_missing, lndrate ~ b10_1 + b10_2 + b10_3 + b10_4 + b10_5 + b10_6 + b10_8 + b10_9 + b10_10 +
                                            (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month +
                                            lri * month + statemo + yearmo + year2 + devp25 + devp75)
summary(M1)

# regression with all the bins except for [60-70)° F (b_10_7) + all control variables specified in the paper + interaction with decades (categorical variable - two levels)
M2 <- lm(data = DATA_1931_2004_no_missing, lndrate ~ (b10_1 + b10_2 + b10_3 + b10_4 + b10_5 + b10_6 + b10_8 + b10_9 + b10_10) * factor(decade_two) +
                                          (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month +
                                           lri * month + statemo + yearmo + year2 + devp25 + devp75)
summary(M2)

# plot to see the interaction effect 
ggplot(DATA_1931_2004_no_missing, aes(x=b10_10, y=lndrate, color = factor(decade_two))) + geom_point() + geom_smooth(method = "lm") 
# As seen from the plot, for days with average temperature higher than 90, the mortality rate decreases for the later decades. 
# This is also consistent with the significant interaction effect
ggplot(DATA_1931_2004_no_missing, aes(x=b10_1, y=lndrate, color = factor(decade_two))) + geom_point() + geom_smooth(method = "lm")
# For days with average temperature lower than 10, this contradicts the claim from the paper
ggplot(DATA_1931_2004_no_missing, aes(x=b10_9, y=lndrate, color = factor(decade_two))) + geom_point() + geom_smooth(method = "lm")
# For days with average temperature between 80 and 89, the interaction is non-significant

# regression with all the bins except for [60-70)° F (b_10_7) + all control variables specified in the paper + interaction with decades (categorical variable - seven levels)
M3 <- lm(data = DATA_1931_2004_no_missing, lndrate ~ (b10_1 + b10_2 + b10_3 + b10_4 + b10_5 + b10_6 + b10_8 + b10_9 + b10_10) * factor(decade) +
           (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month +
           lri * month + statemo + yearmo + year2 + devp25 + devp75)
summary(M3)

# plot to see the interaction effect 
ggplot(DATA_1931_2004_no_missing, aes(x=b10_10, y=lndrate, color = factor(decade))) + geom_point() + geom_smooth(method = "lm")
# As seen from the slopes of different decades, the temperature-mortality relationships are not always declining, but there is a general trend
# that later decades have lower slopes as compare to the earlier ones

ggplot(DATA_1931_2004_no_missing, aes(x=b10_9, y=lndrate, color = factor(decade))) + geom_point() + geom_smooth(method = "lm")
# There seem to be an increase in the temperature-mortality relationship for temperature between 80 and 89

# Same regression with only extreme values - two decade levels #
M4 <- lm(data = DATA_1931_2004_no_missing, lndrate ~ (b10_9 + b10_10 + b10_b_4) * factor(decade_two) +
                                                      (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month +
                                                      lri * month + statemo + yearmo + year2 + devp25 + devp75)
summary(M4)


ggplot(DATA_1931_2004_no_missing, aes(x=b10_10, y=lndrate, color = factor(decade_two))) + geom_point() + geom_smooth(method = "lm")
# Again, evidence for decrease in temperature-mortality relationship for days with temparature higher than 90
ggplot(DATA_1931_2004_no_missing, aes(x=b10_9, y=lndrate, color = factor(decade_two))) + geom_point() + geom_smooth(method = "lm")
# Evidence for slight increase in temperature-mortality relationship for days with temparature between 80 and 90
ggplot(DATA_1931_2004_no_missing, aes(x=b10_b_4, y=lndrate, color = factor(decade_two))) + geom_point() + geom_smooth(method = "lm")
# Evidence for decrease in temperature-mortality relationship for days with temparature below 40

# Same regression with only extreme values - seven decade levels #
M5 <- lm(data = DATA_1931_2004_no_missing, lndrate ~ (b10_9 + b10_10 + b10_b_4) * factor(decade) +
                                                     (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month +
                                                     lri * month + statemo + yearmo + year2 + devp25 + devp75)
summary(M5)

ggplot(DATA_1931_2004_no_missing, aes(x=b10_10, y=lndrate, color = factor(decade))) + geom_point() + geom_smooth(method = "lm")
# Again, evidence for overall decreasing trend in temperature-mortality relationship for days with temperature higher than 90
ggplot(DATA_1931_2004_no_missing, aes(x=b10_9, y=lndrate, color = factor(decade))) + geom_point() + geom_smooth(method = "lm")
# Evidence for slight increase in temperature-mortality relationship for days with temperature between 80 and 90
ggplot(DATA_1931_2004_no_missing, aes(x=b10_b_4, y=lndrate, color = factor(decade))) + geom_point() + geom_smooth(method = "lm")
# Evidence not so clear for days with temperature below 40, as also seen with the insignificant interaction



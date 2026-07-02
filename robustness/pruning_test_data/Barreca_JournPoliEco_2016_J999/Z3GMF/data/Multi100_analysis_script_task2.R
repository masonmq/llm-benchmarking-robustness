# 1. library required -------

library(foreign) # for reading stata data
library(dplyr)
library(ggplot2)
library(tidyr)

# 2. setting working directory ------

setwd('D:/OneDrive/multi100/R_analysis')

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

# 5. Add "decade" variable to test for the hypothesis ------
# 5.1 Add "decade_two" variable with two levels (before/after the year 1959) -------
DATA_1900_2004 <-DATA_1900_2004 %>% mutate(decade_two = case_when(year <= 1959 ~ 1,
                                                                  year >  1959 ~ 2)) 
# 6 Data cleaning -----
# remove the missing data - according to the mortality rate #
DATA_1900_2004_no_missing <- DATA_1900_2004[!is.na(DATA_1900_2004$lndrate),]
# Get the data from year 1931 on since the paper only reported data from the year 1931 on 
DATA_1931_2004_no_missing <- subset (DATA_1900_2004_no_missing, DATA_1900_2004_no_missing$year >= 1931)
# This dataset (DATA_1931_2004_no_missing) is to be used for the modelling and plotting 


# 7.Model & Plots 
# Only b10_10 as temperature extremes; control for share of state population (four categories), interacting with month;
# state-month and year-month fixed effects; quadratic term of the year.
M1 <- lm(data = DATA_1931_2004_no_missing, lndrate ~ b10_10 * factor(decade_two) +
           (sh_0000 + sh_0144 + sh_4564 + sh_6599) * month + yearmo + year2)
summary(M1)

# plot to see the interaction effect 
ggplot(DATA_1931_2004_no_missing, aes(x=b10_10, y=lndrate, color = factor(decade_two))) + geom_point() + geom_smooth(method = "lm") 
# As seen from the plot, for days with average temperature higher than 90, the mortality rate decreases for the later decades. 
# This is also consistent with the significant interaction effect


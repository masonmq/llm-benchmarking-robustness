#ignore warnings
options(warn=-1)

#Packages download
install.packages('haven')
install.packages('dplyr')
install.packages('tseries')

#Loading packages
library(haven)
library(tseries)
library(dplyr)
library(car)

#Data Loading
powell_original <- read_dta("powell_original.dta")
df <- powell_original
df<-as.data.frame(df)

#Filtering SMD to 1 ('SMD'=smd)
df <- df %>% filter(smd == 1)

#Filtering columns
df <- df[c('pty1d','effptyv1','ideosdw','ptyideo')]
View(df)

#Delete Missing values
df<-na.omit(df)

#Split DataFrame into X and y
X<-df[,c('effptyv1','ideosdw','ptyideo')]
y<-df[,c('pty1d')]

#ADF test over all variables
pty1d <- adf.test(as.vector(df[,1]))
pty1d
effptyv1 <- adf.test(as.vector(df[,2]))
effptyv1
ideosdw <- adf.test(as.vector(df[,3]))
ideosdw
ptyideo <- adf.test(as.vector(df[,4]))
ptyideo


#VIF test
best_model <- lm(pty1d~effptyv1+ideosdw+ptyideo, data=df) #Regression model of all variables (y~X)
vif(best_model)


summary(best_model) # Summary of Linear model (t-Test)


#extract F-statistic
F_statistic <- summary(best_model)$fstat
print(F_statistic)

#Sample size
n <- nobs(best_model)
print(n)



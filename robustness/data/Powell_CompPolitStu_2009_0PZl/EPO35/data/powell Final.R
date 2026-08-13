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
df <- df[c('pty1d','effptyv1','ptysize','pldist1','ideosdw','secdist1','ptyideo')]
View(df)

#Delete Missing values
df<-na.omit(df)

#Split DataFrame into X and y
X<-df[,c('effptyv1','ptysize','pldist1','ideosdw','secdist1','ptyideo')]
y<-df[,c('pty1d')]

#ADF test over all variables
effptyv1 <- adf.test(as.vector(df[,2]))
effptyv1
ptysize <- adf.test(as.vector(df[,3]))
ptysize
pldist1 <- adf.test(as.vector(df[,4]))
pldist1
ideosdw <- adf.test(as.vector(df[,5]))
ideosdw
secdist1 <- adf.test(as.vector(df[,6]))
secdist1
ptyideo <- adf.test(as.vector(df[,7]))
ptyideo
pty1d <- adf.test(as.vector(df[,1]))
pty1d

#VIF test
linear <- lm(pty1d~effptyv1+ptysize+pldist1+ideosdw+secdist1+ptyideo, data=df) #Regression model of all variables (y~X)
vif(linear)

#Best Model
best_model <- lm(pty1d~effptyv1+ideosdw+secdist1+ptyideo, data=df) #Regression model of the selected variables based on VIF results below
vif(best_model) #VIF of the selected model (Multicolinearity test)
summary(best_model) # Summary of Linear model (t-Test)
anova(best_model) #Variance analysis (F-test)
sample_size <- length(df[,1]) #sample_size = n
degree_freedom <- anova(best_model)$Df[5] #df = n-p-1>0
print(sample_size)
print(degree_freedom)

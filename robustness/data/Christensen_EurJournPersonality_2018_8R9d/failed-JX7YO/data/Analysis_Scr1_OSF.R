library(readr)
require(dplyr)
require(tidyr)
require(tidyverse)
require(ggplot2)
require(infotheo)
require(igraph)
require(NetworkToolbox)
require(Hmisc)

#План:
# 1. Посчитать вероятность нахождения двух итемов в одном списке
# 2. Посчитать количество информации, которое появляется от нахождения двух итемов в списке
# 3. Построить сети на основе имеющихся итемов, исходя из значений информации
# 4. Пороги?
# 5. Посчитать графные метрики

dem = read_csv("Data/Cleaned FINAL/FINAL demo open fluency.csv") #Read Clean data


tt = dem %>% select(starts_with('vf_an_')) #Selecd semantic data
list_of_words = na.omit(unique(unlist(tt))) #Only unique words

###
# Create an enthropy matrix  
#For each pair of words, we find the frequency of paired occurrence (both words must be specified) in the respondents answers. 
#For the resulting frequencies, we find the entropy value. 

ent_matrix = data.frame(matrix(nrow = length(list_of_words), ncol = length(list_of_words)))
colnames(ent_matrix) = list_of_words
rownames(ent_matrix) = list_of_words

for (x in 1:length(list_of_words)) { #there should be a better way to do it
  for (y in 1:x) {
    count = c()
    
    for (n in 1:nrow(tt)) { 
      #if both word are presented in the same answer (row in a semantic data) we add 1 to the total count. Else we add 0
      is_word = ifelse(as.numeric(list_of_words[x] %in% tt[n, ]) + as.numeric(list_of_words[y] %in% tt[n, ]) == 2, 1, 0) 
      
      count = c(count, is_word)
    }
    probabilities = prop.table(table(count)) #probability table
    ent_matrix[x, y] = -sum(probabilities*log2(probabilities)) #total entropy of the probability distribution. Lower entropy means more deterministic process
  }
  
}

########
#Slight modifications
ent_matrix_mod = ent_matrix
ent_matrix_mod[is.na(ent_matrix_mod)] = 99
ent_matrix_mod[ent_matrix_mod == 0] = 0.99 #Entropy 1 means random process (P = 0.5), so all values without a pair get a value 0.99


##
#Analysis by group
#openness - o_ffi #It is not clear from the data and description how exactly authors creted high and low groups


#%%
#Function for finding mode in the data
Modes <- function(x) {
  ux <- unique(x)
  tab <- tabulate(match(x, ux))
  ux[tab == max(tab)]
}

#The main idea ini this section is to create a network for each indivial based on the total sample 

dem2 = dem #mst

dem2$cpl = 0 #The descrease in the CPL value reflects the more deterministic choice of words, increase - more random
dem2$betw_mean = 0 #Higher betwenness means more nodes have random connections 
dem2$betw_max = 0
dem2$part_mean = 0 #Participation coefficient directly test the level of integration in the network, higher participation coefficient means more interconnecdedness

for (n in 1:nrow(tt)) { #again - not the best way
  row = tt[n,]
  
  adj_matrix = ent_matrix_mod
  nn = unique(unlist(row))
  lacking_words = setdiff(list_of_words, nn ) #Each individual network consists only from the existing pairs of words
  
  adj_matrix[lacking_words, lacking_words] = 0.99
  
  graph = graph_from_adjacency_matrix(as.matrix(adj_matrix), diag = F, mode = 'lower', weighted = T)
  graph = mst(graph) #to exctract the main structure, I use th MST. 
  
  
  dem2[n, 'cpl'] = median(distances(graph, algorithm = 'Dijkstra'))
  betw = betweenness(adj_matrix, weighted = T)
  dem2[n, 'betw_mean'] = mean(betw)
  dem2[n, 'betw_max'] = max(betw)
  
  part = participation(adj_matrix, comm = 'louvain')
  dem2[n, 'part_mean'] = mean(part$overall[part$overall>Modes(part$overall)])
  
} 

#%%
#Group comparison and correlations
analysis_df = dem2 %>%  select(., c("d_age", "d_gender", "o_ffi", "oi_bfas",  
                             "o_bfas", "i_bfas", "cpl", "betw_mean", "betw_max",  "part_mean")) %>% 
  mutate(openness_average = rowMeans(select(., c("o_ffi", "oi_bfas", "o_bfas", "i_bfas")))) %>%  #I choose to use the average of what looks like openness scales from different questionnaries
  mutate(group = ifelse(openness_average > median(openness_average), 'high', 'low')) %>% 
  filter(cpl < 10)


aux_df = analysis_df %>% 
  pivot_longer(3:10, names_to = 'names', values_to = 'values')

ggplot(aux_df, aes(x = openness_average, y = values)) +
  geom_point() + facet_grid(names ~., scales = 'free') + theme_minimal()

ggplot(aux_df, aes(x = d_gender, y = values, fill = as.factor(d_gender))) +
  geom_violin() + geom_boxplot(width = 0.2) + facet_grid(names ~., scales = 'free') + theme_minimal()

ggplot(aux_df, aes(x = group, y = values, fill = as.factor(group))) +
  geom_violin() + geom_boxplot(width = 0.2) + facet_grid(names ~., scales = 'free') + theme_minimal()


cor_df = select(analysis_df, c("d_age", "cpl", "betw_mean", "betw_max", "part_mean", 'openness_average'))
corrs = rcorr(as.matrix(cor_df), type = 'spearman') #Basic correlation

#%%
res <- analysis_df %>% 
  select(., c("cpl", "betw_mean", "betw_max",  "part_mean")) %>%
  map_df(~ broom::tidy(t.test(. ~ analysis_df$group)), .id = 'var') #T-test


##############


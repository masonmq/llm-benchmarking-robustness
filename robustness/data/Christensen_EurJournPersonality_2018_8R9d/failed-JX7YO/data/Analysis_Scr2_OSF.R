library(readr)
require(dplyr)
require(tidyr)
require(tidyverse)
require(stats)
require(igraph)
require(NetworkToolbox)

ent_matrix_mod <- as.data.frame(read_csv("ent_matrix_mod.csv"))

rownames(ent_matrix_mod) = ent_matrix_mod[[1]]
ent_matrix_mod <- ent_matrix_mod[-1]


Modes <- function(x) {
  ux <- unique(x)
  tab <- tabulate(match(x, ux))
  ux[tab == max(tab)]
}


dem = read_csv("Data/Cleaned FINAL/FINAL demo open fluency.csv") #Read Clean data

tt = dem %>% select(starts_with('vf_an_')) #Selecd semantic data
list_of_words = na.omit(unique(unlist(tt))) #Only unique words

dem2 = dem #mst

dem2$cpl = 0 #The descrease in the CPL value reflects the more deterministic choice of words, increase - more random
dem2$betw_mean = 0 #Higher betwenness means more nodes have random connections 
dem2$betw_max = 0
dem2$part_mean = 0 #Participation coefficient directly test the level of integration in the network, higher participation coefficient means more interconnecdedness

#ent_matrix_mod =ent_matrix_mod[, 2:ncol(ent_matrix_mod)]




for (n in 1:nrow(tt)) { #again - not the best way
  row = tt[n,]
  
  adj_matrix = ent_matrix_mod
  
  if (n %in% c(386, 499)){ #nrow(adj_matrix)<2
    dem2[n, 'cpl'] = NA
    dem2[n, 'betw_mean'] = NA
    dem2[n, 'betw_max'] = NA
    dem2[n, 'part_mean'] = NA
  
  } else {
    nn = unique(unlist(row))
    
    
    nn <- nn[!sapply(nn, function(x) any(is.na(x)))]  
    nn <- nn[sapply(nn, function(x) !any(x == 99))]
    
    
    adj_matrix = adj_matrix[nn, nn]
    adj_matrix[adj_matrix == 99] = 0
    
    adj_matrix = adj_matrix + t(adj_matrix)
    
    #adj_matrix = 1/adj_matrix
    adj_matrix[adj_matrix > 49] = 0
    
    graph = graph_from_adjacency_matrix(as.matrix(adj_matrix), diag = F, mode = 'lower', weighted = T)
    
    
    weights <- eigen_centrality(graph)$vector
    sorted_weights <- sort(weights)
    nt = length(weights)
    cutoff <- sorted_weights[ceiling(nt*0.9)]
    nodes_to_remove <- which(weights > cutoff)
    graph <- delete_vertices(graph, nodes_to_remove)
    
    graph = mst(graph)
    
    
    dem2[n, 'cpl'] = median(distances(graph, algorithm = 'Dijkstra'))
    betw = betweenness(as_adjacency_matrix(graph), weighted = T)
    dem2[n, 'betw_mean'] = mean(betw)
    dem2[n, 'betw_max'] = max(betw)
    
    #part = participation(as_adjacency_matrix(graph), comm = 'louvain')
    part =  participation(adj_matrix, comm = 'louvain')
    part_mean = mean(part$overall[part$overall>Modes(part$overall)])
    
    if (is.na(part_mean)){
      part_mean = mean(part$overall)
      #break
    }
    
    print(c(n, part_mean))
    dem2[n, 'part_mean'] = mean(part_mean)
  }

} 



#dem_new <- read_csv("dem_new.csv")

analysis_df = dem2 %>%  select(., c("d_age", "d_gender", "o_ffi", "oi_bfas",  
                                    "o_bfas", "i_bfas", "cpl", "betw_mean", "betw_max",  "part_mean")) %>% 
  mutate(openness_average = rowMeans(select(., c("o_ffi", "oi_bfas", "o_bfas", "i_bfas")))) %>%  #I choose to use the average of what looks like openness scales from different questionnaries
  mutate(group = ifelse(openness_average > median(openness_average), 'high', 'low')) %>% 
  filter(cpl < 10) %>% 
  filter(d_gender != '-1')

aux_df = analysis_df %>% 
  pivot_longer(3:10, names_to = 'names', values_to = 'values')

ggplot(aux_df, aes(x = d_gender, y = values, fill = as.factor(d_gender))) +
  geom_violin() + geom_boxplot(width = 0.2) + facet_grid(names ~., scales = 'free') + theme_minimal()


t.test(analysis_df$part_mean ~ analysis_df$d_gender)

       
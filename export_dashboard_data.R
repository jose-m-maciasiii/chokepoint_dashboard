library(tidyverse)
library(sf)

args <- commandArgs(trailingOnly = FALSE)
file_arg <- "--file="
script_path <- sub(file_arg, "", args[grepl(file_arg, args)])

script_dir <- dirname(normalizePath(script_path))
project_dir <- normalizePath(file.path(script_dir, ".."))
data_dir <- file.path(script_dir, "data")

source(file.path(project_dir, "clean_standardize.R"))

dir.create(data_dir, showWarnings = FALSE, recursive = TRUE)

st_write(
  chpoints_plot_sf,
  file.path(data_dir, "chokepoints.geojson"),
  delete_dsn = TRUE,
  quiet = TRUE
)

st_write(
  world_countries_sf |>
    st_transform(4326),
  file.path(data_dir, "countries_of_interest.geojson"),
  delete_dsn = TRUE,
  quiet = TRUE
)

st_write(
  chpoint_buffers_500 |>
    st_transform(4326),
  file.path(data_dir, "buffers_500km.geojson"),
  delete_dsn = TRUE,
  quiet = TRUE
)

st_write(
  chpoint_buffers_1000 |>
    st_transform(4326),
  file.path(data_dir, "buffers_1000km.geojson"),
  delete_dsn = TRUE,
  quiet = TRUE
)

write_csv(
  chokepoint_country_summary,
  file.path(data_dir, "chokepoint_country_summary.csv")
)

write_csv(
  chokepoint_country_proximity,
  file.path(data_dir, "chokepoint_country_proximity.csv")
)

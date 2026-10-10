/*
 * This is a trace-level thermal simulator. It reads power values
 * from an input trace file and outputs the corresponding instantaneous
 * temperature values to an output trace file. It also outputs the steady
 * state temperature values to stdout.
 */
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <string.h>
#include <ctype.h>
#include <math.h>

#include "flp.h"
#include "package.h"
#include "temperature.h"
#include "temperature_block.h"
#include "temperature_grid.h"
#include "util.h"
#include "hotspot.h"
#include "microchannel.h"
#include "materials.h"

// My stuff
#define PRINT_GRID_TRANSIENT 1

/* HotSpot thermal model is offered in two flavours - the block
 * version and the grid version. The block model models temperature
 * per functional block of the floorplan while the grid model
 * chops the chip up into a matrix of grid cells and models the
 * temperature of each cell. It is also capable of modeling a
 * 3-d chip with multiple floorplans stacked on top of each
 * other. The choice of which model to choose is done through
 * a command line or configuration file parameter model_type.
 * "-model_type block" chooses the block model while "-model_type grid"
 * chooses the grid model.
 */

/* Guidelines for choosing the block or the grid model	*/

/**************************************************************************/
/* HotSpot contains two methods for solving temperatures:                 */
/* 	1) Block Model -- the same as HotSpot 2.0	              						  */
/*	2) Grid Model -- the die is divided into regular grid cells       	  */
/**************************************************************************/
/* How the grid model works: 											                        */
/* 	The grid model first reads in floorplan and maps block-based power	  */
/* to each grid cell, then solves the temperatures for all the grid cells,*/
/* finally, converts the resulting grid temperatures back to block-based  */
/* temperatures.                            														  */
/**************************************************************************/
/* The grid model is useful when 				                    						  */
/* 	1) More detailed temperature distribution inside a functional unit    */
/*     is desired.														                            */
/*  2) Too many functional units are included in the floorplan, resulting */
/*		 in extremely long computation time if using the Block Model        */
/*	3) If temperature information is desired for many tiny units,		      */
/* 		 such as individual register file entry.						                */
/**************************************************************************/
/*	Comparisons between Grid Model and Block Model:						            */
/*		In general, the grid model is more accurate, because it can deal    */
/*	with various floorplans and it provides temperature gradient across	  */
/*	each functional unit. The block model models essentially the center	  */
/*	temperature of each functional unit. But the block model is typically */
/*	faster because there are less nodes to solve.						              */
/*		Therefore, unless it is the case where the grid model is 		        */
/*	definitely	needed, we suggest using the block model for computation  */
/*  efficiency.															                              */
/**************************************************************************/

void usage(int argc, char **argv)
{
  fprintf(stdout, "Usage: %s -f <file> -p <file> [-o <file>] [-c <file>] [-d <file>] [options]\n", argv[0]);
  fprintf(stdout, "A thermal simulator that reads power trace from a file and outputs temperatures.\n");
  fprintf(stdout, "Options:(may be specified in any order, within \"[]\" means optional)\n");
  fprintf(stdout, "   -f <file>\tfloorplan input file (e.g. ev6.flp) - overridden by the\n");
  fprintf(stdout, "            \tlayer configuration file (e.g. layer.lcf) when the\n");
  fprintf(stdout, "            \tlatter is specified\n");
  fprintf(stdout, "   -p <file>\tpower trace input file (e.g. gcc.ptrace)\n");
  fprintf(stdout, "  [-o <file>]\ttransient temperature trace output file - if not provided, only\n");
  fprintf(stdout, "            \tsteady state temperatures are output to stdout\n");
  fprintf(stdout, "  [-c <file>]\tinput configuration parameters from file (e.g. hotspot.config)\n");
  fprintf(stdout, "  [-d <file>]\toutput configuration parameters to file\n");
  fprintf(stdout, "  [options]\tzero or more options of the form \"-<name> <value>\",\n");
  fprintf(stdout, "           \toverride the options from config file. e.g. \"-model_type block\" selects\n");
  fprintf(stdout, "           \tthe block model while \"-model_type grid\" selects the grid model\n");
  fprintf(stdout, "  [-detailed_3D <on/off]>\tHeterogeneous R-C assignments for specified layers. Requires a .lcf file to be specified\n"); //BU_3D: added detailed_3D option
}

/*
 * parse a table of name-value string pairs and add the configuration
 * parameters to 'config'
 */
void global_config_from_strs(global_config_t *config, str_pair *table, int size)
{
  int idx;
  if ((idx = get_str_index(table, size, "f")) >= 0) {
      if(sscanf(table[idx].value, "%s", config->flp_file) != 1)
        fatal("invalid format for configuration  parameter flp_file\n");
  } else {
      // If an LCF file is specified, an FLP file is not required
      strcpy(config->flp_file, NULLFILE);
  }
  if ((idx = get_str_index(table, size, "p")) >= 0) {
      if(sscanf(table[idx].value, "%s", config->p_infile) != 1)
        fatal("invalid format for configuration  parameter p_infile\n");
  } else {
      fatal("required parameter p_infile missing. check usage\n");
  }
  if ((idx = get_str_index(table, size, "o")) >= 0) {
      if(sscanf(table[idx].value, "%s", config->t_outfile) != 1)
        fatal("invalid format for configuration  parameter t_outfile\n");
  } else {
      strcpy(config->t_outfile, NULLFILE);
  }
  if ((idx = get_str_index(table, size, "c")) >= 0) {
      if(sscanf(table[idx].value, "%s", config->config) != 1)
        fatal("invalid format for configuration  parameter config\n");
  } else {
      strcpy(config->config, NULLFILE);
  }
  if ((idx = get_str_index(table, size, "d")) >= 0) {
      if(sscanf(table[idx].value, "%s", config->dump_config) != 1)
        fatal("invalid format for configuration  parameter dump_config\n");
  } else {
      strcpy(config->dump_config, NULLFILE);
  }
  if ((idx = get_str_index(table, size, "detailed_3D")) >= 0) {
      if(sscanf(table[idx].value, "%s", config->detailed_3D) != 1)
        fatal("invalid format for configuration  parameter lc\n");
  } else {
      strcpy(config->detailed_3D, "off");
  }
  if ((idx = get_str_index(table, size, "use_microchannels")) >= 0) {
      if(sscanf(table[idx].value, "%d", &config->use_microchannels) != 1)
        fatal("invalid format for configuration  parameter use_microchannels\n");
  } else {
      config->use_microchannels = 0;
  }
  if ((idx = get_str_index(table, size, "materials_file")) >= 0) {
      if(sscanf(table[idx].value, "%s", config->materials_file) != 1)
        fatal("invalid format for configuration parameter materials_file\n");
  } else {
      strcpy(config->materials_file, NULLFILE);
  }
}

/*
 * convert config into a table of name-value pairs. returns the no.
 * of parameters converted
 */
int global_config_to_strs(global_config_t *config, str_pair *table, int max_entries)
{
  if (max_entries < 8)
    fatal("not enough entries in table\n");

  sprintf(table[0].name, "f");
  sprintf(table[1].name, "p");
  sprintf(table[2].name, "o");
  sprintf(table[3].name, "c");
  sprintf(table[4].name, "d");
  sprintf(table[5].name, "detailed_3D");
  sprintf(table[6].name, "use_microchannels");
  sprintf(table[7].name, "materials_file");

  sprintf(table[0].value, "%s", config->flp_file);
  sprintf(table[1].value, "%s", config->p_infile);
  sprintf(table[2].value, "%s", config->t_outfile);
  sprintf(table[3].value, "%s", config->config);
  sprintf(table[4].value, "%s", config->dump_config);
  sprintf(table[5].value, "%s", config->detailed_3D);
  sprintf(table[6].value, "%d", config->use_microchannels);
  sprintf(table[7].value, "%s", config->materials_file);

  return 8;
}

/*
 * read a single line of trace file containing names
 * of functional blocks
 */
int read_names(FILE *fp, char **names)
{
  char line[LINE_SIZE], temp[LINE_SIZE], *src;
  int i;

  /* skip empty lines	*/
  do {
      /* read the entire line	*/
      fgets(line, LINE_SIZE, fp);
      if (feof(fp))
        fatal("not enough names in trace file\n");
      strcpy(temp, line);
      src = strtok(temp, " \r\t\n");
  } while (!src);

  /* new line not read yet	*/
  if(line[strlen(line)-1] != '\n')
    fatal("line too long\n");

  /* chop the names from the line read	*/
  for(i=0,src=line; *src && i < MAX_UNITS; i++) {
      if(!sscanf(src, "%s", names[i]))
        fatal("invalid format of names\n");
      src += strlen(names[i]);
      while (isspace((int)*src))
        src++;
  }
  if(*src && i == MAX_UNITS)
    fatal("no. of units exceeded limit\n");

  return i;
}

/* read a single line of power trace numbers	*/
int read_vals(FILE *fp, double *vals)
{
  char line[LINE_SIZE], temp[LINE_SIZE], *src;
  int i;

  /* skip empty lines	*/
  do {
      /* read the entire line	*/
      fgets(line, LINE_SIZE, fp);
      if (feof(fp))
        return 0;
      strcpy(temp, line);
      src = strtok(temp, " \r\t\n");
  } while (!src);

  /* new line not read yet	*/
  if(line[strlen(line)-1] != '\n')
    fatal("line too long\n");

  /* chop the power values from the line read	*/
  for(i=0,src=line; *src && i < MAX_UNITS; i++) {
      if(!sscanf(src, "%s", temp) || !sscanf(src, "%lf", &vals[i]))
        fatal("invalid format of values\n");
      src += strlen(temp);
      while (isspace((int)*src))
        src++;
  }
  if(*src && i == MAX_UNITS)
    fatal("no. of entries exceeded limit\n");

  return i;
}

/* write a single line of functional unit names	*/
void write_names(FILE *fp, char **names, int size)
{
  int i;
  for(i=0; i < size-1; i++)
    fprintf(fp, "%s\t", names[i]);
  fprintf(fp, "%s\n", names[i]);
}

/* write a single line of temperature trace(in degree C)	*/
void write_vals(FILE *fp, double *vals, int size)
{
  int i;
  for(i=0; i < size-1; i++)
    fprintf(fp, "%.9f\t", vals[i]);
  fprintf(fp, "%.9f\n", vals[i]);
}

char **alloc_names(int nr, int nc)
{
  int i;
  char **m;

  m = (char **) calloc (nr, sizeof(char *));
  assert(m != NULL);
  m[0] = (char *) calloc (nr * nc, sizeof(char));
  assert(m[0] != NULL);

  for (i = 1; i < nr; i++)
    m[i] =  m[0] + nc * i;

  return m;
}

void free_names(char **m)
{
  free(m[0]);
  free(m);
}

void print_dashed_line(int length) {
  int i;
  for(i = 0; i < length; i++)
    printf("-");
  printf("\n");
}

/* Precise mesh maps retain small temperature rises; peaks avoid dense grid traces. */
void dump_exact_grid(grid_model_t *model, double *values, const char *filename) {
  int layer, cell;
  FILE *fp = fopen(filename, "w");
  if (!fp) fatal("unable to open grid map output\n");
  for (layer = 0; layer < model->n_layers; layer++) {
    fprintf(fp, "Layer %d:\n", layer);
    for (cell = 0; cell < model->rows * model->cols; cell++)
      fprintf(fp, "%d\t%.9f\n", cell, values[layer * model->rows * model->cols + cell]);
  }
  fclose(fp);
}

double hottest_grid_cell(grid_model_t *model) {
  int layer, cell;
  double peak = -INFINITY;
  for (layer = 0; layer < model->n_layers; layer++)
    if (model->layers[layer].has_power)
      for (cell = 0; cell < model->rows * model->cols; cell++)
        peak = fmax(peak, model->last_trans->cuboid[0][0][layer*model->rows*model->cols+cell]);
  return peak;
}

#if VERBOSE>1
// TODO: Support summary for modeling secondary paths and for non-3D simulations
void print_simulation_summary(thermal_config_t thermal_config, RC_model_t *model) {
  // This is currently only supported for 3D simulations
  if(model->type != GRID_MODEL)
    return;

  grid_model_t *grid_model = model->grid;
  int i;
  int nl = grid_model->n_layers;
  int hsidx = nl - DEFAULT_PACK_LAYERS + LAYER_SINK;
  int spidx = nl - DEFAULT_PACK_LAYERS + LAYER_SP;
  int intidx = LAYER_INT; // if lcf is not specified
  int silidx = LAYER_SI; // if lcf is not specified

  printf("\n\nSimulation Summary:\n");
  print_dashed_line(25);
  printf("Ambient at %.2f K\n", thermal_config.ambient);
  print_dashed_line(25);

  for(i = grid_model->n_layers - 1; i >= 0; i--) {
    if(i == hsidx)
      printf("Heat Sink : %.2f mm\n", grid_model->layers[i].thickness * 1e3);
    else if(i == spidx)
      printf("Heat Spreader : %.2f mm\n", grid_model->layers[i].thickness * 1e3);
    else if(i == intidx && !grid_model->has_lcf)
      printf("TIM : %.2f um\n", grid_model->layers[i].thickness * 1e6);
    else if(i == silidx && !grid_model->has_lcf)
      printf(" Chip : %.2f um\n", grid_model->layers[i].thickness * 1e6);
    else if(grid_model->has_lcf)
      printf("Layer %d : %.2f um\n", grid_model->layers[i].no, grid_model->layers[i].thickness * 1e6);
    else
      fatal("Unexpected error in print_simulation_summary\n");

    printf("  conductivity = %lf W/(m-K)\n", grid_model->layers[i].k);
    printf("  vol. heat capacity = %lf J/(m^3-K)\n", grid_model->layers[i].sp);

    if(grid_model->layers[i].has_power)
      printf("  dissipates power\n");

    if(grid_model->layers[i].is_microchannel)
      printf("  microfluidic cooling layer\n");

    print_dashed_line(25);
  }
  printf("\n\n");
}
#endif

/*
 * main function - reads instantaneous power values (in W) from a trace
 * file (e.g. "gcc.ptrace") and outputs instantaneous temperature values (in K) to
 * a trace file("gcc.ttrace"). also outputs steady state temperature values
 * (including those of the internal nodes of the model) onto stdout. the
 * trace files are 2-d matrices with each column representing a functional
 * functional block and each row representing a time unit(sampling_intvl).
 * columns are tab-separated and each row is a separate line. the first
 * line contains the names of the functional blocks. the order in which
 * the columns are specified doesn't have to match that of the floorplan
 * file.
 */
int main(int argc, char **argv)
{
  int i, j, idx, base = 0, count = 0, n = 0;
  int num, size, lines = 0, do_transient = TRUE;
  int periodic = 0, mean_init = 0, prescan = 0, cycle = 0, stable_cycles = 0;
  int state_size = 0, state_i, cycle_lines = 0;
  double *cycle_state = NULL, *internal_state = NULL, cycle_delta = 0.0;
  long trace_start;
  char periodic_metadata[STR_SIZE] = "";
  char grid_peak_file[STR_SIZE] = "";
  char precise_steady_file[STR_SIZE] = "";
  double *grid_peaks = NULL;
  char statistics_file[STR_SIZE] = "", record_times_file[STR_SIZE] = "", curve_file[STR_SIZE] = "", snapshot_file[STR_SIZE] = "";
  double record_interval = 0.0, global_peak = -INFINITY, global_peak_time = 0.0, current_peak = 0.0;
  double *sample_sums = NULL, *sample_peaks = NULL, *sample_peak_times = NULL, *peak_snapshot = NULL;
  FILE *record_times = NULL, *curve = NULL;
  int record_stride = 1, last_record_step = 0;
  char **names;
  double *vals;
  /* trace file pointers	*/
  FILE *pin, *tout = NULL;
  /* floorplan	*/
  flp_t *flp;
  /* hotspot temperature model	*/
  RC_model_t *model;
  /* instantaneous temperature and power values	*/
  double *temp = NULL, *power;
  double total_power = 0.0;

  /* steady state temperature and power values	*/
  double *overall_power, *steady_temp;
  /* thermal model configuration parameters	*/
  thermal_config_t thermal_config;
  /* default microchannel parameters */
  microchannel_config_t *microchannel_config = malloc(sizeof(microchannel_config_t));
  /* global configuration parameters	*/
  global_config_t global_config;
  /* table to hold options and configuration */
  str_pair table[MAX_ENTRIES];
  /* material properties */
  materials_list_t materials_list;

  /* variables for natural convection iterations */
  int natural = 0;
  double avg_sink_temp = 0;
  int natural_convergence = 0;
  double r_convec_old;

  /*BU_3D: variable for heterogenous R-C model */
  int do_detailed_3D = FALSE; //BU_3D: do_detailed_3D, false by default
  int use_microchannels = FALSE;
  if (!(argc >= 5 && argc % 2)) {
      usage(argc, argv);
      return 1;
  }

  printf("Parsing input files...\n");
  size = parse_cmdline(table, MAX_ENTRIES, argc, argv);
  global_config_from_strs(&global_config, table, size);

  /* no transient simulation, only steady state	*/
  if(!strcmp(global_config.t_outfile, NULLFILE))
    do_transient = FALSE;

  /* read configuration file	*/
  if (strcmp(global_config.config, NULLFILE))
    size += read_str_pairs(&table[size], MAX_ENTRIES, global_config.config);

  /* earlier entries override later ones. so, command line options
   * have priority over config file
   */
  size = str_pairs_remove_duplicates(table, size);
  if ((idx = get_str_index(table, size, "periodic")) >= 0) {
    if (strcmp(table[idx].value, "0") && strcmp(table[idx].value, "1"))
      fatal("periodic must be 0 or 1\n");
    periodic = atoi(table[idx].value);
  }
  if ((idx = get_str_index(table, size, "mean_steady_init")) >= 0) {
    if (strcmp(table[idx].value, "0") && strcmp(table[idx].value, "1"))
      fatal("mean_steady_init must be 0 or 1\n");
    mean_init = atoi(table[idx].value);
  }
  if ((idx = get_str_index(table, size, "periodic_metadata")) >= 0)
    strcpy(periodic_metadata, table[idx].value);
  if ((idx = get_str_index(table, size, "grid_peak_file")) >= 0)
    strcpy(grid_peak_file, table[idx].value);
  if ((idx = get_str_index(table, size, "precise_steady_file")) >= 0)
    strcpy(precise_steady_file, table[idx].value);
  if ((idx = get_str_index(table, size, "transient_statistics")) >= 0) strcpy(statistics_file, table[idx].value);
  if ((idx = get_str_index(table, size, "record_times")) >= 0) strcpy(record_times_file, table[idx].value);
  if ((idx = get_str_index(table, size, "temperature_curve")) >= 0) strcpy(curve_file, table[idx].value);
  if ((idx = get_str_index(table, size, "grid_peak_snapshot")) >= 0) strcpy(snapshot_file, table[idx].value);
  if ((idx = get_str_index(table, size, "record_intvl")) >= 0 &&
      (sscanf(table[idx].value, "%lf", &record_interval) != 1 || !isfinite(record_interval) || record_interval <= 0))
    fatal("record_intvl must be positive and finite\n");
  if ((periodic || mean_init) && !do_transient)
    fatal("periodic/mean_steady_init requires transient output\n");
  /* Tiny periods can hide ambient warmup under the cycle-delta tolerance. */
  if (periodic && !mean_init)
    fatal("periodic requires mean_steady_init=1; ambient cycle deltas cannot establish periodic steady state\n");
  prescan = mean_init;

  /* BU_3D: check if heterogenous R-C modeling is on */
  if(!strcmp(global_config.detailed_3D, "on")){
      do_detailed_3D = TRUE;
  }
  else if(strcmp(global_config.detailed_3D, "off")){
      //fatal("detailed_3D parameter should be either \'on\' or \'off\'\n");
      do_detailed_3D = FALSE;
  }//end->BU_3D

  // fill in material properties
  default_materials(&materials_list);
  if(strncmp(global_config.materials_file, NULLFILE, STR_SIZE)) {
    materials_add_from_file(&materials_list, global_config.materials_file);
  }

  /* get defaults */
  thermal_config = default_thermal_config();
  /* modify according to command line / config file	*/
  thermal_config_add_from_strs(&thermal_config, &materials_list, table, size);
  if (record_interval > 0) record_stride = (int)ceil(record_interval / thermal_config.sampling_intvl - 1e-12);
  if (record_stride < 1) record_stride = 1;

  use_microchannels = global_config.use_microchannels;
  if(use_microchannels) {
    /* default microchannel config */
    *microchannel_config = default_microchannel_config();

    /* modify according to command line config file */
    microchannel_config_add_from_strs(microchannel_config, &materials_list, table, size);
  }
  else {
    microchannel_config = NULL;
  }

  /* if package model is used, run package model */
  if (((idx = get_str_index(table, size, "package_model_used")) >= 0) && !(table[idx].value==0)) {
      if (thermal_config.package_model_used) {
          avg_sink_temp = thermal_config.ambient + SMALL_FOR_CONVEC;
          natural = package_model(&thermal_config, table, size, avg_sink_temp);
          if (thermal_config.r_convec<R_CONVEC_LOW || thermal_config.r_convec>R_CONVEC_HIGH)
            printf("Warning: Heatsink convection resistance is not realistic, double-check your package settings...\n");
      }
  }

  /* dump configuration if specified	*/
  if (strcmp(global_config.dump_config, NULLFILE)) {
      size = global_config_to_strs(&global_config, table, MAX_ENTRIES);
      size += thermal_config_to_strs(&thermal_config, &table[size], MAX_ENTRIES-size);
      if(use_microchannels)
        size += microchannel_config_to_strs(microchannel_config, &table[size], MAX_ENTRIES-size);
      /* prefix the name of the variable with a '-'	*/
      dump_str_pairs(table, size, global_config.dump_config, "-");
  }

  /* initialization: the flp_file global configuration
   * parameter is overridden by the layer configuration
   * file in the grid model when the latter is specified.
   */
  if(strcmp(thermal_config.grid_layer_file, NULLFILE)) {
    flp = NULL;

    if(strcmp(global_config.flp_file, NULLFILE)) {
      fprintf(stderr, "Warning: Layer Configuration File %s specified. Overriding floorplan file %s\n", thermal_config.grid_layer_file, global_config.flp_file);
    }
  }
  else if(strcmp(global_config.flp_file, NULLFILE)) {
    flp = read_flp(global_config.flp_file, FALSE, FALSE);
  }
  else {
    fatal("Either LCF or FLP file must be specified\n");
  }

  //BU_3D: added do_detailed_3D to alloc_RC_model. Detailed 3D modeling can only be used with grid-level modeling.
  /* allocate and initialize the RC model	*/
  model = alloc_RC_model(&thermal_config, flp, microchannel_config, &materials_list, do_detailed_3D, use_microchannels);

  // Do some error checking on combination of inputs
  if (model->type != GRID_MODEL && do_detailed_3D)
    fatal("-do_detailed_3D can only be used with -model_type grid\n"); //end->BU_3D
  if (model->type == GRID_MODEL && !model->grid->has_lcf && do_detailed_3D)
    fatal("-do_detailed_3D can only be used in 3D mode (if a grid_layer_file is specified)\n");
  if (use_microchannels && (model->type != GRID_MODEL || !do_detailed_3D))
    fatal("-use_microchannels requires -model_type grid and do_detailed_3D on options\n");
  if(model->type != GRID_MODEL && strcmp(model->config->grid_steady_file, NULLFILE)) {
    warning("Ignoring -grid_steady_file because grid model is not being used\n");
    strcpy(model->config->grid_steady_file, NULLFILE);
  }
  if(model->type != GRID_MODEL && strcmp(model->config->grid_transient_file, NULLFILE)) {
    warning("Ignoring -grid_transient_file because grid model is not being used\n");
    strcpy(model->config->grid_transient_file, NULLFILE);
  }

#if VERBOSE > 1
  print_simulation_summary(thermal_config, model);
#endif

  printf("Creating thermal circuit...\n");
  populate_R_model(model, flp);

  if (do_transient)
    populate_C_model(model, flp);

#if VERBOSE > 2
  debug_print_model(model);
#endif

  /* allocate the temp and power arrays	*/
  /* using hotspot_vector to internally allocate any extra nodes needed	*/
  if (do_transient)
    temp = hotspot_vector(model);
  power = hotspot_vector(model);
  steady_temp = hotspot_vector(model);
  overall_power = hotspot_vector(model);

  /* set up initial instantaneous temperatures */
  if (do_transient && strcmp(model->config->init_file, NULLFILE)) {
      if (!model->config->dtm_used)	/* initial T = steady T for no DTM	*/
        read_temp(model, temp, model->config->init_file, FALSE);
      else	/* initial T = clipped steady T with DTM	*/
        read_temp(model, temp, model->config->init_file, TRUE);
  } else if (do_transient)	/* no input file - use init_temp as the common temperature	*/
    set_temp(model, temp, model->config->init_temp);


  /* n is the number of functional blocks in the block model
   * while it is the sum total of the number of functional blocks
   * of all the floorplans in the power dissipating layers of the
   * grid model.
   */
  if (model->type == BLOCK_MODEL)
    n = model->block->flp->n_units;
  else if (model->type == GRID_MODEL) {
      for(i=0; i < model->grid->n_layers; i++)
        if (model->grid->layers[i].has_power)
          n += model->grid->layers[i].flp->n_units;
  } else
    fatal("unknown model type\n");

  if(!(pin = fopen(global_config.p_infile, "r")))
    fatal("unable to open power trace input file\n");
  if(do_transient && !(tout = fopen(global_config.t_outfile, "w")))
    fatal("unable to open temperature trace file for output\n");

  /* names of functional units	*/
  names = alloc_names(MAX_UNITS, STR_SIZE);
  if(read_names(pin, names) != n)
    fatal("no. of units in floorplan and trace file differ\n");
  trace_start = ftell(pin);
  if (do_transient) {
    if (model->type == BLOCK_MODEL) {
      state_size = model->block->n_nodes;
      internal_state = temp;
    } else {
      state_size = model->grid->n_layers * model->grid->rows * model->grid->cols
        + EXTRA + (model->config->model_secondary ? EXTRA_SEC : 0);
      internal_state = model->grid->last_trans->cuboid[0][0];
      /* Initialize the grid once; all replay calls retain the full internal state. */
      xlate_vector_b2g(model->grid, temp, model->grid->last_trans, V_TEMP);
      model->grid->last_temp = temp;
    }
    cycle_state = dvector(state_size);
    memcpy(cycle_state, internal_state, state_size * sizeof(double));
    if (model->type == GRID_MODEL && grid_peak_file[0]) {
      grid_peaks = dvector(state_size);
      memcpy(grid_peaks, internal_state, state_size * sizeof(double));
    }
    if (model->type == GRID_MODEL && snapshot_file[0]) peak_snapshot = dvector(state_size);
    sample_sums = dvector(n);
    sample_peaks = dvector(n);
    sample_peak_times = dvector(n);
  }

  /* header line of temperature trace	*/
  if (do_transient)
    write_names(tout, names, n);

  /* read the instantaneous power trace	*/
  vals = dvector(MAX_UNITS);
start_cycle:
  if (do_transient && !prescan) {
    global_peak = model->type == GRID_MODEL ? hottest_grid_cell(model->grid) : -INFINITY;
    global_peak_time = 0.0;
    last_record_step = 0;
    memset(sample_sums, 0, n*sizeof(double));
    memset(sample_peak_times, 0, n*sizeof(double));
    if (model->type == BLOCK_MODEL)
      for (i = 0; i < n; i++) {
        sample_peaks[i] = temp[get_blk_index(flp, names[i])];
        global_peak = fmax(global_peak, sample_peaks[i]);
      }
    else
      for (i=0, base=0, count=0; i < model->grid->n_layers; i++) {
        if (model->grid->layers[i].has_power) {
          for (j=0; j < model->grid->layers[i].flp->n_units; j++) {
            idx = get_blk_index(model->grid->layers[i].flp, names[count+j]);
            sample_peaks[count+j] = temp[base+idx];
          }
          count += model->grid->layers[i].flp->n_units;
        }
        base += model->grid->layers[i].flp->n_units;
      }
    if (peak_snapshot) memcpy(peak_snapshot, internal_state, state_size*sizeof(double));
    if (record_times_file[0]) {
      if (record_times) fclose(record_times);
      if (!(record_times = fopen(record_times_file, "w"))) fatal("unable to open recorded timestamps\n");
      fprintf(record_times, "solver_step,time_us\n");
    }
    if (curve_file[0]) {
      if (curve) fclose(curve);
      if (!(curve = fopen(curve_file, "w"))) fatal("unable to open temperature curve\n");
      fprintf(curve, "solver_step,time_us,global_hotspot_K\n");
      fprintf(curve, "0,0,%.12g\n", global_peak);
    }
  }
replay_trace:
  while ((num=read_vals(pin, vals)) != 0) {
      if(num != n)
        fatal("invalid trace file format\n");

      /* permute the power numbers according to the floorplan order	*/
      if (model->type == BLOCK_MODEL)
        for(i=0; i < n; i++)
          power[get_blk_index(flp, names[i])] = vals[i];
      else
        for(i=0, base=0, count=0; i < model->grid->n_layers; i++) {
            if(model->grid->layers[i].has_power) {
                for(j=0; j < model->grid->layers[i].flp->n_units; j++) {
                    idx = get_blk_index(model->grid->layers[i].flp, names[count+j]);
                    power[base+idx] = vals[count+j];
                }
                count += model->grid->layers[i].flp->n_units;
            }
            base += model->grid->layers[i].flp->n_units;
        }

      /* compute temperature	*/
      if (do_transient && !prescan) {
          /* if natural convection is considered, update transient convection resistance first */
          if (natural) {
              avg_sink_temp = calc_sink_temp(model, temp);
              natural = package_model(model->config, table, size, avg_sink_temp);
              populate_R_model(model, flp);
          }

          printf("Computing temperatures for t = %e...\n", lines*model->config->sampling_intvl);

          /* for the grid model, only the first call to compute_temp
           * passes a non-null 'temp' array. if 'temp' is  NULL,
           * compute_temp remembers it from the last non-null call.
           * this is used to maintain the internal grid temperatures
           * across multiple calls of compute_temp
           */
          if (model->type == BLOCK_MODEL)
            compute_temp(model, power, temp, model->config->sampling_intvl);
          else
            compute_temp(model, power, NULL, model->config->sampling_intvl);
          if (grid_peaks)
            for (state_i = 0; state_i < state_size; state_i++)
              grid_peaks[state_i] = fmax(grid_peaks[state_i], internal_state[state_i]);


        // Print grid transient temperatures to file if one has been specified
        if(model->type == GRID_MODEL && strcmp(model->config->grid_transient_file, NULLFILE)) {
          dump_transient_temp_grid(model->grid, cycle_lines, model->config->sampling_intvl, model->config->grid_transient_file);
        }
          /* permute back to the trace file order	*/
          if (model->type == BLOCK_MODEL)
            for(i=0; i < n; i++)
              vals[i] = temp[get_blk_index(flp, names[i])];
          else
            for(i=0, base=0, count=0; i < model->grid->n_layers; i++) {
                if(model->grid->layers[i].has_power) {
                    for(j=0; j < model->grid->layers[i].flp->n_units; j++) {
                        idx = get_blk_index(model->grid->layers[i].flp, names[count+j]);
                        vals[count+j] = temp[base+idx];
                    }
                    count += model->grid->layers[i].flp->n_units;
                }
                base += model->grid->layers[i].flp->n_units;
            }
          /* output instantaneous temperature trace	*/
          current_peak = model->type == GRID_MODEL ? hottest_grid_cell(model->grid) : -INFINITY;
          for (i = 0; i < n; i++) {
            sample_sums[i] += vals[i];
            if (vals[i] > sample_peaks[i]) {
              sample_peaks[i] = vals[i];
              sample_peak_times[i] = (cycle_lines+1)*model->config->sampling_intvl*1e6;
            }
            if (model->type == BLOCK_MODEL) current_peak = fmax(current_peak, vals[i]);
          }
          if (current_peak > global_peak) {
            global_peak = current_peak;
            global_peak_time = (cycle_lines+1)*model->config->sampling_intvl*1e6;
            if (peak_snapshot) memcpy(peak_snapshot, internal_state, state_size*sizeof(double));
          }
          if ((cycle_lines+1) % record_stride == 0) {
            write_vals(tout, vals, n);
            last_record_step = cycle_lines+1;
            if (record_times) fprintf(record_times, "%d,%.12g\n", last_record_step, last_record_step*model->config->sampling_intvl*1e6);
            if (curve) fprintf(curve, "%d,%.12g,%.12g\n", last_record_step, last_record_step*model->config->sampling_intvl*1e6, current_peak);
          }
      }

      /* for computing average	*/
      if (model->type == BLOCK_MODEL)
        for(i=0; i < n; i++)
          overall_power[i] += power[i];
      else
        for(i=0, base=0; i < model->grid->n_layers; i++) {
            if(model->grid->layers[i].has_power)
              for(j=0; j < model->grid->layers[i].flp->n_units; j++)
                overall_power[base+j] += power[base+j];
            base += model->grid->layers[i].flp->n_units;
        }

      lines++;
      cycle_lines++;
  }
  if(!lines)
    fatal("no power numbers in trace file\n");
  if (do_transient && !prescan && last_record_step != cycle_lines) {
    write_vals(tout, vals, n);
    if (record_times) fprintf(record_times, "%d,%.12g\n", cycle_lines, cycle_lines*model->config->sampling_intvl*1e6);
    if (curve) fprintf(curve, "%d,%.12g,%.12g\n", cycle_lines, cycle_lines*model->config->sampling_intvl*1e6, current_peak);
  }

  if (prescan) {
    int power_size = model->type == BLOCK_MODEL ? model->block->n_nodes : model->grid->total_n_blocks + EXTRA;
    for (state_i = 0; state_i < power_size; state_i++)
      overall_power[state_i] /= lines;
    steady_state_temp(model, overall_power, steady_temp);
    if (model->type == BLOCK_MODEL)
      memcpy(temp, steady_temp, state_size * sizeof(double));
    else {
      /* Copy exact cells and package nodes, never remap averaged block temperatures. */
      memcpy(internal_state, model->grid->last_steady->cuboid[0][0], state_size * sizeof(double));
      xlate_temp_g2b(model->grid, temp, model->grid->last_trans);
    }
    memset(overall_power, 0, power_size * sizeof(double));
    memcpy(cycle_state, internal_state, state_size * sizeof(double));
    if (grid_peaks) memcpy(grid_peaks, internal_state, state_size * sizeof(double));
    prescan = 0;
    lines = cycle_lines = 0;
    fseek(pin, trace_start, SEEK_SET);
    goto start_cycle;
  }
  if (periodic) {
    cycle++;
    cycle_delta = 0.0;
    for (state_i = 0; state_i < state_size; state_i++) {
      if (!isfinite(internal_state[state_i]))
        fatal("non-finite periodic thermal state\n");
      cycle_delta = fmax(cycle_delta, fabs(internal_state[state_i] - cycle_state[state_i]));
    }
    stable_cycles = cycle_delta <= 0.01 ? stable_cycles + 1 : 0;
    fprintf(stdout, "Periodic cycle %d: full-state delta %.9g K, stable %d/3\n", cycle, cycle_delta, stable_cycles);
    if (stable_cycles < 3) {
      if (cycle >= 1000) {
        if (periodic_metadata[0]) {
          FILE *meta = fopen(periodic_metadata, "w");
          if (!meta) fatal("unable to open periodic failure metadata\n");
          fprintf(meta, "{\"status\":\"failed\",\"cycles\":1000,\"max_full_state_delta_K\":%.12g,\"consecutive_cycles\":%d}\n", cycle_delta, stable_cycles);
          fclose(meta);
        }
        fatal("periodic thermal convergence failed after 1000 full cycles\n");
      }
      memcpy(cycle_state, internal_state, state_size * sizeof(double));
      if (grid_peaks) memcpy(grid_peaks, internal_state, state_size * sizeof(double));
      fseek(pin, trace_start, SEEK_SET);
      cycle_lines = 0;
      /* Keep only the latest complete waveform; never expand the input trace. */
      if (!(tout = freopen(global_config.t_outfile, "w", tout)))
        fatal("unable to rewind transient output\n");
      write_names(tout, names, n);
      if (model->type == GRID_MODEL && strcmp(model->config->grid_transient_file, NULLFILE))
        remove(model->config->grid_transient_file);
      goto start_cycle;
    }
    if (periodic_metadata[0]) {
      FILE *meta = fopen(periodic_metadata, "w");
      if (!meta) fatal("unable to open periodic metadata\n");
      fprintf(meta, "{\"status\":\"converged\",\"cycles\":%d,\"max_full_state_delta_K\":%.12g,\"consecutive_cycles\":%d,\"tolerance_K\":0.01,\"cycle_samples\":%d}\n", cycle, cycle_delta, stable_cycles, cycle_lines);
      fclose(meta);
    }
  }
  if (grid_peaks)
    dump_exact_grid(model->grid, grid_peaks, grid_peak_file);
  if (peak_snapshot) dump_exact_grid(model->grid, peak_snapshot, snapshot_file);
  if (statistics_file[0] && do_transient) {
    FILE *fp = fopen(statistics_file, "w");
    if (!fp) fatal("unable to open transient statistics\n");
    fprintf(fp, "{\"solver_samples\":%d,\"record_stride\":%d,\"record_interval_us\":%.12g,\"global_peak_temperature_K\":%.12g,\"global_peak_time_us\":%.12g,\"chiplets\":{", cycle_lines, record_stride, record_stride*model->config->sampling_intvl*1e6, global_peak, global_peak_time);
    for (i = 0; i < n; i++)
      fprintf(fp, "%s\"%s\":{\"mean_temperature_K\":%.12g,\"peak_temperature_K\":%.12g,\"peak_time_us\":%.12g}", i ? "," : "", names[i], sample_sums[i]/cycle_lines, sample_peaks[i], sample_peak_times[i]);
    fprintf(fp, "}}\n");
    fclose(fp);
  }

  /* for computing average	*/
  if (model->type == BLOCK_MODEL)
    for(i=0; i < n; i++) {
        overall_power[i] /= lines;
        total_power += overall_power[i];
    }
  else
    for(i=0, base=0; i < model->grid->n_layers; i++) {
        if(model->grid->layers[i].has_power)
          for(j=0; j < model->grid->layers[i].flp->n_units; j++) {
              overall_power[base+j] /= lines;
              total_power += overall_power[base+j];
          }
        base += model->grid->layers[i].flp->n_units;
    }
  /* natural convection r_convec iteration, for steady-state only */
  natural_convergence = 0;
  if (natural) { /* natural convection is used */
      while (!natural_convergence) {
          r_convec_old = model->config->r_convec;
          /* steady state temperature	*/
          steady_state_temp(model, overall_power, steady_temp);
          avg_sink_temp = calc_sink_temp(model, steady_temp) + SMALL_FOR_CONVEC;
          natural = package_model(model->config, table, size, avg_sink_temp);
          populate_R_model(model, flp);
          if (avg_sink_temp > MAX_SINK_TEMP)
            fatal("too high power for a natural convection package -- possible thermal runaway\n");
          if (fabs(model->config->r_convec-r_convec_old)<NATURAL_CONVEC_TOL)
            natural_convergence = 1;
      }
  }	else {/* natural convection is not used, no need for iterations */
      fprintf(stderr, "Computing steady-state temperatures...\n");
      steady_state_temp(model, overall_power, steady_temp);
    }

  /* dump steady state temperatures on to file if needed	*/
  if (strcmp(model->config->steady_file, NULLFILE))
    dump_temp(model, steady_temp, model->config->steady_file);
  if (precise_steady_file[0]) {
    FILE *fp = fopen(precise_steady_file, "w");
    if (!fp) fatal("unable to open precise steady output\n");
    if (model->type == BLOCK_MODEL)
      for (i = 0; i < flp->n_units; i++)
        fprintf(fp, "%s\t%.9f\n", flp->units[i].name, steady_temp[i]);
    else
      for (i = 0, base = 0; i < model->grid->n_layers; i++) {
        if (model->grid->layers[i].has_power)
          for (j = 0; j < model->grid->layers[i].flp->n_units; j++) {
            if (model->grid->has_lcf) fprintf(fp, "layer_%d_", i);
            fprintf(fp, "%s\t%.9f\n", model->grid->layers[i].flp->units[j].name, steady_temp[base+j]);
          }
        base += model->grid->layers[i].flp->n_units;
      }
    fclose(fp);
  }
  /* for the grid model, optionally dump the most recent
   * steady state temperatures of the grid cells
   */
  if (model->type == GRID_MODEL &&
      strcmp(model->config->grid_steady_file, NULLFILE))
    dump_exact_grid(model->grid, model->grid->last_steady->cuboid[0][0], model->config->grid_steady_file);


#if VERBOSE > 2
  if (model->type == BLOCK_MODEL) {
      if (do_transient) {
          fprintf(stdout, "printing temp...\n");
          dump_dvector(temp, model->block->n_nodes);
      }
      fprintf(stdout, "printing steady_temp...\n");
      dump_dvector(steady_temp, model->block->n_nodes);
  } else {
      if (do_transient) {
          fprintf(stdout, "printing temp...\n");
          dump_dvector(temp, model->grid->total_n_blocks + EXTRA);
      }
      fprintf(stdout, "printing steady_temp...\n");
      dump_dvector(steady_temp, model->grid->total_n_blocks + EXTRA);
  }
#endif

  /* cleanup	*/
  fclose(pin);
  if (do_transient)
    fclose(tout);
  if(model->type == BLOCK_MODEL || !model->grid->has_lcf)
    free_flp(flp, FALSE, FALSE);
  delete_RC_model(model);
  if (do_transient)
    free_dvector(temp);
  free_materials(&materials_list);
  free_microchannel(microchannel_config);
  free_dvector(power);
  free_dvector(steady_temp);
  free_dvector(overall_power);
  free_names(names);
  free_dvector(vals);
  if (cycle_state) free_dvector(cycle_state);
  if (grid_peaks) free_dvector(grid_peaks);
  if (sample_sums) free_dvector(sample_sums);
  if (sample_peaks) free_dvector(sample_peaks);
  if (sample_peak_times) free_dvector(sample_peak_times);
  if (peak_snapshot) free_dvector(peak_snapshot);
  if (record_times) fclose(record_times);
  if (curve) fclose(curve);

  printf("Simulation complete.\n");
  return 0;
}

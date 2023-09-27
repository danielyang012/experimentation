# -*- coding: utf-8 -*-
"""DY Commerce Stats_Engine.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1_FOtfI3Nqm-_jvXwmtlkK1lafdInzhMm

# Commerce/Growth Marketing Stats Engine

**Overview:**

Welcome to the Commerce/Growth Marketing Stats Engine, your tool for all things related to experimentation. This program currently supports:


1.   Query structuring based off user inputs
2.   Automated time series analysis and visualization
3.   Automated hypothesis testing and visualization

**Instructions:**

1.   Update user inputs in "Experiment Parameters" section.
2.   Go to Runtime on Colab tool bar and click "Run All".
3.   See directory folder for automatically generated experiment folder and outputs!


**Experiment Parameter Definitions:**

*   id_type = determines whether to query visitor or tracking_id
*   experiment_id = numeric experiment id from Optimizely
*   significance_level = alpha (type 1 error rate)
*   experiment_start_date = start date to include experiment exposed users
*   experiment_end_date = end date to include experiment exposed users
*   url_1_metric_name = determines name of  "been_to_url1"
*   url_2_metric_name = determines name of  "been_to_url2"
*   url_3_metric_name = determines name of  "been_to_url3"
*   url_4_metric_name = determines name of "been_to_url4". Fill as "None" if not used
*   which_url_determines_conversion = selects which url_metric to calculate conversion metrics for (numerator)
*   which_url_determines_denominator = selects which url_metric to utilize for the denominator in conversion rates
*   control_name = determines which variant name


*   Note: When you open the Excel spreadsheets generated by this program, Excel may raise an error due to certain sheet names being too long. Please ignore.
"""

# Commented out IPython magic to ensure Python compatibility.
# @title Load Packages
# %pip install sqldf
# %pip install statsmodels
# %pip install tabulate
# %pip install reportlab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus.flowables import PageBreak
from io import BytesIO
import sqldf
import pandas as pd
import seaborn as sns
from scipy import stats
import numpy as np
from google.cloud import bigquery
import random as r
import warnings
import matplotlib.pyplot as plt
import datetime, pytz
import os
import math
import time
from datetime import date, datetime, timedelta
from tqdm import tqdm
from scipy.stats import norm, binom
import seaborn as sns
from statsmodels.stats import proportion as prop
from matplotlib.ticker import FuncFormatter
import shutil
from tabulate import tabulate

warnings.filterwarnings('ignore')

from google.colab import auth
auth.authenticate_user()
print('Authenticated to Bigquery!')

# %load_ext google.colab.data_table

# @title Experiment Parameters { run: "auto", vertical-output: true, form-width: "50%", display-mode: "both" }
table_type = "tracking id" # @param ["visitor", "tracking id"]
user_cohorts = "all" # @param ["all", "new acquisition", "existing"]

experiment_id = 25003380671 # @param {type:"string"}
significance_level = .1 # @param {type:"number"}

experiment_start_date = '2023-08-09' # @param{type:"date"}
experiment_end_date = '2023-08-29'# @param{type:"date"}


url_1_metric_name = 'Visits' #@param {type:"string"}
url_2_metric_name = 'Clicks' #@param {type:"string"}
url_3_metric_name = 'Conversions' #@param {type:"string"}
url_4_metric_name = 'None' #@param {type:"string"}

bq_config_vars = {'project_id': 'nbcu-ds-sandbox-a-001',
                  'dataset_id': 'nbcu-ds-prod-001'}

which_url_determines_conversion = 3 # @param [3, 4]
which_url_determines_denominator = 1 # @param [1, 2,3]
include_plan_level_conversion_metrics = "No" # @param ["No", "Yes"]
control_name = 'Control' #@param {type:"string"}


url_metric_name_list = [url_1_metric_name,
            url_2_metric_name,
            url_3_metric_name,
            url_4_metric_name
]
denom_name = url_metric_name_list[which_url_determines_denominator - 1]

print("Please review your experiment parameters. Consult the ReadMe for definitions.")

# @title Query Dolphin
def get_experiment_data(table_type):
  if table_type == "visitor":
    id = 'visitor_id'
    table = '`nbcu-ds-prod-001.PeacockDataMartProductAnalyticsSilver.silver_commerce_web_test_visitor_level`'
  elif table_type == "tracking id":
    id = 'tracking_id'
    table = '`nbcu-ds-prod-001.PeacockDataMartProductAnalyticsSilver.silver_commerce_web_test_tracking_id_level`'
  else:
    print("Invalid user type parameter given. Reconfigure Experiment Parameters please.")
    pass

  if user_cohorts == "all":
    user_filter_snippet = "AND 1=1"
  else:
    user_filter_snippet = f"AND user_status = '{user_cohorts}'"
  query = f"""
    SELECT
    {id} AS id,
    min_date AS exposure_date,
    test_name,
    variant_name,
    status,
    visitor_entitlement,
    billing_cycle,
    user_status,
    been_to_url1,
    been_to_url2,
    been_to_url3,
    been_to_url4
    FROM
    {table}
    WHERE 1=1
    AND test_id = '{experiment_id}'
    {user_filter_snippet}
    AND min_date BETWEEN '{experiment_start_date}' AND '{experiment_end_date}'
  """
  print("Here's your query which will be the data for your analysis today: ")
  print(query)
  df  = pd.read_gbq(query,project_id = bq_config_vars['project_id'], use_bqstorage_api=True, progress_bar_type = 'tqdm')
  experiment_name = df['test_name'].unique().astype('str')[0]
  return(df, experiment_name,query)

results = get_experiment_data(table_type)
query_df, experiment_name, query = results[0], results[1], results[2]

#@title Set up Output Directory
# Create subfolders
al_name, htv_name, tsv_name = "Analysis Log", "Hypothesis Test Visuals", "Time Series Visuals"
parent_folder = "Report: " + experiment_name
diagnostics_folder = "Diagnostics: " + experiment_name
# Create the parent folder if it doesn't exist
if not os.path.exists(parent_folder):
    os.mkdir(parent_folder)
    print("Making report folder: ", parent_folder)
if not os.path.exists(diagnostics_folder):
    os.mkdir(diagnostics_folder)
    print("Making diagnostics folder: ", diagnostics_folder)
  # Change the working directory to the parent folder
os.chdir(diagnostics_folder)
# Create the subfolders if they don't exist
for subfolder in [al_name, htv_name, tsv_name]:
    if not os.path.exists(subfolder):
        os.mkdir(subfolder)
        print("Making subfolder: ", subfolder)

# Switch working directory back to the parent folder
os.chdir("..")  # Use ".." to navigate up one level
# Verify the current working directory
current_directory = os.getcwd()
print("Output directories have been set up! Your analysis and outputs will be stored here.")

# @title Parse out Conversions
def parse_conversions(df):
  """
  Description:

  This function takes in experiment data pulled from Bigquery and creates new columns based on url_metric_name(s) defined in "Experiment Parameters.
  This function takes "been_to_url" columns and turns them into funnel metrics using AND conditioning. i.e. For a user to be counted as a conversion of url2,
  they must also have been a conversion of url1.

  This function also removes "false conversions" from the dataset. ex: rows where conversion is True, but visitor_entitlement = 'Free' or null.

  Finally, this function adds in columns for subscription level conversions (Premium, Premium+, Monthly, Annual)
  """
  url4_condition = ((df['been_to_url1'] == 1) & (df['been_to_url2'] == 1) & (df['been_to_url3'] == 1) & (df['been_to_url4'] == 1))
  url3_condition = (url4_condition | ((df['been_to_url1'] == 1) & (df['been_to_url2'] == 1) & (df['been_to_url3'] == 1) & (df['been_to_url4'] == 0)))
  url2_condition = (url3_condition | ((df['been_to_url1'] == 1) & (df['been_to_url2'] == 1) & (df['been_to_url3'] == 0) & (df['been_to_url4'] == 0)))
  url1_condition = (url2_condition | ((df['been_to_url1'] == 1) & (df['been_to_url2'] == 0) & (df['been_to_url3'] == 0) & (df['been_to_url4'] == 0)))

  df[url_1_metric_name] = url1_condition
  df[url_2_metric_name] = url2_condition
  df[url_3_metric_name] = url3_condition
  df[url_4_metric_name] = url4_condition

  potential_conversion_cols = [df[url_1_metric_name], df[url_2_metric_name], df[url_3_metric_name], df[url_4_metric_name]]
  for i, v in enumerate(potential_conversion_cols):
    if i+1 == which_url_determines_conversion:
      conversion_col = v

  #remove rows where conversion is True, but entitlement = Free or Empty
  false_conversion_condition = ((df[url_metric_name_list[which_url_determines_conversion-1]] == True) & \
   ((df['visitor_entitlement'] == "Free") | (df['visitor_entitlement'].isna())))
  df.drop(df[false_conversion_condition].index, inplace=True)

  df['Monthly Conversions'] = (conversion_col) & (df['billing_cycle'] == 'MONTHLY')
  df['Annual Conversions'] = (conversion_col) & (df['billing_cycle'] == 'ANNUAL')
  df['Premium Conversions'] = (conversion_col) & (df['visitor_entitlement'] == 'Premium')
  df['Premium Plus Conversions'] = (conversion_col) & (df['visitor_entitlement'] == 'Premium+')

  df['Premium Monthly Conversions'] = df['Premium Conversions'] & (df['billing_cycle'] == 'MONTHLY')
  df['Premium Monthly Plus Conversions'] = df['Premium Plus Conversions'] & (df['billing_cycle'] == 'MONTHLY')
  df['Premium Annual Conversions'] = df['Premium Conversions'] & (df['billing_cycle'] == 'ANNUAL')
  df['Premium Plus Annual Conversions'] = df['Premium Plus Conversions'] & (df['billing_cycle'] == 'ANNUAL')
  return(df)

conversion_df = parse_conversions(query_df)
print("Writing experiment data to csv (500K row partitions)")
experiment_csv_file = diagnostics_folder + '/' + al_name + '/'+ 'Experiment Level Data' + '.csv'
conversion_df.to_csv(experiment_csv_file, index=False, chunksize=500000)

print(parse_conversions.__doc__)
print("Here's a preview of your parsed conversions data:")
display(conversion_df.head())
print("Here's summary statistics on numeric columns in your parsed conversions data:")
display(conversion_df.describe())
print("Here's summary of nulls and data types of columns in your parsed conversions data:")
display(conversion_df.info())

# @title Aggregate Counts
def aggregate_counts(df):
  """
  Description: This function takes in dataframe with parsed conversions and returns a dictionary of dataframes with sum/cumsum of raw, granular conversions

  6 dataframes are returned with the following names, indicating the type of aggregation performed on metrics:
      'Daily Variant-User Status Level'
      'Daily Variant Level'
      'Cumulative Daily Variant-User Status Level'
      'Cumulative Daily Variant Level'
      'Overall Variant-User Status Level'
      'Overall Variant Level'
  """
  #value list will be all booleans from above
  value_list = df.select_dtypes(include='bool').columns.tolist()
  try:
    value_list.remove('None')
    print("Aggregating the following: ", value_list)
  except:
    print("No booleans for value list found")
  try:
    date_col = df.select_dtypes(include = 'dbdate').columns.tolist()[0]
  except:
    print("No Date column Found Error!")

  try: #agg to grain level
    grain_level_df = df.groupby([date_col, "variant_name", "user_status"])[value_list].agg('sum')
    # get cumulative daily sum by grain
    cum_daily_grain_level_df = grain_level_df.sort_values(["variant_name", "user_status",date_col]).groupby(['variant_name', 'user_status']).cumsum()
  except:
    grain_level_df = pd.DataFrame()
    cum_daily_grain_level_df = pd.DataFrame()
    print("daily grain level aggregation failed")

  try: # agg to variant level
    daily_variant_level_df = df.groupby([date_col, 'variant_name'])[value_list].agg('sum')
    # get cumulative daily sum by variant
    cum_daily_variant_level_df = daily_variant_level_df.sort_values(["variant_name", date_col]).groupby('variant_name').cumsum()
  except:
    daily_variant_level_df = pd.DataFrame()
    cum_daily_variant_level_df = pd.DataFrame()
    print('daily variant level agg failed')

  try:  #agg to overalls
    overall_grain_level_df = df.groupby(['variant_name', 'user_status'])[value_list].agg('sum')
    # #aggregate to overall by variant
    overall_variant_level_df = df.groupby(['variant_name'])[value_list].agg('sum')
  except:
    overall_grain_level_df = pd.DataFrame()
    overall_variant_level_df = pd.DataFrame()
    print('overall level agg failed')

  #place dataframes into a dictionary to return
  analysis_data_dict = {
      'Daily Variant-User Status Level' : grain_level_df.reset_index(),
      'Daily Variant Level': daily_variant_level_df.reset_index(),
      'Cumulative Daily Variant-User Status Level': cum_daily_grain_level_df.reset_index(),
      'Cumulative Daily Variant Level': cum_daily_variant_level_df.reset_index(),
      'Overall Variant-User Status Level': overall_grain_level_df.reset_index(),
      'Overall Variant Level': overall_variant_level_df.reset_index()
  }
  return(analysis_data_dict)

#instantiate dictionary of aggregated data
print(aggregate_counts.__doc__)
agg_dfs_dict = aggregate_counts(conversion_df)
for i,v in agg_dfs_dict.items():
  display(f"Info on {i}")
  display(v.head())
  display(v.describe())
  display(v.info())

#@title Compute Conversion Rate
def compute_conversions(dict):
  """ Description: This function takes in a dictionary of dataframes produced by aggregate_counts function and
  returns an updated dictionary of dataframes with conversion metrics as new columns for each dataframe
  """
  dict_copy = dict.copy()
  for key, val in enumerate(dict_copy):
    #grab a data frame
    df = dict_copy[val]
    #get numeric numerator columns, exclude denominator column
    num_cols = df.select_dtypes(include = 'int64').columns.tolist()
    num_cols.remove(denom_name) # dont need conversion on denominator
    #compute conversion rate for each numerator/denominator
    for i in num_cols:
      if i.endswith("s") or i.endswith("es"):
        new_i = i[:-1]
      else:
        new_i = i
      new_col = new_i+" Rate"
      df[new_col] = df[i]/df[denom_name]
    #update dictionary
    updates = {val: df}
    dict_copy.update(updates)
  return(dict_copy)
#create conversion dict
print(compute_conversions.__doc__)
agg_conversions_dict = compute_conversions(agg_dfs_dict)

# @title Compute Relative Lifts
def compute_relative_lift(dict):
  """ This function takes in a dictionary of dataframes with computed conversions and adds in relative lifts against Control
  """
  dict_copy = dict.copy()
  for key, val in enumerate(dict_copy):
    df = dict_copy[val]
    control_df = df[df['variant_name'] == control_name]
    join_keys = df.select_dtypes(exclude=np.number).columns.tolist()
    join_keys.remove('variant_name')
    #get rate columns
    rate_cols =  [col for col in df.columns if np.logical_or('Rate' in col, col== denom_name)]
    control_suffix = '_control_val'
    #merge in corresponding control value based on join keys
    if len(join_keys) > 0:
      df_with_control = df.merge(control_df, on = join_keys, how = 'left', suffixes = ('', control_suffix))
    else:
      df['key'] =1
      control_df['key'] = 1
      df_with_control = df.merge(control_df, on = 'key', how = 'left', suffixes = ('', control_suffix))
      df_with_control.drop(columns = 'key', inplace = True)
    for i in rate_cols:
      new_col = i+" Relative Lift vs Control"
      # add new column which is current value/ control value
      df_with_control[new_col] = df_with_control[i]/df_with_control[i+control_suffix] - 1.0
    # parse joined control values after calculation
    columns_to_drop = [col for col in df_with_control.columns if control_suffix in col]
    # Drop the columns containing control suffix, no longer needed
    df_with_control.drop(columns=columns_to_drop, inplace=True)
    #update dictionary
    updates = {val: df_with_control}
    dict_copy.update(updates)
  return(dict_copy)
#add relative lifts to dictionary
print(compute_relative_lift.__doc__)
agg_lifts_dict = compute_relative_lift(agg_conversions_dict)

# @title Visualize Time Series Data

def percentage_formatter(x, pos):
        return f'{x * 100:.2f}%'

def visualize_experiment_data(data_dict):
  """ This function takes in a dictionary of dataframes with relative lifts, creates time series charts and saves them to output subfolder
  """
  for k, v in data_dict.items():
    if k.find('Daily Variant Level') >= 0:
      # Define metric groups based on user inputs
      metric_list_ov = url_metric_name_list.copy()
      try:
        metric_list_ov.remove("None") #remove Nones
      except ValueError:
        pass
      #get copy to edit
      metric_list_ov_fun = metric_list_ov.copy()
      #drop denominator column based on user inputs
      metric_list_ov_fun.remove(denom_name)

      """ NOTE: The following hard-coded lines"""
      metric_list_sub = ['Monthly Conversions', 'Annual Conversions', 'Premium Conversions', 'Premium Plus Conversions']
      #drop s and match metric naming conventions
      metric_list_ov_fun_new = [x[:-1] for x in metric_list_ov_fun if x.endswith('s')]
      metric_list_sub_new = [x[:-1] for x in metric_list_sub if x.endswith('s')]
      metric_list_ov_rate = [m + " Rate" for m in metric_list_ov_fun_new]
      metric_list_sub_rate = [m + " Rate" for m in metric_list_sub_new]
      metric_list_ov_vs_control = [m + " Relative Lift vs Control" for m in metric_list_ov_rate]
      metric_list_sub_vs_control = [m + " Relative Lift vs Control" for m in metric_list_sub_rate]

      metric_lol = [
            metric_list_ov, metric_list_sub,
            metric_list_ov_rate, metric_list_sub_rate,
            metric_list_ov_vs_control, metric_list_sub_vs_control
      ]
      metric_names_lol = ['Funnel Metrics','Subscription Metrics','Funnel Rates',
                          'Subscription Rates','Funnel Rates vs Control','Subscription Rates vs Control']


      """ End of hard-coding heavy section """
      for i, metric_group in enumerate(metric_lol):
        chart_name = f"{metric_names_lol[i]}: {k}.png"
        # Create a single set of subplots for each metric group
        fig, axes = plt.subplots(len(metric_group), 1, figsize=(8, len(metric_group)*4), sharey = False)
        plt.style.use('seaborn-v0_8-darkgrid')
        palette = sns.color_palette("colorblind")
        for a, metric in enumerate(metric_group):
          ax = axes[a]
          if metric.find('Rate') > 0: #if metric is a rate, apply percentages on y-axis
              ax.yaxis.set_major_formatter(FuncFormatter(percentage_formatter))
          for i, variant_name in enumerate(v['variant_name'].unique()):
            sub_v = v[v['variant_name'] == variant_name]
            color = palette[i % len(palette)]
            if variant_name == control_name and metric.find('Relative Lift') > 0 :
              pass
            else: # if relative_lift_vs_control visualization and control variant, don't plot the data
              if metric.find('Relative Lift') > 0:
                ax.axhline(y=0.0, color='red', linestyle='dotted', alpha = .5)
              ax.plot(sub_v['exposure_date'], sub_v[metric], marker='o', markersize=3, linestyle='-', label=variant_name, color=color)
              # set up y-axis start point
              ylim_bot = min(sub_v[sub_v['variant_name'] == variant_name][metric].min() * 1.5, 0)
              ylim_top = max(sub_v[sub_v['variant_name'] == variant_name][metric].max() * 1.5, 0)
              try:
                ax.set_ylim(ylim_bot , ylim_top, auto = True)
              except: #errors if denominator is 0
                ax.set_ylim(auto = True)
          ax.set_xlabel('Exposure Date', fontsize = 8)
          ax.set_xticklabels(ax.get_xticklabels(), rotation=45, fontsize = 9)
          ax.set_title(f'{k}: {metric}')
          ax.legend(loc='best',  frameon=True, fontsize=8)
        plt.tight_layout(pad = 2)
        plt.show()
        fig.savefig(diagnostics_folder + '/' + tsv_name +'/'+  chart_name)
        plt.clf()
    else:
        pass
print(visualize_experiment_data.__doc__)
visualize_experiment_data(agg_lifts_dict)

# @title Conduct Hypothesis Testing

def hypothesis_test(dict, alpha):
  """
  This function takes in dataframes from dictionary which are aggregated to an Overall level and conducts proportions hypothesis testing with specified alpha.
  The output returns a dictionary of tables with hypothesis testing results
  """
#new_dict to hold new dictionary of keys where values = dataframe with hypothesis test result s
  new_dict = {}
# iterate through dictionary
  for k,v in dict.items():
    # ADD KEYS TO dataframes
    join_keys_list = v.select_dtypes(include='object').columns.tolist()
    # Join the selected columns across rows and store the result in a new column
    v['key'] = v[join_keys_list].apply(lambda x: '-'.join(x), axis=1)
    #grab non variant_name cols to create a key to grab corresponding control
    find_keys_list = (join_keys_list.copy())
    find_keys_list.remove('variant_name')

    if len(find_keys_list) == 0: #set a key if none
      v['find_key'] = 'join'
    else: #create a concatenated column of non-numerics with variant_name col removed
      v['find_key'] = v[find_keys_list].apply(lambda x: '-'.join(x), axis=1)
    #determine if dataframe is eligible for hypothesis testing
    if k.find('Overall') == 0: #conduct hypothesis testing on "overall_" level data
      print("Starting hypothesis testing for: ",k)
      #split into control vs variants
      control_df = v[v['variant_name'] == control_name]
      variants_df = v[v['variant_name'] != control_name]
      # list of metrics to hypothesis test, int64 parses to non-normalized count metrics
      metric_list = v.select_dtypes(include='int64').columns.tolist()
      metric_list.remove(denom_name)
      # instantiate a dataframe to store hypothesis test results
      hyp_df = pd.DataFrame(columns = ['variant_group', 'metric', 'sample_n', 'control_n', 'sample_mean', 'control_mean', 'absolute_diff', 'relative_diff', \
                                       'standard_error', 'p_value', 'alpha','ci_lower_absolute', 'ci_upper_absolute','ci_lower_relative', 'ci_upper_relative'])
      for vk in variants_df.key.unique(): #iterate through each unique subsetted variant, depends on key uniqueness to work correctly!
        vdf = variants_df[variants_df['key'] == vk] #subset variants_df
        fk = vdf['find_key'].iloc[0] # get find key of variant
        cdf = control_df[control_df['find_key'] == fk] # grab correct control row
        for m in metric_list: #iterate through each metric
          # get control and variant counts of metric
          c_count = cdf[m].iloc[0]
          v_count = vdf[m].iloc[0]
          # get control and variant denominator
          c_nob = cdf[denom_name].iloc[0]
          v_nob = vdf[denom_name].iloc[0]
          prop_c = c_count/c_nob
          prop_v = v_count/v_nob
          var = prop_c * (1 - prop_c)/c_nob + prop_v * (1 - prop_v)/v_nob
          se = np.sqrt(var)
          z_crit = stats.norm().ppf(1 - alpha/2)
          # put into 2x2 array
          counts = np.array([v_count, c_count])
          nobs = np.array([v_nob, c_nob])
          stat, pval = prop.proportions_ztest(counts, nobs)
          sample_mean = prop_v
          control_mean = prop_c
          sample_diff_abs = prop_v - prop_c
          sample_diff_relative = prop_v/prop_c - 1
          ci_lower_abs = sample_diff_abs - z_crit * se
          ci_upper_abs = sample_diff_abs + z_crit * se
          ci_lower_rel = ci_lower_abs/control_mean
          ci_upper_rel = ci_upper_abs/control_mean
          hyp_test_row = [vk, m, v_nob, c_nob, sample_mean, control_mean, sample_diff_abs, sample_diff_relative, \
                          se, pval, alpha, ci_lower_abs, ci_upper_abs, ci_lower_rel, ci_upper_rel]
          hyp_df.loc[len(hyp_df)] = hyp_test_row

      #drop s, add _rate to metric names to communicate we conducted proportions test
      hyp_df['metric'] = [x[:-1] for x in hyp_df['metric'] if x.endswith('s')]
      hyp_df['metric'] = hyp_df['metric'] + ' Rate'
      updates = {k: hyp_df}
      print("Showing preview of results for: ", k)
      print(hyp_df.head())
      new_dict.update(updates)
    else: # dataframe not eligible for hyp testing
      pass
  return(new_dict)
print(hypothesis_test.__doc__)
hypothesis_dict = hypothesis_test(agg_lifts_dict, significance_level)

# @title Visualize Hypothesis Testing Data
def visualize_hyp_data(dict):
  """
  This function cycles through dictionary of hypothesis testing data and plots:
  - p-values for each metric with significance line
  - relative lift confidence intervals for each metric
  Note: each metric in hyp dict is expressed as a rate (normalized by denominator set in "Experiment Parameters)
  """
  for k,v in dict.items():
    print("Visualizing", k)
    group_list = v['variant_group'].unique().tolist()
    #set up subplots
    plt.style.use('seaborn-muted')
    palette = sns.color_palette("colorblind")
    for id, g in enumerate(group_list):
      plt.figure(figsize = (8,8))
      #subset data frame to just 1 group
      var_v = v[v['variant_group'] == g]
      metrics_list = ['Click Rate', 'Conversion Rate', 'Monthly Conversion Rate', 'Annual Conversion Rate',
                      'Premium Conversion Rate', 'Premium Plus Conversion Rate']
      sub_v = var_v[var_v['metric'].isin(metrics_list)]
      #plot, name and save p-values
      plt.bar(sub_v['metric'], sub_v['p_value'], color = palette[0])
      #plot data labels
      for i, val in enumerate(sub_v['p_value']):
        plt.text(i, val, round(val,3), ha = 'center', fontsize = 9)
      plt.xticks(fontsize=10, rotation=60)
      plt.yticks(fontsize=10)
      plt.ylabel("p-value", size=10)
      plt.title("P-values for " + g, size=12)
      plt.axhline(y=0.1, color='red', linestyle='dotted', label='Threshold (0.1)', alpha = .5)  # Add the dotted line
      plt.tight_layout(pad = 2)
      plt.savefig(f"{diagnostics_folder}/{htv_name}/{k}; {g}: P-values.png")
      plt.show()
      plt.clf()

      #plot name and save confidence interval
      plt.figure(figsize = (8,8))
      plt.style.use('seaborn-muted')
      for x, lower,relative, upper in zip(range(len(sub_v)), sub_v['ci_lower_relative'],sub_v['relative_diff'], sub_v['ci_upper_relative']):
        plt.plot((x,x,x),(lower,relative,upper), 'o-', color = palette[0] ,markersize = 2)
        plt.text(x+.05, lower, round(lower,3), ha = 'left', fontsize = 7.5)
        plt.text(x+.05, relative, round(relative,3), ha = 'left', fontsize = 7.5)
        plt.text(x+.05, upper, round(upper,3), ha = 'left', fontsize = 7.5)
        plt.xticks(range(len(sub_v)),list(sub_v['metric']), rotation = 60, fontsize=10)
        plt.gca().yaxis.set_major_formatter(FuncFormatter(percentage_formatter))
        plt.ylabel("Relative Lift", size=10)
        plt.title(str(percentage_formatter(1- significance_level,0))+ " Confidence Intervals for: " + g, size=12)
      plt.axhline(y=0.0, color='red', linestyle='dotted', alpha = .5)
      plt.tight_layout(pad = 2)
      plt.savefig(f"{diagnostics_folder}/{htv_name}/{k}: {g}: Relative Lift CI.png")
      plt.show()
      plt.clf()
  plt.close()
  pass
#run function
print(visualize_hyp_data.__doc__)
visualize_hyp_data(hypothesis_dict)

# @title Log Data into Excel Sheets
def log_dict_data(dict, name, folder, subfolder_name):
  """ This function takes in a dictionary of dataframes and imports each dataframe as a sheet in an .xlsx spreadsheet
  """
  #log query.txt
  query_file_path = f"{parent_folder}/Query.txt"  # You can change the file name and path as needed
  # Open the file in write mode and write the string to it
  with open(query_file_path, "w") as text_file:
      text_file.write(query)

  # Specify the Excel file name
  excel_file = folder+ '/' + subfolder_name + '/'+ name + '.xlsx'
  # Create a Pandas Excel writer using ExcelWriter
  with pd.ExcelWriter(excel_file) as writer:
      # Iterate through the dictionary and write each DataFrame to a sheet
      for sheet_name, df in dict.items():
          df.to_excel(writer, sheet_name=sheet_name, index=False)
print(log_dict_data.__doc__)
log_dict_data(agg_lifts_dict, 'Analysis Data', diagnostics_folder, al_name )
log_dict_data(hypothesis_dict, 'Hypothesis Testing Data', diagnostics_folder, al_name)
print("Data Logged!")

#@title Code to Refresh Directory
print("Optional: Specify a folder to delete")
delete_directory_path = 'sample_data' # @param {type:"string"}
if os.path.exists(delete_directory_path):
    shutil.rmtree(delete_directory_path)  # This deletes a folder and its contents recursively
    print(f"Deleted {delete_directory_path}")
else:
    print(f"The folder '{delete_directory_path}' does not exist.")

# Create a PDF file
pdf_file = f"{experiment_name} Report.pdf"
doc = SimpleDocTemplate(pdf_file, pagesize=letter)

# Define the content for the PDF
story = []

# Set the styles for the document
styles = getSampleStyleSheet()
normal_style = styles["Normal"]

# Add a title
title = Paragraph("Sample PDF Document", styles["Title"])
story.append(title)

# Add text description
description = """
This is a sample PDF document created using Python and ReportLab.
You can include multiple tables, charts, and text descriptions.
"""
story.append(Paragraph(description, normal_style))
story.append(Spacer(1, 0.2 * inch))

# Table 1
data1 = [["Name", "Age", "Occupation"],
         ["Alice", 28, "Engineer"],
         ["Bob", 24, "Designer"],
         ["Charlie", 32, "Data Scientist"]]

table1 = Table(data1, colWidths=[1.5 * inch, 0.8 * inch, 2 * inch])
story.append(table1)
story.append(Spacer(1, 0.2 * inch))

# Chart 1 with text description
plt.figure(figsize=(6, 4))
plt.plot([1, 2, 3, 4, 5], [10, 15, 13, 18, 20])
plt.title("Sample Chart 1")
plt.xlabel("X-axis")
plt.ylabel("Y-axis")
plt.grid(True)

# Save the chart to a BytesIO object
chart_buffer = BytesIO()
plt.savefig(chart_buffer, format="png")
plt.close()
chart_buffer.seek(0)

# Create an Image element from the chart
chart_image = Image(chart_buffer, width=4 * inch, height=3 * inch)
story.append(chart_image)

chart_description = """
Here is a sample line chart. This chart demonstrates the ability to include charts
in the PDF document with corresponding text descriptions.
"""
story.append(Paragraph(chart_description, normal_style))
story.append(Spacer(1, 0.2 * inch))

# Table 2
data2 = [["Product", "Quantity", "Price"],
         ["Product A", 50, 10.99],
         ["Product B", 30, 15.49],
         ["Product C", 20, 8.99]]

table2 = Table(data2, colWidths=[1.5 * inch, 0.8 * inch, 1 * inch])
story.append(table2)

# Build the PDF document
doc.build(story)

print(f"PDF file '{pdf_file}' created successfully.")
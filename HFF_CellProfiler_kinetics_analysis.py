import pandas as pd
import os


def label_conditions(df, plate_columns_map, plate_rows_map):
    """Assigning the conditions used in each well, according to the plate maps.
    Receives dataframe, plate_columns_map, plate_rows_map.
    Returns the dataframe."""

    # add strain and moi info
    df['strain'] = df['column'].apply(lambda value: plate_columns_map[value])
    df['moi'] = df['row'].apply(lambda value: plate_rows_map[value])
    # change the strain of all moi=0 wells to null (so that they are grouped together)
    df.ix[df.moi == 0, 'strain'] = 'null'
    # condition is defined as the strain + moi
    df['condition'] = df.strain.str.cat(df.moi.astype(str))
    return df

def calc_image_numcells(image_grouped):
    """Calculate total number of cell nuclei identified in each image.
    Function receives the data grouped by image(condition + timepoint + well + field)."""
    image_grouped['image_numnuc'] = image_grouped.shape[0]
    return image_grouped


def calc_image_PVcount(image_grouped):
    """Calculate  total number of vacuoles identifired in each image.
    Function receives the data grouped by image(condition + timepoint + well + field)."""
    image_grouped['image_PVcount'] = image_grouped['count'].sum()
    return image_grouped


def calc_image_stat(image_grouped, param):
    """
    calculating the image background or mean fluorescence.
    Background fluorescence is defined as as the 10th lower percentile of the uninfected nuclei
    in the image (cells that shouldn't have received any labeled protein because they are not infected).
    The 10th lower percentile was selected for defining the image background by testing different values for
    their ability to accurately represent the image background while maintaining the distribution of cell values.
    Mean fluorescence defined as mean of all cells in image.
    The calculated value will be added in a new column "image_background" or "image_mean".
    """
    if param == 'background':
        image_grouped['image_'+param] = image_grouped.loc[image_grouped['count'] == 0]['nuc_intens'].quantile(0.1)
    if param == 'mean_intens':
        image_grouped['image_'+param] = image_grouped['nuc_intens'].mean()
    if param == 'totalcount':
        image_grouped['image_' + param] = image_grouped['count'].sum()
    return image_grouped


def remove_outliers_image(condition_grouped, param):
    """
    Remove outlier images which have extreme outlier fluorescent intensity or number of intracellular vacuoles.
    For fluorescent intensity, remove images with mean nuclear fluorescence >5 std away from the
    mean of images from the same conditon.
    For intracelular parasite count, remove images with parasite vacuole count >3 std away from the mean of
    images from the same conditon.
    Function receives the data grouped by the comparison group (condition + timepoint).
    """
    # calculate image mean for each image (received already grouped by the comparison group, and grouped
    # here by well+field for calculating each image mean)
    condition_grouped = condition_grouped.groupby(['well', 'field']).apply(calc_image_stat, param=param)
    # calculate the mean and std of mean image fluorescece for all images in the comparison group
    condition_mean, condition_std = condition_grouped['image_'+str(param)].mean(), condition_grouped['image_'+str(param)].std()
    # remove images with mean values >5 (for fluorescence) or >3 (for vacuole number) std away
    # from the mean of that condition.
    num_std = 3
    if param == 'mean_intens':
        num_std = 5
    condition_grouped = condition_grouped.loc[
            (condition_mean - condition_grouped['image_' + str(param)]).abs() < (num_std * condition_std)]
    return condition_grouped


def make_t0(df):
    """
    Make "timepoint 0" data for each condition by copying the group of uninfected wells (moi=0 / strain=null)
    for each moi and strain.
    Receive and return dataframe.
    """
    # copy all cells of uninfected wells to a new dataframe t0_df
    t0_df = df.loc[df['strain'] == 'null'].copy(deep=True)
    # define them as timepoint 0
    t0_df['timepoint'] = 0
    # remove uninfected wells from the original dataframe
    df = df[df['strain'] != 'null']
    # extract list of mois and strains (=conditions) used in the experiment
    mois = sorted(df['moi'].unique())
    strains = df['strain'].unique()
    # copy the "uninfected wells" dataframe for each moi and strain, so it acts as the "timepoint 0" of each condition
    for strain in strains:
        for moi in mois:
            t0_df['moi'] = moi
            t0_df['strain'] = strain
            t0_df['condition'] = str(strain)+str(moi)
            # add it to the big dataframe
            df = df.append(t0_df)
    return df


def per_group_stats(df, group):
    """
    Get per condition stats tables for all cells, only infected cells, 
    and only protein-delivered (nucleus-positive) cells.
    """
    if group == 'well':
        # use describe to get mean and std statistics per well for: nuclear fluorescence, rate of nuclear delivery,
        # rate of infectio, number of vacuoles per cell, size of vacuole
        statdf_group = df.groupby(['moi', 'timepoint', 'strain', 'well'])['nuc_intens'].describe()
        statdf_group.rename(columns={'mean': 'mean_intens'}, inplace=True)
        statdf_group.rename(columns={'std': 'std_intens'}, inplace=True)
        statdf_group.drop(['min', '25%', '50%', '75%', 'max'], axis=1, inplace=True)
        statdf_group2 = df.groupby(['moi', 'timepoint', 'strain', 'well'])['pos_nuc'].describe()
        statdf_group2.rename(columns={'mean': 'mean_percentposnuc'}, inplace=True)
        statdf_group2.rename(columns={'std': 'std_percentposnuc'}, inplace=True)
        statdf_group3 = df.groupby(['moi', 'timepoint', 'strain', 'well'])['infection'].describe()
        statdf_group3.rename(columns={'mean': 'mean_percentinf'}, inplace=True)
        statdf_group3.rename(columns={'std': 'std_percentinf'}, inplace=True)
        statdf_group4 = df.groupby(['moi', 'timepoint', 'strain', 'well'])['count'].describe()
        statdf_group4.rename(columns={'mean': 'mean_count'}, inplace=True)
        statdf_group4.rename(columns={'std': 'std_count'}, inplace=True)
        statdf_group5 = df.groupby(['moi', 'timepoint', 'strain', 'well'])['PV_area'].describe()
        statdf_group5.rename(columns={'mean': 'mean_PVarea'}, inplace=True)
        statdf_group5.rename(columns={'std': 'std_PVarea'}, inplace=True)
        # combine statistics of different parameters into one composite dateframe
        statdf_group = statdf_group\
            .join(statdf_group2[['mean_percentposnuc', 'std_percentposnuc']])\
            .join(statdf_group3[['mean_percentinf', 'std_percentinf']])\
            .join(statdf_group4[['mean_count', 'std_count']])\
            .join(statdf_group5[['mean_PVarea', 'std_PVarea']])

    elif group == 'well_conditions':
        # use describe to get mean and std statistics per condition for: nuclear fluorescence, rate of nuclear delivery,
        # rate of infectio, number of vacuoles per cell, size of vacuole
        statdf_group = df.groupby(['moi', 'timepoint', 'strain'])['mean_intens'].describe()
        statdf_group.rename(columns={'mean': 'mean_intens'}, inplace=True)
        statdf_group.rename(columns={'std': 'std_intens'}, inplace=True)
        statdf_group.drop(['min', '25%', '50%', '75%', 'max'], axis=1, inplace=True)
        statdf_group2 = df.groupby(['moi', 'timepoint', 'strain'])['mean_percentposnuc'].describe()
        statdf_group2.rename(columns={'mean': 'mean_percentposnuc'}, inplace=True)
        statdf_group2.rename(columns={'std': 'std_percentposnuc'}, inplace=True)
        statdf_group3 = df.groupby(['moi', 'timepoint', 'strain'])['mean_percentinf'].describe()
        statdf_group3.rename(columns={'mean': 'mean_percentinf'}, inplace=True)
        statdf_group3.rename(columns={'std': 'std_percentinf'}, inplace=True)
        statdf_group4 = df.groupby(['moi', 'timepoint', 'strain'])['mean_count'].describe()
        statdf_group4.rename(columns={'mean': 'mean_count'}, inplace=True)
        statdf_group4.rename(columns={'std': 'std_count'}, inplace=True)
        statdf_group5 = df.groupby(['moi', 'timepoint', 'strain'])['mean_PVarea'].describe()
        statdf_group5.rename(columns={'mean': 'mean_PVarea'}, inplace=True)
        statdf_group5.rename(columns={'std': 'std_PVarea'}, inplace=True)
        # combine statistics of different parameters into one composite dateframe
        statdf_group = statdf_group \
            .join(statdf_group2[['mean_percentposnuc', 'std_percentposnuc']]) \
            .join(statdf_group3[['mean_percentinf', 'std_percentinf']]) \
            .join(statdf_group4[['mean_count', 'std_count']]) \
            .join(statdf_group5[['mean_PVarea', 'std_PVarea']])


    return statdf_group


# ### import data, label and arrange ###

folder_join = os.path.join
working_dir = r"hff_cellprofiler_outputs"  # working folder

# import csv files, merge sheets into one big dataframe, 
# re-arrange and change column names so they are easier to work with
# NOTE: because I ran the cellprofiler in batches, 
# the data I'm using must be merged from multiple cellprofiler output files
filenames = os.listdir(working_dir)
print(filenames)
# reading and merging
df = pd.concat([pd.read_csv(folder_join(working_dir, file), header=1, usecols=[0, 1, 5, 6, 7, 36, 54, 58]) for file in filenames], ignore_index=True)
# column 0 : ImageNumber (in the batch this image was processed in)
df = df.rename(index=str, columns={"ObjectNumber": "nuc_num",  # column 1 : serial number of the nucleus (= serial number of the cell)
                                   "Metadata_field": "field",  # column 5 : field of view of the image in respect to the well it was recorded from (5 fields per well)
                                   "Metadata_timepoint": "timepoint",  # column 6 : timepoint (hours after infection)
                                   "Metadata_well": "well",  # column 7 : well in the 384-well plate
                                   "Intensity_MeanIntensity_Green": "nuc_intens",  # column 36 : nuc_intens = mean fluorescence intensity in the nucleus, in the green channel (anti-HA stain)
                                   "Children_parasites_Count": "count",  # column 54 : count = number of parasites identified in this cell.
                                   "Mean_parasites_AreaShape_Area": "PV_area",  # column 58 : PV_area = mean area of all intracellular parasite vacuoles in the cell.
                                   # The CellProfiler analysis associates parasites with human cell nuclei by proximity, meaning that
                                   # its assumed that each identified parasite is inside the same cell as the closest nucleus to the parasite.
                                   })

# extract row and column from 'well'
df['row'], df['column'] = df['well'].str.split(' - ').str
# make sure timepoint and count are numeric
df['timepoint'] = pd.to_numeric(df['timepoint'], errors='coerce')
df['count'] = pd.to_numeric(df['count'], errors='coerce')
# 24 hours was mis-labled as 21 hours (because of my handwriting)
df['timepoint'] = df['timepoint'].replace(21, 24)
# A was removed as for some reason there weren't any parasites there (probably human error when manually
# infecting the plates)
df = df[df.row != 'A']
# convert pixel area to square micron area (Pixel size: 0.3700x0.3700 µm^2)
df['PV_area'] = df['PV_area'] * 0.1369


# label wells by strain and moi (according to location in the plate):

# plate arrangement
plate_columns_map = {'01': 'HA', '02': 'HA', '03': 'HA', '04': 'HA', '05': 'HA', '06': 'HA', '07': 'HA', '08': 'HA',
                         '09': 'MECP', '10': 'MECP', '11': 'MECP', '12': 'MECP', '13': 'MECP', '14': 'MECP', '15' :'MECP', '16': 'MECP',
                         '17': 'TFEB', '18': 'TFEB', '19': 'TFEB', '20': 'TFEB', '21': 'TFEB', '22': 'TFEB', '23': 'TFEB', '24': 'TFEB', }
plate_rows_map = {'A': 3, 'B': 3, 'C': 3, 'D': 3, 'E': 3,
                      'F': 1, 'G': 1, 'H': 1, 'I': 1, 'J': 1,
                      'K': 0.33, 'L': 0.33, 'M': 0.33, 'N': 0.33, 'O': 0.33,
                      'P': 0}

df = label_conditions(df, plate_columns_map, plate_rows_map)

# define infected cells = cells infected with at least one parasite
df.ix[df['count'] > 0, 'infection'] = 100
df['infection'].fillna(value=0, inplace=True)

# ### clean data from artefacts, normalize fluorescence, and define timepoint 0 ###

# record number of cells in the initial dataset (before cleaning from artefacts and outliers)
numcells = df.shape[0]
print(str(numcells) + ' total cells in dataset')

# remove images with too little cells (<100 nuclei)
df = df.groupby(['condition', 'timepoint', 'well', 'field']).apply(calc_image_numcells)
df = df.loc[df['image_numnuc'] >100]
# report how many cells were removed from the dataset in this step
toolittle_cells = numcells - df.shape[0]
print(str(toolittle_cells)+' cells ('+str(toolittle_cells/numcells*100) +
      '%) removed due to too little host cells')

# Remove images of wells which were inoculated with parasites (moi>0 / strain not null),
# but in which no parasites were identified (assumed to be a problem in the immunostaining step,
# causing parasite staining being too weak for the image analysis in some images).
# Also remove images in which too many (>400) parasites were identified (assumed to be a problem
# with object segmentation).
df = df.groupby(['condition', 'timepoint', 'well', 'field']).apply(calc_image_PVcount)
df = pd.concat([df.loc[df['moi'] == 0], df.loc[(df['moi'] != 0) & (df['image_PVcount'] > 0) & (df['image_PVcount'] <400)]])
# report how many cells were removed from the dataset in this step
noparasite_cells = numcells - toolittle_cells - df.shape[0]
print(str(noparasite_cells)+' cells ('+str(noparasite_cells/numcells*100) +
      '%) removed due to images of inoculated wells with no identified parasites - insufficient immunostaining,'
      ' or too many identified parasite - segmentation artefact')

#  calc per image background. Images are defined by groupby condition+timepoint+well+field.
df = df.groupby(['condition', 'timepoint', 'well', 'field']).apply(calc_image_stat, param='background')

# normalize nuclear background fluorescence value by subtracting the image background,
# and multiply by 10000 for ease of plotting (anyway fluorescence units are arbitrary)
df['nuc_intens'] = (df['nuc_intens'] - df['image_background']) * 10000

# remove images with outlier fluorescence (in comparison to all images in that condition)
df = df.groupby(['condition', 'timepoint']).apply(remove_outliers_image, param='mean_intens')
df.reset_index(drop=True, inplace=True)
# report how many cells were removed from the dataset in this step
outliercells = numcells - toolittle_cells - noparasite_cells - df.shape[0]
print(str(outliercells)+' cells ('+str(outliercells/numcells*100) +
      '%) removed due to wells with outlier mean fluorescence - fluorescence artefact')

# remove images with outlier number of intracellular vacuoles (due to inaccurate segmentation of the parasite vacuoles)
df = df.groupby(['condition', 'timepoint']).apply(remove_outliers_image, param='totalcount')
df.reset_index(drop=True, inplace=True)
# report how many cells were removed from the dataset in this step
oversegmentedcells = numcells - toolittle_cells - noparasite_cells - outliercells - df.shape[0]
print(str(oversegmentedcells)+' cells ('+str(oversegmentedcells/numcells*100) +
      '%) removed due to wells with outlier number of parasites - segmentation artefact')

# define nuclei that received the labeled protein (positive nuclei) as nuclei with fluorescence above the
# 0.99 quantile of uninfected cells (cells from moi=0 / strain=null). The 0.99 quantile of uninfected cell
# nuclei was selected as a strict definition for "uninfected nuclei fluorescence" (backgroud/nuclei negative
# for the protein). 0.99 quantile was selected instead of "max" in order to avoid defining this value by the outliers.
uninfectednucintens = df.loc[df['strain'] == 'null']['nuc_intens'].quantile(0.99)
df.ix[df['nuc_intens'] > uninfectednucintens, 'pos_nuc'] = 100
df['pos_nuc'].fillna(value=0, inplace=True)

# make "timepoint 0" data for each condition by copying the group of uninfected wells (moi=0 / strain=null)
# for each moi and strain
df = make_t0(df)

df.reset_index(drop=True, inplace=True)

# ### saving results and generating statistical summary tables ###

# save entire processed df as csv file
df.to_csv('cellprofiler_HFF_sorted_21.1.19.csv')

# for the statistical dataframes, remove timepoints>24, because after that vacuoles have became too big,
# making image segmentation too inaccurate
df = df.loc[df['timepoint'] < 25]

# define df of only infected cells, only cells infected with a single vacuole, and only cells with
# positive nuclear staining. Add to these dataframes the timepoint 0 from the "all cells" dataframe
# (because there weren't really infected or positive-nuclei cells in timepoint 0)
df_inf = df.loc[df['count'] > 1]
df_inf = pd.concat([df.loc[df['timepoint'] == 0], df_inf.loc[df_inf['timepoint'] != 0]])
df_singleinf = df.loc[df['count'] == 1]
df_singleinf = pd.concat([df.loc[df['timepoint'] == 0], df_singleinf.loc[df_singleinf['timepoint'] != 0]])
df_pos = df.loc[df['pos_nuc'] == 100]
df_pos = pd.concat([df.loc[df['timepoint'] == 0], df_pos.loc[df_pos['timepoint'] != 0]])


# calculate per well stats, and save as csv files

# by data from all cells in the dataset
df_HFF_perwell_all = per_group_stats(df, 'well')
df_HFF_perwell_all.to_csv('df_HFF_perwell_all_21.1.19.csv')
# by data from only infected cells in the dataset
df_HFF_perwell_inf = per_group_stats(df_inf, 'well')
df_HFF_perwell_inf.to_csv('df_HFF_perwell_inf_21.1.19.csv')
# by data from only single vacuole-infected cells in the dataset
df_HFF_perwell_singleinf = per_group_stats(df_singleinf, 'well')
df_HFF_perwell_singleinf.to_csv('df_HFF_perwell_singleinf_21.1.19.csv')
# by data from only positive-nuclei cells in the dataset
df_HFF_perwell_pos = per_group_stats(df_pos, 'well')
df_HFF_perwell_pos.to_csv('df_HFF_perwell_pos_21.1.19.csv')


# calculate per condition stats, , and save as csv files

# by data from all cells in the dataset
statdf_HFF_perwell_all = per_group_stats(df_HFF_perwell_all, 'well_conditions')
statdf_HFF_perwell_all.to_csv('statdf_HFF_perwell_all_21.1.19.csv')
# by data from only infected cells in the dataset
statdf_HFF_perwell_inf = per_group_stats(df_HFF_perwell_inf, 'well_conditions')
statdf_HFF_perwell_inf.to_csv('statdf_HFF_perwell_inf_21.1.19.csv')
# by data from only single vacuole-infected cells in the dataset
statdf_HFF_perwell_singleinf = per_group_stats(df_HFF_perwell_singleinf, 'well_conditions')
statdf_HFF_perwell_singleinf.to_csv('statdf_HFF_perwell_singleinf_21.1.19.csv')
# by data from only positive-nuclei cells in the dataset
statdf_HFF_perwell_pos = per_group_stats(df_HFF_perwell_pos, 'well_conditions')
statdf_HFF_perwell_pos.to_csv('statdf_HFF_perwell_pos_21.1.19.csv')


# End of script

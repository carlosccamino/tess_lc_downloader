### Importing necessary libraries ###
import pandas as pd
import argparse
import numpy as np
import lightkurve as lk
import os
import logging
import time
import subprocess
#####################################

#####################
#       Logger      #
#####################
logger = logging.getLogger(__name__)


################################
#          FUNCTIONS           #
################################

def welcome(message:str):
    """
    WELCOME MESSAGE
    """
    logger.info("*"*36)
    logger.info("*"+" "*7+ "WELCOME TO LIGHT CURVE DOWNLOADER"+" "*7+"*")
    logger.info("*"*36+"\n")
    logger.info(message+"\n")

def setup(file_rel_path:str, tic_id:int, cache_dir:str)->None:
    """
    Configuration function. Creates LOGS, SCRIPTS CONSOLIDATED and FAILED folders and paths. Sets up the cache directory.
    """

    # 0. Getting file_abs_path
    logger.info("*"*36)
    if file_rel_path:
        file_abs_path = os.path.abspath(file_rel_path)
        logger.info(f"INPUT TYPE: FILE:\nPath: {file_abs_path}")
    else:
        file_abs_path = None
        logger.info(f"INPUT TYPE: ID\n TIC ID: {tic_id}")
    

    # 1. Getting working directory
    working_dir = os.path.abspath(os.curdir)

    # 2. Creating folder structure
    folders = ['LOGS', 'CONSOLIDATED', 'SCRIPTS', 'FAILED']
    for folder in folders:
        os.makedirs(os.path.join(working_dir, folder), exist_ok=True)

    # 3. Cache directory configuration
    cache_abs_path = os.path.join(os.path.abspath(cache_dir), ".cache/lightkurve/mastDownload")
    os.makedirs(cache_abs_path, exist_ok=True)
    lk.conf.cache_dir = cache_abs_path
    logger.info(f"CACHE DIRECTORY FOR LIGHTKURVE: {cache_abs_path}")
    logger.info("*"*36+"\n")

    # 4. Giving run_batches execution permission
    run_batches_path = os.path.join(
        working_dir,
        "scripts",
        "run_batches.sh"
    )

    try:
        os.chmod(run_batches_path, os.stat(run_batches_path).st_mode | 0o111)
    except OSError as e:
        logger.error(f"File {run_batches_path} could not be made executable: {e}")
        raise PermissionError(
            f"{run_batches_path} needs to be executable."
        ) from e

    if os.access(run_batches_path, os.X_OK):
        logger.info(f"File: {run_batches_path} has execution permissions.")
    else:
        raise PermissionError(
            f"{run_batches_path} needs to be executable."
        )
  
    return file_abs_path, working_dir

def read_input(file_abs_path:str, tic_id:int) -> list:
    """
    Function that reads the type of input specified
    """
    if file_abs_path:
        star_names_df = pd.read_csv(file_abs_path, index_col=False, usecols=[0], dtype=str)
        star_names = star_names_df.iloc[:,0].to_list()

    elif tic_id is not None:
        star_names = [str(tic_id)]

    else:
        raise ValueError(f"Either {tic_id} is not a int value, or {file_abs_path} can't be read.")

    return star_names

def splitting(workers:int, star_names:list)->int:
    """
    Function that creates the batches for multiprocessing
    """

    # Split in batches 
    n_stars = len(star_names)
    n_batches = int(np.ceil(n_stars/workers))
    star_sample = [star_names[i:i+n_batches] for i in range(0, n_stars, n_batches)]
    star_segments = list(enumerate(star_sample))

    return star_segments

def safe_search_lightcurve(star_name:str, mission:str, logger:logging.Logger, **kwargs) -> pd.DataFrame:
    """
    Function retrieve pandas table data from MAST when collapsing.\n
    General Scheme:\n
       1. Request the lightcurves available
       2. If ok -> return the table with data products available
       3. If error -> wait a few seconds a retry
       4. If more than 10 minutes passed, cancel query

    Parameters
    ----------
    - star name: str, mandatory
    - mission: str, mandatory
    - sector: int, optional
    - author: str, optional
    - cadence:int, optional

    Ouput
    -----
    - Product/Error Message
    """

    #Defining the number of retries and the time waiting until next execution
    retries = 10
    delays = {1:5, 2:10, 3:30, 4:60, 5:120, 6:120, 7:120, 8:120, 9:120, 10:120}
    #Loop until it works
    for retry in range(1,retries+1):
        try:
            return lk.search_lightcurve(target="TIC "+ str(star_name), mission=mission, **kwargs).table.to_pandas()
        except Exception as e:
            time.sleep(delays[retry])
            logger.error(f"Query {retry} failed: {e}\n")
    #Raising an error if none worked
    raise Exception(f"After {retry} attempts, query failed\n")

def logger_config(name:str, level, logger_name:str, libraries: dict = None) -> logging.Logger:
    """
    Function to config a customized logger. And disable the rest
    to the level desired.

    Parameters
    ----------
    - name: str
        Name of the file in which logger will be written
    - level: logging._Level
        Minimum level of outputs
    - libraries: dict, optional
        Name of the libraries imported that want to change the logger level(keys), and new logger level(values)\n
        Format {str:logging._Level}
    Ouput
    -----
    Logger customized
    """

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    handler = logging.FileHandler(name)
    handler.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(funcName)s - %(message)s"
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    logging.captureWarnings(True)

    if libraries:
        for lib, lib_level in libraries.items():
            logging.getLogger(lib).setLevel(lib_level)

    return logger

def lightcurve_selector(star_name:str, lc_table:pd.DataFrame, logger:logging.Logger) -> pd.DataFrame:
    """
    Apply filter to the light curve data product table to obtain:\n
        1. Light curve with shortest cadence, if any.
        2. Among the light curves with shortest cadence, the one with more consecutive sectors. 
        If all the same, pick the first
    Function will select authors in this order: TASOC, SPOC, QLP, TGLC, etc.

    Parameters
    ----------
    - star_name: str, mandatory:
        Name of the target for logging purposes, in case it is not available in data

        product.
    - lc_table: pd.Dataframe, mandatory:
        Output from safe_search_lightcurve
    Ouput
    -----
    - pd.Dataframe to merge with consolidated file
        Columns will be: 
        'target_name','author', 'exptime', 'mission', 'Sectors', 'n_consecutives'
    - pd.Dataframe containing the data products fetching the filter
        Columns will be: 
        'target_name','author', 'exptime', 'mission', 'dataURL', "Sector", "Group", "n_consecutives"
    """

    if len(lc_table) == 0:
        raise Exception(f"TIC {star_name} has an empty table\n")
    
    #Selecting appropriates columns
    try:
        lc_table_r = lc_table[['target_name','author', 'exptime', 'mission', 'dataURL']].sort_values(['exptime','mission', 'author'], ascending=[True, True, False])
    except Exception as e:
        raise  ValueError(f"TIC {star_name} columns were not available {e}\n")

    #Applying the filters to obtain best data product
    try:
        #Making sure the target_name is correct (sometimes there are multiples)
        lc_table_r = lc_table_r[lc_table_r['target_name'] == star_name].copy()

        #Creating columns to select min exptime with max consecutive sectors
        #Sector
        lc_table_r['Sector'] = lc_table_r['mission'].apply(lambda x: int(x[-2:]))
        #Group (author,exptime) unique id
        lc_table_r['Group'] = lc_table_r.groupby(['author', 'exptime']).ngroup()
        # If consecutive 1, else >1
        lc_table_r['consecutive'] = lc_table_r.groupby(['Group'])['Sector'].transform(lambda x: (x.sort_values().diff().ne(1)).cumsum())
        #Counting consecutives (how many 1)
        lc_table_r['n_consecutives'] = lc_table_r.groupby(['Group', 'consecutive'])['Sector'].transform('size')

        # Filters to decide the right files
        #min Exptime
        exptime = (lc_table_r['exptime'] == lc_table_r['exptime'].min())
        lc_min_exptime = lc_table_r[exptime].copy()
        #max consecutive sectors
        max_con_sectors = lc_min_exptime['n_consecutives'] == lc_min_exptime['n_consecutives'].max()
        lc_minexp_maxsec = lc_min_exptime[max_con_sectors]
        #In case we have multiple authors, we select in this order: TASOC, SPOC, QLP, TGLC, rest.
        author_preference = ['TASOC', 'SPOC', 'QLP', 'TGLC', 'GSFC-ELEANOR-LITE', 'CDIPS']
        for author in author_preference:
            best_lc = lc_minexp_maxsec[lc_minexp_maxsec['author'].str.contains(author, case=False, na=False)].copy()
            if len(best_lc) != 0:
                # In case there are several groups of consecutive sectors, we just take one (latest one)
                latest_group = best_lc[best_lc['consecutive'] == best_lc['consecutive'].max()]['consecutive'].iloc[0]
                best_lc = best_lc[best_lc['consecutive'] == latest_group].copy()
                break
            else:
                logger.info(f"TIC {star_name} has no lightcurve from {author}\n")
                continue

        # Returning the data frame (it could be empty also)
        # Row for consolidated df
        conso_data = [[best_lc['target_name'].iloc[0],
                      best_lc['author'].iloc[0],
                      best_lc['exptime'].iloc[0],
                      'TESS',
                      list(best_lc['Sector']),
                      best_lc['n_consecutives'].iloc[0]
                      ]]
        consolidated_row = pd.DataFrame(data=conso_data, columns=['target_name', 'author', 'exptime', 'mission', 'Sector', 'n_consecutives'])
        # Row for script df
        script_df_row = best_lc.copy()
        # end of function
        logger.info(f"TIC {star_name} lightcurves url retrieved.\n")

    except Exception as e:
        raise Exception(f"TIC {star_name} could not be filtered: {e}\n")
        #consolidated_row = pd.DataFrame(data=None, columns=['target_name', 'author', 'exptime', 'mission', 'Sector', 'n_consecutives'])
        #script_df_row = pd.DataFrame(data=None, columns=['target_name', 'author', 'exptime', 'mission', 'dataURL', 'Sector', 'Group', 'consecutive', 'n_consecutives'])

    return consolidated_row, script_df_row

def script_maker(script_df:pd.DataFrame, process_number:str, working_dir:str) -> None:
    """
    Function to create a .sh script to curl all the url provided.

    Parameters
    ----------
    - script_df: pd.DataFrame, mandatory

        Dataframe containing: name of the target, data url, cadence, author, etc
    - process_number: str, mandatory

        Process number for logging and naming purposes
        
    Output
    ------
    - .sh file
    """
    with open(f'./SCRIPTS/lc_bulk_downloader_{process_number}.sh', 'w') as script:
        script.write('#!/bin/sh\n')
        for row in script_df.itertuples():
            if pd.notna(row.dataURL):
                tic_id = str(row.target_name)
                first_3 = tic_id[:3]
                last = tic_id[3:]
                dest_dir = os.path.join(working_dir, "LIGHTCURVES_c", first_3, last)
                os.makedirs(dest_dir, exist_ok=True) 
                script.write(f'curl -C - -L -o {dest_dir}/TIC_{tic_id}_S{row.Sector}_{row.exptime}s_{row.author}_lc.fits "https://mast.stsci.edu/api/v0.1/Download/file/?uri={row.dataURL}"\n')
    return

def file_maker(star_names:list, process_number:int, working_dir:str)->None:
    """
    Function that receives a list of star names and creates a consolidated

    file with best products available, and a script to curl them

    Parameters
    ----------
    - star_names: list, mandatory.

        Dataframe containing the names of the stars whose light curve need to be dowloaded

    - process_number: int, mandatory.

        Identifier of the process.

    Output
    ------
    - lc_bulk_downloader_{process_number}.sh: file

        File to be ran

    - lc_consolidated_{process_number}.csv: file

        Consolidated file for the process
    """

    # Defining initial variables
    conso_columns = ['target_name', 'author', 'exptime', 'mission', 'Sector', 'n_consecutives']
    script_columns = ['target_name', 'author', 'exptime', 'mission', 'dataURL', 'Sector', 'Group', 'consecutive', 'n_consecutives']
    consolidated_df = pd.DataFrame(data=None, columns=conso_columns)
    script_df = pd.DataFrame(data=None, columns=script_columns)
    process_number = '000'+str(process_number)
    process_number = process_number[-3:]

    #Configuring logger
    worker_logger = logger_config(name=f'./LOGS/log_{process_number}.log', 
                                  level=logging.INFO, 
                                  logger_name="worker",
                                  libraries={'matplotlib':logging.WARNING, 
                                             'lightkurve':logging.WARNING,
                                             'astropy':logging.WARNING})

    # General loop
    for star_name in star_names:

        worker_logger.info(f'########## TIC {star_name} ##########\n')

        # Defining new empty row
        row_conso = pd.DataFrame(data=[[star_name, np.nan, np.nan, np.nan, np.nan, np.nan]],
                                columns = conso_columns)
        row_script = pd.DataFrame(data=[[star_name, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan]],
                                  columns=script_columns)

        # Getting the product list
        try:
            data_products = safe_search_lightcurve(star_name=star_name, mission='TESS', logger=worker_logger)
            #Filtering the products retrieved
            row_conso, row_script = lightcurve_selector(star_name=star_name, lc_table=data_products, logger=worker_logger)

        except Exception as e:
            with open(f'./FAILED/FAILED_{process_number}.csv', 'a+') as failed:
                failed.write(f'{star_name}\n')
            worker_logger.error(f'Data products not available: {e}\n')

        #Updating dataframes
        consolidated_df = pd.concat([consolidated_df, row_conso], ignore_index=True)
        script_df = pd.concat([script_df, row_script], ignore_index=True)

        worker_logger.info('Star finished\n')
        worker_logger.info(f'#####################################\n\n')

    # Saving the consolidated file

    # Adding a column to track the process
    consolidated_df.loc[:,'Process_Number'] = process_number
    consolidated_df.to_csv(f'./CONSOLIDATED/lc_consolidated_{process_number}.csv', index=False)
    
    # Creating the .sh script
    script_maker(script_df=script_df, process_number=process_number, working_dir=working_dir)
    return

def consolidate():
    """
    Joins all the files to a consolidated one.
    """
    # CONSOLIDATED STARS
    conso_root = os.path.abspath('./CONSOLIDATED')
    files = os.listdir(conso_root)
    paths = [os.path.join(conso_root, file) for file in files]
    dfs = [pd.read_csv(path, index_col=None, dtype={"target_name":str}) for path in paths]
    consolidated = pd.concat(dfs, ignore_index=True)
    consolidated.to_csv('stars_consolidated.csv', index=False)
    return

def downloader(downloaders:int):
    """
    Execute the scripts to download light curves.
    """
    scripts = [os.path.join("./SCRIPTS", script) for script in os.listdir("SCRIPTS")]
    subprocess.run(
        ["./scripts/run_batches.sh", str(downloaders), *scripts],
        check=True
    )
    return

def lc_downloader(file_rel_path:str, tic_id:int, multiprocessing:tuple, cache_dir:str, downloaders:int, description:str) -> None:
    """
    Main function wrapper.
    """

    # WELCOME MESSAGE IN THE MAIN LOG #
    welcome(description)

    # ENVIRONMENT CONFIGURATION (including cache, multiprocessing, scripts downloaders, folders) #
    file_abs_path, working_dir = setup(file_rel_path=file_rel_path, tic_id=tic_id, cache_dir=cache_dir)

    # Reading the input
    star_names = read_input(file_abs_path=file_abs_path, tic_id=tic_id)

    # EVALUATING MULTIPROCESSING
    if multiprocessing and len(star_names)>1:
        workers, cpu_max, ram_max = multiprocessing
        workers = int(workers)
        if workers<=len(star_names):
            star_segments = splitting(workers=workers, star_names=star_names)
            # Define the rap
            rap = ResourceAwarePool(max_cpu=cpu_max, max_ram=ram_max, max_workers=workers,check_interval=20, initial_fraction=0.5)
            # Execute the pool
            rap.map(function=file_maker, iterable=[(batch, process_number) for process_number, batch in star_segments], working_dir=working_dir)
        else:
            raise ValueError(f"Number of workers ({workers}) exceeds number of stars ({len(star_names)})")

    elif multiprocessing and len(star_names) == 1:
        raise ValueError("Multiprocessing only works for files as input with more than n>1 stars and a maximum of n workers")
    
    else:
        file_maker(star_names=star_names, process_number=0, working_dir=working_dir)

    # Consolidation of stars metadata
    consolidate()

    # Running the downloader.
    downloader(downloaders)

def end_message():
    """
    END MESSAGE
    """
    logger.info("*"*36)
    logger.info("*"+" "*7+ "LIGHT CURVE DOWNLOADER FINISHED"+" "*7+"*")
    logger.info("*"*36+"\n")

################################
#           MAIN               #
################################

if __name__ == '__main__':

    ########## DESCRIPTION OF THE SCRIPT ##########
    description = "This script downloads the light curves for each star specified using lightkurve package (Lightkurve Collaboration et al. 2018). It will automatically select the shortest cadence available and download the maximum number of consecutive sectors preserving the pipeline. IT ONLY WORKS FOR LINUX."
    parser = argparse.ArgumentParser(description=description)

    ########## ARGUMENTS ##########
    # Type of input
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("-f", "--file", metavar="FILE", type=str, help="Path where the file containing all the TIC ids is stored. File should have only one column with one id per line. IDs must be pure integers (you must not include 'TIC ' in your ids.)")
    input_group.add_argument("-i", "--id", metavar="TIC ID", type=int, help="TIC ID of one specific star. It must be a pure integer.")

    # Multiprocessing
    parser.add_argument("-m", "--multiprocessing", metavar=("WORKERS", "CPU_MAX", "RAM_MAX"), nargs=3, type=float, required=False, help="This option will enable multiprocessing and parallell process. You must indicate the number of workers, cpu_max (0-1) and ram_max (0-1). Default: 25 0.5 0.5")

    # Cache Directory
    parser.add_argument("-c", "--cache_dir", metavar="DIR", type=str, default=".", required=False, help="Root directory where all the cache memory will be saved in at .cache. PLEASE SELECT A DISC WITH ENOUGH MEMORY.")

    # Script workers
    parser.add_argument("-d", "--downloaders", metavar="WORKERS", type=int, required=False, default=3, help="Once the file/s is/are created. This number of workers will download simoultaneusly the light curves.")

    # Extracting arguments
    args = parser.parse_args()

    file_rel_path = args.file
    tic_id = args.id
    multiprocessing = args.multiprocessing
    cache_dir = args.cache_dir
    downloaders = args.downloaders

    ########## EXTRA LIBRARIES ##########
    if multiprocessing:
        try:
            from pyconfigs.process_manager import ResourceAwarePool
        except Exception:
            raise ImportError("Package pyconfigs needs to be installed to run the code with parallel process.\n Please contact: carlosccamino@ugr.es.")


    ########## LOGGER CONFIG ##########
    logging.basicConfig(
        filename="lc_downloader_general.log",
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s | %(message)s",
        force=True
    )

    ########## MAIN FUNCTION ##########
    lc_downloader(file_rel_path = file_rel_path, tic_id=tic_id, multiprocessing=multiprocessing, cache_dir=cache_dir, downloaders=downloaders, description=description)

    ########## END ##########
    end_message()

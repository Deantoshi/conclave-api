import pandas as pd
# from api import api
from flask import Flask, request, jsonify
import json
from web3 import Web3
import time
import queue
from functools import cache
from concurrent.futures import ThreadPoolExecutor
import threading
import sqlite3
from google.cloud import storage
import google.cloud.storage
import os
import sys
import io
from io import BytesIO

app = Flask(__name__)

PATH = os.path.join(os.getcwd(), 'turtle-api-423200-92c434344f6f.json')

STORAGE_CLIENT = storage.Client(PATH)

@cache
def read_from_cloud_storage(filename, bucketname):
    # storage_client = storage.Client(PATH)
    bucket = STORAGE_CLIENT.get_bucket(bucketname)

    df = pd.read_csv(
    io.BytesIO(
                 bucket.blob(blob_name = filename).download_as_string() 
              ) ,
                 encoding='UTF-8',
                 sep=',') #, dtype={'from_address': str, 'to_address': str, 'tx_hash': str, 'timestamp': str, 'token_address': str, 'reserve_address': str, 'token_volume': str, 'asset_price': str, 'usd_token_amount': str, 'log_index': int, 'transaction_index': int, 'block_number': int})
    
    return df

# @cache
def read_from_cloud_storage_specific_columns(filename, bucketname, column_list, dtype_dict):
    
    # storage_client = storage.Client(PATH)
    bucket = STORAGE_CLIENT.get_bucket(bucketname)

    df = pd.read_csv(
    io.BytesIO(
                 bucket.blob(blob_name = filename).download_as_string() 
              ) ,
                 encoding='UTF-8',
                 sep=',', usecols=column_list, dtype=dtype_dict) #, dtype={'from_address': str, 'to_address': str, 'tx_hash': str, 'timestamp': str, 'token_address': str, 'reserve_address': str, 'token_volume': str, 'asset_price': str, 'usd_token_amount': str, 'log_index': int, 'transaction_index': int, 'block_number': int})
    
    return df

# # will make a dataframe that exists on the first block of Ironclad's deployment to serve as a placeholder to forward fill from
def make_placeholder_starter_df(df, min_block_number):

    user_address = df['user_address'].tolist()
    user_address = user_address[0]

    token_address = df['token_address'].tolist()
    token_address = token_address[0]

    temp_df = pd.DataFrame()

    eth_deposit_receipt_address = '0x9c29a8eC901DBec4fFf165cD57D4f9E03D4838f7'
    wrseth_deposit_receipt_address = '0xe3f709397e87032E61f4248f53Ee5c9a9aBb6440'
    deposit_receipt_list = [token_address]

    filler_text_list = ['N/A']
    filler_number_list = [0]

    temp_df['user_address'] = [user_address]
    temp_df['tx_hash'] = filler_text_list
    temp_df['token_address'] = deposit_receipt_list
    temp_df['token_volume'] = filler_number_list
    temp_df['timestamp'] = filler_number_list
    temp_df['block_number'] = [min_block_number]
    temp_df['asset_price'] = filler_number_list
    temp_df['amount_cumulative'] = filler_number_list

    df_list = [df, temp_df]

    df = pd.concat(df_list)

    return df

# # takes in our regular dataframe with transaction level data and our blank dataframe with block_numbers
# # replaces data in the large block_number data with our info from the regular dataframe
def quick_edit_values(df, block_number_df):

    user_address = df['user_address'].iloc[0]
    token_address = df['token_address'].iloc[0]

    amount_cumulative_list = df['amount_cumulative'].tolist()
    block_number_list = df['block_number'].tolist()

    i = 0
    while i < len(block_number_list):
        block_number = block_number_list[i]
        amount_cumulative = amount_cumulative_list[i]

        block_number_df.loc[block_number_df['block_number'] == block_number, 'amount_cumulative'] = amount_cumulative

        i += 1

    block_number_df['user_address'] = user_address
    block_number_df['token_address'] = token_address

    return block_number_df

# # tries to forward fill the last known block numbers
def forward_fill_df(df, minimum_block, maximum_block):
    
    df['block_number'] = df['block_number'].astype(int)
    # block_number = int(block_number)
    # 1. Get minimum and maximum block numbers (assuming data exists for 10 and 15)
    min_block_number = df['block_number'].min()
    min_block_number = int(min_block_number)

    absolute_min_block_number = 3929720

    # user_address, tx_hash, token_address, token_volume, timestamp, block_number, asset_price, amount_cumulative

    start_time = time.time()
    df = make_placeholder_starter_df(df, absolute_min_block_number)
    new_time = time.time()
    print('Finished making placeholder in: ', str(new_time - start_time))


    # 2. Create a range index for missing block numbers (10 to 1000)
    start_time = time.time()
    missing_block_range = pd.RangeIndex(start=absolute_min_block_number, stop=maximum_block + 1)  # 1001 to be inclusive of 1000
    new_time = time.time()
    print('Finished making block_range in: ', str(new_time - start_time))
    # 3. Filter existing data (block_number 10 and 15)
    existing_data = df

    # 4. Create DataFrame for missing blocks with placeholder values (adjust as needed)
    start_time = time.time()
    missing_data = pd.DataFrame({
        'user_address': [None] * len(missing_block_range),  # Replace with placeholder if needed
        'token_address': [None] * len(missing_block_range),   # Replace with placeholder if needed
        'amount_cumulative': [None] * len(missing_block_range),  # Replace with placeholder if needed (e.g., 0)
        'block_number': missing_block_range
    })
    new_time = time.time()
    print('Finished making missing_data_df in: ', str(new_time - start_time))

    # 5. Concatenate existing and missing data (preserves order)
    start_time = time.time()
    # df = pd.concat([existing_data, missing_data], ignore_index=True)
    df = quick_edit_values(df, missing_data)
    new_time = time.time()
    print('Finished combining dataframes in: ', str(new_time - start_time))

    # 6. Sort by block_number (optional, but recommended for clarity)
    df = df.sort_values(by='block_number')
    
    # # reduces the scope of our dataframe for better performance
    df = df[['user_address', 'token_address', 'amount_cumulative', 'block_number']]
    
    start_time = time.time()
    df = df.ffill()
    new_time = time.time()
    print('finished filling info in: ', str(new_time - start_time))

    df = df.fillna(0)
    
    # # will set our dataframe back to the specified block range
    df = df.loc[df['block_number'] >= minimum_block]
    df = df.loc[df['block_number'] <= maximum_block]

    # Now 'df' has data for block_number 10 to 1000 (with placeholders for missing values)

    return df

# # will make sure our min block is atleat the block we deployed at
def min_block_sanitizer(minimum_block):

    absolute_minimum_block = 3929720

    try:
        minimum_block = int(minimum_block)
    except:
        minimum_block = absolute_minimum_block
    
    if minimum_block < absolute_minimum_block:
        minimum_block = absolute_minimum_block

    return minimum_block

# # will make sure that our max block is the most recent block we have in out data set
def max_block_sanitizer(df, maximum_block):
    
    absolute_maximum_block = df['block_number'].max()
    absolute_maximum_block = int(absolute_maximum_block)

    try:
        maximum_block = int(maximum_block)
    except:
        maximum_block = absolute_maximum_block
    
    if maximum_block > absolute_maximum_block:
        maximum_block = absolute_maximum_block
    
    return maximum_block


# # takes in a wallet_address and a block number
# # returns that user's balance at that blocknumber
def get_user_eth_wrseth_at_block_number(df, wallet_address, minimum_block, maximum_block):
    absolute_minimum_block = 3929720
    absolute_max_block = df['block_number'].max()

    # # makes sure our block inputs are as valid as possible
    minimum_block = min_block_sanitizer(minimum_block)
    maximum_block = max_block_sanitizer(df, maximum_block)

    # # incase the inputs are scuffed, we fix them here
    if minimum_block > maximum_block:
        minimum_block = absolute_minimum_block

    if maximum_block < minimum_block:
        maximum_block = absolute_max_block

    # # makes our dataframe only contain ETH deposit tokens and wrsETH deposit tokens
    eth_deposit_receipt_address = '0x9c29a8eC901DBec4fFf165cD57D4f9E03D4838f7'
    wrseth_deposit_receipt_address = '0xe3f709397e87032E61f4248f53Ee5c9a9aBb6440'

    deposit_receipt_list = [eth_deposit_receipt_address, wrseth_deposit_receipt_address]

    df['block_number'] = df['block_number'].astype(float)
    
    # df = df.loc[df['block_number'] <= maximum_block]

    df = df.loc[df['token_address'].isin(deposit_receipt_list)]
    
    # # will just short circuit the function if the user doesn't have a wrsETH or ETH balance on Ironclad
    df_wallet_checker = df.loc[df['to_address'] == wallet_address]
    if len(df_wallet_checker) < 1:
        return 'User does not have a history of wrsETH or ETH on Ironclad. To find a list of potential suppliers, please try the: /get_all_wrseth_eth_suppliers GET endpoint.'

    # # makes our additions and subtraction flows and drops blacklisted addresses
    index = 0

    df['token_volume'] = df['token_volume'].astype(float)
    df['timestamp'] = df['timestamp'].astype(float)
    df = df.sort_values(by='timestamp', ascending=True)

    df = set_token_flows_no_database(df, index)
    
    # # sets our dataframe to only contain values for our wallet
    df = df.loc[df['user_address'] == wallet_address]

    df = drop_blacklisted_addresses(df)

    df = df.drop_duplicates(subset=['user_address', 'token_address', 'tx_hash', 'token_volume', 'timestamp'])

    # # if our dataframe is > 0 length, we'll make our balance
    if len(df) > 0:
            start_time = time.time()
            
            df = set_rolling_balance(df)

    df_list = []
    for token in deposit_receipt_list:
        temp_df = df.loc[df['token_address'] == token]
        if len(temp_df) > 0:
            temp_df = forward_fill_df(temp_df, minimum_block, maximum_block)
            df_list.append(temp_df)

    df = pd.concat(df_list)

    df.loc[df['token_address'] == eth_deposit_receipt_address, 'supplied_token'] = 'WETH'
    df.loc[df['token_address'] == wrseth_deposit_receipt_address, 'supplied_token'] = 'wrsETH'

    # df['human_readable']  = df['amount_cumulative'] / 1e18

    df.loc[df['amount_cumulative'] < 0, 'amount_cumulative'] = 0
    # df.loc[df['human_readable'] < 0, 'human_readable'] = 0

    response = make_kelp_dao_response(df)
    
    return response


# # returns our dataframe with only unique addresses
def set_unique_users_no_database(df):

    df = df.drop_duplicates(subset=['to_address'])

    return df

def get_token_config_df(index):
    df = pd.read_csv('token_config.csv')
    df = df.loc[df['chain_index'] == index]

    return df

def get_deposit_token_df(index):
    token_df = get_token_config_df(index)

    token_list = token_df['token_name'].tolist()

    token_list = [token for token in token_list if token[0] != 'v']

    deposit_df = pd.DataFrame()

    deposit_df['token_name'] = token_list

    token_df = token_df.loc[token_df['token_name'].isin(token_list)]

    return token_df

def get_borrow_token_df(index):
    token_df = get_token_config_df(index)

    token_list = token_df['token_name'].tolist()

    token_list = [token for token in token_list if token[0] == 'v']

    borrow_df = pd.DataFrame()

    borrow_df['token_name'] = token_list

    token_df = token_df.loc[token_df['token_name'].isin(token_list)]

    return token_df

# # finds if a transaction adds to or reduces a balance 
# # (deposit + borrow add to a balance and withdraw + repay reduce a balance)
def set_token_flows_no_database(event_df, index):
    # event_df = pd.read_csv(csv_name, usecols=['from_address','to_address','timestamp','token_address', 'token_volume','tx_hash'], dtype={'from_address': str,'to_address': str,'timestamp' : str,'token_address': str, 'token_volume': float,'tx_hash': str})
    
    # # tries to remove the null address to greatly reduce computation needs
    # event_df = event_df.loc[event_df['to_address'] != '0x0000000000000000000000000000000000000000']
    
    unique_user_df = set_unique_users_no_database(event_df)

    unique_user_list = unique_user_df['to_address'].to_list()

    deposit_token_df = get_deposit_token_df(index)
    borrow_token_df = get_borrow_token_df(index)

    deposit_token_list = deposit_token_df['token_address'].tolist()
    borrow_token_list = borrow_token_df['token_address'].tolist()

    i = 1

    combo_df = pd.DataFrame()
    temp_df = pd.DataFrame()

    # # handles deposits and borrows
    temp_df = event_df.loc[event_df['to_address'].isin(unique_user_list)]
    deposit_df = temp_df.loc[temp_df['token_address'].isin(deposit_token_list)]
    borrow_df = temp_df.loc[temp_df['token_address'].isin(borrow_token_list)]

    # # handles withdrawals and repays
    temp_df = event_df.loc[event_df['from_address'].isin(unique_user_list)]
    withdraw_df = temp_df.loc[temp_df['token_address'].isin(deposit_token_list)]
    repay_df = temp_df.loc[temp_df['token_address'].isin(borrow_token_list)]

    withdraw_df['token_volume'] = [x * -1 for x in withdraw_df['token_volume'].tolist()]
    repay_df['token_volume'] = [x * -1 for x in repay_df['token_volume'].tolist()]

    deposit_df['user_address'] = deposit_df['to_address']
    borrow_df['user_address'] = borrow_df['to_address']
    
    withdraw_df['user_address'] = withdraw_df['from_address']
    repay_df['user_address'] = repay_df['from_address']

    combo_df = pd.concat([deposit_df, borrow_df, withdraw_df, repay_df])
    combo_df = combo_df[['user_address', 'tx_hash', 'token_address','token_volume', 'timestamp', 'block_number', 'asset_price']]

    # make_user_data_csv(combo_df, token_flow_csv)

    # # tries to remove the null address to greatly reduce computation needs
    combo_df = combo_df.loc[combo_df['user_address'] != '0x0000000000000000000000000000000000000000']

    return combo_df

# # gets rid of our blacklisted addresses in our dataframe
def drop_blacklisted_addresses(df):
    
    # df.loc[df['user_address'] == '0xd93E25A8B1D645b15f8c736E1419b4819Ff9e6EF', 'user_address'] = '0x5bC7b531B1a8810c74E53C4b81ceF4F8f911921F'
    df = df.loc[df['user_address'] != '0xd93E25A8B1D645b15f8c736E1419b4819Ff9e6EF']
    df = df.loc[df['user_address'] != '0x6387c7193B5563DD17d659b9398ACd7b03FF0080']
    df = df.loc[df['user_address'] != '0x0000000000000000000000000000000000000000']
    df = df.loc[df['user_address'] != '0x2dDD3BCA2Fa050532B8d7Fd41fB1449382187dAA']

    return df

def set_rolling_balance(df):
    df['timestamp'] = df['timestamp'].astype(float)
    # df = get_token_flows()

    # df = df.loc[df['user_address'] == '0xE692256D270946A407f8Ba9885D62e883479F0b8']
    df.sort_values(by=['timestamp'], ascending=True)

    # Group the DataFrame by 'name' and calculate cumulative sum
    name_groups = df.groupby(['user_address','token_address'])['token_volume'].transform(pd.Series.cumsum)

    # Print the DataFrame with the new 'amount_cumulative' column
    df = df.assign(amount_cumulative=name_groups)

    # df.to_csv('rolling_balance.csv', index=False)

    return df

# # returns our token_config value
def get_token_config_value(column_name, token_address, index):
    df = get_token_config_df(index)

    df = df.loc[df['chain_index'] == index]

    temp_df = df.loc[df['token_address'] == token_address]

    if len(temp_df) < 1:
        df = df.loc[df['underlying_address'] == token_address]

    config_list = df[column_name].tolist()

    config_value = config_list[0]

    return config_value

def get_time_difference(df):

    # # df = df.loc[df['user_address'] == '0xE692256D270946A407f8Ba9885D62e883479F0b8']
    # # df = df.loc[df['user_address'] == '0x67D69CA5B47F7d45D9A7BB093479fcA732023dfa']

    # Sort by Name and timestamp for correct grouping
    df = df.sort_values(by=['user_address', 'token_address', 'timestamp'])

    # Calculate time difference for each name group
    df['timestamp'] = df['timestamp'].astype(float)
    time_diff = df.groupby(['user_address', 'token_address'])['timestamp'].diff()

    # Handle the first row for each name (no difference)
    # time_diff.iloc[::2] = pd.NA  # Set difference to NaN for the first row of each name group

    # Calculate difference in seconds (adjust as needed)
    time_diff_seconds = time_diff.fillna(0)

    df['time_difference'] = time_diff_seconds

    return df


def get_double_ember_list():
    double_ember_token_list = ['0xe7334Ad0e325139329E747cF2Fc24538dD564987', '0x02CD18c03b5b3f250d2B29C87949CDAB4Ee11488', '0x272CfCceFbEFBe1518cd87002A8F9dfd8845A6c4', '0x58254000eE8127288387b04ce70292B56098D55C', 
                               '0xC17312076F48764d6b4D263eFdd5A30833E311DC', '0xe5415Fa763489C813694D7A79d133F0A7363310C', '0xBcE07537DF8AD5519C1d65e902e10aA48AF83d88', '0x5eEA43129024eeE861481f32c2541b12DDD44c08', 
                               '0x05249f9Ba88F7d98fe21a8f3C460f4746689Aea5', '0x3F332f38926b809670b3cac52Df67706856a1555', '0x4522DBc3b2cA81809Fa38FEE8C1fb11c78826268', '0xF8D68E1d22FfC4f09aAA809B21C46560174afE9c']
    
    return double_ember_token_list

def get_quadriple_ember_list():
    quadriple_ember_token_list = ['0x9c29a8eC901DBec4fFf165cD57D4f9E03D4838f7', '0xe3f709397e87032E61f4248f53Ee5c9a9aBb6440', '0x06D38c309d1dC541a23b0025B35d163c25754288', '0x083E519E76fe7e68C15A6163279eAAf87E2addAE']
    
    return quadriple_ember_token_list

def calculate_accrued_points(df):

    # # temporarily reduces sample size to two people
    # df = df.loc[df['user_address'].isin(['0x67D69CA5B47F7d45D9A7BB093479fcA732023dfa', '0xE692256D270946A407f8Ba9885D62e883479F0b8'])]

    df['previous_amount'] = df['amount_cumulative'].shift(1)
    df['accrued_embers'] = (df['embers'] * df['time_difference'] / 86400) * df['previous_amount'].fillna(0)
    
    # # Set accrued_embers to 0 for rows with timestamps before a specific threshold (March 22nd in this case)
    # df.loc[df['timestamp'] < 1711080000, 'accrued_embers'] = 0

    df = df[['user_address', 'token_address', 'tx_hash', 'timestamp', 'time_difference', 'embers', 'amount_cumulative', 'accrued_embers', 'token_cumulative']]
    return df

def set_realized_embers(df):

    df['timestamp'] = df['timestamp'].astype(float)

    double_ember_token_list = get_double_ember_list()
    quadriple_ember_token_list = get_quadriple_ember_list()

    df = df.groupby(['user_address','token_address']).apply(calculate_accrued_points)

    # 1711080000 = March 22d the start of the embers program
    df.loc[df['timestamp'] < 1711080000, 'accrued_embers'] = 0 

    # 1714147200 = April 26th when 2x and 4x embers began
    df.loc[(df['timestamp'] >= 1714147200) & (df['token_address'].isin(double_ember_token_list)), 'accrued_embers'] *= 2
    df.loc[(df['timestamp'] >= 1714147200) & (df['token_address'].isin(quadriple_ember_token_list)), 'accrued_embers'] *= 4

    return df

def get_last_tracked_embers(df):

    df['timestamp'] = df['timestamp'].astype(float)
    df['accrued_embers'] = df['accrued_embers'].astype(float)
    # Group by wallet_address and token_address
    grouped_df = df.groupby(['user_address', 'token_address'])

    ember_balance = grouped_df['accrued_embers'].sum()

    # df['ember_balance'] = ember_balance.reset_index(drop=True)  # Drop unnecessary index

    # Get max embers and corresponding timestamp using agg
    max_embers_df = grouped_df.agg(max_embers=('accrued_embers', max), max_timestamp=('timestamp', max))

    # Reset index to remove multi-level indexing
    max_embers_df = max_embers_df.reset_index()

    max_embers_df['max_embers'] = ember_balance.reset_index(drop=True) 
    timestamp_list = max_embers_df['max_timestamp'].tolist()
    timestamp_list = [float(timestamp) for timestamp in timestamp_list]

    max_embers_df.rename(columns = {'max_timestamp':'timestamp', 'max_embers': 'ember_balance'}, inplace = True) 

    merged_df = max_embers_df.merge(df, how='inner', on=['user_address', 'token_address', 'timestamp'])

    merged_df = merged_df[['user_address', 'token_address', 'tx_hash', 'timestamp', 'time_difference', 'embers', 'amount_cumulative', 'ember_balance', 'token_cumulative']]

    # Set amount_cumulative values less than 0 to 0 (in-place modification)
    merged_df['amount_cumulative'] = merged_df['amount_cumulative'].clip(lower=0)
    merged_df['ember_balance'] = merged_df['ember_balance'].clip(lower=0)
    

    return merged_df

# # returns the tvl and embers for a single user
def set_single_user_stats(df, user_address, index):

    df['token_volume'] = df['token_volume'].astype(float)
    df['timestamp'] = df['timestamp'].astype(float)

    start_time = time.time()
    
    df = df.sort_values(by='timestamp', ascending=True)

    df = set_token_flows_no_database(df, index)
    print('set_token_flows complete in: ' + str(time.time() - start_time))

    # df = df.loc[df['user_address'] == user_address]
    
    df = drop_blacklisted_addresses(df)
    
    if len(df) > 0:
        start_time = time.time()
        
        df = set_rolling_balance(df)
        print('set_rolling_balances complete: ' + str(time.time() - start_time))

        config_df = get_token_config_df(index)

        reserve_address_list = config_df['underlying_address'].tolist()
        token_address_list = config_df['token_address'].tolist()
        embers_list = config_df['embers'].tolist()

        df_list = []

        start_time = time.time()
        i = 0
        while i < len(reserve_address_list):
            reserve_address = reserve_address_list[i]
            token_address = token_address_list[i]
            embers = embers_list[i]

            if reserve_address == '0xDfc7C877a950e49D2610114102175A06C2e3167a':
                print('Mode')
            
            decimals = get_token_config_value('decimals', reserve_address, index)

            temp_df = df.loc[df['token_address'] == token_address]
            # temp_df['amount_cumulative'] = temp_df['amount_cumulative'].astype(float)

            if len(temp_df) > 0:
                print(temp_df)
                temp_df['amount_cumulative'] = temp_df['amount_cumulative'] / decimals
                temp_df['token_cumulative'] = temp_df['amount_cumulative']
                temp_df['amount_cumulative'] = temp_df['amount_cumulative'] * temp_df['asset_price']
                print(temp_df)
                temp_df['embers'] = embers

                df_list.append(temp_df)
            
            i += 1
        
        print('amount_cumulative clean up complete' + str(time.time() - start_time))
        
        df = pd.concat(df_list)

        # makes the lowest accumualtive = 0 (user's can't have negative balances)
        df['amount_cumulative'] = df['amount_cumulative'].clip(lower=0)
        df['token_cumulative'] = df['token_cumulative'].clip(lower=0)

        start_time = time.time()
        df = get_time_difference(df)

        print('time_difference complete' + str(time.time() - start_time))

        df = df.reset_index(drop=True)

        start_time = time.time()
        df = set_realized_embers(df)
        df = df.reset_index(drop=True)
        
        print('set_realized_embers complete' + str(time.time() - start_time))

        start_time = time.time()
        df = get_last_tracked_embers(df)
        print('get_last_tracked_embers complete' + str(time.time() - start_time))

        df = df.reset_index(drop=True)

        start_time = time.time()
        df = accrue_latest_embers(df)
        df = df.reset_index(drop=True)
        print('accrue_latest_embers complete' + str(time.time() - start_time))

    else:
        df = pd.DataFrame()
        
    return df

# # function we will apply to out dataframe to estimate how many embers users have earned since their last event
def simulate_accrued_points(df):
  df['ember_balance'] += (df['embers'] * df['time_difference'] / 86400) * df['amount_cumulative'].fillna(0)

  df = df[['user_address', 'token_address', 'tx_hash', 'timestamp', 'time_difference', 'embers', 'amount_cumulative', 'ember_balance']]
  return df

# # function we will apply to out dataframe to estimate how many embers users have earned since their last event
def simulate_regular_accrued_points(df):
  df['regular_ember_balance'] += (df['embers'] * df['time_difference'] / 86400) * df['amount_cumulative'].fillna(0)

  df = df[['user_address', 'token_address', 'tx_hash', 'timestamp', 'time_difference', 'embers', 'amount_cumulative', 'ember_balance', 'regular_ember_balance', 'token_cumulative']]
  return df

# # function we will apply to out dataframe to estimate how many embers users have earned since their last event
def simulate_multiplier_accrued_points(df):
  df['multiplier_ember_balance'] += (df['embers'] * df['time_difference'] / 86400) * df['amount_cumulative'].fillna(0)

  df = df[['user_address', 'token_address', 'tx_hash', 'timestamp', 'time_difference', 'embers', 'amount_cumulative', 'ember_balance', 'regular_ember_balance', 'multiplier_ember_balance', 'token_cumulative']]
  return df

# # takes in a dataframe with the last known balance and accrued ember amount
# # outputs a dataframe with expected accrued embers since last event
def accrue_latest_embers(df):

    double_ember_token_list = get_double_ember_list()
    quadriple_ember_token_list = get_quadriple_ember_list()

    current_unix = int(time.time())

    ember_start_unix = 1711080000
    point_multiplier_start_unix = 1714147200

    # df['time_difference'] = current_unix - df['timestamp']

    # time within the the regular accrural period
    df['time_difference'] = df['timestamp'] - ember_start_unix

    # if a user's last transaction was before the ember start time
    df.loc[df['time_difference'] < 0, 'time_difference'] = (point_multiplier_start_unix - ember_start_unix)

    # if a user's last transaction was between the start and ending of regular embers
    df.loc[(df['timestamp'] > ember_start_unix) & (df['timestamp'] < point_multiplier_start_unix), 'time_difference'] = point_multiplier_start_unix - df['timestamp']

    df.loc[df['timestamp'] > point_multiplier_start_unix, 'time_difference'] = 0

    # df['time_difference'] = point_multiplier_start_unix - ember_start_unix

    df['regular_ember_balance'] = 0

    df = df.groupby(['user_address','token_address']).apply(simulate_regular_accrued_points)
    df = df.reset_index(drop=True)

    # # accrues regular embers to users > ember start time and < multiplier start time
    # baseline sees what people's time difference is
    df['time_difference'] = df['timestamp'] - point_multiplier_start_unix
    # if someone has a < 0 time difference, we just make them current unix timestamp - the start of multipier points :)
    df.loc[df['time_difference'] < 0, 'time_difference'] = current_unix - point_multiplier_start_unix
    df.loc[df['timestamp'] > point_multiplier_start_unix, 'time_difference'] = current_unix - df['timestamp']

    # df['time_difference'] = current_unix - point_multiplier_start_unix

    df['multiplier_ember_balance'] = 0

    df = df.groupby(['user_address','token_address']).apply(simulate_multiplier_accrued_points)
    df = df.reset_index(drop=True)

    df.loc[df['token_address'].isin(double_ember_token_list), 'multiplier_ember_balance'] *= 2

    df.loc[df['token_address'].isin(quadriple_ember_token_list), 'multiplier_ember_balance'] *= 4

    df['total_ember_balance'] = df.groupby('user_address')['ember_balance'].transform('sum')
    df['total_ember_balance'] += df.groupby('user_address')['regular_ember_balance'].transform('sum')
    df['total_ember_balance'] += df.groupby('user_address')['multiplier_ember_balance'].transform('sum')

    df = df.loc[df['total_ember_balance'] > 0]

    return df
# # function we will apply to out dataframe to estimate how many embers users have earned since their last event
def simulate_accrued_points(df):
  df['ember_balance'] += (df['embers'] * df['time_difference'] / 86400) * df['amount_cumulative'].fillna(0)

  df = df[['user_address', 'token_address', 'tx_hash', 'timestamp', 'time_difference', 'embers', 'amount_cumulative', 'ember_balance']]
  return df

# # function we will apply to out dataframe to estimate how many embers users have earned since their last event
def simulate_regular_accrued_points(df):
  df['regular_ember_balance'] += (df['embers'] * df['time_difference'] / 86400) * df['amount_cumulative'].fillna(0)

  df = df[['user_address', 'token_address', 'tx_hash', 'timestamp', 'time_difference', 'embers', 'amount_cumulative', 'ember_balance', 'regular_ember_balance', 'token_cumulative']]
  return df

# # function we will apply to out dataframe to estimate how many embers users have earned since their last event
def simulate_multiplier_accrued_points(df):
  df['multiplier_ember_balance'] += (df['embers'] * df['time_difference'] / 86400) * df['amount_cumulative'].fillna(0)

  df = df[['user_address', 'token_address', 'tx_hash', 'timestamp', 'time_difference', 'embers', 'amount_cumulative', 'ember_balance', 'regular_ember_balance', 'multiplier_ember_balance', 'token_cumulative']]
  return df

# # makes our json response for a users total tvl and embers
def get_user_tvl_and_embers(user_address):

    data = []
    index = 0
    
    start_time = time.time()
    df = read_from_cloud_storage('kelp_dao_data.csv', 'kelp_dao')
    print('Finished Reading Data in: ' + str(time.time() - start_time))

    user_address = Web3.to_checksum_address(user_address)
    df = df[(df['to_address'].str.contains(user_address)) | (df['from_address'].str.contains(user_address))]
    
    if len(df) > 0:
        df = df.drop_duplicates(subset=['tx_hash','log_index', 'transaction_index', 'token_address'], keep='last')
        df = set_single_user_stats(df, user_address, index)
    #if we have an address with no transactions
    if len(df) < 1:
        data.append({
           "user_address": user_address,
            "user_tvl": 0,
            "user_total_embers": 0
        })
    
    else:
        total_tvl = df['amount_cumulative'].sum()
        total_embers = df['total_ember_balance'].median()
        # # downrates embers a bit
        total_embers = total_embers * 0.65

        data.append({
           "user_address": user_address,
            "user_tvl": total_tvl,
            "user_total_embers": total_embers
        })

    # Create JSON response
    response = {
        "data": {
            "result": data
        }
    }
    
    return response

# # makes our json response for a users total tvl and embers
def calculate_batch_users_tvl_and_embers(df, user_address):

    data = []
    index = 0
    response = {}

    start_time = time.time()
    print('Finished Reading Data in: ' + str(time.time() - start_time))

    user_address = Web3.to_checksum_address(user_address)
    df = df[(df['to_address'].str.contains(user_address)) | (df['from_address'].str.contains(user_address))]
    
    if len(df) > 0:
        df = df.drop_duplicates(subset=['tx_hash','log_index', 'transaction_index', 'token_address', 'token_volume'], keep='last')
        df = set_single_user_stats(df, user_address, index)
    #if we have an address with no transactions
    if len(df) < 1:
        response = {
            "user_tvl": 0,
            "user_total_embers": 0
        }
    
    else:
        total_tvl = df['amount_cumulative'].sum()
        total_embers = df['total_ember_balance'].median()
        # # downrates embers a bit
        total_embers = total_embers * 0.65

        response = {
            "user_tvl": total_tvl,
            "user_total_embers": total_embers
        }
    
    return response

# # quickly turns our dataframe into a dictionary to be used as a json response
def make_vectorized_kelp_response(df, grouped_df):
    # Get column names (assuming all groups have same columns)
    column_names = list(df.columns)

    return grouped_df[column_names].to_dict(orient='index')

# # makes our kelp_dao response of wrsETH and ETH supply each block
def make_kelp_dao_response(df):

    # # makes temporary dataframes that only has tokens from respective tokens
    temp_df_1 = df.loc[df['supplied_token'] == 'wrsETH']
    temp_df_2 = df.loc[df['supplied_token'] == 'WETH']


    # # makes new columns for a third temp_df for wrseth_supplied and weth_supplied
    temp_df_3 = temp_df_1[['user_address', 'block_number']]
    temp_df_3['wrseth_supplied'] = temp_df_1['amount_cumulative']
    temp_df_3['weth_supplied'] = temp_df_2['amount_cumulative']

    # # reassigns df to the new token df
    df = temp_df_3
    
    wallet_address = df['user_address'].tolist()[0]

    df = df[['block_number', 'wrseth_supplied', 'weth_supplied']]

    df = df.set_index('block_number')

    data_dict = df.to_dict(orient='dict')

    df_dict = {}

    df_dict[wallet_address] = data_dict

    data = []

    # Create JSON response
    response = data

    return df_dict

# # makes our nested response
def make_nested_response(df):

    data = []

    #if we have an address with no transactions
    if len(df) < 1:
        temp_df = pd.DataFrame()
        data.append({
           "wallet_address": 'N/A',
        })

    else:
        # wallet_addresses = ", ".join(df["to_address"].tolist())
        # data.append({"wallet_address": wallet_addresses})
        temp_df = df[['to_address']]
        # Process data
        for i in range(temp_df.shape[0]):
            row = temp_df.iloc[i]
            data.append({
                "wallet_address": str(row['to_address']),
            })

    # Create JSON response
    response = {
        "data": {
            "result": data
        }
    }
    
    return response

# #  gets all transactions for a specified user_address
def get_users_transactions(user_address):
    
    data = []

    df = read_from_cloud_storage('kelp_dao_data.csv', 'kelp_dao')
    
    df = df[(df['from_address'] == user_address) | (df['to_address'] == user_address)]


    if len(df) < 1:
        return {"error": "The address is not valid or does not exist in the database."}, 400
    
    else:
        from_address = df['from_address']
        to_address = df['to_address']
        tx_hash = df['tx_hash']
        timestamp = df['timestamp']
        token_address = df['token_address']
        reserve_address = df['reserve_address']
        token_volume = df['token_volume']
        asset_price = df['asset_price']
        usd_token_amount = df['usd_token_amount']
        block_number = df['block_number']
        
        for i in range(df.shape[0]):
            row = df.iloc[i]
            data.append({
                "from_address": str(row['from_address']),
                "to_address": str(row['to_address']),
                "tx_hash": str(row['tx_hash']),
                "timestamp": str(row['timestamp']),
                "token_address": str(row['token_address']),
                "reserve_address": str(row['reserve_address']),
                "token_volume": str(row['token_volume']),
                "asset_price": str(row['asset_price']),
                "usd_token_amount": str(row['usd_token_amount']),
                "block_number": str(row['block_number']),
            })

    # Create JSON response
    response = {
        "data": {
            "result": data
        }
    }


    return response

# # makes a plain jane dictionary resposnse
def make_df_to_dict_response(df):

    df = df.set_index('user_address')
    
    df_dict = df.to_dict(orient='dict')

    return df_dict


@app.route("/user_tvl_and_embers/", methods=["POST"])
def get_api_response():

    data = json.loads(request.data)

    user_address = data['user_address']  # Assuming data is in form format
    
    # Threads
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_user_tvl_and_embers, user_address)
    
    response = future.result()

    return jsonify(response), 200

# # processes batches of addresses
@app.route("/batch_users_tvl_and_embers/", methods=["POST"])
def get_batch_users_tvl_and_embers_response():

    data = request.get_json()

    # Check if data is present and a list
    if not data or not isinstance(data, list):
        return jsonify({"error": "Invalid request format. Please provide a list of user addresses."}), 400
    
    else:
        user_addresses = data
    
    df = read_from_cloud_storage('kelp_dao_data.csv', 'kelp_dao')

    response_dict = {}
    for user_address in user_addresses:
        # Threads (optional)
        with ThreadPoolExecutor() as executor:
            future = executor.submit(calculate_batch_users_tvl_and_embers, df, user_address)
            response_dict[user_address] = future.result()  # Append individual responses

    reponse_dict = {
        "data": response_dict
    }
    return jsonify(response_dict), 200

# # will be an endpoint we can ping to try to keep our website online for quicker response times
@app.route("/keep_online/", methods=["GET"])
def get_filler_response():

    user_address = '0x2dDD3BCA2Fa050532B8d7Fd41fB1449382187dAA'

    # Threads
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_user_tvl_and_embers, user_address)
    
    response = future.result()

    return jsonify(response), 200

# # will be an endpoint we can ping to try to keep our website online for quicker response times
@app.route("/get_all_users/", methods=["GET"])
def get_all_users():

    df = read_from_cloud_storage('kelp_dao_data.csv', 'kelp_dao')
    df = set_unique_users_no_database(df)
    df = df[['to_address', 'log_index']]

    # Threads
    with ThreadPoolExecutor() as executor:
        future = executor.submit(make_nested_response, df)
    
    response = future.result()

    return jsonify(response), 200

@app.route("/get_user_transactions/", methods=["POST"])
def get_them_transactions():

    data = json.loads(request.data)

    user_address = data['user_address']  # Assuming data is in form format

    # Threads
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_users_transactions, user_address)
    
    response = future.result()

    return jsonify(response), 200

@app.route("/get_wallet_wrseth_eth_supply/", methods=["POST"])
def get_wrseth_eth_api_response():

    df = read_from_cloud_storage('kelp_dao_data.csv', 'kelp_dao')

    data = json.loads(request.data)

    wallet_address = data['wallet_address']  # Assuming data is in form format
    minimum_block = data['minimum_block']
    maximum_block = data['maximum_block']

    eth_deposit_receipt_address = '0x9c29a8eC901DBec4fFf165cD57D4f9E03D4838f7'
    wrseth_deposit_receipt_address = '0xe3f709397e87032E61f4248f53Ee5c9a9aBb6440'
    receipt_list = [eth_deposit_receipt_address, wrseth_deposit_receipt_address]

    temp_df_checker = df.loc[df['to_address'] == wallet_address]
    temp_df_checker = df.loc[df['token_address'].isin(receipt_list)]

    if len(temp_df_checker) < 1:
        response = 'User does not have a history of supplying wrsETH nor WETH on Ironclad. To find a list of potential suppliers, please try the: /get_all_wrseth_eth_suppliers GET endpoint.'
        return jsonify(response), 200

    # Threads
    with ThreadPoolExecutor() as executor:
        future = executor.submit(get_user_eth_wrseth_at_block_number, df, wallet_address, minimum_block, maximum_block)
    
    response = future.result()

    return jsonify(response), 200

# # will be an endpoint we can ping to try to keep our website online for quicker response times
@app.route("/get_all_wrseth_eth_suppliers/", methods=["GET"])
def get_all_kelp_dao_users():

    df = read_from_cloud_storage('kelp_dao_data.csv', 'kelp_dao')
    df = set_unique_users_no_database(df)

    eth_deposit_receipt_address = '0x9c29a8eC901DBec4fFf165cD57D4f9E03D4838f7'
    wrseth_deposit_receipt_address = '0xe3f709397e87032E61f4248f53Ee5c9a9aBb6440'
    receipt_list = [eth_deposit_receipt_address, wrseth_deposit_receipt_address]
    df = df.loc[df['token_address'].isin(receipt_list)]

    df = df[['to_address']]

    # Threads
    with ThreadPoolExecutor() as executor:
        future = executor.submit(make_nested_response, df)
    
    response = future.result()

    return jsonify(response), 200

# # processes batches of addresses
@app.route("/get_all_tvl_and_embers/", methods=["GET"])
def get_all_tvl_and_embers():
    
    df = read_from_cloud_storage('kelp_dao_data.csv', 'kelp_dao')

    response_dict = {}

    # Threads (optional)
    with ThreadPoolExecutor() as executor:
        future = executor.submit(make_df_to_dict_response, df)
        
    response = future.result()  # Append individual responses

    return jsonify(response), 200

if __name__ =='__main__':
    app.run()

# file_name = 'current_user_tvl_embers.csv'
# bucket_name = 'cooldowns2'
# minimum_block_number = 1
# maximum_block_number = 2
# wallet_address = '0x515F4055395db22C06DA6FbDD7Cac92A08a01EEa'

# eth_deposit_receipt_address = '0x9c29a8eC901DBec4fFf165cD57D4f9E03D4838f7'
# wrseth_deposit_receipt_address = '0xe3f709397e87032E61f4248f53Ee5c9a9aBb6440'

# column_list = tuple(['from_address', 'to_address', 'tx_hash', 'token_address', 'token_volume', 'timestamp', 'block_number', 'asset_price'])
# dtype_dict = {'from_address': str, 'to_address': str, 'tx_hash':str, 'token_address':str, 'token_volume': float, 'timestamp': float, 'block_number': float,'asset_price': float}

# start_time = time.time()
# df = read_from_cloud_storage_specific_columns(file_name, bucket_name, column_list, dtype_dict)
# new_time = time.time()
# print('Finished Reading in: ', str(new_time - start_time))

# start_time = time.time()
# df = get_user_eth_wrseth_at_block_number(df, wallet_address, minimum_block_number, maximum_block_number)
# new_time = time.time()
# print('Finished Making Blocks in: ', str(new_time - start_time))

# print(df.loc[df['token_address'] == eth_deposit_receipt_address])

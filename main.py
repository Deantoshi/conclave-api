import pandas as pd
from lending_pool import lp_tracker
from lending_pool import balance_and_points as bp
from sql_interfacer import sql
# from cloud_storage import cloud_storage as cs
import sqlite3

connection = sqlite3.connect("turtle.db")

cursor = connection.cursor()

# sql.make_table(cursor, 'aurelius_lending_pool')

rows = sql.select_star(cursor, 'aurelius_lending_pool')

print(rows)

# index_list = [0]

# for index in index_list:
#     lp_tracker.find_all_lp_transactions(index)
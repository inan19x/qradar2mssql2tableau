#!/usr/bin/env python3

# @author Futuhal Arifin Annasri - IBM Security
# This script will process CSV data from file located at 'csv4tableau' folder to MSSQL database.
# The raw log will be stored at DB named QRadarLogs

import sys
import os
import csv
import pyodbc
import time
from datetime import datetime

def main():
	connection = get_mssql_connection()

	path = os.path.realpath('csv4tableau')

	log_files = []
	log_report = []

	for r, d, f in os.walk(path):
		for file in f:
			if '.csv' in file:
				log_files.append(file)

	for file in log_files:
		table_metadata = examine_csv_file(path, file)
		if table_metadata['error'] == 'No':
			create_mssql_table(connection, table_metadata)
			insert_table(connection, table_metadata)

			if table_metadata['application']:
				join_table(connection, table_metadata)

			log_report.append("{0} - Success importing log {1} to Database.".format(datetime.strftime(datetime.now(), 
				'%Y-%m-%d %H:%M:%S'), file))
		else:
			print('Skip importing log from {}'.format(file))
			log_report.append("{0} - Unable importing log {1}. Maybe the file was empty or corrupt.".format(datetime.strftime(datetime.now(), 
				'%Y-%m-%d %H:%M:%S'), file))

		os.remove(os.path.join(path, file))

	record_activity_log(log_report)


def record_activity_log(record):
	file = open('CSV2SQL.log', 'a+')

	for activity in record:
		file.write(activity+'\n')
	file.close()


def create_mssql_table(connection, table_metadata):
	print('Process Table {}'.format(table_metadata['name']))
	cursor = connection.cursor()

	# Delete table if exist (will be replaced)
	query_expression = "DROP TABLE IF EXISTS {0}".format(table_metadata['name'])
	cursor.execute(query_expression)
	connection.commit()

	column_detail = []

	for n in range(len(table_metadata['header'])):
		column_detail.append('"' + table_metadata['header'][n] + '" ' + table_metadata['data_type'][n])

	query_expression = """
		CREATE TABLE {0}
		({1})
		""".format(table_metadata['name'], ', '.join(column_detail))

	cursor.setinputsizes([(pyodbc.SQL_WVARCHAR, 0, 0)])	
	print(query_expression)
	
	retry_flag = True
	retry_count = 0
	cursor.execute(query_expression)
	connection.commit()


def insert_table(connection, table_metadata):

	print('Process Table {}'.format(table_metadata['name']))
	cursor = connection.cursor()

	query_expression = "TRUNCATE TABLE {}".format(table_metadata['name'])
	cursor.execute(query_expression)
	connection.commit()

	cursor.fast_executemany = True  # new in pyodbc 4.0.19

	query_expression = """INSERT INTO {0} ({1}) VALUES ({2})""".format(table_metadata['name'],
		', '.join([f'"{i}"' for i in table_metadata['header']]).replace('"None"', 'NULL'),
		', '.join(['?' for i in range(len(table_metadata['header']))]))

	params = table_metadata['data']
	cursor.executemany(query_expression, params)
	connection.commit()

	print("Completed process Table {}!".format(table_metadata['name']))


def join_table(connection, table_metadata):
	cursor = connection.cursor()

	if 'Source IP' in table_metadata['header']:
		join_column = 'Source IP'
	else:
		join_column = 'Destination IP'

	query_expression = "DROP TABLE IF EXISTS #TEMP"
	cursor.execute(query_expression)
	connection.commit()

	query_expression = "DROP TABLE IF EXISTS {0}".format(table_metadata['name'])
	cursor.execute(query_expression)
	connection.commit()

	query_expression = """
		SELECT *
		INTO [QRadarLogs].[dbo].{0}
		FROM #TEMP
		""".format(table_metadata['name'])
	cursor.execute(query_expression)
	connection.commit()	

	query_expression = "DROP TABLE IF EXISTS #TEMP"
	cursor.execute(query_expression)
	connection.commit()


def get_mssql_connection():
	connection = pyodbc.connect('driver={ODBC Driver 17 for SQL Server};server=DBHOST;database=DBNAME;uid=DBUSER;pwd=DBPASSW;ColumnEncryption=Enabled;') #Hardcoded

	return connection


def examine_csv_file(path, filename): 
	table_metadata = {}

	try:
		with open(os.path.join(path, filename)) as csvfile:
			readCSV = csv.reader(csvfile, delimiter=',')
			is_header = True
			data = []
			for row in readCSV:
				if is_header:
					table_metadata['header'] = row
					is_header = False
					continue

				data.append(row)

			table_metadata['data'] = data
			table_metadata['data_type']	= lookup_the_data_type(table_metadata)
			table_metadata['name'] = filename.replace('.csv', '')
			table_metadata['error'] = 'No'
			table_metadata['application'] = False

			if 'Source IP' in table_metadata['header'] or 'Destination IP' in table_metadata['header']:
				table_metadata['application'] = True 

	except Exception as e:
		print('Reading file error or maybe log is empty. skip...')
		print(e)
		table_metadata['error'] = 'Yes'

	return table_metadata


def lookup_the_data_type(table_metadata):

	info_of_max_num_char = [0]*len(table_metadata['header'])

	for data in table_metadata['data']:
		for n in range(len(data)):
			if len(data[n]) > info_of_max_num_char[n]:
				info_of_max_num_char[n] = len(data[n])

	data_type = [None]*len(table_metadata['header'])
	for counter in range(len(table_metadata['header'])):
		if 'QID' in table_metadata['header'][counter]: 
			data_type[counter] = 'int'
		elif 'Datetime' in table_metadata['header'][counter]:
			data_type[counter] = 'datetime'
		elif table_metadata['data'][0][counter].count('.') == 1 and table_metadata['data'][0][counter].replace('.','').isnumeric():
			data_type[counter] = 'float'
		elif not table_metadata['data'][0][counter].isnumeric() and info_of_max_num_char[counter] < 200:
			data_type[counter] = 'varchar({})'.format(info_of_max_num_char[counter])
		else:
			data_type[counter] = 'varchar(max)'

	return data_type


if __name__ == "__main__":
	main()
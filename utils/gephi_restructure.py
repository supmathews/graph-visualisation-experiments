import sys
import os
from typing import List, Tuple, Dict, Optional
import logging

import boto3
import psycopg2
from psycopg2.extensions import connection

import pandas as pd


# PostgreSQL config
ConfigDict = Dict[str, str]

def get_db_tables(conn: connection) -> List[str]:
    sql_query = """
    SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public';
    """
    try:
        with conn.cursor() as curr:
            curr.execute(sql_query)
            result = curr.fetchall()

            table_names = [row[0]  for row in result]

            return table_names
    except psycopg2.Error as err:
        print(f'Error fetching the data from the PostgreSQL database: {err}')
        return None


def get_db_version(conn: connection)-> List[str]:
        sql_query = "SELECT version();"
        try:
            with conn.cursor() as curr:
                curr.execute(sql_query)
                result = curr.fetchone()

                return result[0]
        except psycopg2.Error as err:
            print(f'Error fetching the data from the PostgreSQL database: {err}')
            return None


def db_connect(db_params: ConfigDict) -> Optional[connection]:
    '''
    Establish a connection to the PostgreSQL db.
    '''
    try:
        conn: connection = psycopg2.connect(
            host=db_params['ENDPOINT'], 
            port=db_params['PORT'], 
            database=db_params['DBNAME'], 
            user=db_params['USER'], 
            password=db_params['PASSWORD'])
        
        print('Database connection established.')
        return conn
    
    except psycopg2.Error as err:
        print(f'Error connecting to the PostgreSQL database: {err}')
        return None


def db_pull(conn: connection) -> Optional[pd.DataFrame]:
    '''
    Pull the data from the database.
    '''

    # TODO: Need to add where clause to fetch new records
    sql_query: str = """
            SELECT
                s.name as SubTopic,
                t.name as Topic,
                m.name as MacroTopic
            FROM
                qnaSubtopic s
            JOIN
                Topic t ON s.topicid = t.id
            JOIN
                Macrotopic m ON t.macrotopicid = m.id
            WHERE
                s.Status = 0 AND t.Status = 0 AND m.Status = 0;
        """

    try:
        with conn.cursor() as cur:
            cur.execute(sql_query)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            data = [dict(zip(columns, row)) for row in rows]
            df: pd.DataFrame = pd.DataFrame(data)
            if df.shape[0] > 0:
                print('Data fetched successfully.')
            else:
                print('No data in the table.')
            return df
    except psycopg2.Error as err:
        print(f'Error fetching the data from the PostgreSQL database: {err}')
        return None
    
    
def print_results(results: List[Tuple]) -> None:
    '''
    Log the results fetched from the database.
    '''
    for row in results:
        logging.info(f"Row: {row}")


def db_push(conn: connection, df_nodes: pd.DataFrame, df_edges: pd.DataFrame) -> bool:
    '''
    Push nodes and edges DataFrames to the GephiNode and GephiEdges tables in the database.
    '''
    try:
        with conn.cursor() as cur:
            # Push nodes to GephiNode table
            for _, row in df_nodes.iterrows():
                cur.execute("INSERT INTO GephiNode (nodeLabel) VALUES (%s);", (row['nodeLabel'],))

            # Push edges to GephiEdges table
            for _, row in df_edges.iterrows():
                cur.execute("INSERT INTO GephiEdges (source, target, type) VALUES (%s, %s);", (row['Source'], row['Target'] ,row['Type']))

            # Commit the changes
            conn.commit()

            logging.info('Data pushed successfully.')
            return True
    except psycopg2.Error as err:
        logging.error(f'Error pushing data to the database: {err}')
        return False


def db_rollback(conn: connection):
    try:
        conn.rollback()
    except psycopg2.Error as err:
        print(f'Error rolling back PostgreSQL database: {err}')
 

def gephi_restructure(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    '''
    Restructure the data for Gephi and return nodes and edges DataFrames.
    '''
    # Create a unique set of nodes from topics, subtopics, and macrotopics
    unique_nodes = set(df['SubTopic']) | set(df['Topic']) | set(df['MacroTopic'])

    # Create a DataFrame for nodes
    nodes_df = pd.DataFrame(list(unique_nodes), columns=['nodeLabel'])

    # Create a DataFrame for edges
    edges_df = pd.DataFrame(columns=['Source', 'Target', 'Type'])

    # Iterate through the DataFrame to create edges
    for index, row in df.iterrows():
        source_node = row['MacroTopic']
        target_node = row['Topic']
        edges_df = edges_df.append({'Source': source_node, 'Target': target_node, 'Type': 'undirected'}, ignore_index=True)

        source_node = row['Topic']
        target_node = row['SubTopic']
        edges_df = edges_df.append({'Source': source_node, 'Target': target_node, 'Type': 'undirected'}, ignore_index=True)

    return nodes_df, edges_df

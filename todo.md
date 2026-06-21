### create database to store stocks data (stocks.db)

data_fetcher.py at src folder is a good reference for you to download the data from internet. you have to make change because current version is to export csv file. you have to create database (sqlite database) and then save the result to the database instead of csv file.
        CREATE TABLE data (
            stock  TEXT,
            DT     INT,
            Date   TEXT,
            Open   REAL,
            Close  REAL,
            High   REAL,
            Low    REAL,
            Volume REAL,
            PRIMARY KEY(DT, stock)
        );


### Analysis on this project
study all files at folder docs and then write a implementation plan for this project. let you have any question, please feel free to ask.
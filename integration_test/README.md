A sample project to test rqworker and site interraction

## Prerequisites

Install PostgreSQL

    sudo apt-get install postgresql

Create user and database

    sudo -u postgres psql
    # drop database djangorqdb;
    # drop user djangorqusr;
    # create user djangorqusr with createrole superuser password 'djangorqusr';
    # create database djangorqdb owner djangorqusr;

Init database schema

    ./manage.py migrate

Install required packages:

    pip install -r requirements.txt

## Test

To run tests:

    python _test.py

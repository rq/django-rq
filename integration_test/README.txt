# ############################################################################
# PostgreSQL
# ############################################################################

# Install PostgreSQL

# Create user and database
sudo -u postgres psql
drop database djangorqdb;
drop user djangorqusr;
create user djangorqusr with createrole superuser password 'djangorqusr';
create database djangorqdb owner djangorqusr;

# Init schema
./manage.py migrate

#!/usr/bin/env bash
set -o errexit
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
# Starts the Django development server to run the application locally
# This allows developers to test the application during development before deployment
# The server runs on the default address (typically http://127.0.0.1:8000/)
# python manage.py runserver




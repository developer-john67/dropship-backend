#!/bin/bash
set -e

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Creating media directory..."
mkdir -p /opt/render/project/src/media
mkdir -p /opt/render/project/src/media/products

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Build complete!"
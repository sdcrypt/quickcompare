# quickcompare

# RUN THIS to clean DB table
docker compose exec db psql -U postgres quickcompare -c "DELETE FROM products;"

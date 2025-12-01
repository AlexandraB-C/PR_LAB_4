build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

test:
	python3 integration_test.py

perf:
	python3 performance_analysis.py

clean:
	docker-compose down -v --remove-orphans
	docker system prune -f

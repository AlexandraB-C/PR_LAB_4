build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

check:
	python3 verify_setup.py

quick:
	./quick_test.sh

basic:
	python3 test_basic.py

test:
	python3 integration_test.py

perf:
	python3 performance_analysis.py

clean:
	docker-compose down -v --remove-orphans
	docker system prune -f

.PHONY: build up down check quick basic test perf clean

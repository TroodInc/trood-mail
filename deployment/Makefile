default: run

build:
	@docker-compose build

test:
	@docker-compose exec mail pytest

run: build
	@docker-compose up -d

down:
	@docker-compose down

.PHONY: run default build test down

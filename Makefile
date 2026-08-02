.PHONY: dev dev-api dev-web setup db-upgrade test test-api test-web

setup:
	conda env update -n read-books -f environment.yml --prune
	npm --prefix apps/web install
	$(MAKE) db-upgrade

db-upgrade:
	conda run -n read-books alembic -c apps/api/alembic.ini upgrade head

dev:
	@trap 'kill 0' INT TERM EXIT; \
	conda run --no-capture-output -n read-books uvicorn app.main:app --reload --app-dir apps/api --host 127.0.0.1 --port 8000 & \
	npm --prefix apps/web run dev & \
	wait

dev-api:
	conda run --no-capture-output -n read-books uvicorn app.main:app --reload --app-dir apps/api --host 127.0.0.1 --port 8000

dev-web:
	npm --prefix apps/web run dev

test: test-api test-web

test-api:
	conda run -n read-books pytest apps/api/tests

test-web:
	npm --prefix apps/web run lint

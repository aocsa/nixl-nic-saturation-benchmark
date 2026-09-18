.PHONY: probe install run control workers score

control:
	./scripts/start-control-plane.sh

run:
	./run.sh inventory.env

probe:
	./scripts/probe-net.sh

install:
	./scripts/install-deps.sh

score:
	python3 scripts/score.py

kill-stale:
	./scripts/kill-stale.sh

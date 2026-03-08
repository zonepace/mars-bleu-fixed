gen: install
	uv run python3 scrape.py

genpush: gen push

push:
	./run-and-tail-workflow.sh


install:
	uv sync

serve:
	@python3 -mhttp.server 6302 --directory html

.PHONY: gen install serve push

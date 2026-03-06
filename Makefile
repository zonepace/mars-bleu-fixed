gen: install
	uv run python3 scrape.py

install:
	uv sync

serve:
	@python3 -mhttp.server 6302

.PHONY: gen install serve

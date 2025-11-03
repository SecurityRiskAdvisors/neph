# https://python-poetry.org/docs/cli/#version
# 	major	1.3.0	2.0.0
# 	minor	2.1.4	2.2.0
# 	patch	4.1.1	4.1.2
bumprule="patch"

format:
	poetry run black -l 120 neph/ test/

dependencies:
	poetry install --all-extras --quiet --no-root --with dev

.PHONY: dist
dist:
	mkdir -p dist
	rm dist/* || true
	poetry version $(bumprule)
	poetry build -f wheel

git:
	$(eval branch := $(shell git branch --show-current))
	git add .
	git commit -a -m "$(message)"
	git push origin $(branch)

push: format dist git

dl_policies:
	curl -fSsL "https://github.com/iann0036/iam-dataset/archive/refs/heads/master.zip" -o "neph/data/policies.zip"

.PHONY: test
test:
	python -m unittest -v

.PHONY: autodocs
autodocs:
	rm -r autodocs/ || true
	rm autodocs/neph*.rst || true
	sphinx-apidoc -o autodocs/ -d 3 --full neph/
	cp sphinx_config.py autodocs/conf.py
	PYTHONPATH=$PYTHONPATH:$(CURDIR) $(MAKE) -C autodocs/ html

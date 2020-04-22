# Evan Widloski - 2019-03-04
# makefile for building

.PHONY: dist
dist:
	python setup.py sdist bdist_wheel

.PHONY: pypi
pypi: dist
	twine upload dist/*

.PHONY: clean
clean:
	rm dist/*

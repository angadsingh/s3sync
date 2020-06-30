#!/bin/bash

#python3 -m pip install --user --upgrade setuptools wheel
#python3 -m pip install --user --upgrade twine

rm -rf dist/*
python3 setup.py sdist bdist_wheel
#python3 -m twine upload --repository testpypi dist/*
python3 -m twine upload dist/*
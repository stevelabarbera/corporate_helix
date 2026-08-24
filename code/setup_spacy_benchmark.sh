#!/usr/bin/env bash
set -e
python3 -m pip install -U "spacy>=3.8,<4"
python3 -m spacy download en_core_web_sm
echo "spaCy benchmark backend ready."

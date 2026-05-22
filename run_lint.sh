#!/bin/bash
uv run ruff format .
uv run ruff check --fix .

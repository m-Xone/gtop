# gtop build / install
#
# Override the install location with:  make install BIN_DIR=~/.local/bin

UNAME := $(shell uname -s)
ifeq ($(UNAME),Linux)
	SYSTEM := linux
else ifeq ($(UNAME),Darwin)
	SYSTEM := macos
else
	# The PyInstaller path is Linux/macOS only. Windows is supported through
	# the package install instead, which pulls in windows-curses.
	$(error Unsupported platform for "make": $(UNAME). Install with: pip install .)
endif

PYTHON        ?= python3
VENV          := .venv
VENV_BIN      := $(VENV)/bin
BIN_DIR       ?= /usr/local/bin

.PHONY: all build install uninstall clean dev test lint typecheck check check-env

all: build install

# ---------------------------------------------------------------------------
# Build / install
# ---------------------------------------------------------------------------

build: check-env
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install pyinstaller .
	$(VENV_BIN)/pyinstaller --onefile main.py -n gtop

install: build
	@read -p "Installing to $(BIN_DIR)/gtop. Proceed? [y/N] " yn; \
	case $$yn in \
		[Yy]* ) install -m 0755 dist/gtop $(BIN_DIR)/gtop && echo "Installed $(BIN_DIR)/gtop";; \
		* ) echo "Installation canceled.";; \
	esac

uninstall:
	@read -p "Uninstall $(BIN_DIR)/gtop. Proceed? [y/N] " yn; \
	case $$yn in \
		[Yy]* ) rm -f $(BIN_DIR)/gtop && $(MAKE) clean && echo "Uninstalled.";; \
		* ) echo "Uninstall canceled.";; \
	esac

clean:
	rm -rf dist build *.spec .pytest_cache .mypy_cache .ruff_cache

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

dev:
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip
	$(VENV_BIN)/pip install -e '.[dev]'

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy gtop tests

check: lint typecheck test

# ---------------------------------------------------------------------------
# Environment verification
#
# gtop reads CPU stats through psutil and GPU stats through nvidia-smi, so
# there are no distro packages to install beyond a working Python. nvidia-smi
# ships with the NVIDIA driver; its absence is a warning, not a build failure.
# ---------------------------------------------------------------------------

check-env:
	@echo "------------ ENV VERIFICATION ------------"
	@command -v $(PYTHON) >/dev/null 2>&1 \
		|| { echo "ERROR: $(PYTHON) not found on PATH"; exit 1; }
	@echo "$(PYTHON) - PASS ($$($(PYTHON) --version 2>&1))"
	@$(PYTHON) -c 'import curses' 2>/dev/null \
		|| { echo "ERROR: python curses module unavailable"; exit 1; }
	@echo "curses - PASS"
	@command -v nvidia-smi >/dev/null 2>&1 \
		&& echo "nvidia-smi - PASS" \
		|| echo "WARNING: nvidia-smi not found; gtop needs it at runtime."
	@echo "------------------------------------------"

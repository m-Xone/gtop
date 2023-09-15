# Determine the user's platform (Linux, macOS, or WSL)
UNAME := $(shell uname -s)
ifeq ($(UNAME),Linux)
	SYSTEM := linux
else ifeq ($(UNAME),Darwin)
	SYSTEM := macos
else
	$(error Unsupported platform: $(UNAME))
endif

# Define commands and paths based on the system
ifeq ($(SYSTEM),linux)
	VENV_ACTIVATE = . .venv/bin/activate
	CP_CMD = cp
	RM_CMD = rm -rf
	BIN_DIR = /usr/local/bin
else ifeq ($(SYSTEM),macos)
	VENV_ACTIVATE = . .venv/bin/activate
	CP_CMD = cp
	RM_CMD = rm -rf
	BIN_DIR = /usr/local/bin
endif

# Targets
all: build install

build:
	python3 -m venv .venv && \
	$(VENV_ACTIVATE) && \
	pip install pyinstaller psutil && \
	pyinstaller --onefile gtop.py -n gtop

install: build
	@read -p "Installing to $(BIN_DIR)/gtop. Proceed? [y/N] " yn; \
	case $$yn in \
		[Yy]* ) sudo $(CP_CMD) dist/gtop $(BIN_DIR)/gtop;; \
		* ) echo "Installation canceled.";; \
	esac

uninstall:
	$(RM_CMD) dist build *.spec
	$(RM_CMD) $(BIN_DIR)/gtop

clean:
	$(RM_CMD) dist build *.spec

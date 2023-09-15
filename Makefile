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

build: ENV_VERIFICATION
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
	@read -p "Uninstall $(BIN_DIR)/gtop. Proceed? [y/N] " yn; \
	case $$yn in \
		[Yy]* ) sudo $(RM_CMD) dist build *.spec $(BIN_DIR)/gtop;; \
		* ) echo "Uninstall canceled.";; \
	esac

clean:
	$(RM_CMD) dist build *.spec

ENV_VERIFICATION:
	@echo ------------START ENV VERIFICATION--------------- 
	@if ! dpkg -s sudo | grep Status | grep -q installed; then \
	  	@echo ERROR: sudo is not installed!; \
	  	@exit 1; \
	else \
		echo "sudo installed - PASS"; \
	fi
	@if ! dpkg -s sysstat | grep Status | grep -q installed; then \
	  	@echo WARNING: sysstat package not installed. CPU usage will not be available without sysstat.; \
	  	@read -p "Install sysstat? [y/N] " yn; \
	  		case $$yn in \
			[Yy]* ) sudo apt install -y sysstat;; \
			* ) echo "Skipping sysstat installation. CPU usage will not be available in gtop.";; \
			esac \
	else \
		echo "sysstat installed - PASS"; \
	fi
	@echo ------------END ENV VERIFICATION---------------

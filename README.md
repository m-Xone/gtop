# gtop

A curses-based terminal monitor for NVIDIA GPUs and host CPUs, with colored
progress bars for utilization, memory, power, temperature, and fan speed, plus
a table of the processes resident on each device.

![Screenshot from 2023-09-15 15-18-23](https://github.com/m-Xone/gtop/assets/19239090/b7f0b699-61fb-4280-a232-f31d0e418096)

## Requirements

- Python 3.9 or newer
- An NVIDIA driver providing `nvidia-smi` on your `PATH` (all GPU telemetry)

CPU statistics come from [psutil](https://github.com/giampaolo/psutil), which is
installed automatically. No distro packages beyond Python are required.

Linux and Windows are both supported. On Windows, `pip` additionally installs
[windows-curses](https://pypi.org/project/windows-curses/), because CPython
ships no `curses` module there.

> Earlier versions shelled out to `mpstat` and needed the `sysstat` package.
> That dependency is gone — if you installed `sysstat` only for `gtop`, you can
> remove it.

## Installation

### As a Python package

```sh
git clone https://github.com/m-Xone/gtop.git
cd gtop
pip install .
```

This puts a `gtop` command on your `PATH`.

### As a standalone binary

The Makefile builds a self-contained executable with PyInstaller and installs
it to `/usr/local/bin`:

```sh
git clone https://github.com/m-Xone/gtop.git
cd gtop
make install
```

Override the destination with `make install BIN_DIR=~/.local/bin`.

To update an existing install, `make uninstall && make install`.

The Makefile targets are Linux/macOS only. On Windows, use the package install
above.

### Windows notes

`pip install .` pulls in `windows-curses` automatically, and `nvidia-smi` is
found on `PATH` like any other platform. Two behaviors differ:

- Windows consoles do not deliver a resize event as reliably as a Unix
  terminal. The layout still adapts, but on the next refresh rather than
  instantly — lower `-l` if you want it to keep up more closely.
- PDCurses (which `windows-curses` wraps) cannot inherit the terminal's
  background color, so `gtop` falls back to an explicit black background
  rather than losing color entirely.

Use [Windows Terminal](https://aka.ms/terminal) if you can. The bars and rules
use box-drawing characters, which a legacy code page cannot represent; on those
consoles `gtop` automatically substitutes `#` and `-` rather than failing, and
`-f` lets you pick an ASCII fill explicitly.

## Usage

```
usage: gtop [-h] [-l INTERVAL] [-i DEVICE] [-v] [-g] [-f {█,*,|,=,o,.,+}]

options:
  -h, --help            show this help message and exit
  -l INTERVAL, --loop INTERVAL
                        refresh interval (s)
  -i DEVICE, --index DEVICE
                        display status of a single device (e.g. 'gtop -i 0')
  -v, --verbose         display full process names, including command line
                        arguments (may require elevated privileges)
  -g, --gpu-only        only display GPU stat bars (suppress CPU stat bars)
  -f {█,*,|,=,o,.,+}, --fill-char {█,*,|,=,o,.,+}
                        fill char for GPU/CPU status bars
```

### Keyboard controls

| Key | Action |
| --- | --- |
| `q`, `Q` | quit |
| `↑` / `↓`, `k` / `j` | scroll one line |
| `PgUp` / `PgDn` | scroll one page |
| `Home` / `End` | jump to top / bottom |
| `←` / `→`, `h` / `l` | scroll horizontally |

The display re-lays out when the terminal is resized, and content taller or
wider than the window can be scrolled rather than being clipped.

### Examples

Display usage for device 0, updating every 2 seconds, GPU bars only:

```sh
gtop -i 0 -l 2 -g
```

Display all connected devices with full process command lines:

```sh
gtop -v
```

## Compatibility

`gtop` was tested on:

1. Ubuntu 22.04 LTS with a single NVIDIA 4080 GPU
2. Ubuntu 22.04 LTS with two NVIDIA 4090 GPUs
3. Ubuntu 22.04 LTS with one legacy NVIDIA 5400M integrated GPU

Depending on your hardware, driver, and `nvidia-smi` version, some fields may be
unavailable and will render as `[data not available]` in place of a status bar.
Process information is likewise unavailable on some older hardware.

`nvidia-smi`'s XML schema has changed across driver releases — for example,
power readings live under `<gpu_power_readings>` on recent drivers and
`<power_readings>` on older ones. Both are handled. If a stat shows as
unavailable but you can see it in `nvidia-smi -q -x` output under a different
field name, please open an issue with the field name and it will be added.

## Development

```sh
make dev        # create .venv and install with dev dependencies
make test       # pytest
make lint       # ruff check + ruff format --check
make typecheck  # mypy
make check      # all of the above
```

### Layout

| Module | Responsibility |
| --- | --- |
| `gtop/collectors.py` | Data acquisition: psutil and `nvidia-smi`. No formatting. |
| `gtop/widgets.py` | Output-agnostic primitives. Emits `Segment`/`Line` data, no escape codes. |
| `gtop/views.py` | Panel layout: turns collector output into lines of segments. |
| `gtop/render.py` | Curses renderer: color pairs, pad-backed scrollable viewport. |
| `gtop/cli.py` | Argument parsing and the render loop. |

Widgets emit semantic colors rather than escape sequences, so the view layer is
testable without a terminal and an alternative renderer can be added without
touching layout code.

## License

GNU GPL — fork, clone, and modify as much as you want.

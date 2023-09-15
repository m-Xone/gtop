# gtop

Simple wrapper for nvidia-smi that offers improved visuals for better GPU resource awareness

![Screenshot from 2023-09-15 15-18-23](https://github.com/m-Xone/gtop/assets/19239090/b7f0b699-61fb-4280-a232-f31d0e418096)


## Installation

#### Prerequisites

Debian-based systems

    sudo apt update && sudo apt install sysstat build-essential python3-pip python3-dev python3-venv

`gtop` is conveniently installed to `/usr/local/bin/gtop` via the use of PyInstaller. You can edit the Makefile to change this.

    git clone https://github.com/m-Xone/gtop.git
    cd gtop
    make install

#### Updates

    git clone https://github.com/m-Xone/gtop.git
    cd gtop
    make uninstall
    make install

## Compatibility

`gtop` was tested on three systems:
    
1. a Linux system running Ubuntu 22.04 LTS with a single NVIDIA 4080 GPU.
2. a Linux system running Ubuntu 22.04 LTS with two NVIDIA 4090 GPUs.
4. a Linux system running Ubuntu 22.04 LTS with one legacy NVIDIA 5400M integrated GPU.

Depending on your hardware, installed NVIDIA drivers, and `nvidia-smi` version, some status fields may not be available. These will display as `[data not available]` in place of a status bar. Additionally, for older hardware, process information may not be available. That said, it is very possible that I have not captured all variants of the XML field names from `nvidia-smi -q -x` output. If you come across a missing stat while running `gtop` locally and are able to confirm that the stat data is available under a different field name when running `nvidia-smi -q -x`, please open an Issue and I will add it.

## Usage

The `loop` and `i` options mirror those of `nvidia-smi`:

    usage: gtop [-h] [-l INTERVAL] [-i DEVICE] [-v] [-g] [-f {*,|,=,o,.,+}]

    options:
      -h, --help            show this help message and exit
      -l INTERVAL, --loop INTERVAL
                            refresh interval (s)
      -i DEVICE, --index DEVICE
                            display status of a single device (e.g., 'gtop -i 0')
      -v, --verbose         display full process names, including command line arguments (may require elevated privileges)
      -g, --gpu-only        only display GPU stat bars (suppress CPU stat bars)
      -f {*,|,=,o,.,+}, --fill-char {*,|,=,o,.,+}
                            fill char for GPU/CPU status bars

      

## Examples

Display usage for device 0; update every 2 seconds; only display GPU statistics

    gtop -i 0 -l 2 -g

Display usage for all connected devices; show verbose process names
  
    gtop -v

## License

GNU GPL - fork, clone, modify as much as you want. This code was built to solve a simple issue and is thus simple in nature.

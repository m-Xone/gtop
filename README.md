# gtop
Simple wrapper for nvidia-smi that offers improved visuals for better GPU resource awareness

![example](https://github.com/m-Xone/gtop/assets/19239090/528b4bfb-13dd-4038-886f-09197c319f9b)


## Installation

`gtop` is conveniently installed to `/usr/local/bin/gtop` via the use of PyInstaller. You can edit the Makefile to change this.

    git clone https://github.com/m-Xone/gtop
    make build

## Compatibility

`gtop` was tested on a Linux system running Ubuntu 22.04 LTS with a single NVIDIA GPU. It _should_ run without modification on WSL and Darwin systems.

## Usage

The `loop` and `i` options mirror those of `nvidia-smi`:

    usage: gtop [-h] [-l INTERVAL] [-i DEVICE] [-n]

    options:
      -h, --help            show this help message and exit
      -l INTERVAL, --loop INTERVAL
                            refresh interval (s)
      -i DEVICE, --index DEVICE
                            display status of a specific device (e.g., 'gtop -i 0')
      -n, --name-only       display process names without their cmdline arguments (less verbose)

## Examples

Display usage for device 0; update every 2 seconds

    gtop -i 0 -l 2

Display usage for all connected devices; show process names only (no command line arguments)
  
    gtop -n

## License

GNU GPL - fork, clone, modify as much as you want. This code was built to solve a simple issue and is thus simple in nature.

import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from argparse import ArgumentParser
from typing import Sequence
from xml.etree.ElementTree import Element

import psutil

process = None


class DeviceNotFoundError(Exception):
    ...


def signal_handler(signum, frame):
    global process
    if process:
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    print("exit")
    os._exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def clear_screen():
    sys.stdout.write("\033[H")  # Move cursor to the top left
    sys.stdout.write("\033[J")  # Clear from cursor to end of screen


def pid_to_procname(pid: int) -> str:
    try:
        pid = int(pid) if not isinstance(pid, int) else pid
        p = psutil.Process(pid)
        with p.oneshot():
            cmdline = p.cmdline()
            exe = p.exe()
            nm = p.name()
        if cmdline:
            return " ".join(cmdline)
        elif exe:
            return exe
        elif nm:
            return nm
        else:
            raise psutil.NoSuchProcess
    except psutil.AccessDenied:
        return "Permission Denied"
    except Exception:
        return "unavailable"


def get_gpu_info(dev_idx: int = -1) -> None:
    global process
    try:
        args = (
            ["nvidia-smi", "-q", "-x", "-i", f"{dev_idx}"]
            if dev_idx >= 0
            else ["nvidia-smi", "-q", "-x"]
        )
        process = subprocess.Popen(
            args,
            text=True,
            close_fds=True,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result, _ = process.communicate()
        if process.returncode == 0:
            root = ET.fromstring(result)
            return root
        elif process.returncode == 6:
            raise DeviceNotFoundError("device not found")
        else:
            return None
    except FileNotFoundError:
        print("nvidia-smi not detected")
        raise RuntimeError("problem encountered; exiting")
    except subprocess.TimeoutExpired:
        print("nvidia-smi command timed out")
        return None
    except InterruptedError:
        return None
    except DeviceNotFoundError as e:
        print(str(e))
        return None


def render_titled_progress_bar(
    pct: float,
    title: str,
    bar_length: int = 60,
    # fill_char: str = "█",
    fill_char: str = "|",
    empty_char: str = " ",
    unit: str = "",
    thresh: Sequence = [0.5, 0.9],
    epilogue: str = "",
) -> None:
    # Define ANSI escape codes for text color
    colors = {
        "green": "\033[92m",  # Green text color
        "red": "\033[91m",  # Red text color
        "blue": "\033[94m",  # Blue text color
        "yellow": "\033[93m",  # Yellow text color
        "reset": "\033[0m",  # Reset text color to default
    }
    # progress
    pct = pct / 100.0 if isinstance(pct, int) else pct
    progress = int(pct * bar_length)

    # create the bar
    fill = min(
        bar_length - 3, progress
    )  # shorten progress bar to make space for text (if necessary)
    empty = bar_length - progress - 3
    bar = "["
    if pct > thresh[1]:
        bar += colors["red"]
    elif pct > thresh[0]:
        bar += colors["yellow"]
    else:
        bar += colors["green"]
    bar += str(fill_char[:1]) * fill
    bar += str.ljust(f"{pct*100:.0f}", 3)
    bar += colors["reset"]
    bar += empty_char * empty + "]"

    # display bar
    print(
        f"{str.ljust(f'{title[:16]} {unit}',16)} {bar} {epilogue[:min(len(epilogue),20)]}"
    )


def render_gpu_memory(gpu: Element) -> None:
    try:
        total_memory = int(gpu.find("fb_memory_usage").find("total").text.split()[0])
        used_memory = int(gpu.find("fb_memory_usage").find("used").text.split()[0])
        reserved_memory = int(
            gpu.find("fb_memory_usage").find("reserved").text.split()[0]
        )
        memory_usage_percentage = (used_memory + reserved_memory) / total_memory
        render_titled_progress_bar(
            title="Memory Usage",
            pct=memory_usage_percentage,
            unit="%",
            epilogue=f"{used_memory+reserved_memory} MiB/{total_memory} MiB",
        )
    except Exception:
        print("Memory Usage [data not available]")


def render_gpu_utilization(gpu: Element) -> None:
    try:
        utilization_gpu = int(gpu.find("utilization").find("gpu_util").text.rstrip("%"))
        render_titled_progress_bar(
            title="Utilization ", pct=max(0, min(utilization_gpu, 100)), unit="%"
        )
    except Exception:
        print("Utilization  [data not available]")


def render_gpu_power(gpu: Element) -> None:
    try:
        power_draw = float(
            gpu.find("gpu_power_readings").find("power_draw").text.split()[0]
        )
        power_limit = float(
            gpu.find("gpu_power_readings").find("current_power_limit").text.split()[0]
        )
        power_usage_percentage = power_draw / power_limit
        render_titled_progress_bar(
            title="Power Usage ",
            pct=power_usage_percentage,
            unit="%",
            epilogue=f"{power_draw} W/{power_limit} W",
        )
    except Exception:
        print("Power Usage  [data not available]")


def render_gpu_temperature(gpu: Element) -> None:
    try:
        temp = int(gpu.find("temperature").find("gpu_temp").text.split()[0])
        scale = gpu.find("temperature").find("gpu_temp").text.split()[1]
        temp_scale = 100 if scale == "C" else 212
        temp_pct = temp / temp_scale
        render_titled_progress_bar(
            title="Temperature ",
            pct=temp_pct,
            thresh=[0.6, 0.7],
            unit=scale,
            epilogue=f"{temp} {scale}",
        )
    except Exception:
        print("Temperature  [data not available]")


def render_gpu_metadata(gpu: Element) -> None:
    try:
        gpu_id = gpu.find("minor_number").text
        gpu_name = gpu.find("product_name").text
        try:
            gpu_arch = "(" + gpu.find("product_architecture").text + ")"
        except Exception:
            gpu_arch = ""
        print(f"GPU {gpu_id}: {gpu_name} {gpu_arch}")
    except Exception:
        gpu_id = gpu.find("minor_number").text
        print(f"GPU {gpu_id}")


def render_gpu_data(gpu_info: Element) -> None:
    for gpu in gpu_info.findall(".//gpu"):
        render_gpu_metadata(gpu)
        render_gpu_utilization(gpu)
        render_gpu_memory(gpu)
        render_gpu_power(gpu)
        render_gpu_temperature(gpu)
        print()


def pretty_print(seq: Sequence, widths: Sequence) -> None:
    for itm, w in zip(seq, widths):
        print(f"{str.ljust(itm,w)}  ", end="")
    print()


def render_process_data(gpu_info: Element, simple_names: bool = False) -> None:
    name_width = 50
    widths = [6, 10, name_width, 11]

    for gpu in gpu_info.findall(".//gpu"):
        gpu_id = gpu.find("minor_number").text
        reserved_memory = gpu.find("fb_memory_usage").find("reserved").text
        pids = []
        proc_names = []
        used_memorys = []
        for i, proc in enumerate(gpu.findall("processes/process_info")):
            pids.append(proc.find("pid").text)
            if simple_names:
                proc_names.append(proc.find("process_name").text)
            else:
                proc_names.append(pid_to_procname(int(pids[i])))
            used_memorys.append(proc.find("used_memory").text)
            if len(proc_names[i]) > name_width:
                n = proc_names[i][:23]
                n += "..."
                n += proc_names[i][26:name_width]
                proc_names[i] = n
    # display
    pretty_print(["-" * 6, "-" * 10, "-" * name_width, "-" * 11], widths)
    pretty_print(["GPU ID", "Process ID", "Name", "GPU Mem"], widths)
    pretty_print(["-" * 6, "-" * 10, "-" * name_width, "-" * 11], widths)
    pretty_print([gpu_id, "N/A", "GPU Reserved Memory", reserved_memory], widths)
    for i in range(len(pids)):
        pretty_print([gpu_id, pids[i], proc_names[i], used_memorys[i]], widths)
    pretty_print(["-" * 6, "-" * 10, "-" * name_width, "-" * 11], widths)


def argparser():
    argparse = ArgumentParser()
    argparse.add_argument(
        "-l",
        "--loop",
        dest="interval",
        type=int,
        default=1,
        help="refresh interval (s)",
    )
    argparse.add_argument(
        "-i",
        "--index",
        dest="device",
        type=int,
        default=-1,
        help="display status of a specific device (e.g., 'gtop -i 0')",
    )
    argparse.add_argument(
        "-n",
        "--name-only",
        dest="name",
        action="store_true",
        help="display process names without their cmdline arguments (less verbose)",
    )
    return argparse.parse_args()


def main() -> None:
    args = argparser()

    try:
        while True:
            if gpu_info := get_gpu_info(args.device):
                clear_screen()
                render_gpu_data(gpu_info)
                render_process_data(gpu_info, args.name)
            else:
                raise RuntimeError("failed to process data update")
            time.sleep(args.interval)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()

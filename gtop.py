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


power_nodes = {
    "gpu_power_readings": {
        "power_draw": "power_draw",
        "power_limit": "current_power_limit",
    },
    "power_readings": {
        "power_draw": "power_draw",
        "power_limit": "power_limit",
    },
}


def signal_handler(signum, frame):
    global process
    if process:
        try:
            process.terminate()
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
    print("exit")
    os._exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def clear_screen():
    sys.stdout.write("\033[H")  # Move cursor to the top left
    sys.stdout.write("\033[J")  # Clear from cursor to end of screen


def pretty_print(seq: Sequence, widths: Sequence) -> str:
    s = ""
    for itm, w in zip(seq, widths):
        s += f"{str.ljust(itm,w)}  "
    s += "\n"
    return s


def get_all_cpu_usage() -> list[float]:
    global process
    err_msg = 'no results'
    try:
        args = ["mpstat","-P","ALL","1","1"]
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
            mpstat_out = result
        else:
            raise ValueError(err_msg)
        
        args = ["awk",'/%nice/ { for(i=1; i<=NF; ++i) if ($i==\"%idle\") print i-1; exit }']
        process = subprocess.Popen(
            args,
            text=True,
            close_fds=True,
            start_new_session=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result,_ = process.communicate(input=mpstat_out)
        if process.returncode == 0:
            col = int(result)
        else:
            raise ValueError(err_msg)

        args = ["awk",'/Average:/ && $2 ~ /[0-9]/ {print 100-$%d}' % col]
        process = subprocess.Popen(
            args,
            text=True,
            close_fds=True,
            start_new_session=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result,_ = process.communicate(input=mpstat_out)
        if process.returncode == 0:
            return result.split('\n')
        else:
            raise ValueError(err_msg)
    except Exception:
        return []

def pid_to_cpupct(pid: int) -> float:
    global process
    try:
        pid = int(pid) if not isinstance(pid, int) else pid
        args = ["ps", "-p", f"{pid}", "-o", "%cpu"]
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
            return float(result.split()[1])
        else:
            return None
    except FileNotFoundError:
        print("ps not detected")
        raise RuntimeError("problem encountered; exiting")
    except subprocess.TimeoutExpired:
        print("ps command timed out")
        return None
    except InterruptedError:
        return None


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
    fill_char: str = "█",
    # fill_char: str = "|",
    empty_char: str = " ",
    unit: str = "",
    thresh: Sequence = [0.5, 0.9],
    epilogue: str = "",
    sep = "\n",
) -> str:
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
    return f"{str.ljust(f'{title[:14]} {unit}',16)} {bar} {epilogue[:min(len(epilogue),20)]}{sep}"


def render_cpu_data() -> str:
    s = ''
    try:
        usage = [float(p) for p in get_all_cpu_usage() if p != '']
        for i,p in enumerate(usage):
            s += render_titled_progress_bar(pct = float(p)/100,
                                            title=f"CPU {i}",
                                            bar_length=30,
                                            unit='%',
                                            sep='')
            s = s + '\n' if (i+1) % 2 == 0 else s
        s += '\n'
        return s
    except Exception:
        return s
                


def render_gpu_memory(gpu: Element) -> str:
    try:
        total_memory = int(gpu.find("fb_memory_usage").find("total").text.split()[0])
        used_memory = int(gpu.find("fb_memory_usage").find("used").text.split()[0])
        reserved_memory = 0
        if gpu.find("fb_memory_usage").find("reserved") is not None:
            reserved_memory = int(
                gpu.find("fb_memory_usage").find("reserved").text.split()[0]
            )
        if total_memory <= 0:
            raise ValueError("total_memory <= 0")
        memory_usage_percentage = (used_memory + reserved_memory) / total_memory
        return render_titled_progress_bar(
            title="Memory Usage",
            pct=memory_usage_percentage,
            unit="%",
            epilogue=f"{used_memory+reserved_memory} MiB/{total_memory} MiB",
        )
    except Exception:
        return f"{str.ljust('Memory Usage',16)} [data not available]\n"


def render_gpu_utilization(gpu: Element) -> str:
    try:
        utilization_gpu = int(gpu.find("utilization").find("gpu_util").text.rstrip("%"))
        return render_titled_progress_bar(
            title="Utilization ", pct=max(0, min(utilization_gpu, 100)), unit="%"
        )
    except Exception:
        return f"{str.ljust('Utilization',16)} [data not available]\n"


def render_gpu_power(gpu: Element) -> str:
    try:
        for k in power_nodes.keys():
            if gpu.find(k) is not None:
                if (
                    power_draw := gpu.find(k).find(power_nodes[k]["power_draw"]).text
                ) == "N/A":
                    raise ValueError("unavailable")
                power_draw = float(power_draw.split()[0])
                if (
                    power_limit := gpu.find(k).find(power_nodes[k]["power_limit"]).text
                ) == "N/A":
                    raise ValueError("unavailable")
                power_limit = float(power_limit.split()[0])
                break
        if power_limit <= 0:
            raise ValueError("power_limit <= 0")
        return render_titled_progress_bar(
            title="Power Usage ",
            pct=power_draw / power_limit,
            unit="%",
            epilogue=f"{power_draw} W/{power_limit} W",
        )
    except Exception:
        return f"{str.ljust('Power Usage',16)} [data not available]\n"


def render_gpu_temperature(gpu: Element) -> str:
    try:
        temp = int(gpu.find("temperature").find("gpu_temp").text.split()[0])
        scale = gpu.find("temperature").find("gpu_temp").text.split()[1]
        temp_scale = 100 if scale == "C" else 212
        temp_pct = temp / temp_scale
        return render_titled_progress_bar(
            title="Temperature ",
            pct=temp_pct,
            thresh=[0.6, 0.7],
            unit=scale,
            epilogue=f"{temp} {scale}",
        )
    except Exception:
        return f"{str.ljust('Temperature',16)} [data not available]\n"


def render_gpu_fanspeed(gpu: Element) -> str:
    try:
        if (fanpct := gpu.find("fan_speed").text) == "N/A":
            raise ValueError("fan speed unavailable")
        fanpct = int(fanpct.split()[0])
        return render_titled_progress_bar(
            title="Fan Speed   ",
            pct=fanpct,
            thresh=[0.5, 0.75],
            unit="%",
        )
    except Exception:
        return f"{str.ljust('Fan Speed',16)} [data not available]\n"


def render_gpu_metadata(gpu: Element) -> str:
    try:
        gpu_id = gpu.find("minor_number").text
        gpu_name = gpu.find("product_name").text
        try:
            gpu_arch = "(" + gpu.find("product_architecture").text + ")\n"
        except Exception:
            gpu_arch = ""
        return f"GPU {gpu_id}: {gpu_name} {gpu_arch}"
    except Exception:
        gpu_id = gpu.find("minor_number").text
        return f"GPU {gpu_id}\n"


def render_gpu_data(gpu_info: Element) -> str:
    d = ""
    for gpu in gpu_info.findall(".//gpu"):
        d += render_gpu_metadata(gpu)
        d += render_gpu_utilization(gpu)
        d += render_gpu_memory(gpu)
        d += render_gpu_power(gpu)
        d += render_gpu_temperature(gpu)
        d += render_gpu_fanspeed(gpu)
        d += "\n"
    return d


def render_process_data(gpu_info: Element, verbose: bool = False) -> str:
    name_width = 50
    
    widths = [6, 10, name_width, 7, 11]

    gpu_data = []

    for i, gpu in enumerate(gpu_info.findall(".//gpu")):
        gpu_data.append(
            {
                "gpu_id": gpu.find("minor_number").text,
                "pid": [],
                "proc_name": [],
                "cpu_pct": [],
                "mem": [],
            }
        )
        # reserved memory for this GPU
        if gpu.find("fb_memory_usage").find("reserved") is not None:
            reserved_memory = gpu.find("fb_memory_usage").find("reserved").text
            gpu_data[i]["pid"].append("N/A")
            gpu_data[i]["proc_name"].append("[reserved]")
            gpu_data[i]["cpu_pct"].append("N/A")
            gpu_data[i]["mem"].append(reserved_memory)

        # check for process feature
        if len(gpu.findall("processes/process_info")) == 0:
            return "Process data unavailable\n"

        # all other processes
        for j, proc in enumerate(gpu.findall("processes/process_info")):
            pid = proc.find("pid").text
            gpu_data[i]["pid"].append(pid)
            cpu_pct = pid_to_cpupct(pid) if pid_to_cpupct(pid) is not None else "N/A"
            gpu_data[i]["cpu_pct"].append(str(cpu_pct))
            proc_name = (
                proc.find("process_name").text
                if not verbose
                else pid_to_procname(int(pid))
            )
            gpu_data[i]["mem"].append(proc.find("used_memory").text)
            if len(proc_name) > name_width:
                n = proc_name[:23]
                n += "..."
                n += proc_name[26:name_width]
                proc_name = n
            gpu_data[i]["proc_name"].append(proc_name)

    # display
    s = pretty_print(["-" * 6, "-" * 10, "-" * name_width, "-" * 7, "-" * 11], widths)
    s += pretty_print(["GPU ID", "Process ID", "Name", "CPU %", "GPU Mem"], widths)
    s += pretty_print(["-" * 6, "-" * 10, "-" * name_width, "-" * 7, "-" * 11], widths)
    for d in gpu_data:
        for i in range(len(d["proc_name"])):
            s += pretty_print(
                [
                    d["gpu_id"],
                    d["pid"][i],
                    d["proc_name"][i],
                    d["cpu_pct"][i],
                    d["mem"][i],
                ],
                widths,
            )
    s += pretty_print(["-" * 6, "-" * 10, "-" * name_width, "-" * 7, "-" * 11], widths)
    return s


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
        "-v",
        "--verbose",
        dest="name",
        action="store_true",
        help="display full process names, including command line arguments (may require elevated privileges)",
    )
    argparse.add_argument(
        "-g",
        "--gpu-only",
        dest="gpu",
        action="store_true",
        help="only display GPU stat bars (suppress CPU usage bars)"
    )
    return argparse.parse_args()


def main() -> None:
    args = argparser()

    try:
        while True:
            if gpu_info := get_gpu_info(args.device):
                s = render_cpu_data() if not args.gpu else ''
                s += render_gpu_data(gpu_info)
                s += render_process_data(gpu_info, args.name)
                clear_screen()
                print(s)
            else:
                raise RuntimeError("failed to process data update")
            time.sleep(args.interval)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()

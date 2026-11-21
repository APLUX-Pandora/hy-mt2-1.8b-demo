"""CLI adapter for Runtime CPU placement."""
from pandora_hy_mt2_1_8b import CpuOptions

def cpu_options(text):
    if text in ("inherit", "default"):return CpuOptions(text)
    parts=text.split(",")
    if not parts or any(not x.isascii() or not x.isdecimal() for x in parts):
        raise ValueError("CPU affinity must be inherit, default, or comma-separated CPU IDs")
    return CpuOptions([int(x) for x in parts])

def add_cpu_argument(parser):
    parser.add_argument("--cpu-affinity",type=cpu_options,default="default",
                        help="default: select the Linux SoC CPU profile; inherit; or CPU IDs such as3,4")

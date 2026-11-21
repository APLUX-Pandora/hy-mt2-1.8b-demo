"""Provider-local Runtime configuration for the native model backend.
Configuration requests and actual backend submission are reported separately.
"""
import ctypes as C
from dataclasses import dataclass
import os
import threading
import json
from collections.abc import Iterable
from itertools import islice

_RUNTIME_ABI = 4

_MODES = {"burst": 0, "sustained_high_performance": 3, "high_performance": 4,
          "balanced": 1, "low_balanced": 5, "high_power_saver": 6,
          "power_saver": 7, "low_power_saver": 8, "extreme_power_saver": 9,
          "system_settings": 2}
_PRIORITIES = {"low": 0, "normal": 100, "normal_high": 150, "high": 200}
_LOCKS = {"off": 0, "best_effort": 1}

@dataclass(frozen=True)
class QnnOptions:
    performance_mode: str = "burst"
    priority: str = "normal"
    rpc_control_latency_us: int | None = None
    rpc_polling_time_us: int | None = None
    device_id: int = 0
    def __post_init__(self):
        if type(self.device_id) is not int:
            raise TypeError("device_id must be a uint32 integer, not bool/float")
        if not 0 <= self.device_id <= 2**32-1:
            raise ValueError("device_id must be in 0..4294967295")
        for name, choices in (("performance_mode", _MODES), ("priority", _PRIORITIES)):
            value = getattr(self, name)
            if not isinstance(value, str): raise TypeError(name + " must be a string")
            if value not in choices: raise ValueError(name + " must be one of: " + ", ".join(choices))
        for name, limit in (("rpc_control_latency_us", 2**32-1), ("rpc_polling_time_us", 9999)):
            value = getattr(self, name)
            if value is not None:
                if type(value) is not int: raise TypeError(name + " must be an integer or None")
                if not 0 <= value <= limit: raise ValueError(name + " is outside the supported range")
                if self.performance_mode == "system_settings": raise ValueError("system_settings does not accept RPC overrides")

@dataclass(frozen=True)
class CpuOptions:
    """Model execution affinity: inherit, default, or an immutable CPU ID collection.

    This provider binds model execution and backend-created workers by inheritance.
    CPU sets constrain placement; they do not reserve cores or change NPU priority.
    """
    affinity: str | Iterable[int] = "default"

    def __post_init__(self):
        value = self.affinity
        if isinstance(value, str):
            if value not in ("inherit", "default"):
                raise ValueError("affinity must be 'inherit', 'default', or a CPU ID collection")
        else:
            if isinstance(value, (bytes, bytearray, dict)) or not isinstance(value, Iterable):
                raise TypeError("affinity must be a policy string or CPU ID collection")
            values = tuple(islice(iter(value), 1025))
            if not values or len(values) > 1024:
                raise ValueError("explicit affinity needs 1..1024 CPU IDs")
            if any(type(cpu) is not int for cpu in values):
                raise TypeError("CPU IDs must be integers, not bool/float")
            if any(cpu < 0 or cpu >= 64 for cpu in values):
                raise ValueError("CPU IDs must be integers in0..63 for this Genie provider")
            object.__setattr__(self, "affinity", tuple(sorted(set(values))))

class _Cpu(C.Structure):
    _fields_ = [("struct_size", C.c_uint32), ("abi_version", C.c_uint32),
                ("policy", C.c_uint32), ("cpu_count", C.c_uint32),
                ("cpu_ids", C.POINTER(C.c_uint32)), ("reserved", C.c_uint32 * 2)]
class _CpuStatus(C.Structure):
    _fields_ = [(key,C.c_uint32) for key in ("struct_size","abi_version","policy","coverage",
        "supported_policies","backend_override_supported","active_workers","observed_threads",
        "verified_threads","profile_id")] + [("reserved",C.c_uint32*2),("affinity_failures",C.c_uint64),("package_mask",C.c_uint64),("backend_mask",C.c_uint64),("config_flags",C.c_uint32),("reserved_tail",C.c_uint32)]
class _CpuThread(C.Structure):
    _fields_ = [("struct_size",C.c_uint32),("abi_version",C.c_uint32),("tid",C.c_uint64),
                ("scope",C.c_uint32),("cpu_count",C.c_uint32),("verified",C.c_uint32),("reserved",C.c_uint32)]

class _Qnn(C.Structure):
    _fields_ = [("mode", C.c_uint32), ("priority", C.c_int32), ("device_id", C.c_uint32), ("reserved", C.c_uint32)]
class _Config(C.Structure):
    _fields_ = [("struct_size", C.c_uint32), ("abi_version", C.c_uint32),
                ("backend", C.c_uint32), ("memory_lock", C.c_uint32), ("qnn", _Qnn), ("override_flags", C.c_uint32),
                ("rpc_control_latency_us", C.c_uint32), ("rpc_polling_time_us", C.c_uint32), ("reserved", C.c_uint32),("cpu",_Cpu)]
class _Status(C.Structure):
    _fields_ = [("struct_size", C.c_uint32), ("abi_version", C.c_uint32),
                ("performance_mode", C.c_uint32), ("priority", C.c_int32),
                ("memory_lock", C.c_uint32), ("active_contexts", C.c_uint32),
                ("power_client_created", C.c_uint32), ("active_executions", C.c_uint32),
                ("accepted_active_votes", C.c_uint64), ("accepted_release_votes", C.c_uint64),
                ("rpc_control_latency_us", C.c_uint32), ("rpc_polling_time_us", C.c_uint32),
                ("process_rpc_polling_time_us", C.c_uint32), ("deferred_vote_failures", C.c_uint32)]

class _Submission(C.Structure):
    _fields_ = [(name,C.c_uint32) for name in ("struct_size","abi_version","configured_fields","submitted_fields","active_contexts","backend_performance_mode","backend_rpc_control_latency_us","reserved")]

class _DeviceStatus(C.Structure):
    _fields_ = [(name,C.c_uint32) for name in (
        "struct_size","abi_version","requested_device_id","bound",
        "execution_device_id","power_device_id","power_core_id","power_client_id")]

class RuntimeNativeError(RuntimeError):
    """Native provider failure with a machine-readable SDK error code."""
    def __init__(self, code, message):
        super().__init__(message + " (code " + str(code) + ")")
        self.code = self.native_code = code

class Runtime:
    """Immutable provider-local CPU/QNN requests. Model load validates the device.
    Default configuration is CPU default, burst, normal, device 0.
    Close attached models before closing the Python Runtime.
    """
    def __init__(self, *, cpu=None, qnn=None):
        backend, options, memory_lock = "qnn", qnn, "best_effort"
        if backend != "qnn": raise ValueError("Only the qnn backend is supported")
        if options is not None and not isinstance(options, QnnOptions):
            raise TypeError("options must be QnnOptions or None")
        if not isinstance(memory_lock, str): raise TypeError("memory_lock must be a string")
        if memory_lock not in _LOCKS: raise ValueError("memory_lock must be off or best_effort")
        if options is None:
            options = QnnOptions()
        if (options.performance_mode != "burst" or options.priority != "normal"
                or options.rpc_control_latency_us is not None
                or options.rpc_polling_time_us is not None):
            from ._generation import UnsupportedFeatureError
            raise UnsupportedFeatureError(
                "This provider supports burst/normal; legacy RPC overrides remain unsupported",
                native_code=-7, operation="runtime_create")
        self._qnn = options
        if cpu is None:cpu=CpuOptions()
        if not isinstance(cpu,CpuOptions):raise TypeError("cpu must be this SDK CpuOptions")
        self._cpu=cpu
        self._pid, self._closed = os.getpid(), False
        self._slot, self._lib = C.c_void_p(), None
        self._lock = threading.RLock()
    @property
    def cpu(self):return self._cpu
    @property
    def qnn(self): return self._qnn
    @property
    def memory_lock(self): return "best_effort"
    def _check_process(self):
        if os.getpid() != self._pid:
            raise RuntimeError("Runtime inherited through fork; initialize after spawn/exec")

    def _check(self):
        self._check_process()
        if self._closed: raise RuntimeError("Runtime is closed")
    def _error(self, rc):
        if rc < 0:
            message=self._lib.pandora_runtime_last_error().decode(errors="replace")
            if rc == -7:
                from ._generation import UnsupportedFeatureError
                raise UnsupportedFeatureError(message,native_code=rc,operation="runtime")
            raise RuntimeNativeError(rc, message)
    def _bind(self, lib):
        self._check()
        if self._lib is not None and self._lib._handle != lib._handle:
            raise RuntimeError("A native Runtime cannot be shared across different SDK providers")
        if not self._slot.value:
            self._lib=lib
            lib.pandora_runtime_last_error.restype=C.c_char_p
            lib.pandora_runtime_create.argtypes=[C.POINTER(_Config),C.POINTER(C.c_void_p)]
            lib.pandora_runtime_create.restype=C.c_int
            try:
                lib.pandora_runtime_get_device_status.argtypes=[C.c_void_p,C.POINTER(_DeviceStatus)]
                lib.pandora_runtime_get_device_status.restype=C.c_int
            except AttributeError as error:
                raise RuntimeError("SDK/native Runtime ABI mismatch: device_id requires ABI4") from error
            lib.pandora_runtime_get_submission_status.argtypes=[C.c_void_p,C.POINTER(_Submission)]
            lib.pandora_runtime_get_submission_status.restype=C.c_int
            lib.pandora_runtime_get_status.argtypes=[C.c_void_p,C.POINTER(_Status)]
            lib.pandora_runtime_get_status.restype=C.c_int
            lib.pandora_runtime_destroy.argtypes=[C.POINTER(C.c_void_p)]
            lib.pandora_runtime_destroy.restype=C.c_int
            for name,args in {
                "pandora_runtime_get_cpu_status":[C.c_void_p,C.POINTER(_CpuStatus)],
                "pandora_runtime_get_cpu_ids":[C.c_void_p,C.c_uint32,C.POINTER(C.c_uint32),C.POINTER(C.c_uint32)],
                "pandora_runtime_get_cpu_thread":[C.c_void_p,C.c_uint32,C.POINTER(_CpuThread),C.POINTER(C.c_uint32),C.POINTER(C.c_uint32)]}.items():
                function=getattr(lib,name);function.argtypes=args;function.restype=C.c_int
            affinity=self.cpu.affinity
            ids=None if isinstance(affinity,str) else (C.c_uint32*len(affinity))(*affinity)
            config=_Config();config.struct_size,config.abi_version=C.sizeof(config), _RUNTIME_ABI
            config.backend=1;config.memory_lock=1;config.qnn.mode=0;config.qnn.priority=100
            config.qnn.device_id=self.qnn.device_id
            config.cpu=_Cpu(C.sizeof(_Cpu),1,0 if affinity=="inherit" else 1 if affinity=="default" else 2,0 if ids is None else len(ids),ids)
            try: self._error(lib.pandora_runtime_create(C.byref(config),C.byref(self._slot)))
            except BaseException:
                if self._slot.value: lib.pandora_runtime_destroy(C.byref(self._slot))
                raise
        return self._slot.value
    def capabilities(self):
        self._check()
        return {"provider":"genie_qnn248", "performance_modes":("burst",),
                "priorities":("normal",), "device_id":True,
                "rpc_control_latency":False,"rpc_polling_time":False,
                "cpu_affinity":("inherit","default","explicit"),
                "cpu_default_source":"linux_soc_id"}

    def status(self):
        self._check_process()
        with self._lock:
            self._check()
            return self._status()

    def _status(self):
        result={"backend":"qnn","provider":"genie_qnn248",
                "performance_mode":"burst","priority":"normal","memory_lock":"best_effort",
                "rpc_control_latency_us":100,"rpc_polling_time_us":None,
                "process_rpc_polling_time_us":None,"active_contexts":0,"active_executions":0,
                "power_client_created":False,"accepted_active_votes":0,"accepted_release_votes":0,
                "configured_fields":0,"submitted_fields":0,"requested_device_id":self.qnn.device_id,
                "backend_performance_mode":None,"backend_rpc_control_latency_us":None,
                "device_bound":False,"execution_device_id":None,"power_device_id":None,
                "power_core_id":None,"power_client_id":None}
        if self._slot.value:
            meta=_Status();meta.struct_size,meta.abi_version=C.sizeof(meta), _RUNTIME_ABI
            self._error(self._lib.pandora_runtime_get_status(self._slot,C.byref(meta)))
            result.update(active_contexts=meta.active_contexts,active_executions=meta.active_executions,
                          power_client_created=bool(meta.power_client_created),
                          accepted_active_votes=meta.accepted_active_votes,
                          accepted_release_votes=meta.accepted_release_votes)
            submission=_Submission();submission.struct_size,submission.abi_version=C.sizeof(submission), _RUNTIME_ABI
            self._error(self._lib.pandora_runtime_get_submission_status(self._slot,C.byref(submission)))
            result.update(configured_fields=submission.configured_fields,submitted_fields=submission.submitted_fields,
                          backend_performance_mode=None if submission.backend_performance_mode==2**32-1 else submission.backend_performance_mode,
                          backend_rpc_control_latency_us=None if submission.backend_rpc_control_latency_us==2**32-1 else submission.backend_rpc_control_latency_us)
            device=_DeviceStatus();device.struct_size,device.abi_version=C.sizeof(device), _RUNTIME_ABI
            self._error(self._lib.pandora_runtime_get_device_status(self._slot,C.byref(device)))
            result["device_bound"]=bool(device.bound)
            if device.bound:
                result.update(execution_device_id=device.execution_device_id,
                              power_device_id=device.power_device_id,power_core_id=device.power_core_id,
                              power_client_id=device.power_client_id)
        result["cpu"]=self._cpu_status()
        return result

    def _cpu_status(self):
        request=self.cpu.affinity
        value={"requested_affinity":request if isinstance(request,str) else list(request),
               "scope":"model_execution", "coverage":"model_primary_observed_backend_configured", "backend_override_supported":True,
               "backend_threads":"genie_cpu_mask_and_owned_worker", "complete_thread_coverage":False,
               "process_timer_helper":"libc_process_lifetime_not_model_worker", "preexisting_process_threads":"unchanged", "binding_state":"unbound", "allowed_cpu_ids":None,
               "resolved_cpu_ids":None,"default_cpu_ids":None,"default_profile":None,
               "active_workers":0,"threads":[],"affinity_failures":0,
               "package_cpu_mask":None,"backend_cpu_mask":None,"backend_override_submitted":False,
               "backend_cpu_mask_read_back":False,
               "default_source":"linux_soc_id",
               "bootstrap_scope":"owned_worker_platform_default_before_model_load" if request=="default" else "owned_worker_requested_set"}
        if not self._slot.value:return value
        meta=_CpuStatus();meta.struct_size,meta.abi_version=C.sizeof(meta),1
        self._error(self._lib.pandora_runtime_get_cpu_status(self._slot,C.byref(meta)))
        def ids(kind):
            count=C.c_uint32(0);self._error(self._lib.pandora_runtime_get_cpu_ids(self._slot,kind,None,C.byref(count)))
            if not count.value:return []
            array=(C.c_uint32*count.value)();self._error(self._lib.pandora_runtime_get_cpu_ids(self._slot,kind,array,C.byref(count)))
            return list(array)[:count.value]
        threads=[]
        for index in range(meta.observed_threads):
            row=_CpuThread();row.struct_size,row.abi_version=C.sizeof(row),1
            count=C.c_uint32(0)
            self._error(self._lib.pandora_runtime_get_cpu_thread(self._slot,index,C.byref(row),None,C.byref(count)))
            array=(C.c_uint32*count.value)()
            self._error(self._lib.pandora_runtime_get_cpu_thread(self._slot,index,C.byref(row),array,C.byref(count)))
            threads.append({"tid":row.tid,"scope":"model_primary" if row.scope==3 else "runtime_control" if row.scope==4 else "runtime_power" if row.scope==5 else "unknown",
                            "observed_cpu_ids":list(array)[:count.value],"verified":bool(row.verified)})
        value.update(allowed_cpu_ids=ids(0),resolved_cpu_ids=ids(1),default_cpu_ids=ids(2),
                     default_profile="linux_soc_id" if meta.profile_id==3 else None,
                     supported_policies=[name for i,name in enumerate(("inherit","default","explicit")) if meta.supported_policies&(1<<i)],
                     active_workers=meta.active_workers,threads=threads,affinity_failures=meta.affinity_failures,
                     binding_state="mismatch" if meta.observed_threads and meta.verified_threads!=meta.observed_threads else "inherited" if request=="inherit" and meta.observed_threads else "verified" if meta.observed_threads else "idle")
        profile_buffer=C.create_string_buffer(1024)
        profile_fn=self._lib.pandora_runtime_get_cpu_profile
        profile_fn.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t];profile_fn.restype=C.c_int
        self._error(profile_fn(self._slot,profile_buffer,len(profile_buffer)))
        value.update(json.loads(profile_buffer.value))
        value.update(package_cpu_mask=hex(meta.package_mask) if meta.config_flags&1 else None,
                     backend_cpu_mask=hex(meta.backend_mask) if meta.config_flags & 4 else None,
                     backend_override_submitted=bool(meta.config_flags & 4),
                     default_source="linux_soc_id",
                     bootstrap_scope="owned_worker_platform_default_before_model_load" if request=="default" else "owned_worker_requested_set")
        if request=="default" and not meta.config_flags&1 and meta.observed_threads:value["binding_state"]="resolving_package_default"
        return value

    def close(self):
        if os.getpid()!=self._pid: raise RuntimeError("Cannot close a Runtime inherited through fork")
        with self._lock:
            if self._closed:
                return
            if self._slot.value:
                status = _Status()
                status.struct_size, status.abi_version = C.sizeof(status), _RUNTIME_ABI
                self._error(self._lib.pandora_runtime_get_status(self._slot, C.byref(status)))
                if status.active_contexts:
                    raise RuntimeError("Close attached models before closing the Runtime")
                self._error(self._lib.pandora_runtime_destroy(C.byref(self._slot)))
            self._closed = True
    def __enter__(self):self._check();return self
    def __exit__(self,*_):self.close()

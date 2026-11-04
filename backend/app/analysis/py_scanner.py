"""Find security-relevant behaviour in Python source files by reading the AST.

The code is only parsed, never executed. Common idioms and tricks such as
dynamic imports, aliased modules, base64 payloads, subprocess execution,
and credential harvesting are inspected statically.
"""

import ast
import math
from collections import Counter

from app.analysis.js_scanner import (
    _BASE64_TEXT,
    _COLLECTION_HOST,
    _CREDENTIAL_NAME,
    _HEX_TEXT,
    _MIN_ENCODED_ENTROPY,
    _OBFUSCATOR_MIN_NAMES,
    _OBFUSCATOR_NAME,
    _PUBLIC_IP_URL,
    _RISKY_COMMAND,
    _SECRET_PATH,
    _STARTUP_PATH,
    _WHITESPACE,
    MAX_EVIDENCE_CHARS,
    Hit,
    ScanResult,
    Signal,
)
from app.analysis.models import FindingConfidence, Severity

_DECODER_MODULE_FUNCTIONS = {
    "base64": {
        "b64decode",
        "urlsafe_b64decode",
        "b32decode",
        "b16decode",
        "b85decode",
        "a85decode",
        "decodebytes",
        "decodestring",
    },
    "binascii": {"unhexlify", "a2b_base64", "a2b_hex", "a2b_hqx"},
    "codecs": {"decode"},
    "zlib": {"decompress"},
    "gzip": {"decompress"},
    "bz2": {"decompress"},
    "lzma": {"decompress"},
    "quopri": {"decodestring"},
}

_PROCESS_MODULE_FUNCTIONS = {
    "subprocess": {
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
        "getstatusoutput",
        "getoutput",
    },
    "os": {
        "system",
        "popen",
        "popen2",
        "popen3",
        "popen4",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "posix_spawn",
        "posix_spawnp",
    },
    "pty": {"spawn"},
    "asyncio": {"create_subprocess_exec", "create_subprocess_shell"},
    "commands": {"getoutput", "getstatusoutput"},
}

_PROCESS_INTERNALS = {
    "ctypes": {"CDLL", "windll", "cdll", "WinDLL", "OleDLL", "oledll"},
    "_posixsubprocess": {"fork_exec"},
}

_NETWORK_MODULES = {
    "requests",
    "urllib",
    "urllib.request",
    "http.client",
    "httpx",
    "aiohttp",
    "socket",
    "websocket",
    "websockets",
    "ftplib",
    "telnetlib",
    "urllib3",
    "paramiko",
}

_NETWORK_CALL_NAMES = {
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "head",
    "options",
    "request",
    "urlopen",
    "urlretrieve",
    "HTTPConnection",
    "HTTPSConnection",
    "Client",
    "AsyncClient",
    "ClientSession",
    "socket",
    "create_connection",
    "connect",
    "send",
    "sendto",
    "sendall",
}

_DYNAMIC_IMPORT_FUNCTIONS = {
    "importlib.import_module",
    "__import__",
    "builtins.__import__",
    "__builtin__.__import__",
    "imp.load_module",
    "imp.load_source",
}

_FS_READ_METHODS = {"read_text", "read_bytes", "open"}
_FS_WRITE_METHODS = {"write_text", "write_bytes"}
_FS_WRITE_MODES = {"w", "wb", "a", "ab", "w+", "wb+", "a+", "ab+", "r+", "rb+", "x", "xb"}


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, source_text: str) -> None:
        self.source_text = source_text
        self.lines = source_text.splitlines()
        self.hits: list[Hit] = []

        # Local alias -> canonical module name
        self.module_aliases: dict[str, str] = {}
        # Local alias -> canonical full function name
        self.func_aliases: dict[str, str] = {}
        # Local var -> dangerous global name (e.g. `e = eval`)
        self.global_aliases: dict[str, str] = {}
        # Local names holding `os.environ`
        self.environment_vars: set[str] = set()
        # Reported lines for environment to avoid duplicate ENV hits on same node
        self.reported_environment: set[int] = set()
        # Variables that hold decoded data (e.g. payload = b64decode(...))
        self.decoded_variables: set[str] = set()
        # Variables holding compiled code objects: var -> whether it contains decoded payload
        self.compiled_variables: dict[str, bool] = {}
        # Statically known string variables: var -> value
        self.string_variables: dict[str, str] = {}
        # Statically known command lists: var -> list of str
        self.command_variables: dict[str, list[str]] = {}
        # Obfuscator-style variable names
        self.obfuscator_names: list[tuple[str, ast.AST]] = []

    def _hit(
        self,
        rule_id: str,
        node: ast.AST,
        severity: Severity,
        confidence: FindingConfidence,
        signal: Signal | None = None,
        evidence: str | None = None,
    ) -> None:
        lineno = getattr(node, "lineno", 1)
        if evidence is None:
            raw_text = ast.get_source_segment(self.source_text, node)
            if not raw_text and 0 <= lineno - 1 < len(self.lines):
                raw_text = self.lines[lineno - 1]
            evidence = raw_text or ""
        cleaned = _WHITESPACE.sub(" ", evidence).strip()[:MAX_EVIDENCE_CHARS]
        self.hits.append(Hit(rule_id, lineno, severity, confidence, cleaned, signal))

    def _static_string(self, node: ast.AST | None, depth: int = 0) -> str | None:
        if node is None or depth > 10:
            return None
        if isinstance(node, ast.Name) and node.id in self.string_variables:
            return self.string_variables[node.id]
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return node.value
            if isinstance(node.value, bytes):
                try:
                    return node.value.decode("utf-8")
                except UnicodeDecodeError:
                    return node.value.decode("latin-1", errors="replace")
        elif isinstance(node, ast.JoinedStr):
            # Format string with static constants or known static variables
            parts: list[str] = []
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, (str, bytes)):
                    val = (
                        part.value
                        if isinstance(part.value, str)
                        else part.value.decode("utf-8", errors="replace")
                    )
                    parts.append(val)
                elif isinstance(part, ast.FormattedValue):
                    s = self._static_string(part.value, depth + 1)
                    if s is not None:
                        parts.append(s)
                    else:
                        return None
                else:
                    return None
            return "".join(parts)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._static_string(node.left, depth + 1)
            right = self._static_string(node.right, depth + 1)
            if left is not None and right is not None:
                return left + right
        return None

    def _extract_strings(self, node: ast.AST | None, depth: int = 0) -> list[str]:
        if node is None or depth > 8:
            return []
        strings: list[str] = []
        if isinstance(node, ast.Name):
            if node.id in self.string_variables:
                strings.append(self.string_variables[node.id])
            elif node.id in self.command_variables:
                strings.extend(self.command_variables[node.id])
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, (str, bytes)):
                val = (
                    child.value
                    if isinstance(child.value, str)
                    else child.value.decode("utf-8", errors="replace")
                )
                strings.append(val)
            elif isinstance(child, ast.Name):
                if child.id in self.string_variables:
                    strings.append(self.string_variables[child.id])
                elif child.id in self.command_variables:
                    strings.extend(self.command_variables[child.id])
        return strings

    def _resolve_call_target(self, node: ast.AST) -> tuple[str | None, str | None]:
        """Resolve a Call's func into (module, function_name)."""
        if isinstance(node, ast.Name):
            name = node.id
            if name in self.func_aliases:
                canonical = self.func_aliases[name]
                if "." in canonical:
                    mod, fn = canonical.rsplit(".", 1)
                    return mod, fn
                return None, canonical
            if name in self.global_aliases:
                return None, self.global_aliases[name]
            return None, name

        if isinstance(node, ast.Attribute):
            attr = node.attr
            # Check attribute chains like subprocess.run or os.path.join
            if isinstance(node.value, ast.Name):
                base_name = node.value.id
                module_name = self.module_aliases.get(base_name, base_name)
                # Check for os.environ.get
                if base_name in self.environment_vars or module_name in (
                    "os.environ",
                    "os.environb",
                ):
                    return "os.environ", attr
                return module_name, attr

            if isinstance(node.value, ast.Attribute):
                # E.g. urllib.request.urlopen or pathlib.Path.open
                sub_mod, sub_fn = self._resolve_call_target(node.value)
                if sub_mod and sub_fn:
                    return f"{sub_mod}.{sub_fn}", attr
                if sub_fn:
                    return sub_fn, attr

            if isinstance(node.value, ast.Call):
                call_mod, call_fn = self._resolve_call_target(node.value.func)
                base: str | None = (
                    f"{call_mod}.{call_fn}" if call_mod and call_fn else (call_fn or call_mod)
                )
                return base, attr

            return None, attr

        return None, None

    def _is_decoder_node(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Call):
            mod, fn = self._resolve_call_target(node.func)
            if mod in _DECODER_MODULE_FUNCTIONS and fn in _DECODER_MODULE_FUNCTIONS[mod]:
                return True
            if fn in {
                "b64decode",
                "urlsafe_b64decode",
                "b32decode",
                "b16decode",
                "b85decode",
                "a85decode",
                "unhexlify",
                "a2b_base64",
                "a2b_hex",
                "decompress",
            }:
                return True
        elif isinstance(node, ast.Name):
            if node.id in self.decoded_variables:
                return True
        return False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            self.module_aliases[asname] = name

            if name == "subprocess":
                self._hit("PROC-001", node, Severity.INFO, FindingConfidence.HIGH)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module == "subprocess":
            self._hit("PROC-001", node, Severity.INFO, FindingConfidence.HIGH)

        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            full_name = f"{module}.{name}" if module else name
            self.func_aliases[asname] = full_name

            if module in ("builtins", "__builtin__") and name in ("eval", "exec", "compile"):
                self.global_aliases[asname] = name
            elif module == "os" and name in ("environ", "environb"):
                self.environment_vars.add(asname)
            elif module in _DECODER_MODULE_FUNCTIONS and name in _DECODER_MODULE_FUNCTIONS[module]:
                self.func_aliases[asname] = f"{module}.{name}"
            elif module in _PROCESS_MODULE_FUNCTIONS and name in _PROCESS_MODULE_FUNCTIONS[module]:
                self.func_aliases[asname] = f"{module}.{name}"

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Check if RHS is a global like `e = eval`
        if isinstance(node.value, ast.Name):
            if node.value.id in {"eval", "exec", "compile"}:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.global_aliases[target.id] = node.value.id
            elif node.value.id in self.environment_vars:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.environment_vars.add(target.id)

        # Check if RHS is `os.environ`
        elif isinstance(node.value, ast.Attribute):
            mod, attr = self._resolve_call_target(node.value)
            if mod == "os" and attr in ("environ", "environb"):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.environment_vars.add(target.id)

        # Check if RHS is a decoder call
        elif self._is_decoder_node(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.decoded_variables.add(target.id)

        # Check if RHS is a compile call
        elif isinstance(node.value, ast.Call):
            mod, fn = self._resolve_call_target(node.value.func)
            if (mod in {None, "builtins", "__builtin__"} and fn == "compile") or (
                fn is not None and fn in self.global_aliases
            ):
                is_dec = bool(node.value.args and self._is_decoder_node(node.value.args[0]))
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.compiled_variables[target.id] = is_dec

        # Track static strings and static commands
        static_val = self._static_string(node.value)
        if static_val is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.string_variables[target.id] = static_val
        elif isinstance(node.value, (ast.List, ast.Tuple)):
            elem_strs = [self._static_string(el) for el in node.value.elts]
            if all(s is not None for s in elem_strs):
                cmd_list = [s for s in elem_strs if s is not None]
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.command_variables[target.id] = cmd_list

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            if isinstance(node.value, ast.Name):
                if node.value.id in {"eval", "exec", "compile"}:
                    if isinstance(node.target, ast.Name):
                        self.global_aliases[node.target.id] = node.value.id
            elif self._is_decoder_node(node.value):
                if isinstance(node.target, ast.Name):
                    self.decoded_variables.add(node.target.id)
            elif isinstance(node.value, ast.Call):
                mod, fn = self._resolve_call_target(node.value.func)
                if (mod in {None, "builtins", "__builtin__"} and fn == "compile") or (
                    fn is not None and fn in self.global_aliases
                ):
                    is_dec = bool(node.value.args and self._is_decoder_node(node.value.args[0]))
                    if isinstance(node.target, ast.Name):
                        self.compiled_variables[node.target.id] = is_dec

            static_val = self._static_string(node.value)
            if static_val is not None and isinstance(node.target, ast.Name):
                self.string_variables[node.target.id] = static_val
            elif isinstance(node.value, (ast.List, ast.Tuple)) and isinstance(
                node.target, ast.Name
            ):
                elem_strs = [self._static_string(el) for el in node.value.elts]
                if all(s is not None for s in elem_strs):
                    self.command_variables[node.target.id] = [s for s in elem_strs if s is not None]

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        mod, fn = self._resolve_call_target(node.func)
        full_call = f"{mod}.{fn}" if mod else (fn or "")

        # 1. Dynamic Code Execution
        is_dynamic_exec = False
        if mod in {None, "builtins", "__builtin__"} and fn in {"eval", "exec", "compile"}:
            is_dynamic_exec = True
        elif fn is not None and fn in self.global_aliases:
            is_dynamic_exec = True

        if is_dynamic_exec:
            self._check_dynamic_execution(node)

        # 2. Process Execution
        elif self._is_process_call(mod, fn, full_call):
            self._check_process_execution(node, mod, fn)

        # 3. Process Internals (ctypes, etc.)
        elif self._is_process_internal(mod, fn, full_call):
            self._hit("PROC-005", node, Severity.HIGH, FindingConfidence.HIGH, Signal.PROCESS)

        # 4. Environment Access via Calls
        elif full_call in {"os.getenv", "os.environ.get", "os.environb.get"} or (
            mod in self.environment_vars and fn == "get"
        ):
            self._check_environment_call(node)

        # 5. Network Calls
        elif self._is_network_call(mod, fn, full_call):
            self._check_network_call(node)

        # 6. Dynamic Imports
        elif full_call in _DYNAMIC_IMPORT_FUNCTIONS or (
            mod == "importlib" and fn in {"import_module", "__import__"}
        ):
            self._check_dynamic_import(node)

        # 7. Decoders
        elif (mod in _DECODER_MODULE_FUNCTIONS and fn in _DECODER_MODULE_FUNCTIONS[mod]) or (
            fn
            in {
                "b64decode",
                "urlsafe_b64decode",
                "b32decode",
                "b16decode",
                "b85decode",
                "a85decode",
                "unhexlify",
                "a2b_base64",
                "a2b_hex",
                "decompress",
            }
        ):
            self._hit("OBF-004", node, Severity.INFO, FindingConfidence.HIGH, Signal.DECODE)

        # 8. Filesystem Operations
        elif self._is_filesystem_call(mod, fn, full_call):
            self._check_filesystem_call(node, fn)

        # 9. String built from character codes
        elif self._is_char_code_join(node):
            self._hit("OBF-003", node, Severity.MEDIUM, FindingConfidence.MEDIUM, Signal.DECODE)

        self.generic_visit(node)

    def _check_dynamic_execution(self, node: ast.Call) -> None:
        if not node.args:
            self._hit(
                "EXEC-001",
                node,
                Severity.MEDIUM,
                FindingConfidence.MEDIUM,
                Signal.EXECUTION,
            )
            return

        arg0 = node.args[0]
        is_decoded = self._is_decoder_node(arg0)
        if isinstance(arg0, ast.Name) and self.compiled_variables.get(arg0.id) is True:
            is_decoded = True

        if is_decoded:
            self._hit(
                "EXEC-003",
                node,
                Severity.CRITICAL,
                FindingConfidence.HIGH,
                Signal.EXECUTION,
            )
        elif self._static_string(arg0) is not None:
            self._hit("EXEC-002", node, Severity.LOW, FindingConfidence.HIGH)
        else:
            self._hit(
                "EXEC-001",
                node,
                Severity.MEDIUM,
                FindingConfidence.MEDIUM,
                Signal.EXECUTION,
            )

    def _is_process_call(self, mod: str | None, fn: str | None, full_call: str) -> bool:
        if mod in _PROCESS_MODULE_FUNCTIONS and fn in _PROCESS_MODULE_FUNCTIONS[mod]:
            return True
        if full_call in {
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.call",
            "subprocess.check_call",
            "subprocess.check_output",
            "os.system",
            "os.popen",
            "pty.spawn",
        }:
            return True
        return False

    def _is_process_internal(self, mod: str | None, fn: str | None, full_call: str) -> bool:
        if mod in _PROCESS_INTERNALS and fn in _PROCESS_INTERNALS[mod]:
            return True
        if full_call in {"ctypes.CDLL", "ctypes.windll", "_posixsubprocess.fork_exec"}:
            return True
        return False

    def _check_process_execution(self, node: ast.Call, mod: str | None, fn: str | None) -> None:
        # Check command argument (arg 0 or 'args' keyword)
        cmd_arg = None
        if node.args:
            cmd_arg = node.args[0]
        else:
            for kw in node.keywords:
                if kw.arg in ("args", "cmd", "command"):
                    cmd_arg = kw.value
                    break

        strings = self._extract_strings(cmd_arg)
        joined_cmd = " ".join(strings)

        if cmd_arg is not None and self._is_decoder_node(cmd_arg):
            self._hit("PROC-004", node, Severity.HIGH, FindingConfidence.HIGH, Signal.PROCESS)
        elif strings and _RISKY_COMMAND.search(joined_cmd):
            self._hit("PROC-004", node, Severity.HIGH, FindingConfidence.HIGH, Signal.PROCESS)
        elif self._is_static_command(cmd_arg):
            self._hit("PROC-002", node, Severity.LOW, FindingConfidence.HIGH, Signal.PROCESS)
        else:
            self._hit("PROC-003", node, Severity.MEDIUM, FindingConfidence.MEDIUM, Signal.PROCESS)

    def _is_static_command(self, node: ast.AST | None) -> bool:
        if node is None:
            return False
        if self._static_string(node) is not None:
            return True
        if isinstance(node, (ast.List, ast.Tuple)):
            return all(self._static_string(elem) is not None for elem in node.elts)
        return False

    def _check_environment_call(self, node: ast.Call) -> None:
        key_arg = node.args[0] if node.args else None
        key_str = self._static_string(key_arg) if key_arg else None

        lineno = getattr(node, "lineno", 1)
        self.reported_environment.add(lineno)

        if key_str is not None:
            if _CREDENTIAL_NAME.search(key_str):
                self._hit(
                    "ENV-002",
                    node,
                    Severity.MEDIUM,
                    FindingConfidence.MEDIUM,
                    Signal.CREDENTIAL,
                )
            else:
                self._hit("ENV-001", node, Severity.INFO, FindingConfidence.HIGH)
        else:
            self._hit("ENV-001", node, Severity.LOW, FindingConfidence.LOW)

    def _is_network_call(self, mod: str | None, fn: str | None, full_call: str) -> bool:
        if mod in _NETWORK_MODULES:
            return True
        if mod and any(mod.startswith(m) for m in _NETWORK_MODULES):
            return True
        if fn in _NETWORK_CALL_NAMES and (mod in _NETWORK_MODULES or mod is None):
            return True
        return False

    def _check_network_call(self, node: ast.Call) -> None:
        strings = self._extract_strings(node)
        destinations = " ".join(strings)
        if _COLLECTION_HOST.search(destinations) or _PUBLIC_IP_URL.search(destinations):
            self._hit("NET-002", node, Severity.HIGH, FindingConfidence.HIGH, Signal.NETWORK)
        else:
            self._hit("NET-001", node, Severity.INFO, FindingConfidence.HIGH, Signal.NETWORK)

    def _check_dynamic_import(self, node: ast.Call) -> None:
        arg0 = node.args[0] if node.args else None
        if arg0 is None:
            return

        if self._is_decoder_node(arg0):
            self._hit("EXEC-005", node, Severity.HIGH, FindingConfidence.HIGH)
        elif self._static_string(arg0) is not None:
            # Harmless fixed import like importlib.import_module("json")
            pass
        else:
            self._hit("EXEC-004", node, Severity.LOW, FindingConfidence.MEDIUM)

    def _is_filesystem_call(self, mod: str | None, fn: str | None, full_call: str) -> bool:
        if full_call in {"open", "builtins.open"}:
            return True
        if mod == "os" and fn in {"remove", "unlink", "chmod", "rename", "replace"}:
            return True
        if mod == "shutil" and fn in {"rmtree", "copy", "copy2", "move"}:
            return True
        if fn in _FS_READ_METHODS or fn in _FS_WRITE_METHODS:
            return True
        return False

    def _check_filesystem_call(self, node: ast.Call, fn: str | None) -> None:
        strings = self._extract_strings(node)
        joined_paths = " ".join(strings)

        # Check sensitive credential access
        if _SECRET_PATH.search(joined_paths):
            self._hit(
                "FS-001",
                node,
                Severity.MEDIUM,
                FindingConfidence.MEDIUM,
                Signal.CREDENTIAL,
            )

        # Check write to startup or persistence paths
        is_write = (fn in _FS_WRITE_METHODS) or self._is_open_write_mode(node)
        if is_write and _STARTUP_PATH.search(joined_paths):
            self._hit("FS-002", node, Severity.HIGH, FindingConfidence.HIGH)

    def _is_open_write_mode(self, node: ast.Call) -> bool:
        # Check mode in args (arg 1) or keyword 'mode'
        if len(node.args) >= 2:
            mode_str = self._static_string(node.args[1])
            if mode_str and any(m in mode_str for m in ("w", "a", "x", "+")):
                return True
        for kw in node.keywords:
            if kw.arg == "mode":
                mode_str = self._static_string(kw.value)
                if mode_str and any(m in mode_str for m in ("w", "a", "x", "+")):
                    return True
        return False

    def _is_char_code_join(self, node: ast.Call) -> bool:
        # Catch ''.join([chr(...) for ...]) or ''.join(chr(x) for x in ...)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            if node.args:
                arg = node.args[0]
                if isinstance(arg, (ast.ListComp, ast.GeneratorExp)):
                    if isinstance(arg.elt, ast.Call):
                        mod, fn = self._resolve_call_target(arg.elt.func)
                        if fn == "chr":
                            return True
        return False

    def visit_Subscript(self, node: ast.Subscript) -> None:
        # Check `os.environ[...]` or `env[...]`
        is_environ = False
        if isinstance(node.value, ast.Attribute):
            mod, attr = self._resolve_call_target(node.value)
            if mod == "os" and attr in ("environ", "environb"):
                is_environ = True
        elif isinstance(node.value, ast.Name):
            if node.value.id in self.environment_vars:
                is_environ = True

        if is_environ:
            lineno = getattr(node, "lineno", 1)
            self.reported_environment.add(lineno)
            key_str = self._static_string(node.slice)
            if key_str is not None:
                if _CREDENTIAL_NAME.search(key_str):
                    self._hit(
                        "ENV-002",
                        node,
                        Severity.MEDIUM,
                        FindingConfidence.MEDIUM,
                        Signal.CREDENTIAL,
                    )
                else:
                    self._hit("ENV-001", node, Severity.INFO, FindingConfidence.HIGH)
            else:
                self._hit("ENV-001", node, Severity.LOW, FindingConfidence.LOW)

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # Check for obfuscator identifiers
        if _OBFUSCATOR_NAME.match(node.id):
            self.obfuscator_names.append((node.id, node))

        # Check whole environment access: `dict(os.environ)` or passing `env` directly
        if node.id in self.environment_vars:
            lineno = getattr(node, "lineno", 1)
            if lineno not in self.reported_environment:
                self.reported_environment.add(lineno)
                self._hit(
                    "ENV-003",
                    node,
                    Severity.MEDIUM,
                    FindingConfidence.MEDIUM,
                    Signal.CREDENTIAL,
                )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Check whole environment access: passing `os.environ` directly
        if isinstance(node.value, ast.Name) and node.value.id == "os":
            if node.attr in ("environ", "environb"):
                lineno = getattr(node, "lineno", 1)
                if lineno not in self.reported_environment:
                    self.reported_environment.add(lineno)
                    self._hit(
                        "ENV-003",
                        node,
                        Severity.MEDIUM,
                        FindingConfidence.MEDIUM,
                        Signal.CREDENTIAL,
                    )

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            text = node.value
            if len(text) >= 8 and _COLLECTION_HOST.search(text):
                self._hit(
                    "NET-003",
                    node,
                    Severity.MEDIUM,
                    FindingConfidence.HIGH,
                    Signal.NETWORK,
                )
            if len(text) >= 200:
                is_hex = _HEX_TEXT.fullmatch(text) is not None
                is_b64 = not is_hex and _BASE64_TEXT.fullmatch(text) is not None
                if (is_hex or is_b64) and _entropy(text) >= _MIN_ENCODED_ENTROPY:
                    self._hit(
                        "OBF-002",
                        node,
                        Severity.LOW,
                        FindingConfidence.MEDIUM,
                        Signal.OBFUSCATION,
                        evidence=f"{len(text)} characters: {text[:60]}...",
                    )
        self.generic_visit(node)

    def finalize(self) -> None:
        if len(self.obfuscator_names) >= _OBFUSCATOR_MIN_NAMES:
            first_node = self.obfuscator_names[0][1]
            self._hit(
                "OBF-001",
                first_node,
                Severity.MEDIUM,
                FindingConfidence.HIGH,
                Signal.OBFUSCATION,
            )


def scan_python(source: bytes | str) -> ScanResult:
    """Parse Python source code using ast.parse and return security hits.

    Never executes untrusted code. Gracefully reports syntax errors as parse gaps.
    """
    if isinstance(source, bytes):
        try:
            source_text = source.decode("utf-8")
        except UnicodeDecodeError:
            try:
                source_text = source.decode("latin-1")
            except Exception:
                return ScanResult(hits=(), has_parse_errors=True)
    else:
        source_text = source

    try:
        tree = ast.parse(source_text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return ScanResult(hits=(), has_parse_errors=True)

    visitor = _PythonVisitor(source_text)
    visitor.visit(tree)
    visitor.finalize()

    return ScanResult(hits=tuple(visitor.hits), has_parse_errors=False)

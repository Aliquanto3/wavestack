"""GGUF probe: full load in a child process before first use (AD-7).

Run as ``python -m wavestack.models.probe <path>``. A GGUF never loaded
successfully before is probed this way so a corrupt or incompatible file
cannot crash the main process mid-session (AD-16).

Lot E (E2): the child loads the model at the session's window and the engine's batch, then
evaluates a neutral prompt of one full batch, so the RSS it measures holds the compute
buffers llama.cpp reserves for a batch, not only the weights (`probe_version = 2`).

Installs the same network guard as the main process (AD-15), since loading
a model must never reach the network.
"""

from __future__ import annotations

import functools
import json
import os
import sys
import time
from importlib import metadata
from pathlib import Path
from typing import Any

import psutil
from pydantic import BaseModel

from wavestack import config
from wavestack.messages import Message
from wavestack.models import gguf_meta

# Lot E (E2): version 2 measures the RSS after a real evaluation; an entry of an older probe
# (or without its measures) is probed again.
PROBE_VERSION = 2
DEFAULT_WINDOW = 4096
# A neutral text, repeated up to one full batch: its content does not matter, its length does.
_NEUTRAL_TEXT = (
    "Le harnais prépare le contexte, appelle le modèle et lit sa réponse. "
    "Chaque brique ajoute une capacité et un coût, que WaveStack montre à l'écran. "
)


class ProbeResult(BaseModel):
    ok: bool
    path: str
    # In French: a `Message` becomes its French text here (and in settings.json);
    # `discovery.reason_message` gives the `Message` back, for the session to render.
    reason: str | None = None
    detail: str | None = None  # lot E (E6): the loader's own message, a technical detail
    architecture: str | None = None
    has_chat_template: bool = False
    # RSS gained by the model once loaded at the window and a full batch evaluated (peak).
    rss_bytes: int | None = None
    size_bytes: int | None = None
    mtime: float | None = None
    size_label: str | None = None  # `general.size_label`, e.g. « 2B » (DESIGN.md)
    # AD-8: the KV cache's bytes per token of context (f16 K and V), when the GGUF says it.
    kv_bytes_per_token: int | None = None
    # Lot E (E2): the probe's version, the context it created (llama.cpp clears the whole KV
    # buffer at creation: the KV of `probe_window` tokens is in `rss_bytes`), and the tokens
    # it evaluated before reading the RSS.
    probe_version: int | None = None
    probe_window: int | None = None
    rss_eval_tokens: int | None = None
    # Lot E: a failure that says nothing about the file (memory, time): never remembered.
    transient: bool = False


def _int_meta(meta: dict[str, Any], key: str) -> int | None:
    try:
        value = int(meta[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if value > 0 else None


def _key_value_lengths(meta: dict[str, Any], arch: str) -> tuple[int | None, int | None]:
    heads = _int_meta(meta, f"{arch}.attention.head_count")
    key_length = _int_meta(meta, f"{arch}.attention.key_length")
    if key_length is None:
        embedding = _int_meta(meta, f"{arch}.embedding_length")
        key_length = embedding // heads if embedding and heads else None
    value_length = _int_meta(meta, f"{arch}.attention.value_length") or key_length
    return key_length, value_length


def _kv_per_layer(meta: dict[str, Any], arch: str) -> list[int] | None:
    """Story 2: `head_count_kv`'s per-layer list, or its single value (`head_count` when
    absent) once per layer; `None` when that single value goes with a
    `full_attention_interval` above 1 (that case never combines with a sliding-window
    pattern), or is unreadable, or the layer count is unknown."""
    raw = meta.get(f"{arch}.attention.head_count_kv")
    if isinstance(raw, list | tuple):
        try:
            return [int(n) for n in raw]
        except (TypeError, ValueError):
            return None
    interval = _int_meta(meta, f"{arch}.full_attention_interval")
    if raw is not None and interval and interval > 1:
        return None
    heads = _int_meta(
        meta,
        f"{arch}.attention.head_count_kv" if raw is not None else f"{arch}.attention.head_count",
    )
    layers = _int_meta(meta, f"{arch}.block_count")
    return [heads] * layers if layers and heads else None


def _sliding_layers(meta: dict[str, Any]) -> list[bool] | None:
    """Story 2: `{arch}.attention.sliding_window_pattern`, one boolean per layer (true =
    sliding-window layer), as `get_key_or_arr` of llama.cpp reads it: a list as long as
    `block_count` or the `head_count_kv` list, or a single value broadcast to every layer
    (needs `block_count` then). Anything else (absent, wrong length, wrong type) is `None`:
    the pattern is ignored, never an exception."""
    arch = meta.get("general.architecture")
    if not arch:
        return None
    raw = meta.get(f"{arch}.attention.sliding_window_pattern")
    if raw is None:
        return None
    layers = _int_meta(meta, f"{arch}.block_count")
    if isinstance(raw, bool):
        return [raw] * layers if layers else None
    if isinstance(raw, list | tuple):
        kv_raw = meta.get(f"{arch}.attention.head_count_kv")
        kv_len = len(kv_raw) if isinstance(kv_raw, list | tuple) else None
        if len(raw) not in {n for n in (layers, kv_len) if n}:
            return None
        try:
            return [bool(v) for v in raw]
        except (TypeError, ValueError):
            return None
    return None


def sliding_kv(meta: dict[str, Any]) -> tuple[int, int] | None:
    """Story 3: the fixed part llama.cpp keeps per sliding-window layer (bytes per token of
    those layers alone, f16 K and V, `2 × Σ over sliding layers (KV heads × (key + value
    size))`) and the window's length (`{arch}.attention.sliding_window`); `None` without a
    readable window, pattern, or per-layer KV head count."""
    arch = meta.get("general.architecture")
    if not arch:
        return None
    window = _int_meta(meta, f"{arch}.attention.sliding_window")
    mask = _sliding_layers(meta)
    kv_per_layer = _kv_per_layer(meta, arch)
    if not window or mask is None or kv_per_layer is None or len(mask) != len(kv_per_layer):
        return None
    kv_heads_total = sum(
        kv for kv, is_sliding in zip(kv_per_layer, mask, strict=True) if is_sliding
    )
    if not kv_heads_total:
        return None
    key_length, value_length = _key_value_lengths(meta, arch)
    if not key_length or not value_length:
        return None
    return 2 * kv_heads_total * (key_length + value_length), window


def kv_bytes_per_token(meta: dict[str, Any], *, sliding: bool = False) -> int | None:
    """AD-8: the KV cache's bytes per token of context, f16 (2 bytes), K and V:
    `2 × Σ over layers (KV heads × (key size + value size))`, from the GGUF metadata.

    `head_count_kv` may be one integer or one value per layer (hybrid models such as
    Qwen3.5, whose linear-attention layers have 0 KV head); a value that is neither (e.g.
    an array llama-cpp-python only shows as text) gives `None`, never the attention heads
    instead.

    Story 2: with `sliding=True` and a valid `{arch}.attention.sliding_window_pattern`
    (`_sliding_layers`) plus a positive `{arch}.attention.sliding_window`, the layers the
    pattern marks as sliding-window are left out: the caller says its engine allocates a
    reduced cache for them (llama-server's default). Without `sliding`, or with an absent,
    invalid, or unusable pattern, every layer counts, as before (an overestimate for a
    sliding-window layer, by design: `sliding_kv` gives its fixed part instead).

    Lot K (A2): a hybrid model may give one integer and `{arch}.full_attention_interval` = n
    instead (Qwen3.5 GGUF: one layer in n has full attention, hence a KV cache; the others
    are linear-attention layers without one): only `block_count // n` layers count. A
    per-layer list stays the reference when present (the interval is then ignored, and
    never combined with a sliding-window pattern either).
    """
    arch = meta.get("general.architecture")
    if not arch:
        return None
    key_length, value_length = _key_value_lengths(meta, arch)
    kv_key = f"{arch}.attention.head_count_kv"
    kv_per_layer = _kv_per_layer(meta, arch)
    masked = False
    if kv_per_layer is not None:
        if sliding:
            mask = _sliding_layers(meta)
            window = _int_meta(meta, f"{arch}.attention.sliding_window")
            if mask is not None and window and len(mask) == len(kv_per_layer):
                kv_per_layer = [
                    kv for kv, is_sliding in zip(kv_per_layer, mask, strict=True) if not is_sliding
                ]
                masked = True
        kv_heads_total = sum(kv_per_layer)
    else:
        layers = _int_meta(meta, f"{arch}.block_count")
        per_layer = _int_meta(meta, kv_key)
        interval = _int_meta(meta, f"{arch}.full_attention_interval")
        if layers and interval and interval > 1:
            layers = layers // interval
        kv_heads_total = layers * per_layer if layers and per_layer else None
    # 0 only when the pattern left every KV layer out; a header without any KV head stays None.
    if (
        kv_heads_total is None
        or not (kv_heads_total or masked)
        or not key_length
        or not value_length
    ):
        return None
    return 2 * kv_heads_total * (key_length + value_length)


def incompatible_fr(architecture: str | None = None) -> str:
    """Lot E (E6): why llama-cpp-python refuses a file, a `Message` (French as a text,
    rendered by the session in its language); its own message is kept apart, as a technical
    detail. Story LFM3: with `architecture` (the header read in Python), names the probable
    cause instead of the generic text."""
    version = _llama_cpp_version()
    lib = f"llama-cpp-python {version}" if version else "llama-cpp-python"
    if architecture:
        return Message("models.probe.incompatible_architecture", lib=lib, architecture=architecture)
    return Message("models.probe.incompatible", lib=lib)


def transient_fr() -> str:
    """Lot E: a probe that lacked memory or time says nothing about the file: not
    remembered, the file is probed again when chosen. A `Message`, as `incompatible_fr`."""
    return Message("models.probe.transient")


def not_found_fr() -> str:
    """The file is not there (a `Message`)."""
    return Message("models.probe.not_found")


def not_installed_fr() -> str:
    """llama-cpp-python is missing (a `Message`)."""
    return Message("models.probe.not_installed")


def _load_refused(exc: BaseException) -> bool:
    """llama.cpp refused the file itself (« Failed to load model »), not the memory for its
    context (« Failed to create llama_context », `MemoryError`)."""
    return not isinstance(exc, MemoryError) and "Failed to load model" in str(exc)


def _os_peak_rss() -> int | None:
    """This process's peak resident memory, as the OS keeps it (POSIX `ru_maxrss`: kB on
    Linux, bytes on macOS); `None` where it does not (Windows: `peak_wset` instead)."""
    try:
        import resource
    except ImportError:
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak) if sys.platform == "darwin" else int(peak) * 1024


def _peak_rss(process: psutil.Process) -> int:
    """The largest resident memory seen: now, the Windows working set's peak, the OS peak."""
    info = process.memory_info()
    peaks = [info.rss, getattr(info, "peak_wset", None), _os_peak_rss()]
    return max(int(p) for p in peaks if p)


def _neutral_prompt(llm: Any, n_tokens: int) -> list[int]:
    """`n_tokens` ids of a neutral text (the text repeated as needed)."""
    once = llm.tokenize(_NEUTRAL_TEXT.encode("utf-8"), add_bos=False, special=False)
    if not once:
        return []
    return (once * (n_tokens // len(once) + 1))[:n_tokens]


def probe_file(path: str, window: int = DEFAULT_WINDOW) -> ProbeResult:
    """Load `path` in this process at `window` tokens of context and the engine's batch
    (llama-cpp-python's default, as `LlamaCppEngine`), evaluate one full batch of a neutral
    prompt, and report the outcome with the RSS peak gained. Never raises."""
    file_path = Path(path)
    if not file_path.is_file():
        return ProbeResult(ok=False, path=path, reason=not_found_fr())

    try:
        from llama_cpp import Llama
    except ImportError:
        return ProbeResult(ok=False, path=path, reason=not_installed_fr())

    process = psutil.Process(os.getpid())
    before = process.memory_info().rss  # the interpreter and llama-cpp-python, without weights
    n_ctx = max(window, 16)
    try:
        llm = Llama(model_path=str(file_path), n_ctx=n_ctx, verbose=False)
    except Exception as exc:  # noqa: BLE001 - the file itself, or its context's memory
        if _load_refused(exc):
            header = gguf_meta.try_read_metadata(file_path, stop_at="tokenizer.") or {}
            architecture = header.get("general.architecture")
            architecture = architecture if isinstance(architecture, str) and architecture else None
            return ProbeResult(
                ok=False, path=path, reason=incompatible_fr(architecture), detail=str(exc)
            )
        return _transient(path, exc)

    try:
        metadata: dict[str, Any] = getattr(llm, "metadata", {}) or {}
        try:
            # One full batch (never the whole window): the compute buffers of a batch.
            batch = int(getattr(llm, "n_batch", 512) or 512)
            prompt = _neutral_prompt(llm, max(1, min(batch, n_ctx - 1)))
            if prompt:
                llm.eval(prompt)
        except Exception as exc:  # noqa: BLE001 - loaded: memory or time (MemoryError too)
            return _transient(path, exc)
        rss_bytes = max(0, _peak_rss(process) - before)  # the model's own share, at its peak
        # Lot E: the KV from the header read in Python (llama-cpp-python shows an array,
        # a hybrid model's per-layer `head_count_kv`, as text).
        header = gguf_meta.try_read_metadata(file_path) or metadata
        stat = file_path.stat()
        return ProbeResult(
            ok=True,
            path=path,
            architecture=metadata.get("general.architecture"),
            has_chat_template=bool(metadata.get("tokenizer.chat_template")),
            rss_bytes=rss_bytes,
            size_bytes=stat.st_size,
            mtime=stat.st_mtime,
            size_label=metadata.get("general.size_label") or None,
            kv_bytes_per_token=kv_bytes_per_token(header),
            probe_version=PROBE_VERSION,
            probe_window=n_ctx,
            rss_eval_tokens=len(prompt),
        )
    finally:
        if hasattr(llm, "close"):
            llm.close()


def _transient(path: str, exc: BaseException) -> ProbeResult:
    detail = str(exc) or type(exc).__name__
    return ProbeResult(ok=False, path=path, reason=transient_fr(), detail=detail, transient=True)


def record_success(result: ProbeResult) -> None:
    """Persist a successful probe (path, size, mtime, measured cost) in settings.json (AD-7,
    AD-8, AD-20)."""
    if not result.ok:
        return
    probed = config.read_settings().get("probed_models", {})
    probed[result.path] = {
        "size_bytes": result.size_bytes,
        "mtime": result.mtime,
        "architecture": result.architecture,
        "has_chat_template": result.has_chat_template,
        "rss_bytes": result.rss_bytes,
        "size_label": result.size_label,
        "kv_bytes_per_token": result.kv_bytes_per_token,
        "probe_version": result.probe_version,
        "probe_window": result.probe_window,
        "rss_eval_tokens": result.rss_eval_tokens,
        "probed_at": time.time(),
    }
    config.save_setting("probed_models", probed)
    failed = config.read_settings().get("failed_probes", {})
    if failed.pop(result.path, None) is not None:
        config.save_setting("failed_probes", failed)


def _llama_cpp_version() -> str | None:
    try:
        return metadata.version("llama-cpp-python")
    except metadata.PackageNotFoundError:
        return None


def _same_file(entry: dict[str, Any], path: str) -> bool:
    file_path = Path(path)
    if not file_path.is_file():
        return False
    stat = file_path.stat()
    return entry.get("size_bytes") == stat.st_size and entry.get("mtime") == stat.st_mtime


def record_failure(path: str, reason: str) -> None:
    """Remember a deterministic probe failure so the file is not reprobed at every launch.

    Skipped when the file is gone or llama-cpp-python is missing: neither says
    anything about the file itself. A llama-cpp-python upgrade invalidates the entry.
    """
    version = _llama_cpp_version()
    file_path = Path(path)
    if version is None or not file_path.is_file():
        return
    stat = file_path.stat()
    failed = config.read_settings().get("failed_probes", {})
    failed[path] = {
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "reason": reason,
        "llama_cpp_version": version,
        "probe_version": PROBE_VERSION,
    }
    config.save_setting("failed_probes", failed)


def failed_entry(path: str) -> dict[str, Any] | None:
    """The remembered failure for `path`, if still valid (same size, mtime, llama-cpp-python,
    and written by the current probe: lot E, an older one's reason may be English)."""
    entry = config.read_settings().get("failed_probes", {}).get(path)
    if not entry or entry.get("llama_cpp_version") != _llama_cpp_version():
        return None
    if entry.get("probe_version") != PROBE_VERSION:
        return None
    if not _same_file(entry, path):
        return None
    # Story 24: a reason an older WaveStack read in cp1252 is repaired at every read;
    # settings.json is never rewritten by a read (a remembered failure is not probed again,
    # so the stored text stays garbled until the file or llama-cpp-python changes).
    if isinstance(entry.get("reason"), str):
        entry = {**entry, "reason": repair_mojibake(entry["reason"])}
    return entry


# Story 24: what UTF-8 text read as cp1252 shows (« Ã® » for « î », « â€™ » for « ’ »).
_MOJIBAKE_MARKS = ("Ã", "Â", "â€")


def repair_mojibake(text: str) -> str:
    """Story 24: `text` as it was before UTF-8 bytes were decoded as cp1252 (« abÃ®mÃ© » →
    « abîmé »), when it shows the marks of it; unchanged otherwise, or when the repair is
    impossible (never an exception)."""
    if not any(mark in text for mark in _MOJIBAKE_MARKS):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text


def measured(path: str) -> bool:
    """AD-8, lot E (E2): `path` has a valid entry of the current probe, complete: its RSS
    after a real evaluation, its context and the tokens evaluated, and its KV cache (a
    `null` the probe wrote because the GGUF does not say it counts; a missing key does
    not). An older entry (before
    story 17, or before lot E) is not: the file is probed again, at the diagnostic and before
    a hot switch."""
    entry = probed_entry(path)
    return (
        entry is not None
        and entry.get("probe_version") == PROBE_VERSION
        and entry.get("rss_bytes") is not None
        and entry.get("probe_window") is not None
        and entry.get("rss_eval_tokens") is not None
        and "kv_bytes_per_token" in entry
    )


def probed_entry(path: str) -> dict[str, Any] | None:
    """The probe cache entry for `path` (architecture...), if still valid (same size/mtime).

    Lot K (A2): its `kv_bytes_per_token` is recomputed from the GGUF header at every read
    (pure Python, cached per file version), so an entry an older formula wrote (a hybrid
    model counted 4 times too high) is corrected without probing again and without
    rewriting settings.json; the stored value stays when the header is unreadable."""
    entry = config.read_settings().get("probed_models", {}).get(path)
    if not entry or not _same_file(entry, path):
        return None
    header = _header_kv(str(path), entry["size_bytes"], entry["mtime"], False)
    if header is not None and "kv_bytes_per_token" in entry:
        entry = {**entry, "kv_bytes_per_token": header}
    return entry


def gguf_kv_bytes_per_token(path: str | None, *, sliding: bool = False) -> int | None:
    """Lot E (E1): the KV cache's bytes per token of a GGUF on this disk (a file llama-server
    loaded), from its header read in pure Python: no weight, never llama.cpp in WaveStack's
    process (AD-16). `None` when unreadable. Story 2: `sliding`, passed to
    `kv_bytes_per_token` -- only `servers.served_kv` passes `True` (llama-server's default
    cache is reduced for sliding-window layers; Ollama's and the direct path's are not)."""
    if not path:
        return None
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return _header_kv(str(path), stat.st_size, stat.st_mtime, sliding)


@functools.lru_cache(maxsize=32)
def _header_kv(path: str, size: int, mtime: float, sliding: bool = False) -> int | None:
    """Read once per file version (`size`, `mtime`, `sliding`): the diagnostic lists servers
    often. Finition V1 (#19): through `catalog.header_metadata`, which the diagnostic warms
    for the model table anyway (82 % of `discovery.discover()` on the target PC was this
    read, done twice); imported here, `catalog` imports `discovery`, which imports this
    module."""
    from wavestack.models import catalog

    header = catalog.header_metadata(path)
    return kv_bytes_per_token(header[1], sliding=sliding) if header else None


def _args(argv: list[str]) -> tuple[str, int] | None:
    """`[--window N] <path>`: the path last, as the diagnostic writes it."""
    window = DEFAULT_WINDOW
    if argv[:1] == ["--window"]:
        try:
            window = int(argv[1])
        except (IndexError, ValueError):
            return None
        argv = argv[2:]
    return (argv[0], window) if len(argv) == 1 and window > 0 else None


def main() -> int:
    from wavestack.net.guard import install as install_guard

    cfg = config.load_config()
    install_guard(cfg.allowed_hosts)

    args = _args(sys.argv[1:])
    if args is None:
        print(json.dumps({"ok": False, "reason": "Usage: probe.py [--window N] <path>"}))
        return 2

    result = probe_file(*args)
    # Story 24: ASCII JSON (accents as `\u` escapes), whatever the console's code page, and
    # UTF-8 besides: the parent reads it as UTF-8 on every OS (cp1252 garbled it on Windows).
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass  # not a text stream that can be reconfigured: the JSON is ASCII anyway
    print(json.dumps(result.model_dump(mode="json")))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from vct import cuda_pack as C
from vct import updater
from vct.paths import cuda_libs_dir


def make_wheel(path: Path, members: dict) -> str:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pypi_json(filename="x-1-py3-none-win_amd64.whl", sha="a" * 64, url=None, size=10):
    url = url or f"https://files.pythonhosted.org/packages/xx/{filename}"
    return {"urls": [
        {"packagetype": "sdist", "filename": "x-1.tar.gz", "url": url, "digests": {"sha256": "b" * 64}},
        {"packagetype": "bdist_wheel", "filename": "x-1-py3-none-manylinux.whl", "url": url, "digests": {"sha256": "c" * 64}},
        {"packagetype": "bdist_wheel", "filename": filename, "url": url, "size": size, "digests": {"sha256": sha}},
    ]}


def test_pick_wheel_chooses_the_windows_wheel_with_its_checksum():
    w = C.pick_wheel(pypi_json(sha="d" * 64))
    assert w.filename.endswith("win_amd64.whl") and w.sha256 == "d" * 64 and w.size == 10


@pytest.mark.parametrize("data,msg", [
    ({"urls": []}, "no win_amd64"),
    (pypi_json(sha="short"), "no checksum"),
    (pypi_json(url="https://evil.example/x-1-py3-none-win_amd64.whl"), "not on files.pythonhosted.org"),
])
def test_pick_wheel_rejects_bad_data(data, msg):
    with pytest.raises(C.CudaPackError, match=msg):
        C.pick_wheel(data)


def test_only_runtime_dlls_are_selected():
    names = ["nvidia/cublas/bin/cublas64_12.dll", "nvidia/cublas/include/cublas.h", "nvidia/cublas/lib/x64/cublas.lib",
             "nvidia/cudnn/bin/cudnn64_9.dll", "x-1.dist-info/METADATA", "nvidia/a/b/bin/evil.dll", "../evil.dll"]
    assert C.dll_members(names) == ["nvidia/cublas/bin/cublas64_12.dll", "nvidia/cudnn/bin/cudnn64_9.dll"]


def test_extract_writes_only_dlls_under_the_target(tmp_path):
    wheel = tmp_path / "w.whl"
    make_wheel(wheel, {"nvidia/cublas/bin/cublas64_12.dll": b"dll", "nvidia/cublas/include/x.h": b"h"})
    out = C.extract_dlls(wheel, tmp_path / "target")
    assert [p.name for p in out] == ["cublas64_12.dll"]
    assert not (tmp_path / "target/nvidia/cublas/include").exists()


def test_extract_refuses_path_traversal(tmp_path, monkeypatch):
    wheel = tmp_path / "w.whl"
    make_wheel(wheel, {"nvidia/p/bin/ok.dll": b"x"})
    monkeypatch.setattr(C, "dll_members", lambda names: ["nvidia/../../escape.dll"])
    with zipfile.ZipFile(wheel, "a") as z:
        z.writestr("nvidia/../../escape.dll", b"x")
    with pytest.raises(C.CudaPackError, match="unsafe"):
        C.extract_dlls(wheel, tmp_path / "target")
    assert not (tmp_path / "escape.dll").exists()


class Net:
    """Fake PyPI + downloads: each package gets a wheel with the DLLs it should contain."""

    def __init__(self, tmp_path, corrupt=None):
        self.tmp, self.corrupt, self.sha = tmp_path, corrupt, {}
        self.dlls = {"nvidia-cuda-nvrtc-cu12": {"nvidia/cuda_nvrtc/bin/nvrtc64_120_0.dll": b"n"},
                     "nvidia-cublas-cu12": {"nvidia/cublas/bin/cublas64_12.dll": b"c"},
                     "nvidia-cudnn-cu12": {"nvidia/cudnn/bin/cudnn64_9.dll": b"d"}}
        self.wheels = {}
        for name, members in self.dlls.items():
            wheel = tmp_path / f"{name}.src.whl"
            self.sha[name] = make_wheel(wheel, members)
            self.wheels[name] = wheel

    def fetch(self, url):
        name = url.split("/pypi/")[1].split("/")[0]
        return pypi_json(filename=f"{name}-1-py3-none-win_amd64.whl", sha=self.sha[name], size=1_000_000)

    def download(self, url, dest, progress, expected_size=0, timeout=30.0):
        name = Path(url).name.split("-1-py3")[0]
        data = self.wheels[name].read_bytes()
        dest.write_bytes(b"corrupted" if name == self.corrupt else data)
        progress(len(data), len(data))


def run_install(tmp_path, net):
    logs, seen = [], []
    target = tmp_path / "cuda"
    C.install(target, tmp_path / "dl", lambda n, d, t: seen.append(n), logs.append, net.fetch, net.download)
    return target, logs, seen


def test_install_downloads_verifies_unpacks_and_marks_complete(tmp_path):
    target, logs, seen = run_install(tmp_path, Net(tmp_path))
    assert C.is_installed(target)
    assert {p.name for p in (target / "nvidia").glob("*/bin/*.dll")} == {
        "nvrtc64_120_0.dll", "cublas64_12.dll", "cudnn64_9.dll"}
    assert set(seen) == {p.name for p in C.PACKAGES}
    assert not list((tmp_path / "dl").glob("*.whl"))             # downloaded wheels are deleted
    assert "installed" in logs[-1]


def test_corrupt_download_is_rejected_and_nothing_is_marked_complete(tmp_path):
    with pytest.raises(C.CudaPackError, match="checksum"):
        run_install(tmp_path, Net(tmp_path, corrupt="nvidia-cublas-cu12"))
    assert not C.is_installed(tmp_path / "cuda")


def test_network_error_becomes_a_clear_error(tmp_path):
    net = Net(tmp_path)
    def broken(url):
        raise updater.UpdateError("offline")
    with pytest.raises(C.CudaPackError, match="could not reach PyPI"):
        C.install(tmp_path / "cuda", tmp_path / "dl", lambda *a: None, lambda m: None, broken, net.download)


def test_is_installed_needs_marker_and_key_libraries(tmp_path):
    target = tmp_path / "cuda"
    (target / "nvidia/cublas/bin").mkdir(parents=True)
    (target / "nvidia/cublas/bin/cublas64_12.dll").write_bytes(b"x")
    assert not C.is_installed(target)                             # no marker, cuDNN missing
    (target / C.MARKER).write_text("{}")
    assert not C.is_installed(target)                             # still no cuDNN
    (target / "nvidia/cudnn/bin").mkdir(parents=True)
    (target / "nvidia/cudnn/bin/cudnn64_9.dll").write_bytes(b"x")
    assert C.is_installed(target)


def test_interrupted_reinstall_clears_the_old_marker(tmp_path):
    target = tmp_path / "cuda"
    run_install(tmp_path, Net(tmp_path))
    assert C.is_installed(target)
    with pytest.raises(C.CudaPackError):
        C.install(target, tmp_path / "dl2", lambda *a: None, lambda m: None,
                  lambda url: (_ for _ in ()).throw(updater.UpdateError("offline")), Net(tmp_path).download)
    assert not C.is_installed(target)


def _norm(path) -> str:
    """Compare paths independently of the OS running the test (Windows paths on Linux/macOS)."""
    return str(path).replace("\\", "/")


def test_cuda_libs_dir_locations():
    home = Path("/h")
    assert _norm(cuda_libs_dir("win32", {"LOCALAPPDATA": r"C:\Users\u\AppData\Local"}, home)) == \
        "C:/Users/u/AppData/Local/VoiceChatTool/cuda"
    assert _norm(cuda_libs_dir("win32", {}, home)) == _norm(home / "AppData/Local/VoiceChatTool/cuda")
    assert _norm(cuda_libs_dir("win32", {"VCT_DATA_DIR": "/o"}, home)) == "/o/cuda"
    assert _norm(cuda_libs_dir("linux", {}, home)) == _norm(home / ".config/VoiceChatTool/cuda")


def test_transcriber_looks_in_the_downloaded_folder(tmp_path):
    from vct.transcriber import cuda_dll_dirs

    (tmp_path / "nvidia/cublas/bin").mkdir(parents=True)
    assert tmp_path / "nvidia/cublas/bin" in cuda_dll_dirs([tmp_path])


def test_licence_texts_are_kept_next_to_the_libraries(tmp_path):
    wheel = tmp_path / "w.whl"
    make_wheel(wheel, {"nvidia_cublas_cu12-12.9.dist-info/licenses/License.txt": b"EULA",
                       "nvidia_cublas_cu12-12.9.dist-info/METADATA": b"m",
                       "nvidia/cublas/bin/cublas64_12.dll": b"x"})
    out = C.extract_licenses(wheel, tmp_path / "target")
    assert [p.relative_to(tmp_path / "target").as_posix() for p in out] == [
        "licenses/nvidia_cublas_cu12-12.9/License.txt"]
    assert out[0].read_bytes() == b"EULA"


def test_install_also_keeps_the_licence_texts(tmp_path):
    net = Net(tmp_path)
    for name in list(net.dlls):
        dist = name.replace("-", "_")
        net.dlls[name][f"{dist}-1.dist-info/licenses/License.txt"] = b"EULA"
        wheel = tmp_path / f"{name}.src.whl"
        net.sha[name] = make_wheel(wheel, net.dlls[name])
    target, _, _ = run_install(tmp_path, net)
    assert len(list((target / "licenses").glob("*/License.txt"))) == 3

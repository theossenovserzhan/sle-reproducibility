"""Extract prospective unseen-identity LFW features from the local archive."""
from pathlib import Path
from collections import defaultdict
import hashlib
import io
import json
import os
import tarfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parent
FIRST = ROOT.parent
os.environ.setdefault("TORCH_HOME", str(FIRST / "model_cache"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    import torch
    import torchvision
    from PIL import Image
    from torchvision import transforms
    from facenet_pytorch import InceptionResnetV1

    cfg_path = ROOT / "lfw_extended_protocol.json"
    cfg = json.loads(cfg_path.read_text())
    output = ROOT / "data"
    output.mkdir(exist_ok=True)
    archive_path = FIRST / "image_cache/lfw_home/lfw-funneled.tgz"
    with np.load(FIRST / "float_features/lfw_facenet_vggface2.npz") as old:
        old_subjects = {Path(str(row[0])).parts[-2] for row in old["image_ids"]}
    with tarfile.open(archive_path) as archive:
        groups = defaultdict(list)
        for member in archive.getmembers():
            if member.isfile() and member.name.endswith(".jpg"):
                groups[Path(member.name).parts[-2]].append(member.name)
    remaining = sorted(set(groups) - old_subjects)
    rng = np.random.default_rng(cfg["selection_seed"])
    subjects = rng.permutation(remaining).tolist()
    image_ids = [sorted(groups[name])[int(rng.integers(len(groups[name])))] for name in subjects]
    cohorts = ["calibration" if i < 512 else "test_unknown" if i < 1024 else "distractor"
               for i in range(len(subjects))]
    manifest = {"protocol_sha256": digest(cfg_path), "archive_sha256": digest(archive_path),
                "subjects": subjects, "image_ids": image_ids, "cohorts": cohorts,
                "source_images_per_identity": [len(groups[name]) for name in subjects],
                "old_subjects_excluded": len(old_subjects)}
    selection_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    manifest_path = output / "lfw_extended_selection.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise RuntimeError("Frozen extended selection changed")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    progress_path = output / "lfw_extended_progress.json"
    features_path = output / "lfw_extended_features.npy"
    n = len(subjects)
    start = 0
    if features_path.exists() and progress_path.exists():
        progress = json.loads(progress_path.read_text())
        if progress["selection_hash"] != selection_hash:
            raise RuntimeError("Checkpoint selection mismatch")
        start = int(progress["completed"])
        features = np.lib.format.open_memmap(features_path, mode="r+")
    else:
        features = np.lib.format.open_memmap(features_path, mode="w+", dtype=np.float32, shape=(n, 512))
    if start == n:
        print("Extended LFW features already complete", flush=True)
        return
    print(f"New LFW identities={n}, calibration=512, test unknown=512; resuming at {start}", flush=True)
    wanted = {path: i for i, path in enumerate(image_ids) if i >= start}
    images = {}
    with tarfile.open(archive_path) as archive:
        for member in archive:
            if member.name not in wanted:
                continue
            with archive.extractfile(member) as stream:
                image = Image.open(io.BytesIO(stream.read())).convert("RGB")
            image = image.crop((78, 70, 172, 195)).resize((94, 125))
            array = np.asarray(image, dtype=np.float32) / 255.0
            array = np.clip(array * 255.0, 0, 255).astype(np.uint8)
            images[wanted[member.name]] = Image.fromarray(array)
    torch.set_num_threads(2)
    model = InceptionResnetV1(pretrained="vggface2").eval()
    transform = transforms.Compose([transforms.Resize((160, 160)), transforms.ToTensor(),
                                    transforms.Normalize([0.5]*3, [0.5]*3)])
    began = time.monotonic()
    with torch.inference_mode():
        for offset in range(start, n, 32):
            stop = min(n, offset + 32)
            batch = torch.stack([transform(images.pop(i)) for i in range(offset, stop)])
            values = torch.nn.functional.normalize(model(batch), dim=1).numpy()
            if not np.isfinite(values).all():
                raise RuntimeError("Nonfinite embeddings")
            features[offset:stop] = values
            features.flush()
            progress_path.write_text(json.dumps({"selection_hash": selection_hash,
                                                  "completed": stop, "total": n}, indent=2))
            if offset % 256 == 0 or stop == n:
                print(f"Extended LFW FaceNet {stop}/{n}, elapsed_s={time.monotonic()-began:.1f}", flush=True)
    metadata = {"selection_hash": selection_hash, "features_sha256": digest(features_path),
                "script_sha256": digest(__file__), "torch": torch.__version__,
                "torchvision": torchvision.__version__, "numpy": np.__version__,
                "device": "cpu", "threads": 2, "new_identities": n,
                "elapsed_this_run_s": time.monotonic()-began,
                "protocol_sha256": digest(cfg_path), "first_batch_identities_excluded": 192}
    (output / "lfw_extended_extraction.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()

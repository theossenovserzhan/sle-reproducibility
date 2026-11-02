"""Re-extract frozen FaceNet/VGGFace2 features with explicit image provenance.

Custom LFW pipeline matches the earlier notebook's crop/resize and seed. Data
and checkpoint caches are kept in this experiment directory. No random model
or synthetic face fallback is allowed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import socket
import sys
import tarfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
socket.setdefaulttimeout(45)
os.environ.setdefault("TORCH_HOME", str(ROOT / "model_cache"))

from evaluate_float_binary import evaluate
from run_experiments import sha256, write_json


def lfw_images():
    from PIL import Image
    from collections import defaultdict

    archive = ROOT / "image_cache/lfw_home/lfw-funneled.tgz"
    if not archive.exists():
        from sklearn.datasets import fetch_lfw_people
        fetch_lfw_people(data_home=str(ROOT / "image_cache"), funneled=True,
                         resize=1.0, min_faces_per_person=6, color=True,
                         download_if_missing=True)
    print("Loading complete LFW archive, matching sklearn crop, ordering and RandomState(42) shuffle", flush=True)
    with tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers() if m.isfile() and m.name.endswith(".jpg")]
        groups = defaultdict(list)
        for member in members:
            groups[Path(member.name).parts[-2]].append(member.name)
        names = sorted(name for name, paths in groups.items() if len(paths) >= 6)
        target_names = np.unique([name.replace("_", " ") for name in names])
        files, original_labels = [], []
        for name in names:
            paths = sorted(groups[name])
            files.extend(paths)
            original_labels.extend([int(np.searchsorted(target_names, name.replace("_", " ")))] * len(paths))
        indices = np.arange(len(files))
        np.random.RandomState(42).shuffle(indices)
        labels = np.asarray(original_labels)[indices]
        shuffled_files = np.asarray(files)[indices]
    eligible = np.unique(labels)
    if len(eligible) < 192:
        raise RuntimeError(f"Need 192 eligible identities, found {len(eligible)}")
    rng = np.random.default_rng(20260723)
    evaluation_ids = np.sort(rng.choice(eligible, 128, replace=False))
    extra_rng = np.random.default_rng(20261029)
    extras = extra_rng.choice(np.setdiff1d(eligible, evaluation_ids), 64, replace=False)
    cohorts = [evaluation_ids, np.sort(extras[:32]), np.sort(extras[32:])]
    identity_rows, image_ids = [], []
    for group, identities in enumerate(cohorts):
        selection_rng = rng if group == 0 else extra_rng
        for identity in identities:
            chosen = selection_rng.choice(np.flatnonzero(labels == identity), 6, replace=False)
            identity_rows.append(int(identity))
            image_ids.append(shuffled_files[chosen].tolist())
    selected = set(name for row in image_ids for name in row)
    loaded, hashes_by_name = {}, {}
    with tarfile.open(archive) as tar:
        for member in tar:
            if member.name not in selected:
                continue
            with tar.extractfile(member) as stream:
                image = Image.open(io.BytesIO(stream.read())).convert("RGB")
            # Exact sklearn default slice and resize=1.0, followed by the
            # previous notebook's float [0,1] -> uint8 conversion.
            image = image.crop((78, 70, 172, 195)).resize((94, 125))
            array = np.asarray(image, dtype=np.float32) / 255.0
            array = np.clip(array * 255.0, 0, 255).astype(np.uint8)
            if array.std() < 2:
                raise RuntimeError("LFW pixel conversion collapsed")
            loaded[member.name] = Image.fromarray(array, mode="RGB")
            hashes_by_name[member.name] = hashlib.sha256(array.tobytes()).hexdigest()
    result = [[loaded[name] for name in row] for row in image_ids]
    image_hashes = [[hashes_by_name[name] for name in row] for row in image_ids]
    write_json(ROOT / "float_features/lfw_input_audit.json", {
        "archive_sha256": sha256(archive), "archive_jpeg_count": len(members),
        "eligible_at_least_six": len(eligible), "selected_identities": len(identity_rows),
        "selected_images": len(selected), "loader": "complete archive; partial extraction/joblib cache bypassed",
        "reference_loader": "scikit-learn 1.7.2 _lfw.py _fetch_lfw_people and _load_imgs",
        "ordering": "sorted original file paths then RandomState(42).shuffle",
        "crop": [78, 70, 172, 195], "source_resize": [94, 125]})
    return result, identity_rows, image_ids, image_hashes


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "TBIOM-MSLE-revision/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def celeba_rows(identity):
    query = urllib.parse.urlencode({"dataset": "flwrlabs/celeba", "config": "img_align+identity+attr",
                                    "split": "train", "where": f'"celeb_id"={int(identity)}',
                                    "offset": 0, "length": 6})
    return fetch_json("https://datasets-server.huggingface.co/filter?" + query)["rows"]


def celeba_images():
    from PIL import Image

    fixed = np.load(ROOT / "inputs/celeba_128_binary_roots.npz")
    evaluation_ids = list(map(int, fixed["gallery_labels"]))
    result, identity_rows, image_ids, image_hashes = [], [], [], []
    rng = np.random.default_rng(20261029)
    extra_candidates = list(map(int, rng.permutation(np.setdiff1d(np.arange(1, 10178), evaluation_ids))))
    desired = [(identity, True) for identity in evaluation_ids] + [(identity, False) for identity in extra_candidates]
    for identity, required in desired:
        if len(result) == 192:
            break
        rows = celeba_rows(identity)
        if len(rows) < 6:
            if required:
                raise RuntimeError(f"Submitted identity {identity} has fewer than six images in source")
            continue
        images, ids, hashes = [], [], []
        for record in rows:
            src = record["row"]["image"]["src"]
            with urllib.request.urlopen(src, timeout=45) as response:
                payload = response.read()
            hashes.append(hashlib.sha256(payload).hexdigest())
            images.append(Image.open(io.BytesIO(payload)).convert("RGB").copy())
            ids.append(f"celeba_train_row_{record['row_idx']}")
        result.append(images)
        identity_rows.append(identity)
        image_ids.append(ids)
        image_hashes.append(hashes)
        if len(result) % 16 == 0:
            print(f"CelebA selected images: {len(result)}/192 identities", flush=True)
    if len(result) != 192:
        raise RuntimeError("Could not collect the fixed evaluation and disjoint calibration/unknown cohorts")
    return result, identity_rows, image_ids, image_hashes


def extract(dataset):
    import torch
    import torchvision
    from facenet_pytorch import InceptionResnetV1
    from torchvision import transforms

    output = ROOT / "float_features"
    output.mkdir(exist_ok=True)
    archive = output / f"{dataset.lower()}_facenet_vggface2.npz"
    if archive.exists():
        print(f"Reusing frozen feature archive {archive.name}", flush=True)
        return archive
    images, identities, image_ids, hashes = lfw_images() if dataset == "LFW" else celeba_images()
    torch.set_num_threads(2)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = InceptionResnetV1(pretrained="vggface2").eval().to(device)
    transform = transforms.Compose([transforms.Resize((160, 160)), transforms.ToTensor(),
                                    transforms.Normalize([0.5] * 3, [0.5] * 3)])
    all_images = [image for row in images for image in row]
    batches = []
    started = time.monotonic()
    with torch.inference_mode():
        for start in range(0, len(all_images), 16):
            inputs = torch.stack([transform(image) for image in all_images[start:start+16]])
            values = torch.nn.functional.normalize(model(inputs.to(device)), dim=1)
            batches.append(values.cpu().numpy())
            if start % 128 == 0:
                print(f"{dataset} FaceNet: {start+len(inputs)}/{len(all_images)}, device={device}", flush=True)
    features = np.concatenate(batches).astype(np.float32).reshape(len(identities), 6, 512)
    if np.var(features, axis=(0, 1)).mean() < 1e-8:
        raise RuntimeError("embedding collapse")
    np.savez_compressed(archive, embeddings=features, identities=np.asarray(identities),
                        image_ids=np.asarray(image_ids), image_sha256=np.asarray(hashes))
    metadata = {"dataset": dataset, "archive_sha256": sha256(archive), "script_sha256": sha256(__file__),
                "python": sys.version, "torch": torch.__version__, "torchvision": torchvision.__version__,
                "platform": platform.platform(), "device": device, "extraction_wall_s": time.monotonic()-started,
                "shape": list(features.shape), "n_eval": 128, "n_calibration": 32, "n_unknown": 32,
                "identity_selection": "evaluation first, then calibration, then unknown; disjoint",
                "backbone": "InceptionResnetV1 pretrained vggface2",
                "preprocessing": "Resize160x160, ToTensor, Normalize(0.5,0.5); no added detector or alignment",
                "model_checkpoints": {p.name: sha256(p) for p in (ROOT / "model_cache/checkpoints").glob("*.pt")}}
    if dataset == "CelebA":
        with np.load(ROOT / "inputs/celeba_128_binary_roots.npz") as submitted:
            fixed_g = (features[:128, :2].mean(1) >= 0).astype(np.uint8)
            fixed_p = (features[:128, 2:] >= 0).astype(np.uint8).reshape(-1, 512)
            metadata["fixed_split_gallery_bit_mismatches"] = int(np.count_nonzero(fixed_g != submitted["gallery_roots"]))
            metadata["fixed_split_probe_bit_mismatches"] = int(np.count_nonzero(fixed_p != submitted["probe_roots"]))
            metadata["fixed_split_reproduction_note"] = "Nonzero mismatches mean this is a new paired protocol, not exact recovery of submitted image selection."
    write_json(output / f"{dataset.lower()}_extraction.json", metadata)
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["LFW", "CelebA"], required=True)
    args = parser.parse_args()
    archive = extract(args.dataset)
    evaluate(archive, ROOT / "results" / f"paired_{args.dataset.lower()}", args.dataset)

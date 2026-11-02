"""Download only public, pinned model/runtime assets; no face images leave disk."""
from pathlib import Path
import hashlib,json,urllib.request

ROOT=Path(__file__).resolve().parent

def fetch(url,target,expected=None,size=None):
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        temporary=target.with_name(target.name+".partial")
        with urllib.request.urlopen(url,timeout=180) as response,temporary.open("wb") as out:
            while True:
                part=response.read(1024*1024)
                if not part:break
                out.write(part)
        value=hashlib.sha256(temporary.read_bytes()).hexdigest()
        assert (expected is None or value==expected) and (size is None or temporary.stat().st_size==size),(target,value)
        temporary.replace(target)
    value=hashlib.sha256(target.read_bytes()).hexdigest()
    assert expected is None or value==expected
    assert size is None or target.stat().st_size==size
    print("ASSET_READY "+target.name,flush=True)
    return {"source_url":url,"path":str(target.relative_to(ROOT)),"sha256":value,"bytes":target.stat().st_size}

def main():
    cfg=json.loads((ROOT/"second_encoder_protocol.json").read_text())
    base="https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
    models=ROOT/"data/sface_models"
    result={"recognition":fetch(base+"face_recognition_sface/face_recognition_sface_2021dec.onnx",models/"face_recognition_sface_2021dec.onnx",cfg["recognition_sha256"],cfg["recognition_bytes"]),
        "detector":fetch(base+"face_detection_yunet/face_detection_yunet_2023mar.onnx",models/"face_detection_yunet_2023mar.onnx",cfg["detector_sha256"],cfg["detector_bytes"])}
    raw="https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/"
    for name in ("face_recognition_sface","face_detection_yunet"):
        result[name+"_license"]=fetch(raw+name+"/LICENSE",models/(name+"_LICENSE.txt"))
    url="https://pypi.org/pypi/opencv-python-headless/4.11.0.86/json"
    with urllib.request.urlopen(url,timeout=60) as stream:metadata=json.load(stream)
    wheels=[item for item in metadata["urls"] if item["filename"].endswith("cp37-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl")]
    assert len(wheels)==1
    wheel=wheels[0]
    result["opencv_wheel"]=fetch(wheel["url"],ROOT/"data/wheels"/wheel["filename"],wheel["digests"]["sha256"],wheel["size"])
    result["protocol_sha256"]=hashlib.sha256((ROOT/"second_encoder_protocol.json").read_bytes()).hexdigest()
    (ROOT/"data/sface_assets.json").write_text(json.dumps(result,indent=2))
    print("SFACE_ASSETS_COMPLETE",flush=True)

if __name__=="__main__":main()

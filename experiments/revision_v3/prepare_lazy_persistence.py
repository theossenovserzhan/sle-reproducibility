"""Use the proven share-file entry point with the new representation's exact core."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parent

def main():
    virtual=(ROOT/"mpc/msle_lazy_epoch_system.mpc").read_text()
    old=(ROOT/"mpc/msle_persistent_system.mpc").read_text()
    core_marker="current_locs,current_c,current_labels,current_ties ="
    loaded=virtual[:virtual.index("start_timer(30)")]+old[old.index("start_timer(30)"):old.index(core_marker)]+virtual[virtual.index(core_marker):]
    target=ROOT/"mpc/msle_lazy_persistent_system.mpc"
    target.write_text(loaded)
    driver=(ROOT/"persisted_driver.py").read_text()
    driver=driver.replace("msle_system.mpc","msle_lazy_epoch_system.mpc").replace("msle_persistent_system","msle_lazy_persistent_system")
    driver=driver.replace("persisted_","lazy_persisted_")
    marker='from mpc_driver import setup_runtime,write_inputs,run\n'
    assert marker in driver
    driver=driver.replace(marker,marker+'''from reference import masks as raw_masks,evolve as prp_evolve
def masks(keys,locators,bits=512):
    return raw_masks(keys,prp_evolve(keys[0],locators),bits)
def evolve(key,locators):
    return list(locators)

''')
    driver=driver.replace('ROOT/f"data/lfw_gallery_n{n}.npz"','ROOT.parent/f"revision_v2/data/lfw_gallery_n{n}.npz"')
    (ROOT/"persisted_lazy_driver.py").write_text(driver)
    digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    result={"virtual_source_sha256":digest(ROOT/"mpc/msle_lazy_epoch_system.mpc"),"persisted_source_sha256":digest(target),
        "driver_sha256":digest(ROOT/"persisted_lazy_driver.py"),"input_block_from_frozen_share_loader":True,
        "helpers_and_transition_query_tail_identical_to_virtual_source":True,"semantic_change":"Stable secret handles; independent clear oracle derives Pi(key,handle) for masks; actual own-share-file load remains unchanged"}
    assert loaded[:loaded.index("start_timer(30)")]==virtual[:virtual.index("start_timer(30)")]
    assert loaded[loaded.index(core_marker):]==virtual[virtual.index(core_marker):]
    (ROOT/"results/lazy_persistence_source_audit.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()

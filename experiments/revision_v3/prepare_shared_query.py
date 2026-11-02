"""External query client: every computing party receives one sharing evaluation."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parent

def main():
    parent=(ROOT/"mpc/msle_vector_lazy_bucket_poly_query_system.mpc").read_text()
    old=(ROOT/"mpc/msle_lazy_persistent_system.mpc").read_text()
    marker="current_locs,current_c,current_labels,current_ties ="
    inputs=old[old.index("start_timer(30)"):old.index(marker)]
    old_probe='''if MODE != 1:
    probe = sint.Array(D)
    probe.input_from(1)
    threshold = sint.get_input_from(1)
'''
    new_probe='''if MODE != 1:
    # Client inputs are degree-two polynomial evaluations, not plaintext
    # probe bits at one computing server. Reconstruct only on secret wires.
    probe=sint.Array(D)
    probe.assign_all(0)
    threshold=sint(0)
    weights=[5,-10,10,-5,1]
    for party in range(5):
        local_probe=sint.Array(D)
        local_probe.input_from(party)
        local_threshold=sint.get_input_from(party)
        probe.assign_vector(probe.get_vector()+weights[party]*local_probe.get_vector())
        threshold+=weights[party]*local_threshold
'''
    assert old_probe in inputs
    inputs=inputs.replace(old_probe,new_probe)
    source=parent[:parent.index("start_timer(30)")]+inputs+parent[parent.index(marker):]
    (ROOT/"mpc/msle_shared_query_system.mpc").write_text(source)
    driver=(ROOT/"persisted_lazy_driver.py").read_text()
    driver=driver.replace("msle_lazy_epoch_system.mpc","msle_vector_lazy_bucket_poly_query_system.mpc").replace("msle_lazy_persistent_system","msle_shared_query_system").replace("lazy_persisted_","shared_query_")
    old='    if mode!=1:by_party[1].extend([*map(int,probe),threshold])'
    new='''    query_dealing_seconds=0.0
    if mode!=1:
        query_started=time.monotonic()
        values=[*map(int,probe),threshold]
        first=[secrets.randbelow(P) for _ in values]
        second=[secrets.randbelow(P) for _ in values]
        evaluations=[[(value+a*(party+1)+b*(party+1)**2)%P for value,a,b in zip(values,first,second)] for party in range(5)]
        weights=(5,-10,10,-5,1)
        assert all(sum(weights[j]*evaluations[j][i] for j in range(5))%P==value for i,value in enumerate(values))
        for party in range(5):by_party[party].extend(evaluations[party])
        query_dealing_seconds=time.monotonic()-query_started
'''
    assert old in driver
    driver=driver.replace(old,new)
    marker='"whole_state_read_from_own_share_file":True,"plaintext_db_or_index_input":False}'
    assert marker in driver
    driver=driver.replace(marker,'"whole_state_read_from_own_share_file":True,"plaintext_db_or_index_input":False,"plaintext_probe_input":False,"query_client_sharing_degree":2,"query_client_dealing_seconds":query_dealing_seconds,"query_sharing_reconstruction_checked_all_fields":bool(mode!=1)}')
    (ROOT/"persisted_shared_query_driver.py").write_text(driver)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    result={"parent_kernel_sha256":sha(ROOT/"mpc/msle_vector_lazy_bucket_poly_query_system.mpc"),"new_source_sha256":sha(ROOT/"mpc/msle_shared_query_system.mpc"),
        "new_driver_sha256":sha(ROOT/"persisted_shared_query_driver.py"),"changes":"Only query/threshold ingestion and own-share-file state loading; normalized helpers and transition/query tail match the validated vectorized virtual kernel.",
        "privacy_scope":"Trusted external client deals degree-two shares over private channels; at most2 passive computing parties; honest bit-valued query interface. Not malicious-input validation."}
    (ROOT/"results/shared_query_source_audit.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()

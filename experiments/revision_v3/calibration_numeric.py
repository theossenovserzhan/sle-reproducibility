"""Preserve strict order-statistic thresholds under NumPy2 scalar promotion."""
import numpy as np

def binary_scores(left,right):
    # 0/1 dot products and the integer Hamming result are exact in float32
    # at the studied widths. Cast BEFORE comparing nextafter(float64) cutoffs.
    assert left.shape[1]<2**21
    product=left@right.T
    return np.asarray(2*product-left.sum(1)[:,None]-right.sum(1)[None,:],dtype=np.float64)

def self_test():
    values=np.array([-101,-100,-99],dtype=np.float32)
    threshold=float(np.nextafter(-100.,np.inf))
    assert (values>=threshold).tolist()==[False,True,True] # reproduces defect
    assert (values.astype(np.float64)>=threshold).tolist()==[False,False,True]
    left=np.array([[0,1,1],[1,0,1]],dtype=np.float32)
    right=np.array([[0,1,1],[0,0,0]],dtype=np.float32)
    scores=binary_scores(left,right)
    assert scores.dtype==np.float64
    assert np.array_equal(scores,np.array([[0,-2],[-2,-2]]))
    assert not np.any(scores>=float(np.nextafter(0.,np.inf)))
    tied=np.repeat(np.arange(-127,-111,dtype=np.float32),32)
    cutoff=float(np.nextafter(float(tied[-6]),np.inf))
    assert np.count_nonzero(tied>=cutoff)==32
    assert np.count_nonzero(tied.astype(np.float64)>=cutoff)==0
    return {"strict_boundary":True,"all_tied_boundary":True,"independent_hamming_matrix":True,"numpy":np.__version__}

if __name__=="__main__":print(self_test())

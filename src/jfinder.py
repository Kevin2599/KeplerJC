from __future__ import division
from core import *
from mugp import MuGP

class JumpFinder(object):
    def __init__(self, cadence, flux, kernel='e', chunk_size=128, **kwargs):
        """Discontinuity detection for photometric time series.

        Parameters
        ----------
        cadence  : 1D array
        flux  : 1D array

        Keyword arguments
        -----------------
        excluded_cadences : list of cadence ranges to be excluded

        n_iterations   : int
        min_gap_width  : int
        min_separation : int

        sigma    : float
        csize    :   int
        wnoise   : float
        clength  :   int

        Returns
        -------
        jumps : list of jump objects
        """
        self.gp = MuGP(kernel=kernel)
        self._cadence_o = np.asarray(cadence)
        self._flux_o = np.asarray(flux)
        self.hps = None
        self.hp  = None

        self.mask = np.isfinite(self._cadence_o) & np.isfinite(self._flux_o)
        self.cadence = self._cadence_o[self.mask]
        self.flux    = self._flux_o[self.mask] / np.nanmedian(self._flux_o) - 1.

        self.chunk_size = cs = chunk_size
        self.n_chunks   = nc = self.flux.size // chunk_size
        self.chunks = [s_[i*cs:(i+1)*cs] for i in range(nc)] + [s_[cs*nc:]]
        
        #excluded_cadences = kwargs.get('excluded_cadences', [])
    
        
    def minfun(self, pv, sl):
        if any(pv <= 0): 
            return inf
        self.gp.set_parameters(pv)
        return -self.gp.lnlikelihood(self.cadence[sl], self.flux[sl])

    
    def learn_hp(self, max_chunks=50):
        self.hps = [fmin(self.minfun, self.gp.pv0, args=(sl,), disp=False)
                        for sl in self.chunks[:max_chunks]]
        self.hp = median(self.hps, 0)

        
    def compute_lnl(self):
        self.lnlike = lnlike = zeros_like(self.flux)
        self.gp.set_parameters(self.hp)
        
        for sl in self.chunks:
            breaks = [None]+list(self.cadence[sl])
            lnl = array([self.gp.lnlikelihood(self.cadence[sl], self.flux[sl], br) for br in breaks])
            lnl[1] = lnl[2]
            lnlike[sl] = lnl[1:]-lnl[0]
        return lnlike

    
    def find_jumps(self, sigma=10, learn=True, cln=True):
        if learn:
            self.learn_hp(max_chunks=15)
        if cln:
            self.compute_lnl()
        
        mlnlike = self.lnlike - mf(self.lnlike, 90)
        sigma  = 1.4826 * median(abs(mlnlike-median(mlnlike)))
        lnmask = mlnlike > 15*sigma
        labels, nl = label(ndi.binary_dilation(lnmask, iterations=5))
        jumps = [self.cadence[argmax(where(labels==i, self.lnlike, 0))] for i in range(1,nl+1)]
        jumps = [j for j in jumps if j>0]
        
        ## Compute the amplitudes
        ## ----------------------
        jids   = [self.cadence.searchsorted(j) for j in jumps]
        slices = [s_[max(0,j-self.chunk_size//2):min(self.flux.size-1, j+self.chunk_size//2)] for j in jids]
        
        amplitudes = []
        for jump,sl in zip(jumps,slices):  
            cad = self.cadence[sl]
            self.gp.compute(cad, jump)
            pr = self.gp.predict(self.flux[sl])
            k = np.argmin(np.abs(cad-jump))
            amplitudes.append(pr[k]-pr[k-1])
        return [Jump(j,a) for j,a in zip(jumps,amplitudes)]

    
    def plot(self, chunk=0, ax=None):
        if ax is None:
            fig, ax = subplots(1,1)
            
        sl = self.chunks[chunk]
        self.gp.set_parameters(self.hp)
        self.gp.compute(self.cadence[sl])
        ax.plot(self.cadence[sl], self.flux[sl], '.', c='0.5')
        ax.plot(self.cadence[sl], self.gp.predict(self.flux[sl]), c='w', lw=4, alpha=0.7)
        ax.plot(self.cadence[sl], self.gp.predict(self.flux[sl]), c='k', lw=2)

# pylint: disable=too-few-public-methods, method-hidden
""" Contains Sampler-classes. """

from copy import copy
import numpy as np
try:
    import scipy.stats as ss
except ImportError:
    pass

# if empirical probability of truncation region is less than
# this number, truncation throws a ValueError
SMALL_SHARE = 1e-2

# aliases for Numpy, Scipy-Stats, TensorFlow-samplers
ALIASES = {
    'n': {'np': 'normal', 'ss': 'norm', 'tf': 'Normal'},
    'u': {'np': 'uniform', 'ss': 'uniform', 'tf': 'Uniform'},
    'mvn': {'np': 'multivariate_normal', 'ss': 'multivariate_normal'},
    'e': {'np': 'exponential', 'ss': 'expon', 'tf': 'Exponential'},
    'g': {'np': 'gamma', 'ss': 'gamma', 'tf': 'Gamma'},
    'be' : {'np': 'beta', 'ss': 'beta', 'tf': 'Beta'},
    'mnm': {'np': 'multinomial', 'ss': 'multinomial', 'tf': 'Multinomial'},
    'f': {'np': 'f', 'ss': 'f'},
    'p': {'np': 'poisson', 'ss': 'poisson'},
    'w': {'np': 'weibull', 'ss': 'dweibull'},
    'ln': {'np': 'lognormal', 'ss': 'lognorm'},
    'b' : {'np': 'binomial', 'ss': 'binom'},
    'chi2': {'np': 'chisquare', 'ss': 'chi2'},
    'c': {'np': 'choice'}
}

def _get_method_by_alias(alias, module, tf_distributions=None):
    """ Fetch fullname of a randomizer from ``scipy.stats``, ``tensorflow`` or
    ``numpy`` by its alias or fullname.
    """
    rnd_submodules = {'np': np.random,
                      'tf': tf_distributions,
                      'ss': ss}
    # fetch fullname
    fullname = ALIASES.get(alias, {module: alias for module in ['np', 'tf', 'ss']}).get(module, None)
    if fullname is None:
        raise ValueError("Distribution %s has no implementaion in module %s" % (alias, module))

    # check that the randomizer is implemented in corresponding module
    if not hasattr(rnd_submodules[module], fullname):
        raise ValueError("Distribution %s has no implementaion in module %s" % (fullname, module))

    return fullname

def arithmetize(cls):
    """ Add arithmetic operations to Sampler-class.
    """
    ops = ['__add__', '__mul__', '__truediv__', '__sub__', '__pow__', '__floordiv__', '__mod__']
    rops = ['__radd__', '__rmul__', '__rtruediv__', '__rsub__', '__rpow__', '__rfloordiv__', '__rmod__']

    for oper, rop in zip(ops, rops):
        def transform(self, other, fake=oper):
            """ Arithmetic operation on couple of Samplers.

            Implemented via corresponding operation in ndarrays.

            Parameters
            ----------
            other : Sampler
                second Sampler, the operation is applied to.

            Returns
            -------
            Sampler
                resulting sampler.
            """
            result = cls()
            if isinstance(other, cls):
                result.sample = lambda size: getattr(self.sample(size), fake)(other.sample(size))
            else:
                result.sample = lambda size: getattr(self.sample(size), fake)(np.array(other))
            return result

        def rtransform(self, other, fake=rop):
            """ Arithmetic operation on Sampler and array/number.

            Implemented via corresponding operation in ndarrays.

            Parameters
            ----------
            other : Sampler or np.ndarray
                second item, the operation is applied to.

            Returns
            -------
            Sampler
                resulting sampler.
            """
            result = cls()
            other = np.array(other)
            result.sample = lambda size: getattr(self.sample(size), fake)(other)
            return result

        setattr(cls, oper, transform)
        setattr(cls, rop, rtransform)

    return cls

@arithmetize
class Sampler():
    """ Base class Sampler that implements algebra of Samplers.

    Attributes
    ----------
    weight : float
        weight of Sampler self in mixtures.
    """
    def __init__(self, *args, **kwargs):
        self.__array_priority__ = 100
        self.weight = 1.0

        # if dim is supplied, redefine sampling method
        if 'dim' in kwargs:
            # assemble stacked sampler
            dim = kwargs.pop('dim')
            stacked = type(self)(*args, **kwargs)
            for _ in range(dim - 1):
                stacked = type(self)(*args, **kwargs) & stacked

            # redefine sample of self
            self.sample = stacked.sample

    def sample(self, size):
        """ Sampling method of a sampler.

        Parameters
        ----------
        size : int
            lentgh of sample to be generated.

        Returns
        -------
        np.ndarray
            Array of size (len, Sampler's dimension).
        """
        raise NotImplementedError('The method should be implemented in child-classes!')

    def __or__(self, other):
        """ Implementation of '|' operation for two instances of Sampler-class.

        The result is the mixture of two samplers. Weights are taken from
        samplers' weight-attributes.

        Parameters
        ----------
        other : Sampler
            the sampler to be added to self.

        Returns
        -------
        Sampler
            resulting mixture of two samplers.
        """
        # init new Sampler
        result = Sampler()

        # calculate probs of samplers in mixture
        _ws = np.array([self.weight, other.weight])
        result.weight = np.sum(_ws)
        _normed = _ws / np.sum(_ws)

        # redefine the sampling procedure of a sampler
        def concat_sample(size):
            """ Sampling procedure of a mixture of two samplers.
            """
            _up_size = np.random.binomial(size, _normed[0])
            _low_size = size - _up_size

            _up = self.sample(size=_up_size)
            _low = other.sample(size=_low_size)
            _sample = np.concatenate([_up, _low])
            sample = _sample[np.random.permutation(size)]

            return sample

        result.sample = concat_sample
        return result

    def __and__(self, other):
        """ Implementation of '&' operation for instance of Sampler-class.

        Two cases are possible: if ``other`` is numeric, then "&"-operation changes
        the weight of a sampler. Otherwise, if ``other`` is also a Sampler, the resulting
        Sampler is a multidimensional sampler, with starting coordinates being sampled from
        ``self``, and trailing - from ``other``.

        Parameters
        ----------
        other : int or float or Sampler
            the sampler/weight for multiplication.

        Returns
        -------
        Sampler
            result of the multiplication.
        """
        result = Sampler()

        # case of numeric other
        if isinstance(other, (float, int)):
            result.sample = self.sample
            result.weight *= other

        # when other is a Sampler
        elif isinstance(other, Sampler):
            def concat_sample(size):
                """ Sampling procedure of a product of two samplers.
                """
                _left = self.sample(size)
                _right = other.sample(size)
                return np.concatenate([_left, _right], axis=1)

            result.sample = concat_sample

        return result

    def __rand__(self, other):
        """ Implementation of '&' operation on a weight for instance of Sampler-class.

        see docstring of Sampler.__and__.
        """
        return self & other

    def apply(self, transform):
        """ Apply a transformation to the sampler.

        Build new sampler, which sampling function is given by `transform(self.sample(size))``.

        Parameters
        ----------
        transform : callable
            function, that takes ndarray of shape (size, dim_sampler) and produces
            ndarray of shape (size, new_dim_sampler).

        Returns
        -------
        Sampler
            instance of class Sampler with redefined method `sample`.
        """
        result = Sampler()
        result.sample = lambda size: transform(self.sample(size))
        return result

    def truncate(self, high=None, low=None, expr=None, prob=0.5):
        """ Truncate a sampler. Resulting sampler poduces points satisfying ``low <= pts <= high``.
        If ``expr`` is suplied, the condition is ``low <= expr(pts) <= high``.

        Parameters
        ----------
        high : ndarray, list, float
            upper truncation-bound.
        low : ndarray, list, float
            lower truncation-bound.
        expr : callable, optional.
            Some vectorized function. Accepts points of sampler, returns either bool or float.
            In case of float, either high or low should also be supplied.
        prob : float, optional
            estimate of P(truncation-condtion is satisfied). When supplied,
            can improve the performance of sampling-method of truncated sampler.

        Returns
        -------
        Sampler
            new Sampler-instance, truncated version of self.
        """
        # clean up truncation params
        if high is not None:
            high = np.array(high).reshape(1, -1)
        if low is not None:
            low = np.array(low).reshape(1, -1)

        def truncated(size):
            """ Truncated sampling method.
            """
            if size == 0:
                return self.sample(size=0)

            # set batch-size
            expectation = size / prob
            sigma = np.sqrt(size * (1 - prob) / (prob**2))
            batch_size = int(expectation + 2 * sigma)

            # sample, filter out, concat
            ctr = 0
            cumulated = 0
            samples = []
            while cumulated < size:
                # sample points and compute condition-vector
                sample = self.sample(size=batch_size)
                cond = np.ones(shape=batch_size).astype(np.bool)
                if low is not None:
                    if expr is not None:
                        cond &= np.greater_equal(expr(sample).reshape(batch_size, -1), low).all(axis=1)
                    else:
                        cond &= np.greater_equal(sample, low).all(axis=1)

                if high is not None:
                    if expr is not None:
                        cond &= np.less_equal(expr(sample).reshape(batch_size, -1), high).all(axis=1)
                    else:
                        cond &= np.less_equal(sample, high).all(axis=1)

                if high is None and low is None:
                    cond &= expr(sample).all(axis=1)

                # check that truncation-prob is not to small
                _share = np.sum(cond) / batch_size
                if _share < SMALL_SHARE and ctr > 0:
                    raise ValueError('Probability of region of interest is too small. Try other truncation bounds')

                # get points from region of interest
                samples.append(sample[cond])
                cumulated += np.sum(cond)
                ctr += 1

            return np.concatenate(samples)[:size]

        # init new Sampler, define its sampling-method
        result = Sampler()
        result.sample = truncated

        return result


class ConstantSampler(Sampler):
    """ Sampler of a constant.

    Parameters
    ----------
    constant : int, str, float, list
        constant, associated with the Sampler. Can be multidimensional,
        e.g. list or np.ndarray.

    Attributes
    ----------
    constant : np.array
        vectorized constant, associated with the Sampler.

    """
    def __init__(self, constant, **kwargs):
        self.constant = np.array(constant).reshape(1, -1)
        super().__init__(constant, **kwargs)

    def sample(self, size):
        """ Sampling method of ``ConstantSampler``.

        Repeats sampler's constant ``size`` times.

        Parameters
        ----------
        size : int
            the size of sample to be generated.

        Returns
        -------
        np.ndarray
            array of shape (size, 1) containing Sampler's constant.
        """
        return np.repeat(self.constant, repeats=size, axis=0)

class NumpySampler(Sampler):
    """ Sampler based on a distribution from np.random.

    Parameters
    ----------
    name : str
        name of a distribution (method from np.random) or its alias.
    seed : int
        random seed for setting up sampler's state.
    **kwargs
        additional keyword-arguments defining properties of specific
        distribution. E.g., ``loc`` for name='normal'.

    Attributes
    ----------
    name : str
        name of a distribution (method from np.random).
    _params : dict
        dict of args for Sampler's distribution.
    """
    def __init__(self, name, seed=None, **kwargs):
        super().__init__(name, seed, **kwargs)
        name = _get_method_by_alias(name, 'np')
        self.name = name
        self._params = copy(kwargs)
        self.state = np.random.RandomState(seed=seed)


    def sample(self, size):
        """ Sampling method of ``NumpySampler``.

        Generates random samples from distribution ``self.name``.

        Parameters
        ----------
        size : int
            the size of sample to be generated.

        Returns
        -------
        np.ndarray
            array of shape (size, Sampler's dimension).
        """
        sampler = getattr(self.state, self.name)
        sample = sampler(size=size, **self._params)
        if len(sample.shape) == 1:
            sample = sample.reshape(-1, 1)
        return sample

class ScipySampler(Sampler):
    """ Sampler based on a distribution from `scipy.stats`.

    Parameters
    ----------
    name : str
        name of a distribution, class from `scipy.stats`, or its alias.
    seed : int
        random seed for setting up sampler's state.
    **kwargs
        additional parameters for specification of the distribution.
        For instance, `scale` for name='gamma'.

    Attributes
    ----------
    name : str
        name of a distribution (class from `scipy.stats`).
    state : int
        sampler's random state.
    """
    def __init__(self, name, seed=None, **kwargs):
        super().__init__(name, seed, **kwargs)
        name = _get_method_by_alias(name, 'ss')
        self.name = name
        self.state = np.random.RandomState(seed=seed)
        self.distr = getattr(ss, self.name)(**kwargs)

    def sample(self, size):
        """ Sampling method of ``ScipySampler``.

        Generates random samples from distribution ``self.name``.

        Parameters
        ----------
        size : int
            the size of sample to be generated.

        Returns
        -------
        np.ndarray
            array of shape (size, Sampler's dimension).
        """
        sampler = self.distr.rvs
        sample = sampler(size=size, random_state=self.state)
        if len(sample.shape) == 1:
            sample = sample.reshape(-1, 1)
        return sample

class HistoSampler(Sampler):
    """ Sampler based on a histogram, output of `np.histogramdd`.

    Parameters
    ----------
    histo : tuple
        histogram, on which the sampler is based.
        Make sure that it is unnormalized (`normed=False` in `np.histogramdd`).
    edges : list
        list of len=histo_dimension, contains edges of bins along axes.
    seed : int
        random seed for setting up sampler's state.

    Attributes
    ----------
    bins : np.ndarray
        bins of base-histogram (see `np.histogramdd`).
    edges : list
        edges of base-histogram.

    Notes
    -----
        The sampler should be based on unnormalized histogram.
        if `histo`-arg is supplied, it is used for histo-initilization.
        Otherwise, edges should be supplied. In this case all bins are empty.
    """
    def __init__(self, histo=None, edges=None, seed=None, **kwargs):
        super().__init__(histo, edges, seed, **kwargs)
        if histo is not None:
            self.bins = histo[0]
            self.edges = histo[1]
        elif edges is not None:
            self.edges = edges
            bins_shape = [len(axis_edge) - 1 for axis_edge in edges]
            self.bins = np.zeros(shape=bins_shape, dtype=np.float32)
        else:
            raise ValueError('Either `histo` or `edges` should be specified.')

        self.l_all = cart_prod(*(range_dim[:-1] for range_dim in self.edges))
        self.h_all = cart_prod(*(range_dim[1:] for range_dim in self.edges))

        self.probs = (self.bins / np.sum(self.bins)).reshape(-1)
        self.nonzero_probs_idx = np.asarray(self.probs != 0.0).nonzero()[0]
        self.nonzero_probs = self.probs[self.nonzero_probs_idx]

        self.state = np.random.RandomState(seed=seed)
        self.state_sampler = self.state.uniform

    def sample(self, size):
        """ Sampling method of ``HistoSampler``.

        Generates random samples from distribution, represented by
        histogram (self.bins, self.edges).

        Parameters
        ----------
        size : int
            the size of sample to be generated.

        Returns
        -------
        np.ndarray
            array of shape (size, histo dimension).
        """
        # Choose bins to use according to non-zero probabilities
        bin_nums = np.random.choice(self.nonzero_probs_idx, p=self.nonzero_probs, size=size)

        # uniformly generate samples from selected boxes
        low, high = self.l_all[bin_nums], self.h_all[bin_nums]
        return self.state_sampler(low=low, high=high)

    def update(self, points):
        """ Update bins of sampler's histogram by throwing in additional points.

        Parameters
        ----------
        points : np.ndarray
            Array of points of shape (n_points, histo_dimension).
        """
        histo_update = np.histogramdd(sample=points, bins=self.edges)
        self.bins += histo_update[0]


def cart_prod(*arrs):
    """ Get array of cartesian tuples from arbitrary number of arrays.

    Faster version of itertools.product. The order of tuples is lexicographic.

    Parameters
    ----------
    arrs : tuple, list or ndarray.
        Any sequence of ndarrays.

    Returns
    -------
    ndarray
        2d-array with rows (arr[0][i], arr[2][j],...,arr[n][k]).
    """
    grids = np.meshgrid(*arrs, indexing='ij')
    return np.stack(grids, axis=-1).reshape(-1, len(arrs))

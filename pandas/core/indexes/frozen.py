"""
frozen (immutable) data structures to support MultiIndexing

These are used for:

- .names (FrozenList)
- .levels & .codes (FrozenNDArray)

"""
import warnings

import numpy as np

from pandas.core.dtypes.cast import coerce_indexer_dtype

from pandas.core.base import PandasObject

from pandas.io.formats.printing import pprint_thing


class FrozenList(PandasObject, list):
    """
    Container that doesn't allow setting item *but*
    because it's technically non-hashable, will be used
    for lookups, appropriately, etc.
    """

    # Side note: This has to be of type list. Otherwise,
    #            it messes up PyTables type checks.

    def union(self, other) -> "FrozenList":
        """
        Returns a FrozenList with other concatenated to the end of self.

        Parameters
        ----------
        other : array-like
            The array-like whose elements we are concatenating.

        Returns
        -------
        diff : FrozenList
            The collection difference between self and other.
        """
        if isinstance(other, tuple):
            other = list(other)
        return type(self)(super().__add__(other))

    def difference(self, other) -> "FrozenList":
        """
        Returns a FrozenList with elements from other removed from self.

        Parameters
        ----------
        other : array-like
            The array-like whose elements we are removing self.

        Returns
        -------
        diff : FrozenList
            The collection difference between self and other.
        """
        other = set(other)
        temp = [x for x in self if x not in other]
        return type(self)(temp)

    # TODO: Consider deprecating these in favor of `union` (xref gh-15506)
    __add__ = __iadd__ = union

    def __getitem__(self, n):
        if isinstance(n, slice):
            return self.__class__(super().__getitem__(n))
        return super().__getitem__(n)

    def __radd__(self, other):
        if isinstance(other, tuple):
            other = list(other)
        return self.__class__(other + list(self))

    def __eq__(self, other) -> bool:
        if isinstance(other, (tuple, FrozenList)):
            other = list(other)
        return super().__eq__(other)

    __req__ = __eq__

    def __mul__(self, other):
        return self.__class__(super().__mul__(other))

    __imul__ = __mul__

    def __reduce__(self):
        return self.__class__, (list(self),)

    def __hash__(self):
        return hash(tuple(self))

    def _disabled(self, *args, **kwargs):
        """This method will not function because object is immutable."""
        raise TypeError(
            "'{cls}' does not support mutable operations.".format(
                cls=self.__class__.__name__
            )
        )

    def __str__(self) -> str:
        return pprint_thing(self, quote_strings=True, escape_chars=("\t", "\r", "\n"))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)})"

    __setitem__ = __setslice__ = __delitem__ = __delslice__ = _disabled
    pop = append = extend = remove = sort = insert = _disabled


class FrozenNDArray(PandasObject, np.ndarray):

    # no __array_finalize__ for now because no metadata
    def __new__(cls, data, dtype=None, copy=False):
        warnings.warn(
            "\nFrozenNDArray is deprecated and will be removed in a "
            "future version.\nPlease use `numpy.ndarray` instead.\n",
            FutureWarning,
            stacklevel=2,
        )

        if copy is None:
            copy = not isinstance(data, FrozenNDArray)
        res = np.array(data, dtype=dtype, copy=copy).view(cls)
        return res

    def _disabled(self, *args, **kwargs):
        """This method will not function because object is immutable."""
        raise TypeError(
            "'{cls}' does not support mutable operations.".format(cls=self.__class__)
        )

    __setitem__ = __setslice__ = __delitem__ = __delslice__ = _disabled
    put = itemset = fill = _disabled

    def _shallow_copy(self):
        return self.view()

    def values(self):
        """returns *copy* of underlying array"""
        arr = self.view(np.ndarray).copy()
        return arr

    def __repr__(self) -> str:
        """
        Return a string representation for this object.
        """
        prepr = pprint_thing(self, escape_chars=("\t", "\r", "\n"), quote_strings=True)
        return f"{type(self).__name__}({prepr}, dtype='{self.dtype}')"

    def searchsorted(self, value, side="left", sorter=None):
        """
        Find indices to insert `value` so as to maintain order.

        For full documentation, see `numpy.searchsorted`

        See Also
        --------
        numpy.searchsorted : Equivalent function.
        """

        # We are much more performant if the searched
        # indexer is the same type as the array.
        #
        # This doesn't matter for int64, but DOES
        # matter for smaller int dtypes.
        #
        # xref: https://github.com/numpy/numpy/issues/5370
        try:
            value = self.dtype.type(value)
        except ValueError:
            pass

        return super().searchsorted(value, side=side, sorter=sorter)


def _ensure_frozen(array_like, categories, copy=False):
    array_like = coerce_indexer_dtype(array_like, categories)
    array_like = array_like.view(FrozenNDArray)
    if copy:
        array_like = array_like.copy()
    return array_like

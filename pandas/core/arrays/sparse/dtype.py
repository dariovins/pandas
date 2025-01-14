"""Sparse Dtype"""

import re
from typing import Any

import numpy as np

from pandas.core.dtypes.base import ExtensionDtype
from pandas.core.dtypes.cast import astype_nansafe
from pandas.core.dtypes.common import (
    is_bool_dtype,
    is_object_dtype,
    is_scalar,
    is_string_dtype,
    pandas_dtype,
)
from pandas.core.dtypes.dtypes import register_extension_dtype
from pandas.core.dtypes.missing import isna, na_value_for_dtype

from pandas._typing import Dtype


@register_extension_dtype
class SparseDtype(ExtensionDtype):
    """
    Dtype for data stored in :class:`SparseArray`.

    This dtype implements the pandas ExtensionDtype interface.

    .. versionadded:: 0.24.0

    Parameters
    ----------
    dtype : str, ExtensionDtype, numpy.dtype, type, default numpy.float64
        The dtype of the underlying array storing the non-fill value values.
    fill_value : scalar, optional
        The scalar value not stored in the SparseArray. By default, this
        depends on `dtype`.

        =========== ==========
        dtype       na_value
        =========== ==========
        float       ``np.nan``
        int         ``0``
        bool        ``False``
        datetime64  ``pd.NaT``
        timedelta64 ``pd.NaT``
        =========== ==========

        The default value may be overridden by specifying a `fill_value`.

    Attributes
    ----------
    None

    Methods
    -------
    None
    """

    # We include `_is_na_fill_value` in the metadata to avoid hash collisions
    # between SparseDtype(float, 0.0) and SparseDtype(float, nan).
    # Without is_na_fill_value in the comparison, those would be equal since
    # hash(nan) is (sometimes?) 0.
    _metadata = ("_dtype", "_fill_value", "_is_na_fill_value")

    def __init__(self, dtype: Dtype = np.float64, fill_value: Any = None) -> None:

        if isinstance(dtype, type(self)):
            if fill_value is None:
                fill_value = dtype.fill_value
            dtype = dtype.subtype

        dtype = pandas_dtype(dtype)
        if is_string_dtype(dtype):
            dtype = np.dtype("object")

        if fill_value is None:
            fill_value = na_value_for_dtype(dtype)

        if not is_scalar(fill_value):
            raise ValueError(
                "fill_value must be a scalar. Got {} instead".format(fill_value)
            )
        self._dtype = dtype
        self._fill_value = fill_value

    def __hash__(self):
        # Python3 doesn't inherit __hash__ when a base class overrides
        # __eq__, so we explicitly do it here.
        return super().__hash__()

    def __eq__(self, other) -> bool:
        # We have to override __eq__ to handle NA values in _metadata.
        # The base class does simple == checks, which fail for NA.
        if isinstance(other, str):
            try:
                other = self.construct_from_string(other)
            except TypeError:
                return False

        if isinstance(other, type(self)):
            subtype = self.subtype == other.subtype
            if self._is_na_fill_value:
                # this case is complicated by two things:
                # SparseDtype(float, float(nan)) == SparseDtype(float, np.nan)
                # SparseDtype(float, np.nan)     != SparseDtype(float, pd.NaT)
                # i.e. we want to treat any floating-point NaN as equal, but
                # not a floating-point NaN and a datetime NaT.
                fill_value = (
                    other._is_na_fill_value
                    and isinstance(self.fill_value, type(other.fill_value))
                    or isinstance(other.fill_value, type(self.fill_value))
                )
            else:
                fill_value = self.fill_value == other.fill_value

            return subtype and fill_value
        return False

    @property
    def fill_value(self):
        """
        The fill value of the array.

        Converting the SparseArray to a dense ndarray will fill the
        array with this value.

        .. warning::

           It's possible to end up with a SparseArray that has ``fill_value``
           values in ``sp_values``. This can occur, for example, when setting
           ``SparseArray.fill_value`` directly.
        """
        return self._fill_value

    @property
    def _is_na_fill_value(self):
        return isna(self.fill_value)

    @property
    def _is_numeric(self):
        return not is_object_dtype(self.subtype)

    @property
    def _is_boolean(self):
        return is_bool_dtype(self.subtype)

    @property
    def kind(self):
        """
        The sparse kind. Either 'integer', or 'block'.
        """
        return self.subtype.kind

    @property
    def type(self):
        return self.subtype.type

    @property
    def subtype(self):
        return self._dtype

    @property
    def name(self):
        return "Sparse[{}, {}]".format(self.subtype.name, self.fill_value)

    def __repr__(self) -> str:
        return self.name

    @classmethod
    def construct_array_type(cls):
        from .array import SparseArray

        return SparseArray

    @classmethod
    def construct_from_string(cls, string):
        """
        Construct a SparseDtype from a string form.

        Parameters
        ----------
        string : str
            Can take the following forms.

            string           dtype
            ================ ============================
            'int'            SparseDtype[np.int64, 0]
            'Sparse'         SparseDtype[np.float64, nan]
            'Sparse[int]'    SparseDtype[np.int64, 0]
            'Sparse[int, 0]' SparseDtype[np.int64, 0]
            ================ ============================

            It is not possible to specify non-default fill values
            with a string. An argument like ``'Sparse[int, 1]'``
            will raise a ``TypeError`` because the default fill value
            for integers is 0.

        Returns
        -------
        SparseDtype
        """
        msg = "Could not construct SparseDtype from '{}'".format(string)
        if string.startswith("Sparse"):
            try:
                sub_type, has_fill_value = cls._parse_subtype(string)
            except ValueError:
                raise TypeError(msg)
            else:
                result = SparseDtype(sub_type)
                msg = (
                    "Could not construct SparseDtype from '{}'.\n\nIt "
                    "looks like the fill_value in the string is not "
                    "the default for the dtype. Non-default fill_values "
                    "are not supported. Use the 'SparseDtype()' "
                    "constructor instead."
                )
                if has_fill_value and str(result) != string:
                    raise TypeError(msg.format(string))
                return result
        else:
            raise TypeError(msg)

    @staticmethod
    def _parse_subtype(dtype):
        """
        Parse a string to get the subtype

        Parameters
        ----------
        dtype : str
            A string like

            * Sparse[subtype]
            * Sparse[subtype, fill_value]

        Returns
        -------
        subtype : str

        Raises
        ------
        ValueError
            When the subtype cannot be extracted.
        """
        xpr = re.compile(r"Sparse\[(?P<subtype>[^,]*)(, )?(?P<fill_value>.*?)?\]$")
        m = xpr.match(dtype)
        has_fill_value = False
        if m:
            subtype = m.groupdict()["subtype"]
            has_fill_value = m.groupdict()["fill_value"] or has_fill_value
        elif dtype == "Sparse":
            subtype = "float64"
        else:
            raise ValueError("Cannot parse {}".format(dtype))
        return subtype, has_fill_value

    @classmethod
    def is_dtype(cls, dtype):
        dtype = getattr(dtype, "dtype", dtype)
        if isinstance(dtype, str) and dtype.startswith("Sparse"):
            sub_type, _ = cls._parse_subtype(dtype)
            dtype = np.dtype(sub_type)
        elif isinstance(dtype, cls):
            return True
        return isinstance(dtype, np.dtype) or dtype == "Sparse"

    def update_dtype(self, dtype):
        """
        Convert the SparseDtype to a new dtype.

        This takes care of converting the ``fill_value``.

        Parameters
        ----------
        dtype : Union[str, numpy.dtype, SparseDtype]
            The new dtype to use.

            * For a SparseDtype, it is simply returned
            * For a NumPy dtype (or str), the current fill value
              is converted to the new dtype, and a SparseDtype
              with `dtype` and the new fill value is returned.

        Returns
        -------
        SparseDtype
            A new SparseDtype with the corret `dtype` and fill value
            for that `dtype`.

        Raises
        ------
        ValueError
            When the current fill value cannot be converted to the
            new `dtype` (e.g. trying to convert ``np.nan`` to an
            integer dtype).


        Examples
        --------
        >>> SparseDtype(int, 0).update_dtype(float)
        Sparse[float64, 0.0]

        >>> SparseDtype(int, 1).update_dtype(SparseDtype(float, np.nan))
        Sparse[float64, nan]
        """
        cls = type(self)
        dtype = pandas_dtype(dtype)

        if not isinstance(dtype, cls):
            fill_value = astype_nansafe(np.array(self.fill_value), dtype).item()
            dtype = cls(dtype, fill_value=fill_value)

        return dtype

    @property
    def _subtype_with_str(self):
        """
        Whether the SparseDtype's subtype should be considered ``str``.

        Typically, pandas will store string data in an object-dtype array.
        When converting values to a dtype, e.g. in ``.astype``, we need to
        be more specific, we need the actual underlying type.

        Returns
        -------

        >>> SparseDtype(int, 1)._subtype_with_str
        dtype('int64')

        >>> SparseDtype(object, 1)._subtype_with_str
        dtype('O')

        >>> dtype = SparseDtype(str, '')
        >>> dtype.subtype
        dtype('O')

        >>> dtype._subtype_with_str
        str
        """
        if isinstance(self.fill_value, str):
            return type(self.fill_value)
        return self.subtype

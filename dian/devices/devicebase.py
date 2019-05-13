from collections import OrderedDict
from collections.abc import Iterable  # NOQA
import sympy as smp
from sympy.tensor.array import MutableDenseNDimArray
import logging
import numpy as np
from dian.utils import non_commutative_sympify

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
sh = logging.StreamHandler()
logger.addHandler(sh)


class DeviceBase(object):
    """
    Base class for devices with universal properties and functions

    # TODO: before sympifying, use self.n to define array symbols
    # TODO: provide an option to populate default data when the number of devices are given

    #  {Constant, Symbol {scalar, vector {parameter, variable{internal, external}, matrix}, Anything}

    """
    def __init__(self, system):

        self.system = system
        self.idx = []

        # options for the whole class
        self._options = OrderedDict()

        # parameter data loaded from data files or data classes

        self._param_data = OrderedDict()

        # default set of parameters
        self._param_int = ['name', 'u']
        self._param_int_default = {'name': '', 'u': 1}
        self._param_int_non_computational = ['name']

        # computed internal parameters in a list of (parameter, equation)
        self._param_int_computed = OrderedDict()

        # internal parameters that are computed with custom functions
        self._param_int_custom = []

        # external parameters before any computation in tuples (device, original_name, new_name)
        self._param_ext = []  # TODO: method to update external parameters

        # external parameters that are computed by the external device in tuples (device, original name, new_name)
        self._param_ext_computed = []  # TODO: method to update computed external parameters

        # store the idx to internal index mapping
        self._int = OrderedDict()

        # define the parameters of the current model that are referencing the idx of other devices in tuples of
        # (device, parameter)
        self._foreign_keys = OrderedDict()

        # define the internal algebraic variables of the current model
        self._algeb_int = []

        # define the internal algebraic variables that are also interface variables
        self._algeb_intf = []

        # define the external algebraic variables that are interface variables of other devices in tuples
        # (model, algeb_name)
        self._algeb_ext = OrderedDict()

        # computed algebraic variables using either internal or external algebs
        self._var_int_computed = OrderedDict()

        # internal custom computed variables
        self._var_int_custom = OrderedDict()

        # define the internal state variables of the current model
        self._state_int = []

        # define the internal state variables that are also interface variables (UNCOMMON)
        self._state_intf = []

        # define the external state variables that are interface variables of other devices in tuples
        # (model, algeb_name) (UNCOMMON)
        self._state_ext = []

        # define the current status in the work flow
        self._workflow = None

        # equations to be added to the external algebraic equations. Must correspond to `_algeb_ext`
        self._gcall_ext = OrderedDict()
        self._gcall_ext_symbolic_singleton = OrderedDict()
        self._gcall_ext_symbolic = OrderedDict()

        # pairs of singleton variables and symbols, e.g., ('a', a)
        self._symbol_singleton = OrderedDict()

        # internal gcall equations, must equal to the number of `_gcall_int`
        self._gcall_int = OrderedDict()
        self._gcall_int_symbolic_singleton = OrderedDict()
        self._gcall_int_symbolic = OrderedDict()

        # special flags
        self._special_flags = {'no_algeb_ext_check': False,
                               'state_group_by_element': True,
                               'algeb_group_by_element': True,
                               }

        # non-commutative var_int
        self._var_int_non_commutative = OrderedDict()

        # dae address for variable and equations
        self._dae_address = OrderedDict()

    def make_gcall_ext_symbolic(self):
        """
        Generate symbolic expressions for algebraic equations, based on `self._gcall_ext`, linked to external
        algebraic variables

        Returns
        -------
        None
        """

        for var, eq in self._gcall_ext.items():
            equation_singleton = smp.sympify(eq)
            self._gcall_ext_symbolic_singleton[var] = equation_singleton

    def make_gcall_int_symbolic(self):
        """
        Generate symbolic expressions for algebraic equations, based on `self._gcall_ext`, linked to internal
        variables

        Returns
        -------
        None
        """

        for var, eq in self._gcall_int.items():
            # convert equation singleton
            equation_singleton = smp.sympify(eq)
            self._gcall_int_symbolic_singleton[var] = equation_singleton

    def delayed_symbol_sub(self, in_dict_name: str, out_dict_name: str, subs_type='vectorized', output_type=None,
                           update=False):
        """
        Execute symbolic substitution for a dictionary whose values are symbolic equation singletons

        Parameters
        ----------
        in_dict_name : str
            The name of the dictionary which is a member of this instance with the keys as the equation names
            and values as the symbolic equation singletons

        out_dict_name : str
            The name of a dictionary to which the equations with substituted symbols will be stored

        subs_type : str
            The type of the substitution in `('vectorized', 'singleton')`

        output_type : Type
            The type of the returned vectorized substitution for each equation. Can be returned as a list or
            a sympy.Arrray

        update : bool
            Update the value if the key already exists in the output dictionary

        Returns
        -------
        None
        """
        assert subs_type in ('vectorized', 'singleton')

        singleton_dict = self.__dict__[in_dict_name]
        for var, eq in singleton_dict.items():
            if not update and var in self.__dict__[out_dict_name]:
                continue

            if subs_type == 'vectorized':
                self.__dict__[out_dict_name][var] = self._subs_all_vectorized(eq, return_as=output_type)
            elif subs_type == 'singleton':
                self.__dict__[out_dict_name][var] = self._subs_all_singleton(eq, return_as=output_type)

    def delayed_symbol_sub_all(self):
        """
        Delayed substitution for symbols. May need to call `self._subs_all_vectorized` and
        `self._subs_all_singleton` respectively for each devices

        Returns
        -------
        None

        """
        self.delayed_symbol_sub(in_dict_name='_gcall_ext_symbolic_singleton', out_dict_name='_gcall_ext_symbolic',
                                subs_type='vectorized', output_type=smp.Array)
        self.delayed_symbol_sub(in_dict_name='_gcall_int_symbolic_singleton', out_dict_name='_gcall_int_symbolic',
                                subs_type='vectorized', output_type=smp.Array)

    def _subs_all_vectorized(self, equation_singleton, return_as=list):
        """Substitute symbol singletons with element-wise variable names for the provided expression"""

        free_syms = equation_singleton.free_symbols

        n_element = min([len(self.__dict__[str(x)]) for x in free_syms])

        ret = [0] * n_element
        for i in range(n_element):

            sym_list = []
            for symbol in free_syms:
                sym = str(symbol)

                if len(self.__dict__[sym]) == 0:
                    logger.debug(f'_subs_all skips variable {sym} due to empty length')
                    continue
                sym_list.append((symbol, self.__dict__[sym][i]))

            ret[i] = equation_singleton.subs(sym_list)

        # process return type
        if return_as is None:
            pass
        elif return_as is list:
            pass
        else:
            ret = return_as(ret)

        return ret

    def _subs_all_singleton(self, equation_singleton, return_as=None):
        """Substitute symbol singletons with symbols expression"""

        free_syms = equation_singleton.free_symbols

        sym_list = []
        for symbol in free_syms:
            sym = str(symbol)
            sym_list.append((symbol, self.__dict__[sym]))

        # use `simultaneous` subs for matrix substitution
        ret = equation_singleton.subs(sym_list, simultaneous=True)

        # process return type
        if return_as is None:
            pass
        else:
            ret = return_as(ret)
        return ret

    def _init_data(self):
        """
        Initialize data members based on metadata provided in `__init__()`

        Returns
        -------

        """
        # TODO: check for name conflicts

        if self.n == 0:
            return False

        # all computational parameters
        param_int_computational = (set(self._param_int) - set(self._param_int_non_computational))
        if len(param_int_computational) > 0:
            logger.debug(f'{self.__class__.__name__} Param internal computational: ')
            for item in param_int_computational:
                self.__dict__[item] = MutableDenseNDimArray(smp.symbols(self.__class__.__name__ +
                                                                        f'_{item}_0:{self.n}'))
                self._symbol_singleton[item] = smp.symbols(item)
                logger.debug(self.__dict__[item])

        # create placeholders for computed internal parameters
        if len(self._param_int_computed) > 0:
            logger.debug(f'{self.__class__.__name__} Param computed place holder: ')
            for item in self._param_int_computed.keys():
                self.__dict__[item] = MutableDenseNDimArray(smp.symbols(self.__class__.__name__ +
                                                                        f'_{item}_0:{self.n}'))
                self._symbol_singleton[item] = smp.symbols(item)
                logger.debug(self.__dict__[item])

        # create placeholder in `self.__dict__` for custom computed parameters
        if len(self._param_int_custom) > 0:
            logger.debug(f'{self.__class__.__name__} Param custom place holder: ')
            for item in self._param_int_custom:
                self.__dict__[item] = MutableDenseNDimArray(smp.symbols(self.__class__.__name__ +
                                                                        f'_{item}_0:{self.n}'))
                self._symbol_singleton[item] = smp.symbols(item)
                logger.debug(self.__dict__[item])

        # _algeb_int
        if len(self._algeb_int):
            logger.debug(f'{self.__class__.__name__} Internal algeb variables:')
            for item in self._algeb_int:
                self.__dict__[item] = MutableDenseNDimArray(smp.symbols(self.__class__.__name__ +
                                                                        f'_{item}_0:{self.n}'))
                self._symbol_singleton[item] = smp.symbols(item)
                # TODO: register for a variable number in the DAE system
                logger.debug(self.__dict__[item])

        # internal variabled computed
        if len(self._var_int_computed):
            logger.debug(f'{self.__class__.__name__} Algebraic variables computed:')
            for item in self._var_int_computed:
                self.__dict__[item] = MutableDenseNDimArray(smp.symbols(self.__class__.__name__ +
                                                                        f'_{item}_0:{self.n}'))
                self._symbol_singleton[item] = smp.symbols(item, commutative=False)
                logger.debug(self.__dict__[item])

        # _state_int
        if len(self._state_int):
            logger.debug(f'{self.__class__.__name__} Internal state variables:')
            for item in self._state_int:
                self.__dict__[item] = MutableDenseNDimArray(smp.symbols(self.__class__.__name__ +
                                                                        f'_{item}_0:{self.n}'))
                self._symbol_singleton[item] = smp.symbols(item)
                # TODO: register for a variable number in the DAE system
                logger.debug(self.__dict__[item])

    def get_algeb_ext(self):
        """
        Based on the definition of algebraic variables (defined in `self._algeb_ext` and the associated device,
        retrieve the
         - variable symbol singleton (goes to self._symbol_singleton[dest])
         - the variable list for the respective external elements (goes to `self.{dest}` as a sympy.Array)
         - the variable address in the dae (goes to `self._dae_address[f'{dest'}]`)

        Returns
        -------
        None
        """
        if len(self._algeb_ext) > 0:
            logger.debug(f'{self.__class__.__name__} External algebraic variables of device')

            for dest, (fkey, var_name) in self._algeb_ext.items():

                if fkey in self._param_int:  # if fkey is a valid parameter input
                    dev = self._foreign_keys[fkey]
                    int_keys = self._get_int_of_element(dev, fkey)
                else:  # fkey is a device name instead
                    dev = fkey
                    fkey_values = self.system.__dict__[fkey.lower()].idx
                    int_keys = self.system.__dict__[dev.lower()].idx2int(fkey_values)

                # store dae address
                dev_ref = self.system.__dict__[dev.lower()]
                self._dae_address[f'{dest}'] = dev_ref._dae_address[f'{var_name}'][int_keys]

                # get external algebraic variable symbol array by accessing
                algeb_symbol_list = self.get_list_of_symbols_from_ext(dev, var_name, int_keys)
                self.__dict__[dest] = smp.Array(algeb_symbol_list)

                # store the singleton  TODO: should be retrieved
                self._symbol_singleton[dest] = smp.symbols(var_name)
                logger.debug(self.__dict__[dest])

    def _get_int_of_element(self, dev, fkey):
        """
        For device `dev`, get the internal indicex (int) of the elements having `fkey` matching their `idx`

        Parameters
        ----------
        dev : str
            Name of the device
        fkey :
            A list or numpy array as foreign keys indexing into `dev.idx`

        Returns
        -------

        """
        assert dev in self._foreign_keys.values()

        fkey_values = self.__dict__[fkey]
        return self.system.__dict__[dev.lower()].idx2int(fkey_values)

    def get_list_of_symbols_from_ext(self, dev, var_name, int_idx):
        """
        Get a list of symbols from external devices based on the fkey linked to the idx of external devices

        Parameters
        ----------
        dev : str
            Name of the device

        var_name : str
            Name of the variable of the device to access

        int_idx
            A list or numpy array of the internal indices of the elements to access

        Returns
        -------

        """
        dev = dev.lower()
        if isinstance(int_idx, np.ndarray):
            int_idx = int_idx.tolist()  # sympy is not aware of numpy.int64; convert to a list of floats
        return [self.system.__dict__[dev].__dict__[var_name][i] for i in int_idx]

    def idx2int(self, idx):
        """
        Convert external indices `idx` to internal indices as stored in `self.int`

        Returns
        -------
        np.ndarray : an array of internal indices
        """
        return np.array([self._int[i] for i in idx])

    def create_n_default_elements(self, n: int):
        """
        Create `n` elements with the default N-to-N mapping between int and idx. The `idx` and `int` are both
        in range(n).

        Parameters
        ----------
        n : int
            The number of elements to add
        Returns
        -------
        None
        """

        assert n >= 0
        self.idx = list(range(n))
        self._int = {i: i for i in self.idx}

    def _init_equation(self):
        """
        Create storage arrays for equations. The equation name starts with an underscore `_` followed by the
        variable name.

        Included equations are defined in `self._algeb_int`, `self._algeb_intf`, and `self._state_int`.

        Returns
        -------
        None
        """
        for item in (self._algeb_int + self._algeb_intf + self._state_int):
            eq_name = f'_{item}'  # equation names starts with "_" and follows with the corresponding var name
            self.__dict__[eq_name] = MutableDenseNDimArray([0] * self.n)
            logger.debug(self.__dict__[eq_name])

    def _check_number_of_algeb_equations(self):
        """
        Consistency check subroutine: check if the number of equations equal the number of variables.

        Returns
        -------
        None
        """
        if self._special_flags['no_algeb_ext_check'] is False:
            assert len(self._algeb_ext) == len(self._gcall_ext), "{} Number of _algeb_ext does not equal " \
                                                                 "_gcall_ext".format(self.__class__.__name__)
        assert len(self._algeb_int) - len(self._algeb_intf) <= \
            len(self._gcall_int), "{} Too few gcall_int equations".format(self.__class__.__name__)

    def metadata_check(self):
        """
        Check the metadata and find inconsistency. Contains of subroutines for consistency check.

        Returns
        -------
        None
        """
        self._check_number_of_algeb_equations()

    def _compute_param_int(self):
        """
        Compute internal parameters based on `self._param_int_computed`.

        Returns
        -------
        None
        """
        # process internally computed parameters

        if len(self._param_int_computed) > 0:
            logger.debug(f'{self.__class__.__name__} Param computed: ')
            for var, eq in self._param_int_computed.items():
                equation_singleton = smp.sympify(eq)
                # may not need to delay subs here
                self.__dict__[var] = self._subs_all_vectorized(equation_singleton)
                logger.debug(self.__dict__[var])

    def _compute_variable(self):
        """
        Compute internal variable symbols as defined in `self._var_int_computed`. Supports a list of
         - [equation]
         - [equation, compute_type]
         - [equation, compute_type, return_type]

        Returns
        -------
        None

        """
        if len(self._var_int_computed) > 0:
            logger.debug(f'{self.__class__.__name__} Variables computed: ')
            for var, eq in self._var_int_computed.items():
                compute_type = 'vectorized'
                return_type = None
                if isinstance(eq, list):
                    if len(eq) == 3:
                        eq, compute_type, return_type = eq
                    elif len(eq) == 2:
                        eq, compute_type = eq
                    elif len(eq) == 1:
                        eq = eq[0]
                    else:
                        raise NotImplementedError
                else:
                    raise NotImplementedError

                equation_singleton = non_commutative_sympify(eq)

                # process compute_type
                if compute_type == 'vectorized':
                    self.__dict__[var] = self._subs_all_vectorized(equation_singleton, return_as=smp.Array)
                elif compute_type == 'singleton':
                    self.__dict__[var] = self._subs_all_singleton(equation_singleton)
                else:
                    raise NotImplementedError

                if return_type is not None:
                    self.__dict__[var] = return_type(self.__dict__[var])
                logger.debug(self.__dict__[var])

    def _compute_variable_custom(self):
        """
        Hook functions to compute custom variables. To be overloaded by devices.

        Returns
        -------
        None
        """
        pass

    def _compute_param_custom(self):
        """
        Compute custom parameters. To be called at the end of the parameter creation process.

        Parameter initialization:

        _param_int
        _param_ext
        _param_int_computed
        _param_ext_computed
        _param_int_custom

        Returns
        -------

        """
        pass

    @property
    def n(self):
        """
        The count of elements obtained from len(self._idx)

        Returns
        -------
        int
            The count of elements
        """
        return len(self.idx)

    def get_var_address(self):
        """
        Request address for variables in global DAE. Stored in `self._dae_address` with the variable name as
        keys and address array as the values.

        Returns
        -------
        None
        """

        # state variables
        ret = self.system.dae.new_idx(device=self, var_type='x', var_name=self._state_int,
                                      group_by_element=self._special_flags['state_group_by_element'])

        for key, val in ret.items():
            self.__dict__[f'_{key}_addr'] = val
        self._dae_address.update(ret)

        # algebraic variables
        ret = self.system.dae.new_idx(device=self, var_type='y', var_name=self._algeb_int,
                                      group_by_element=self._special_flags['algeb_group_by_element'])
        for key, val in ret.items():
            self.__dict__[f'_{key}_addr'] = val
        self._dae_address.update(ret)

    def is_state(self, var_name):
        """
        Check if a variable `var_name` is a state variable.

        Parameters
        ----------
        var_name : str
            Name of the variable

        Returns
        -------
        bool : True if is a state variable. False otherwise.
        """
        pass

    def is_algeb(self, var_name):
        """
        Check if a variable `var_name` is an algebraic variable.

        Parameters
        ----------
        var_name : str
            Name of the variable

        Returns
        -------
        bool : True if is an algebraic variable. False otherwise.
        """
        pass


class DeviceData(object):
    """Class for storing device data"""
    def __init__(self, device: str, param: list, n_element=0):
        self.device = device  # name of the device to which the data belongs
        for item in param:
            self.__dict__[item] = np.ndarray((n_element, ))

    def load_param_by_row(self, **kwargs):
        """
        Load parameters of a single element (row) from parameter values
        Returns
        -------

        """
        # for key, val in kwargs.items():
        #     if key not in
        pass

    def load_param_from_dataframe(self):
        """
        load parameters of multiple elements from a pandas.DataFrame

        Returns
        -------
        None

        """
        pass

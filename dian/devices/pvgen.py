from .devicebase import DeviceBase


class PV(DeviceBase):
    """Class for static PV gen
    """

    def __init__(self, system):
        super(PV, self).__init__(system)
        self._param_int.extend(['bus', 'p0', 'v0', 'Sn', 'Vn', 'vmax', 'vmin', 'qmax', 'qmin'])
        self._param_int_non_computational.extend(['bus'])
        self._param_int_mandatory.extend(['bus'])
        self._param_int_default.update({'p0': 0,
                                        'v0': 1,
                                        'Sn': 100,
                                        'Vn': 110,
                                        'vmax': 1.1,
                                        'vmin': 0.9,
                                        'qmax': 999,
                                        'qmin': -999
                                        })

        self._foreign_keys.update({'bus': 'Bus'})

        self._algeb_ext.update({'a': ['bus', 'a'], 'v': ['bus', 'v']})

        self._algeb_int.extend(['q'])

        self._gcall_int.update({'q': 'v - v0',
                                })
        self._gcall_ext.update({'a': '-p0',
                                'v': '-q'})


class Slack(PV):
    """
    Class for Slack generator for power flow
    """

    def __init__(self, system):
        super(Slack, self).__init__(system)
        self._param_int.remove('p0')
        self._param_int_default.pop('p0')

        self._param_int.extend(['a0'])
        self._param_int_default.update({'a0': 0})

        self._algeb_int.extend(['p'])

        self._gcall_int.update({'p': 'a - a0'})

        self._gcall_ext.update({'a': '-p'})

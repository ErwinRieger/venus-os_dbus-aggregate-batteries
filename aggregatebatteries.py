#!/usr/bin/env python3

"""
Service to aggregate multiple (serial-) batteries into one virtual battery.
"""

##################################################
# Configuration:
NUMBER_OF_BATTERIES = 2
##################################################

from gi.repository import GLib
import logging
import sys, os
import dbus
from  datetime import datetime as dt

sys.path.append(os.path.join(os.path.dirname(__file__), './ext/velib_python'))
from vedbus import VeDbusService
from dbusmonitor import DbusMonitor, Service, notfound, MonitoredValue
from ve_utils import exit_on_error

VERSION = "0.1"

dummy = {"code": None, "whenToLog": "configChange", "accessLevel": None}

class MyDbusMonitor(DbusMonitor):

    def scan_dbus_service_inner(self, *args, **kwargs):
        exit_on_error(self._scan_dbus_service_inner, *args, **kwargs)

    def _scan_dbus_service_inner(self, serviceName):

        paths = self.dbusTree.get(serviceName, None)
        if paths is None:
            logging.debug("Ignoring service %s, not in the tree" % serviceName)
            return False

        logging.info("Found: %s, scanning and storing items" % serviceName)
        serviceId = self.dbusConn.get_name_owner(serviceName)

        # we should never be notified to add a D-Bus service that we already have. If this assertion
        # raises, check process_name_owner_changed, and D-Bus workings.
        assert serviceName not in self.servicesByName
        assert serviceId not in self.servicesById

        try:
            di = self.dbusConn.call_blocking(serviceName,
                '/DeviceInstance', None, 'GetValue', '', [])
        except dbus.exceptions.DBusException:
            logging.info("       %s was skipped because it has no device instance" % serviceName)
            return False # Skip it

        logging.info("       %s has device instance %s" % (serviceName, di))
        service = Service(serviceId, serviceName, di)

        # Let's try to fetch everything in one go
        values = {}
        try:
            values.update(self.dbusConn.call_blocking(serviceName, '/', None, 'GetValue', '', []))
        except:
            pass

        for path, options in paths.items():
            # path will be the D-Bus path: '/Ac/ActiveIn/L1/V'
            # options will be a dictionary: {'code': 'V', 'whenToLog': 'onIntervalAlways'}
            # check that the whenToLog setting is set to something we expect
            assert options['whenToLog'] is None or options['whenToLog'] in Service.whentologoptions

            # Try to obtain the value we want from our bulk fetch. If we
            # cannot find it there, do an individual query.
            value = values.get(path[1:], notfound)
            if value != notfound:
                service.set_seen(path)
            else:
                try:
                    value = self.dbusConn.call_blocking(serviceName, path, None, 'GetValue', '', [])
                    service.set_seen(path)
                except dbus.exceptions.DBusException as e:
                    if e.get_dbus_name() in (
                            'org.freedesktop.DBus.Error.ServiceUnknown',
                            'org.freedesktop.DBus.Error.Disconnected'):
                        raise # This exception will be handled below

                    # TODO org.freedesktop.DBus.Error.UnknownMethod really
                    # shouldn't happen but sometimes does.
                    logging.info("%s %s does not exist (yet)" % (serviceName, path))
                    value = None

            service.paths[path] = MonitoredValue(value, None, options)

            if options['whenToLog']:
                service[options['whenToLog']].append(path)

        logging.info(f"Finished scanning and storing items for {serviceName} id: {id(self)}")

        # Adjust self at the end of the scan, so we don't have an incomplete set of
        # data if an exception occurs during the scan.
        self.servicesByName[serviceName] = service
        self.servicesById[serviceId] = service
        self.servicesByClass[service.service_class].append(service)
        return True

class DbusAggBatService(object):

    def __init__(self, servicename="com.victronenergy.battery.aggregate"):
        super(DbusAggBatService, self).__init__()

        self.maindbusmon = DbusMonitor({ "com.victronenergy.battery" : { "/Soc": dummy } },
                deviceAddedCallback=self.deviceAddedWrapper,
                deviceRemovedCallback=self.deviceRemovedWrapper)

        self.busmon_scan_dbus_service = self.maindbusmon.scan_dbus_service
        self.maindbusmon.scan_dbus_service = self.scan_dbus_service

        self._dbusservice = VeDbusService(servicename)

        # Create the mandatory objects
        self._dbusservice.add_mandatory_paths(
            processname=__file__,
            processversion="0.0",
            connection="Virtual",
            deviceinstance=1,
            productid=0,
            productname="SAggregateBatteries",
            firmwareversion=VERSION,
            hardwareversion="0.0",
            connected=1,
        )

        # XXX todo !!!!
        # Ess/Chgmode
        # Ess/Throttling
        # "Info/ChargeMode",

        self.addPath = (
            "Info/MaxChargeCurrent",
            "Info/MaxDischargeCurrent",
            "Dc/0/Current",
            "Dc/0/Power",
            "InstalledCapacity",
            "ConsumedAmphours",
            "Capacity",
            "System/NrOfModulesOnline",
            "System/NrOfModulesOffline",
            "System/NrOfModulesBlockingCharge",
            "System/NrOfModulesBlockingDischarge",
            "Alarms/CellImbalance",
            "Alarms/HighCellVoltage",
            "Alarms/HighChargeCurrent",
            "Alarms/InternalFailure_alarm",
            "Alarms/HighChargeTemperature",
            "Alarms/HighDischargeCurrent",
            "Alarms/HighTemperature",
            "Alarms/HighVoltage",
            "Alarms/InternalFailure",
            "Alarms/LowCellVoltage",
            "Alarms/LowChargeTemperature",
            "Alarms/LowSoc",
            "Alarms/LowTemperature",
            "Alarms/LowVoltage",
            "Alarms/BmsCable",
            )

        self.avgPath = (
            "Soc",
            )

        self.minPath = (
            "Info/MaxChargeVoltage",
            "System/MinCellTemperature",
            "System/MinCellVoltage",
            )

        self.maxPath = (
            "Info/BatteryLowVoltage",
            "Dc/0/Voltage",
            "Dc/0/Temperature",
            "System/MaxCellTemperature",
            "System/MaxCellVoltage",
            )

        self.allsetPath = (
            "Io/AllowToCharge",
            "Io/AllowToDischarge",
            "Io/AllowToBalance",
            "TimeToGo",
        )

        self.onesetPath = (
            "Ess/Balancing",
            )
            
        self.ignorePath = (
            'Mgmt/ProcessName',
            'Mgmt/ProcessVersion',
            'Mgmt/Connection',
            'DeviceInstance',
            'ProductId',
            'ProductName',
            'FirmwareVersion',
            'HardwareVersion',
            'Connected',
            'Ess/ForceMode',
            "Dc/0/MidVoltage",
            "Dc/0/MidVoltageDeviation",
            "Ess/Chgmode",
            "Ess/Throttling",
            "History/ChargeCycles",
            "History/TotalAhDrawn",
            "System/MaxVoltageCellId",
            "System/MinVoltageCellId",
            "System/NrOfCellsPerBattery",
            "Balances/Cell1",
            "Balances/Cell2",
            "Balances/Cell3",
            "Balances/Cell4",
            "Balances/Cell5",
            "Balances/Cell6",
            "Balances/Cell7",
            "Balances/Cell8",
            "Balances/Cell9",
            "Balances/Cell10",
            "Balances/Cell11",
            "Balances/Cell12",
            "Balances/Cell13",
            "Balances/Cell14",
            "Balances/Cell15",
            "Balances/Cell16",
            "Voltages/Cell1",
            "Voltages/Cell2",
            "Voltages/Cell3",
            "Voltages/Cell4",
            "Voltages/Cell5",
            "Voltages/Cell6",
            "Voltages/Cell7",
            "Voltages/Cell8",
            "Voltages/Cell9",
            "Voltages/Cell10",
            "Voltages/Cell11",
            "Voltages/Cell12",
            "Voltages/Cell13",
            "Voltages/Cell14",
            "Voltages/Cell15",
            "Voltages/Cell16",
            "Voltages/Diff",
            "Voltages/Sum",
            )

        self.getTextCallbacks = {
            '/Dc/0/Voltage': lambda a, x: "{:.2f}V".format(x),
            '/Dc/0/Current':lambda a, x: "{:.2f}A".format(x),
            '/Dc/0/Power': lambda a, x: "{:.0f}W".format(x),
            '/ConsumedAmphours': lambda a, x: "{:.0f}Ah".format(x),
        }

        self.monitors = {}
        self.batteries = {}
        self.monitorlist = {}

        # Get dynamic servicename for batteries
        battServices = self.maindbusmon.get_service_list(classfilter="com.victronenergy.battery") or []

        if len(battServices) != NUMBER_OF_BATTERIES:
            logging.info(f"Error: found {len(battServices)} batterie(s), should have: {NUMBER_OF_BATTERIES}, exiting!")
            sys.exit(1)
            return

        for batt in battServices:
            logging.info(f"found initial batt: {batt}")
            GLib.timeout_add(250, self.addBatteryWrapper, batt)

        return

    # #############################################################################################################

    # XXX Dbusmonitor tries to scan OUR service, too. This leads to
    # a unnessesary delay/timeout. So filter our own service out here:
    def scan_dbus_service(self, serviceName):
        logging.info("scan_service: " + serviceName)
        if serviceName == "com.victronenergy.battery.aggregate":
            return False
        return self.busmon_scan_dbus_service(serviceName)

    def newBatt(self, batt):
        assert(batt not in self.batteries)

        if batt in self.monitors:
            logging.info(f"newbatt: found existing dbus monitor for {batt}")
            self.batteries[batt] = self.monitors[batt]
            return

        logging.info(f"newbatt: initializing new dbus monitor for {batt}")

        allvalues = self.maindbusmon.dbusConn.call_blocking(batt, '/', None, 'GetValue', '', [])
        for key in allvalues:
            fqnkey = "/"+key
            if key in self.ignorePath or fqnkey in self.monitorlist:
                continue
            self.monitorlist[fqnkey] = dummy

        logging.info(f"newbatt: watching {len(self.monitorlist)} items of {batt}: {self.monitorlist.keys()}")
        dbusmon = MyDbusMonitor({ batt: self.monitorlist },
                valueChangedCallback=self.value_changed_wrapper)
        self.monitors[batt] = dbusmon
        self.batteries[batt] = dbusmon

        for fqnkey in self.monitorlist:
            if fqnkey in self.ignorePath:
                continue
            if fqnkey not in self._dbusservice:
                self._dbusservice.add_path(
                        fqnkey,
                        None,
                        gettextcallback=self.getTextCallbacks.get(fqnkey, None))
            # self.publishValue(batt, fqnkey, dbusmon.get_value(batt, fqnkey))
            self.publishValue(batt, fqnkey, allvalues[fqnkey[1:]])

    # Calls value_changed with exception handling
    def value_changed_wrapper(self, *args, **kwargs):
        exit_on_error(self.value_changed, *args, **kwargs)

    def deviceAddedWrapper(self, service, instance):
        # exit_on_error(self.deviceAddedCallback, service, instance):
        logging.info(f"Error: new battery {service} appeared, exiting!")
        sys.exit(1)

    def deviceRemovedWrapper(self, service, instance):
        # exit_on_error(self.deviceRemovedCallback, service, instance)
        logging.info(f"Error: battery {service} diappeared, exiting!")
        sys.exit(1)

    """
    def deviceAddedCallback(self, service, instance):
        logging.info(f"dbus device added: {service}")
        assert( service.startswith("com.victronenergy.battery") )
        GLib.timeout_add(250, self.addBatteryWrapper, service)

    def deviceRemovedCallback(self, service, instance):
        logging.info(f"dbus device removed: {service}")

        if service in self.batteries:
            # stop using values from this battery
            del self.batteries[service]
    """


    def addBatteryWrapper(self, batt):
        return exit_on_error(self.addBattery, batt)

    def addBattery(self, batt):

        logging.info(f"add battery, waiting for /Soc...")
        soc = self.maindbusmon.get_value(batt, "/Soc")

        logging.info(f"got /Soc: {soc}")

        # Hmmm, sometimes we get None and sometimes a "dbus.Array([], signature=dbus.Signature('i')"
        # value for a None-value on the sender side?
        if soc == None or type(soc) == dbus.Array:
            return True

        self.newBatt(batt)
        return False

    # INFO:root:value_changed com.victronenergy.battery.ttyUSB2 /Voltages/Cell3 {'Value': 3.373, 'Text': dbus.String('3.373V', variant_level=1)}
    def value_changed(self, service, path, options, changes, deviceInstance):
        self.publishValue(service, path, changes["Value"])

    def publishValue(self, service, path, value):

        # logging.info(f'publishValue: {service} {path} {value} {type(value)}')

        if service not in self.batteries:
            logging.info(f"skipping publishValue: early notification...")
            return

        spath = path[1:]

        iv = 0
        lv = []
        sv = ""
        v = None
        vt = type(value)
        if spath in self.addPath:

            for batt in self.batteries:

                battvalue = self.batteries[batt].get_value(batt, path)

                if batt == service:
                    # logging.info(f"add new value {batt} {path} {value}")
                    v = value
                else:
                    # logging.info(f"add old value {batt} {path} {battvalue}")
                    v = battvalue

                if vt == int or vt == float or vt == dbus.Double or vt == dbus.Int32:
                    iv += v
                elif vt == dbus.Array:
                    lv += v
                elif vt == dbus.String:
                    sv += v
                else:
                    logging.info(f"unknown type: {vt}")
                    assert(0)

            if vt == dbus.Array:
                logging.info(f"sum value {batt} {path} {lv}")
                self._dbusservice[path] = lv
            elif vt == dbus.String:
                logging.info(f"sum value {batt} {path} {sv}")
                self._dbusservice[path] = sv
            else: # vt == int or vt == float or vt == dbus.Double or vt == dbus.Int32:
                logging.info(f"sum value {batt} {path} {iv}")
                self._dbusservice[path] = iv

        elif spath in self.avgPath:

            for batt in self.batteries:
                if batt == service:
                    iv += value
                else:
                    iv += self.batteries[batt].get_value(batt, path)

            iv /= len(self.batteries)
            logging.info(f"avg value {batt} {path} {round(iv, 3)}")
            self._dbusservice[path] = round(iv, 3)

        elif spath in self.maxPath:

            for batt in self.batteries:
                if batt == service:
                    iv = max(iv, value)
                else:
                    iv = max(iv, self.batteries[batt].get_value(batt, path))

            logging.info(f"max value {batt} {path} {iv}")
            self._dbusservice[path] = iv

        elif spath in self.minPath:

            iv = 0xffffffff
            for batt in self.batteries:
                if batt == service:
                    iv = min(iv, value)
                else:
                    iv = min(iv, self.batteries[batt].get_value(batt, path))

            logging.info(f"min value {batt} {path} {iv}")
            self._dbusservice[path] = iv

        elif spath in self.allsetPath:

            iv = 1
            for batt in self.batteries:
                if batt == service:
                    if not value:
                        iv = 0
                else:
                    if not self.batteries[batt].get_value(batt, path):
                        iv = 0

            logging.info(f"allset value {batt} {path} {iv}")
            self._dbusservice[path] = iv

        elif spath in self.onesetPath:

            iv = 0
            for batt in self.batteries:
                if batt == service:
                    if value:
                        iv = 1
                else:
                    if self.batteries[batt].get_value(batt, path):
                        iv = 1

            logging.info(f"oneset value {batt} {path} {iv}")
            self._dbusservice[path] = iv

        else:
            logging.info(f"copy single value from {service}: {path} {value}")
            self._dbusservice[path] = value

        return

# ################
# ## Main loop ###
# ################
def main():

    logging.basicConfig(level=logging.INFO)
    logging.info("%s: Starting AggregateBatteries." % (dt.now()).strftime("%c"))
    from dbus.mainloop.glib import DBusGMainLoop

    DBusGMainLoop(set_as_default=True)

    DbusAggBatService()

    logging.info(
        "%s: Connected to DBus, and switching over to GLib.MainLoop()"
        % (dt.now()).strftime("%c")
    )
    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()


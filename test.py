

import sys, os, logging, random
from gi.repository import GLib

sys.path.append(os.path.join(os.path.dirname(__file__), './ext/velib_python'))

class BattSim(object):

    def __init__(self):
        super(BattSim, self).__init__()

        self.soc = 50 + random.random()*2

class ChargerSim(object):

    def __init__(self):
        super(ChargerSim, self).__init__()


class DbusConn:

    def call_blocking(self, batt, path, param, metod, param2, param3):
        return {}


class MonitorSim(object):

    def __init__(self, 
                 tree,
                 deviceAddedCallback=None, deviceRemovedCallback=None,
                 valueChangedCallback=None):
        super(MonitorSim, self).__init__()

        self.services = {
            "com.victronenergy.solarcharger.0": ChargerSim(),
            "com.victronenergy.solarcharger.1": ChargerSim(),
            "com.victronenergy.battery.ttyUSB0": BattSim(),
            "com.victronenergy.battery.ttyUSB1": BattSim(),
            }

        self.dbusConn = DbusConn()
        self.pv = 0
        self.consumption = random.randrange(1000, 2000)
        self.volt = 52 + random.random()
        self.pvvolt = self.volt + random.random()*0.1

    def scan_dbus_service(self):
        assert(0)

    def get_service_list(self, classfilter):
        if classfilter == "com.victronenergy.solarcharger":
            return {"com.victronenergy.solarcharger.0": None, "com.victronenergy.solarcharger.1": None}
        if classfilter == "com.victronenergy.battery":
            return {"com.victronenergy.battery.ttyUSB0": None, "com.victronenergy.battery.ttyUSB1": None}

    def get_value(self, service, path):

        if path == "/Soc":
            return self.services[service].soc
        elif path == "/Dc/0/Current":
            if "battery" in service:
                return (self.pv - self.consumption) / self.volt
            else:
                assert(0)
        elif path == "/Dc/0/Voltage":
            if "battery" in service:
                return self.volt
            else:
                return self.pvvolt

        assert(0)

class VeSim(object):

    def __init__(self, servicename):
        super(VeSim, self).__init__()
        self.dict = {}

    def add_mandatory_paths(self, *args, **kwargs):
        pass

    def __setitem__(self, key, value):
        self.dict[key] = value

# from dbusmonitor import Service, notfound, MonitoredValue
import dbusmonitor, vedbus

dbusmonitor.DbusMonitor = MonitorSim
vedbus.VeDbusService = VeSim

import agg

def main():

    logging.basicConfig(level=logging.INFO)
    logging.info("%s: Testing agg.")

    from dbus.mainloop.glib import DBusGMainLoop

    DBusGMainLoop(set_as_default=True)

    agg.DbusAggBatService()

    logging.info( "Connected to DBus, and switching over to GLib.MainLoop()")
    mainloop = GLib.MainLoop()
    mainloop.run()


if __name__ == "__main__":
    main()


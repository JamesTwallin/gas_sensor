"""Part record used by design.py."""


class Part:
    def __init__(self, ref, symbol, footprint, value, nets, block, lcsc=None, mpn=None,
                 datasheet=None, description=None, dnp=False, virtual=False):
        self.ref, self.symbol, self.footprint, self.value = ref, symbol, footprint, value
        self.nets = {str(k): v for k, v in nets.items()}  # pin number or pin name -> net
        self.block, self.lcsc, self.mpn = block, lcsc, mpn
        self.datasheet, self.description = datasheet, description
        self.dnp, self.virtual = dnp, virtual

    def net_for(self, pin):
        """Net for a symbol pin: explicit pin number wins, then pin name."""
        if pin.number in self.nets:
            return self.nets[pin.number]
        return self.nets.get(pin.name)

    def pad_nets(self, pins):
        """pad number -> net, for the PCB builder."""
        return {p.number: self.net_for(p) for p in pins if self.net_for(p)}


def R(ref, value, a, b, block, lcsc=None, fp="Resistor_SMD:R_0402_1005Metric", dnp=False):
    return Part(ref, "Device:R", fp, value, {"1": a, "2": b}, block, lcsc=lcsc, dnp=dnp)


def C(ref, value, a, b, block, lcsc=None, fp="Capacitor_SMD:C_0402_1005Metric"):
    return Part(ref, "Device:C", fp, value, {"1": a, "2": b}, block, lcsc=lcsc)

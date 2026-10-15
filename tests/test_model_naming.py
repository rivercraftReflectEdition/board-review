import pytest

from boardreview.model import naming, parts


@pytest.mark.parametrize("name, volts", [
    ("3V3", 3.3), ("+3V3", 3.3), ("3.3V", 3.3), ("+3.3V", 3.3), ("VCC_3V3", 3.3), ("VDD_3V3", 3.3),
    ("P3V3", 3.3), ("V3P3", 3.3), ("3P3V", 3.3), ("1V8-SW1", 1.8), ("12V0", 12.0), ("0V9", 0.9),
    ("-5V", -5.0), ("N5V", -5.0), ("3V3A", 3.3), ("/power/+5V", 5.0),
])
def test_voltage_from_rail_names(name, volts):
    assert naming.voltage_of(name) == pytest.approx(volts)


@pytest.mark.parametrize("name", ["3V3", "+5V", "VCC", "VDD_IO", "VBUS", "VIN", "VCORE", "AVDD", "VREF+", "1V8-SW1",
                                  "12V-FILT", "P1V8", "VDDIO_1V8"])
def test_rail_names(name):
    assert naming.is_rail_name(name)
    assert naming.net_kind(name) == "rail"


@pytest.mark.parametrize("name", ["EN-3V3", "PG_1V8", "3V3_PGOOD", "FB_3V3", "SW", "LX_5V", "I2C1_SDA", "NRST",
                                  "VCP_TX", "NetC5_2", "4V-SW-EN"])
def test_not_rail_names(name):
    assert not naming.is_rail_name(name)


@pytest.mark.parametrize("name", ["GND", "AGND", "PGND", "DGND", "GNDA", "GND_ISO", "VSS", "VSSA", "0V", "GND1"])
def test_ground_names(name):
    assert naming.net_kind(name) == "ground"


def test_chassis_and_signal_kinds():
    assert naming.net_kind("CHASSIS") == "chassis"
    assert naming.net_kind("SHIELD") == "chassis"
    assert naming.net_kind("UART_TX") == "signal"


@pytest.mark.parametrize("name, auto", [
    ("NetC105_2", True), ("NetU1_A11", True), ("Net-(R1-Pad2)", True), ("unconnected-(U1-NC-Pad4)", True),
    ("N$12", True), ("PHY_TX_P", False), ("3V3", False), ("NetworkReset", False),
])
def test_auto_named(name, auto):
    assert naming.is_auto_named(name) is auto


def test_unconnected_names():
    for name in (None, "", "N/C", "?", "n/c"):
        assert naming.is_unconnected_name(name)
    assert not naming.is_unconnected_name("NC_PIN_NET")


def test_rail_keys_join_spelling_variants():
    strict = {naming.rail_keys(n)[0] for n in ("3V3", "+3V3", "3.3V", "+3.3V", "P3V3", "V3P3")}
    assert strict == {"3V3"}
    assert naming.rail_keys("VCC_3V3")[1] == naming.rail_keys("3V3")[1]
    assert naming.rail_keys("1V8-SW1")[0] != naming.rail_keys("1V8")[0]
    assert naming.rail_keys("3V3A")[0] != naming.rail_keys("3V3")[0]


@pytest.mark.parametrize("name, reset", [("NRST", True), ("RSTn", True), ("PSRAM-RST-N", True), ("~RESET", True),
                                         ("SYS_RESET_N", True), ("FIRST", False), ("PORT_A", False)])
def test_reset_names(name, reset):
    assert naming.is_reset_name(name) is reset


@pytest.mark.parametrize("name, role", [("I2C4_SDA", "sda"), ("FRAMOS.I2C-SCL0", "scl"), ("SDA", "sda"),
                                        ("SMBCLK", "scl"), ("SPI_SCLK", ""), ("I2S_SDATA", "")])
def test_i2c_roles(name, role):
    assert naming.i2c_role(name) == role


@pytest.mark.parametrize("pin, role", [
    ("SW", "sw"), ("LX", "sw"), ("LX1", "sw"), ("PH", "sw"), ("SW2", "sw"), ("SWN", "sw"),
    ("BST", "boot"), ("BOOT", "boot"), ("CB", "boot"),
    ("FB", "fb"), ("VFB", "fb"), ("VFB1", "fb"), ("ADJ", "fb"), ("VOS", "fb"),
    ("EN", "en"), ("RUN", "en"), ("~{SHDN}", "en"), ("ON", "en"), ("EN/SYNC", "en"), ("EN2", "en"),
    ("PG", "pg"), ("PGOOD", "pg"), ("POK", "pg"), ("PWRGD", "pg"),
    ("GND", "ground"), ("AGND", "ground"), ("PGND", "ground"), ("VSS", "ground"), ("VSSA", "ground"),
    ("EP", "pad"), ("PAD", "pad"), ("NC", "nc"), ("DNC", "nc"),
])
def test_pin_roles_across_vendors(pin, role):
    assert naming.pin_is(pin, role)


def test_pin_roles_do_not_misfire_on_mcu_port_names():
    for pin in ("PH7", "SWDIO", "PH0-OSC_IN", "PA13-JTMS-SWDIO", "BOOT0"):
        assert not naming.pin_is(pin, "sw"), pin
    assert naming.pin_is("PH0-OSC_IN", "xtal")
    assert naming.pin_is("PB7-I2C1_SDA", "sda")
    assert naming.pin_is("PA14-BOOT0", "strap")


@pytest.mark.parametrize("text, kind, value", [
    ("10k", "resistor", 10e3), ("4k7", "resistor", 4.7e3), ("0R", "resistor", 0.0), ("1R5", "resistor", 1.5),
    ("240 ohm", "resistor", 240.0), ("10M", "resistor", 10e6), ("100nF", "capacitor", 100e-9),
    ("4.7u", "capacitor", 4.7e-6), ("1UF", "capacitor", 1e-6), ("2.2n", "capacitor", 2.2e-9),
    ("10uH", "inductor", 10e-6), ("650nH", "inductor", 650e-9), ("STM32", "ic", None),
])
def test_parse_value(text, kind, value):
    got = parts.parse_value(text, kind)
    assert got == (pytest.approx(value) if value is not None else None)


@pytest.mark.parametrize("desc, kind, value", [
    ("100n 10% 50V X7R 0402 Multilayer Ceramic Capacitor", "capacitor", "100nF"),
    ("CAP-A 0.01UF 0402 50V X7R", "capacitor", "0.01UF"),
    ("10k 1% 50V 63mW 100ppm 0402 Thick Film Resistor", "resistor", "10k"),
    ("1 1% 75V 100mW 100ppm 0603 Thick Film Resistor", "resistor", "1"),
    ("RES-A 0402 0ohm Jumper", "resistor", "0"),
    ("63mW Thin Film Resistor 0.1% 240Ω 0402", "resistor", "240"),
    ("Inductor Power Shielded Wirewound 1uH 20% 1MHz Metal 2.7A", "inductor", "1uH"),
    ("650n 16.4mOhm 5Asat 8.3Arms Power Inductor", "inductor", "650nH"),
    ("Ferrite Beads Chip 120Ohm 25% 100MHz 2A 0.045Ohm DCR 0603", "ferrite", "120R@100MHz"),
])
def test_value_from_description(desc, kind, value):
    assert parts.value_from_description(desc, kind) == value


@pytest.mark.parametrize("ref, desc, mpn, kind", [
    ("L5", "Ferrite Beads Chip 120Ohm", "", "ferrite"), ("L3", "Power inductor", "", "inductor"),
    ("L9", "", "BLM18PG221SN1D", "ferrite"), ("FB2", "", "", "ferrite"),
    ("D1", "Trans Voltage Suppressor Diode", "", "tvs"), ("D5", "Schottky diode", "", "diode"),
    ("Y1", "MEMS Clock Oscillator 50MHz", "", "oscillator"), ("Y2", "Crystal 25MHz", "", "crystal"),
    ("X1", "ethernet transformer", "", "transformer"), ("MH3", "", "", "mechanical"),
    ("U7", "", "", "ic"), ("J4", "", "", "connector"), ("TP1", "", "", "testpoint"), ("LED2", "", "", "led"),
])
def test_kind_of(ref, desc, mpn, kind):
    assert parts.kind_of(ref, desc, mpn) == kind

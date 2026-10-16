"""ADC and DAC candidates from part kind and analog, data, reference and clock pin roles."""

from __future__ import annotations

import re

from boardreview.blocks.base import Block, make_block
from boardreview.model import naming
from boardreview.model.board import natural_key
from boardreview.model.graph import Graph

_ANALOG_IN = re.compile(r"^(?:(?:AIN|ANALOGIN|ADCIN|CH\d)[A-Z0-9+-]*|"
                        r"(?:VIN|IN)(?:[A-D0-9]*[PN+-]|[PN+-][A-D0-9]*)[A-D0-9]*)$")
_ANALOG_OUT = re.compile(r"^(?:IOUT|VOUT|AOUT|ANALOGOUT|DACOUT)(?:[A-Z0-9+-]*)$")
_DIGITAL_OUT = re.compile(r"^(?:SDO|DOUT|DCO|TX[PN]|D[AB]?\d|DB\d)(?:[A-Z0-9+-]*)$")
_DIGITAL_IN = re.compile(r"^(?:SDI|DIN|RX[PN]|D[AB]?\d|DB\d)(?:[A-Z0-9+-]*)$")
_CLOCK = re.compile(r"^(?:CLK|CLOCK|DCLK|SCLK|CNV|CONVST|ENC|SAMPLECLK)(?:[A-Z0-9+-]*)$")


def _roles(g: Graph, ref: str) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {"device": [ref]}
    for pin in g.comp_pins.get(ref, []):
        name = re.sub(r"[\s_()/]", "", pin.name.upper())
        hits = []
        if name.startswith("SYSREF"):
            hits.append("sysref")
        elif name.startswith("SYNC"):
            hits.append("sync")
        elif name.startswith(("VCM", "VOCM", "CMOUT")):
            hits.append("common_mode")
        elif name.startswith(("REF", "VREF")):
            hits.append("reference")
        elif pin.type in ("power_in", "power_out"):
            hits.append("supply")
        elif _ANALOG_IN.fullmatch(name):
            hits.append("analog_input")
        elif _ANALOG_OUT.fullmatch(name):
            hits.append("analog_output")
        elif naming.pin_is_supply(pin.name):
            hits.append("supply")
        elif _CLOCK.fullmatch(name):
            hits.append("clock")
        else:
            if _DIGITAL_OUT.fullmatch(name) and pin.type not in ("input", "power_in", "power_out"):
                hits.append("digital_output")
            if _DIGITAL_IN.fullmatch(name) and pin.type not in ("output", "power_in", "power_out"):
                hits.append("digital_input")
        for role in hits:
            roles.setdefault(f"{role}_pins", []).append(pin.key)
            if pin.net is not None:
                roles.setdefault(f"{role}_nets", []).append(pin.net)
    return {role: sorted(set(values), key=natural_key) for role, values in roles.items()}


def find_converters(g: Graph) -> list[Block]:
    """Find explicit ADC or DAC parts and generic ICs with corroborating converter pin groups."""
    found = []
    for ref, comp in sorted(g.model.components.items(), key=lambda item: natural_key(item[0])):
        if comp.kind not in ("ic", "adc", "dac", "data_converter", "transceiver"):
            continue
        roles = _roles(g, ref)
        text = " ".join((comp.description, comp.value))
        for kind, analog, data, description in (
            ("adc", "analog_input", "digital_output", r"\bADC\b|analog[ -]to[ -]digital"),
            ("dac", "analog_output", "digital_input", r"\bDAC\b|digital[ -]to[ -]analog"),
        ):
            explicit = comp.kind == kind or bool(re.search(description, text, re.I))
            structural = all(roles.get(f"{role}_pins") for role in (analog, data, "reference", "clock"))
            if not explicit and not structural:
                continue
            evidence = []
            if explicit:
                evidence.append(f"{ref} part kind or description identifies {kind.upper()}: {comp.kind}; {text.strip()}")
            for role in (analog, data, "reference", "clock", "sysref", "common_mode"):
                if roles.get(f"{role}_pins"):
                    pins = ", ".join(f"{p} ({g.model.pin(p).name})" for p in roles[f"{role}_pins"])
                    evidence.append(f"{role.replace('_', ' ')} pin names: {pins}")
            score = int(explicit) * 2 + sum(bool(roles.get(f"{role}_pins")) for role in (analog, data, "reference", "clock"))
            notes = ["candidate only; confirm converter type, pin roles and operating mode against the datasheet"]
            if not structural:
                notes.append("pin roles are incomplete; part metadata alone does not establish the interface wiring")
            if not comp.fitted:
                notes.append(f"{ref} is DNP: this converter is not in the build")
            found.append(make_block(g, kind, f"{ref} {kind.upper()}", score, 6, 4, evidence, roles, notes))
    return found

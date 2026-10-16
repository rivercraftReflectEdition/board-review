# Lessons

One page per real miss or near miss. Each page states the general rule first, then the case that
taught it, then the checklist items that now catch it. Most cases come from the Sauron rev1 star
tracker carrier (STM32N657, LTC3633A, LT8640, ADIN1200, S28HS01GT, S80KS5123, IMX900 module);
one comes from an offline review of an open-source carrier board. Checklists stay
vendor-neutral; these pages are the examples.

Status: missed = reached hardware; near miss = caught late or by luck; caught = caught by review.

| Page | Status | Checklist items |
|---|---|---|
| [Buck loop outside the example envelope](loop-out-of-example-envelope.md) | missed | BR-1, BR-2, BR-3, BR-4, BR-10 |
| [Forced-continuous buck into a rail that cannot sink](fcm-reverse-current-into-non-sinking-rail.md) | missed | CR-1, BR-5, CR-4 |
| [Bead and capacitor resonating at fsw](bead-tank-at-switching-frequency.md) | caught | FLT-1, FLT-2 |
| [Strap pairs fitted on both sides](strap-pairs-fitted-both-sides.md) | missed | STR-1, STR-2, STR-3, NET-7 |
| [UVLO resistor decade typo](uvlo-resistor-decade-typo.md) | caught | EN-1, NET-6 |
| [Memory buses shorted by a name collision](bus-net-name-collision.md) | caught | NET-1, NET-2, MEM-1 |
| [Enable divider with 40 mV of margin](enable-divider-thin-margin.md) | missed | EN-2, EN-3 |
| [Reset diode-OR margins](reset-diode-or-margins.md) | near miss | RST-1, RST-2, RST-9 |
| [Boot pin divider](boot-pin-divider.md) | caught | STR-5, STR-2 |
| [Watchdog armed with blank flash](watchdog-armed-with-blank-flash.md) | near miss | RST-6, RST-7 |
| [Sheet dropped from the compile](sheet-dropped-from-compile.md) | caught | NET-3, NET-4 |
| [Fix batch regressions](fix-batch-regressions.md) | caught | NET-4 |
| [I2C pins crossed](i2c-pins-crossed.md) | caught | IO-5 |
| [Oscillator output domain](oscillator-output-domain.md) | caught | CLK-1, CLK-4 |
| [Pull-ups above pin abs max](pullups-above-pin-abs-max.md) | caught | IO-2, EN-5 |
| [Simulation setup errors](simulation-setup-errors.md) | near miss | 40_checks sanity checks, BR-2 |
| [I/O range fuses](io-range-fuses.md) | near miss | IO-4, MEM-4 |
| [Module keepout](module-keepout-shadow.md) | caught | LAY-6 |
| [Verifier dispute on ESD grounds](verifier-dispute-esd-grounds.md) | near miss | 50_verify, PROT-4 |
| [DNP in the schematic, fitted in the PCB](dnp-in-schematic-fitted-in-pcb.md) | caught | NET-7, NET-1 |

## Adding a lesson

1. Write the rule in one sentence, vendor-neutral, and link the checklist item. If no item
   covers it, add the item first.
2. What happened, with numbers and document pages. Public part numbers only. No netlists,
   schematic images or BOM extracts.
3. Why the review missed or caught it.
4. In the board-review repo, add the expected finding to the board's local eval file
   (`evals/<board>/local/expected.json`).

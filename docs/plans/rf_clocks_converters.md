# Plan: RF front ends, data converters and clocks

Status: plan only. Nothing here is built. River reviews it first.
Date: 2026-10-15.

How to read: sections 1 to 5 take about 15 minutes. Sections 6 to 16 are reference tables.
The held-out board's revision history is sealed in evals/hackrf_one/local (ignored by git). Anyone writing checklists or lessons must not read it.

Conventions in this page:
- `[KEY p.N]` points to a source in section 16, with the page or section.
- UNSURE: not confirmed in the source. Section 15 lists each one and what would settle it.
- DERIVED: a formula worked out from cited inputs. No vendor page prints it.
- "default": a pass threshold we chose, as in the existing checklists. River may change it.
- Planned modules are named without their package: `jitter.snr_jitter` means the planned
  calculator module `jitter` in the calc package, and `touchstone` is a planned module in the sim
  package. tests/test_skill_names.py resolves every full `calc` or `sim` name cited under docs/,
  so only modules that exist today carry the prefix (for example `calc.lc_tank.lc_filter`).

## 1. Summary

The skill reviews power, resets, straps, Ethernet, cameras and memory well. Its one clock checklist
covers crystals and simple oscillators. RF and converter boards fail for other reasons:
- a balun that covers only part of the tuning range;
- an ESD diode with 1 pF at 6 GHz;
- switch blocking caps that charge up;
- an LVPECL output with no DC path;
- an AC-coupled one-shot SYSREF;
- an oscillator on a noisy digital rail;
- a regulator harmonic sitting on the IF.

This plan adds:

| Piece | What |
|---|---|
| Checklists | `rf_front_end` (RF-1 to RF-14), `data_converters` (ADC-1 to ADC-11), `spur_plan` (SPUR-1 to SPUR-6), `clock_distribution` (CKD-1 to CKD-13). Same item format as today. |
| Calculators | `jitter`, `clock_term`, `pll`, `rf`, `spur`, `converter`. About 35 functions, each returning a `Result`. Section 10 gives worked numbers for tests. |
| Simulation | `touchstone`: read Touchstone 1.x and 2.x, cascade, return and insertion loss, renormalize, passivity. numpy only. |
| Blocks | Finders for baluns, RF switches, amplifiers, attenuator pads, clock buffers, PLLs and converters. |
| Schema | New blocks and failure modes (section 2). |
| Evals | HackRF One r9 held out (history sealed in evals/hackrf_one/local). LimeSDR Mini and ADI FMCOMMS2/5 as dev cases. ADALM-PLUTO as lessons now, scored later. Seeded clock and RF bugs. |
| Bench | A bench test for every check (section 12). |

Out of scope now: impedance and stackup (section 14).

## 2. What changes in the repo

| Path | New or changed | Notes |
|---|---|---|
| skill/checklists/rf_front_end.md | new | RF-1 to RF-14 (section 6) |
| skill/checklists/data_converters.md | new | ADC-1 to ADC-11 (section 7) |
| skill/checklists/spur_plan.md | new | SPUR-1 to SPUR-6 (section 8). Runs once per board, across blocks. |
| skill/checklists/clock_distribution.md | new | CKD-1 to CKD-13 (section 9). clocks_crystals.md keeps CLK-1 to CLK-6 and links here. |
| skill/workflow/00_intake.md | changed | RF requirements block: tuning range, IF, LO side, sample rates, NF, IIP3, spur limit, jitter need per clock consumer, PCIe generation. |
| skill/workflow/40_checks.md | changed | Failure-mode index rows for the new items. |
| skill/schemas/finding.schema.json | changed | Blocks for the four checklists. Failure modes `rf_mismatch`, `rf_instability`, `spur_in_band`, `jitter_budget`, `termination_error`, `sync_fault`. |
| skill/schemas/datasheet_digest.schema.json | changed | Clock I/O type, VOH, VOL, VOD, VCM, input VICM range, PSRR. RF part band, S2P file, its bias and reference plane. Converter clock input, VCM, reference caps, JESD parameters. |
| tools/boardreview/calc/ | new | jitter.py, clock_term.py, pll.py, rf.py, spur.py, converter.py |
| tools/boardreview/sim | new file | touchstone.py (section 11) |
| tools/boardreview/blocks/ | new, changed | rf.py, converters.py; clocks.py extended to buffers and PLLs |
| evals/ | new | hackrf_one (held-out, local files), limesdr_mini (dev), seeded RF and clock classes in bug_classes.json |
| skill/lessons/ | new | Pluto Rev A oscillator supply, FMCOMMS2 crystal, LimeSDR Mini part swap, Si534x termination exceptions |

## 3. Build order (j)

Sizes: S is under a day, M is one to three days, L is a week or more.

| Step | Work | Size | Why now |
|---|---|---|---|
| 0 | Seal HackRF: the history is already moved to `evals/hackrf_one/local`; turn it into `expected.json` and add a held-out manifest row. | S | Must happen before checklist work. |
| 1 | `jitter` with tests W1 to W8 | M | Every clock and converter check needs it. Formulas are short and well sourced. |
| 2 | `clock_term`, clock_distribution.md, digest fields for clock I/O | M | Clocks are on every board, Sauron included. |
| 3 | `pll` (check, 2nd and 3rd order design), tests W19 to W23 | M | |
| 4 | Seeded clock bugs: LVPECL with no pull-downs, LP-HCSL double-terminated, X7R loop filter, gated AC-coupled clock | S | Cheap recall test before real boards. |
| 5 | `spur`, spur_plan.md | M | |
| 6 | `rf` | M | |
| 7 | `touchstone` | M | RF-1 and RF-6 need real part data. |
| 8 | rf_front_end.md, RF block finders | L | Most new parsing work. |
| 9 | `converter`, data_converters.md | M | |
| 10 | Dev evals: LimeSDR Mini change lists, FMCOMMS2 and FMCOMMS5 cases, Pluto lessons | M | |
| 11 | Bench templates in report.md | S | |
| 12 | Freeze checklists, review HackRF r9, reveal, move HackRF to dev | S | |
| Later | PDF or Allegro intake to score Pluto (L); IBIS through KiCad and ngspice (M); Monte Carlo matching with S2P parts (M); impedance and stackup (L) | | |

## 4. Decisions for River

Decided 2026-10-15:
- **Pass limits:** no baked-in defaults. A limit comes from the board's requirement or the part's
  datasheet. Where neither gives one, the reviewer chooses by engineering judgment, states the
  number and the reason, and marks it JUDGMENT. Numbers this plan calls "default" are cited
  starting points only. Calculators take the limit as an argument and report INFO or UNKNOWN
  without one.
- **Manufacturer models:** no model library. The skill says which files to fetch per part kind at
  review time and how to judge whether they apply; the code only reads them (skill/workflow/models.md).
- **Build:** parallel workers, one per calculator module or checklist, reviewed and merged by the
  coordinator.

Still open:

1. **HackRF seal.** Approve step 0? HackRF's history is public, so a reviewer may know it. Score
   on the derivation (nets, levels, math), not on naming the bug.
2. **Pluto.** Its files are Allegro and PDF. Build a PDF or Allegro netlist path (L), or use Pluto
   for lessons only. I suggest lessons only for now.
3. **Default thresholds** in sections 6 to 9. For example:
   - RL 10 dB for matches, 20 dB for ESD parts and pads;
   - 1 dB jitter SNR loss;
   - PLL phase margin 45 degrees;
   - coupling cap Xc under 5 ohm.
   Accept or change.
4. **Names** of the four checklists and six failure modes in section 2.
5. **Intake.** It needs an RF and clock requirements block. Without one, many checks can only
   print INFO.

## 5. Niche misses reviewers make (e)

Each row is a real or vendor-documented miss, with the item it becomes.

| # | Miss | Evidence | Item |
|---|---|---|---|
| 1 | Oscillator with no PSRR powered from a noisy digital rail | Pluto Rev A EVM about -32 dB against a -45 dB goal; fixed with an ADM7160 LDO [PLUTO-HW] | CKD-6 |
| 2 | Narrowband balun on a wideband transceiver | AD9361/AD9364 boards ship a 2.4 to 2.5 GHz balun; ADI says change it for other bands [ADI-CFG] | RF-2 |
| 3 | SYSREF AC-coupled while gapped or one-shot | Charge on the caps gives a false edge on restart [SLYT628 p.16; ADS54J54 p.28; ADC16DX370 p.55] | ADC-9 |
| 4 | SOI switch blocking caps with no discharge path | A few hundred mV on the port stresses the gate oxide; fit 1 to 8 kohm shunts [AN27 p.1 to 2] | RF-8 |
| 5 | ESD diode capacitance read at 1 MHz, not at the band; working voltage under the TX peak | TPD1E0B04 C is specified at 1 MHz [TPD1E0B04 §5.3 to 5.5]; 200 mW in 50 ohm is 3.16 V RMS but 4.47 V peak against a 3.6 V range (DERIVED from [TPD1E0B04 §7.2.2]) | RF-9 |
| 6 | Paste under tiny RF ESD diodes | Shorted Pluto Rev D RF ports to ground; later builds drop the diodes [PLUTO-ESD] | RF-9 |
| 7 | Broadband MMIC unstable below its band | PGA-105+ has k < 1 below 60 MHz without its network [MC-063 Sht 1 to 2] | RF-6 |
| 8 | DC block with a parallel resonance inside the band | 100 pF ATC 100A notches at 1.6 GHz flat-mounted [ATC] | RF-10 |
| 9 | Mixed decoupling values that anti-resonate | 22 nF with 100 pF is worse than 22 nF alone from about 15 to 175 MHz [CY1032 p.2 to 3] | RF-7 |
| 10 | AC-coupled LVPECL with no emitter pull-downs | Output never switches [AN-828 p.1 to 2; SLLA120 p.13] | CKD-3 |
| 11 | The opposite on Si534x: LVPECL must have no source pull-downs; HCSL outputs must be AC-coupled with a divider, never 50 ohm to ground | [AN1051 §2.1 p.4 to 6] | CKD-3 |
| 12 | HCSL style mixed up | Traditional HCSL without 50 ohm to ground does not switch; LP-HCSL with an end termination has half swing [AN-808 p.1; AN-879 p.3 to 4; AN-891 p.2] | CKD-5 |
| 13 | Clock source and sink with opposite coupling rules | Si534x HCSL outputs are AC-coupled only [AN1051 p.5]; Agilex P-tile HCSL refclk inputs are DC-coupled only [683112] | CKD-1, CKD-5 |
| 14 | Coupling cap too small for a low-MHz reference | Xc must be under 5 ohm at the clock frequency [AN1051 §2.2 p.7] | CKD-4 |
| 15 | Bead or LC peaking on an oscillator supply | The peak shows as a phase-noise bump at 10 to 30 kHz offset [AN10006 p.11 to 14] | CKD-6 |
| 16 | X7R in a PLL loop filter | Microphonics and dielectric absorption; slow settling and spurs [ICS663 p.5; SNAA106C p.143, 287 to 288] | CKD-7 |
| 17 | Sample clock routed through an FPGA or logic gate | About 10 ps added, 29 dB SNR lost at 40 MHz [AD42 p.6; MT-031 p.11] | ADC-2 |
| 18 | ADC input shunt C kept for IF sampling; low-pass AAF used in the 2nd Nyquist zone | [AD9268 p.26, 28; MT-002 p.10] | ADC-5 |
| 19 | Reference cap with too low an ESR | A 0.1 ohm ceramic made the reference amplifier peak; a 1.5 ohm part was quieter [SLYT339 AAJ p.15] | ADC-3 |
| 20 | Transceiver analog rail ripple at low frequency | 16 mV at 40 kHz on the AD9361 1.3 V rail took Rx EVM from -37.8 to -24.9 dB [UG-570 p.120 to 123] | ADC-10, SPUR-4 |
| 21 | Spread spectrum on a sensitive DAC or clock rail | SSFM adds noise below about 100 kHz; ADI does not recommend it on an AD9175 rail [OP1 p.3; OP2 p.2] | SPUR-6 |
| 22 | Regulator in PFM near RF | PFM frequency moves with load; forced PWM "reduces or eliminates interference with RF" [TPS62840 §8.4.1 to 8.4.2] | SPUR-1 |
| 23 | End-of-life swap that changes RF capacitance | LimeSDR Mini 2.x replaced a 1.2 pF shunt part with an 11 pF one; loopback attenuation moved [LIME-MINI2 docs v2.2] | RF-14 |
| 24 | Crystal that does not meet the transceiver's spec | Generic TSX-3225 40 MHz on FMCOMMS2 does not meet AD9361 specs [FMC2-HW] | CKD-9 |
| 25 | VCXO tuning range not reached by the DAC | LimeSDR Mini 2v5 changed its tuning DAC divider "to get full VCTRL voltage scale" [LIME-MINI2 2v5] | CKD-13 |
| 26 | Stability formula copied from a note with a typo | Keysight 5990-9974EN p.3 prints Delta as S11S21 - S12S21 [KS5072 p.3] | RF-6 calculator test |
| 27 | Model data at the wrong conditions | Murata and TDK S-parameters have no DC bias; Coilcraft SRF reads high because the fixture is de-embedded [MURATA-S; TDK-README; CC1721] | Section 11 rules |

## 6. RF front end checklist (a)

Applies to every antenna port, match, balun, filter, switch, amplifier, pad and DC block on an RF path.

| ID | Check | Why | Compute | Pass | Not published | Source |
|---|---|---|---|---|---|---|
| RF-1 Matching network parts | Each L and C in a match: value, tolerance, Q and SRF at the band. A tuning footprint (pi) at the antenna and at each match. | Smith-chart values differ from built values. Multilayer inductors have lower Q than wirewound (31 against 78 at 900 MHz for about 2.7 nH 0402). | `rf.element_impedance` for SRF and Q; `rf.match_sweep` for RL at band edges over tolerance | Inductor SRF at least 10 times f_max [CC671]. RL at least 10 dB at every corner (default). Pi footprint on first spins. | Q or SRF missing: use the vendor S2P. None: unknown; require the pi footprint and a VNA check. | [CC671 p.1 to 2, Table 1; SWRA730 §1.2 p.5, §4 p.14]. Vendor RL-against-tolerance figure: UNSURE. |
| RF-2 Balun type, ratio and band | Which port is unbalanced; impedance ratio against the chip's port impedance (50:50, 50:100, 50:200); rated band against the full tuning range. | Outside its band a balun adds loss and phase imbalance. | Digest comparison; `rf.mismatch` for a ratio error | Rated band covers the tuning range; ratio matches the chip's recommended port impedance. | Chip port impedance missing: vendor question and VNA. | [MC-AN20-001 Sht 2 to 3; ADI-CFG; JTI-2450 p.1; JTI-1720 p.1] |
| RF-3 Balun DC path | Whether the balun passes DC (autotransformer, center tap, ceramic "GND or DC feed" pin); what DC the chip's RF pins need; DC current against the balun rating; bypass cap on the DC-feed pin. | An isolated balun leaves pins unbiased. An autotransformer gives no DC isolation. A DC-feed pin without its bypass leaks RF into the supply. | None; digest pin tables. `rf.element_impedance` for the bypass. | DC path matches the chip datasheet; current under rating (TCM1-63AX+ 30 mA abs max); DC-feed pin bypassed (68 pF on 1720BL). | Chip bias need missing: vendor question; footprint for a choke option. AD9361 TX bias detail: UNSURE. | [MC-AN20-001 Sht 2; JTI-1720 p.1 to 2; TCM1 Rev C] |
| RF-4 Filters against tuning range, image and half-IF | For every tuning step and LO side: image band, half-IF band and LO leakage against each preselector and image filter, including switched bands and their control logic. | A mixer answers at f_LO + f_IF and f_LO - f_IF. A filter that covers part of the range lets the image in at some settings. | `spur.frequency_plan` | Image and half-IF attenuated by the receiver's spur requirement at every step; switched bands overlap with no gap. | Rejection curves missing: vendor S2P or bench sweep. | [AN150 p.11 to 12; M1838 p.2 to 3; MT-080 p.5 to 6] |
| RF-5 LNA and PA bias | Bias tee choke SRF and impedance across the band; DC blocks; bias resistor and current limit. Depletion-mode GaAs and GaN: gate negative first, drain after, gate never removed before drain, enforced in hardware. | A choke above its SRF is a capacitor. A drain powered before the gate draws uncontrolled current. | `rf.element_impedance` for the choke; `calc.timing.budget` for sequence delays | Choke impedance at least 10 times Z0 across the band (default); hardware sequencer present. | Choke SRF missing: vendor S2P or bench S21 of the bias tee. | [MC-149 p.2 to 4; CC945 p.1; CC1193; CC671 p.2] |
| RF-6 Amplifier stability (schematic part) | K, abs(Delta) and mu from the device S2P at every frequency in the file, with the resistive loading, choke and decoupling cascaded in. The vendor's stabilizing network fitted. | Broadband MMICs have high gain below the band. Layout parasitics (ground vias) are outside this check and come with layout review. | `rf.stability` on `touchstone` data | K > 1 and abs(Delta) < 1, or mu > 1, at every frequency in the file. | No low-frequency S2P: unknown; require a series R or shunt RC footprint and a bench oscillation check. | [KS5072 p.3 (Delta misprinted); AN154 p.19 to 22; MC-063 Sht 1 to 2; TR1108 p.5, 12 to 13]. Edwards and Sinsky paper not opened: UNSURE. |
| RF-7 RF supply decoupling | Each RF supply pin: cap SRF and first PRF against the band; mixed values that anti-resonate in band; the choke or bead feeding them. | Above SRF a cap is an inductor. Two values in parallel make a high-impedance peak between their SRFs. | `rf.network_impedance` | No anti-resonance peak in the RF band, the IF band or at a listed aggressor (SPUR-1). | ESL missing: a package-based ESL range is an assumption, so the result stays unknown; vendor S2P. | [JTI-SRF p.1; ATC; CY1032 p.2 to 3] |
| RF-8 Switch control and DC on RF ports | Control levels against the driver; supply order (control after VDD where stated); negative supply; DC on RF ports. GaAs positive-control parts need external DC blocks. SOI parts need none at 0 VDC. Capped ports on SOI parts with no discharge path need a 1 to 8 kohm shunt. Isolation and power handling at f_max. | Blocked SOI ports charge on transients. Isolation falls with frequency (PE42423: 47 dB at 2.4 GHz, 43 dB at 6 GHz). | `calc.divider` level check as in IO-1; isolation budget from `rf.cascade` levels | VOH min at least VIH min and VOL max at most VIL max at corners; shunt R where needed; isolation at f_max meets the requirement. | Discharge path not stated: vendor question; fit the resistor footprint. | [AN27 p.1 to 3; PE42423 p.1, 3, 10; AS179 p.2 to 3] |
| RF-9 Antenna port ESD | ESD part capacitance at the band (not the 1 MHz figure); its RL and IL; working voltage against TX peak with mismatch; IEC rating; assembly of tiny diodes. | 1 pF at 5.8 GHz gives RL 3.4 dB and IL 2.6 dB (W26). | `rf.shunt_c`; `rf.peak_voltage` | RL at least 20 dB and IL at most 0.1 dB from the ESD part alone (default); peak voltage under the working voltage. | C at f missing: C-against-f curve or S2P; else unknown and VNA check. | [ESD101 p.1, 10; TPD1E0B04 §5.3 p.4, §7.2.2 p.13 to 14; PLUTO-ESD]. Shunt inductor as ESD path: UNSURE. |
| RF-10 DC blocks | Value against the lowest frequency; SRF and PRF against the highest; voltage rating and bias derating; broadband part for wide tuning. | A series cap is a high-pass. A PRF notch can sit inside the band. | `rf.dc_block` | IL at most 0.1 dB at f_min (default); no SRF or PRF notch in band. | PRF missing: S2P or VNA. | [ATC; JTI-SRF p.1; 550L] |
| RF-11 Shield cans | Frame land pattern against the frame datasheet; parts under the can against its height; removable lid or two-piece frame on first spins; cavity modes against the band and strong harmonics. | An empty can resonates. A 30 x 20 mm can has its first mode near 9.0 GHz (W31). | `rf.cavity_modes` | Lowest mode above the highest significant frequency, or absorber planned. | Land pattern guides: UNSURE (none opened). | [ICM]; via fence spacing [SNAA408 §3.4.2] waits for stackup work. |
| RF-12 Attenuator pads | R values against the formula for A and Z0; E96 rounding effect on A and RL; power in each resistor; resistor type and size for the frequency. | In a 6 dB pi pad the input shunt and the series resistor each take a third of the input power (W29). | `rf.pad` | abs(A - target) at most 0.25 dB; RL at least 20 dB; each resistor at most 50% of rating at max input (defaults). | HF parasitics: thin film, 0402 or smaller above 1 GHz (default). | Formula DERIVED (no vendor page found); [VSH p.2, 4] |
| RF-13 Lineup gain, NF, linearity and levels | Cascaded gain, NF, IIP3 and P1dB per path and gain state; level at each stage against its abs max and the ADC full scale. | Loss before the LNA adds straight to NF. Late stages set IIP3. | `rf.cascade` | Meets the intake requirement; no stage above its abs max input. | A stage's NF or IP3 missing: unknown; Y-factor and two-tone on the bench. | [AN57-1 eq 2-3 p.8; MC-LIN; MC-5G; MC009 p.6] |
| RF-14 RF part substitutions | Any alternate or replacement on an RF net: capacitance, Q, SRF and band against the original. | A substitute with 10 times the capacitance changes RL and attenuation. | `rf.shunt_c` or `rf.element_impedance` for both parts | RL and IL change inside the budget. | Substitute data missing: unknown; VNA check. | [LIME-MINI2 docs v2.2] |

## 7. Data converter checklist (b)

Applies to every ADC, DAC and transceiver with on-chip converters.

| ID | Check | Why | Compute | Pass | Not published | Source |
|---|---|---|---|---|---|---|
| ADC-1 Sample clock jitter against SNR | Clock jitter at the converter (source, each buffer, RSS) plus the converter's aperture jitter, against the SNR needed at the highest input frequency, undersampled bands included. Integrate clock phase noise from 20 Hz to at least fs, better 2 fs. | Jitter SNR falls 20 dB per decade of input frequency. 100 fs limits SNR to 64 dB at 1 GHz. | `jitter.pn_to_jitter`, `jitter.rss`, `jitter.snr_jitter` | SNR loss from jitter at most 1 dB (default; jitter SNR about 6 dB above the converter SNR). | Clock phase noise not published: bench phase noise; result unknown until then. | [MT-008 p.2 eq 1, p.4 eq 2 to 3; MT-007 p.3 to 4; AN-501 p.2 eq 5 to 6; SLYT379 AAJ p.6 to 7; SBAA653A p.2 to 3; MT-200 p.3] |
| ADC-2 Clock path and input | Clock input type and coupling; slew at the pins; no FPGA, CPLD or gate in the sample clock path; clock supply separate from the output driver supply; duty cycle stabilizer limits. | A gate added about 10 ps and cost 29 dB SNR at 40 MHz. Slow edges raise aperture jitter. The DCS fails below about 20 MHz on AD9268. | `jitter.snr_jitter` with the gate's jitter | No logic in the path; slew at least the vendor figure (about 1 V/ns for 100 fs at 70 MHz). | Slew not given: bench measure. | [AD9268 p.30 to 31; AD42 p.2 to 6; MT-031 p.11; MT-200 p.3] |
| ADC-3 Reference | Reference caps against the datasheet: value, ESR, placement; reference buffer drive for SAR parts; required series R. | A SAR reference pin draws charge each conversion. A too-low-ESR ceramic can make a reference amplifier peak. | `calc.mlcc_bias` for capacitance at bias | Values and ESR as the datasheet asks; effective C at bias above its minimum. | ESR limit missing: follow the vendor reference design. | [AD9268 p.41; AD7980 p.9, 18, 25; ADS8910B p.6 to 7; SLYT339 AAJ p.14 to 15; SLYT355 AAJ p.7 to 9] |
| ADC-4 SAR input RC and driver | C_ext against C_DAC (kickback); RC settling to half an LSB in t_acq; C0G; amplifier bandwidth, noise and THD against the ADC. | Too slow an RC leaves the last sample in this one. Too small a C lets kickback through. | `converter.sar_rc` | Settles in t_acq; C_FLT at least 20 C_S; UGB at least 4/(2 pi R C); driver noise under 20% of ADC noise. | C_DAC missing: vendor question. | [AD46 p.1 to 4; ADS8910B p.57 to 58; AD7980 p.17] |
| ADC-5 High-speed input network and AAF | Series R, shunt C, balun or driver; filter type against the Nyquist zone (band-pass in zone 2 and up); transformer low-frequency limit; kickback settling in half a clock. | Shunt C left for IF sampling costs SFDR. A low-pass AAF does nothing for an undersampled band. | `spur.alias` for the band edges | AAF stop band covers every band that folds onto the wanted one, at the required dynamic range. | Filter response missing: bench sweep. | [AD9268 p.26, 28; MT-002 p.10; AN-742 p.1, 3] |
| ADC-6 Common mode | VCM output decoupled and wired to driver VOCM or the transformer center tap; AC-coupled inputs biased; DC-coupled driver CM inside range. | Many inputs are not self-biased. More than 100 ohm between VCM and the inputs needs the CM servo. | `calc.divider` for bias networks | CM inside the datasheet range at corners. | None expected. | [AD9268 p.26 to 27, 41; AD9361 p.5, 17] |
| ADC-7 Parallel outputs (LVDS, CMOS) | LVDS 100 ohm at the far end or internal; CMOS outputs with series R and light loads or a buffer next to the converter; SPI quiet during capture. | CMOS edge current couples back to the input: 10 pF at 1 V/ns is 10 mA per bit. | `calc.timing.rc_edge` | Per datasheet; series R on CMOS outputs (default). | None expected. | [AN-586 p.1 to 3; MT-031 p.8 to 9; AD9268 p.32, 41]. DDR and SDR timing: UNSURE (not researched). |
| ADC-8 JESD204 lanes | Lane rate against both ends and the encoding; AC caps (often 100 nF) and their impedance at the lowest frequency; DC-coupled CM ranges if no caps; 100 ohm differential. | 8b/10b above 12.5 Gb/s is outside JESD204B. | `converter.jesd_lane_rate` | Rate inside both ends' limits; cap impedance under 1 ohm at the lowest frequency. | None expected. | [AD9680 p.9, 68, 73; UG-1578 p.58, 184; ADC12DJ3200 p.5 to 6, 133; SBAA402A p.3 to 4; JESD-SG printed p.18] |
| ADC-9 SYSREF and multi-device sync | SYSREF mode against its coupling; frequency an integer submultiple of LMFC (204B) or LEMC (204C); setup and hold to the device clock; matched clock and SYSREF pairs from one source; SYNC~ wiring. | An AC-coupled gapped or one-shot SYSREF makes a false edge on restart. Continuous SYSREF can add spurs. | `converter.sysref` | DC-coupled for gapped and one-shot (unless the datasheet says otherwise, for example [ADC12DJ3200 p.10]); AC only for about 50% duty periodic with the HPF corner below f_SYSREF/4; integer submultiple; skew inside setup and hold. | Setup and hold missing: vendor question. | [SLYT628 p.15 to 17; ADS54J54 p.28; ADC16DX370 p.54 to 55; LMK04828 p.21, 41; UG-1578 p.27 to 28; AD9680 p.11, 76, 80; JESD-SG printed p.18, 54 to 56] |
| ADC-10 Converter and transceiver supplies | Each rail's PSRR or PSMR against the ripple and noise on it; transceiver analog rails and their switcher frequency; LDO for synthesizer and LO rails. | Low-frequency ripple on a transceiver analog rail degrades EVM (miss 20). | `spur.supply_spur`; `calc.lc_tank.lc_filter` | Supply spur at least 6 dB under the SFDR target (default). | PSRR curve missing: bench injection test. | [MS-2210 p.3, 6; OP1 p.3 to 5; UG-570 p.120 to 126; SLVAEW7 p.3; SLYT720 p.1 to 3] |
| ADC-11 Unused converter pins | Unused inputs, outputs and channels tied as the datasheet says, which can depend on the IP configuration. | RFSoC: an ADC not enabled gets VIN tied to GND; enabled but undriven may float only with AC coupling set. | None | Per datasheet. | None. | [UG583 "Unused ADC & DAC Pins"] |

## 8. Spur plan checklist (c)

Runs once per board. Inputs come from intake (bands, LO plan, sample rates) and from blocks (every
regulator and clock).

| ID | Check | Why | Compute | Pass | Not published | Source |
|---|---|---|---|---|---|---|
| SPUR-1 Aggressor list | Every periodic source: switcher fsw over its range and spread, PFM modes, clocks and dividers, USB 480 MHz, Ethernet, DDR, SPI. | An aggressor not on the list is never checked. PFM frequency moves with load. USB noise at 480 MHz hurt Pluto Rev A. | None; built from blocks and digests | Complete list; switchers near RF in forced PWM or synchronized (default). | fsw range missing: datasheet min and max. | [TPS62840 §8.4.1 to 8.4.2; PLUTO-HW] |
| SPUR-2 Harmonics and aliases | n times f for each aggressor up to an order limit against RF, IF and baseband bands at each tuning setting; aliases into the first Nyquist zone. | A buck harmonic lands on the IF; a clock harmonic folds into baseband. | `spur.search` | No hit, or each hit has a level estimate under the spur limit and a named fix. | Harmonic levels unknown: hit stays a finding with a bench scan. | [MT-002 p.5; MT-003 p.2] |
| SPUR-3 Mixing products | abs(m f_LO plus or minus n f_aggr) in the IF; image; half-IF; odd LO harmonics in switching mixers. | Aggressors mix with the LO even when they miss the RF band. | `spur.search` with the LO list | As SPUR-2. | Mixer spur table missing: m and n up to 3 (default). | [M1838 p.2 to 3; MC011 p.1, 4; MT-080 p.5 to 7] |
| SPUR-4 Supply ripple on PLL, VCO, LO and reference | Ripple and noise at each PLL, VCO and oscillator supply; VCO pushing; charge pump supply rejection. | Ripple frequency-modulates the VCO; sidebands appear at plus and minus f_ripple outside the loop bandwidth. | `jitter.ripple_sideband`; `calc.lc_tank.lc_filter` | Sideband under the spur limit. | Pushing missing: AD45 range 5 to 20% of Kvco as an assumption, result unknown. | [AD45 p.1 to 3; PSMR p.1 to 2; ADF4350 p.3] |
| SPUR-5 Clock spurs onto the signal | Spurs on the sample clock scaled to the input frequency. | A clock spur moves to the signal at 20 log10(f_in/f_clk) relative. | `jitter.spur_transfer` | Under the spur limit. | Clock spur levels missing: bench phase noise. | [AN-756 p.5 eq 12 to 13; MT-200 p.4] |
| SPUR-6 Spread spectrum or sync per regulator | For each switcher near RF or converters: SSFM, sync to a common clock, or fixed. Parts that cannot sync with spread on. | SSFM raises noise below about 100 kHz. Unsynchronized switchers beat. TPS62913 syncs only with spread off. | `spur.search` with the spread range as a band | Plan written per regulator; no SSFM on rails feeding sample clocks, LOs or DACs unless the vendor measured it (default). | Locking the sync clock to the system reference so spurs land at known offsets: no source found (UNSURE). | [OP1 p.3; OP2 p.2; OP3 p.3; LT8650S p.10, 23; TPS62913 p.18 to 19; DOSTAL] |

## 9. Clock distribution checklist (d)

Applies to every differential clock, every PLL, VCXO and TCXO, and every reference input.
Crystals keep CLK-2 and CLK-3.

| ID | Check | Why | Compute | Pass | Not published | Source |
|---|---|---|---|---|---|---|
| CKD-1 Driver and receiver pairing | Each clock net: driver type, receiver type, and whether DC coupling is allowed (table 9.1). | "HCSL" covers two driver styles with opposite needs. Some inputs are DC-coupled only. | `clock_term.compat` | Driver VOH and VOL inside the receiver's VICM range and abs max at worst supplies; VID at least its minimum. | Receiver VICM missing: vendor question; AC couple with a bias footprint. | [SCAA062 Table 3 p.3; SLLA120 p.3 to 16; AN-828 p.11 to 12; 683112] |
| CKD-2 Termination values | Network per standard and rail (table 9.1); series R at the driver; termination at the receiver. | Wrong values shift common mode and swing. | `clock_term.termination` | Within 2% of the computed or vendor network (default). | None expected. | Table 9.1 |
| CKD-3 AC coupling and re-bias | DC path for the driver (LVPECL pull-downs, HCSL 50 ohm); receiver re-bias inside VICM; vendor exceptions. | LVPECL with no pull-down never switches. On Si534x the same pull-downs are wrong. | `clock_term.termination`; `calc.divider` | Per the driver datasheet. Pull-down values differ by vendor (140 to 240 ohm at 3.3 V). | Driver silent on pull-downs: use the vendor family app note. | [SCAA059C p.3 to 8; SLLA120 p.13; AN-828 p.9, 13; AN-953 p.6 to 7, 20; AN1051 §2.1 p.4 to 6] |
| CKD-4 Coupling capacitor sizing | Xc at the clock frequency; corner with the bias network; clock duty cycle; start-stop clocks; data pattern. | High Xc attenuates. A non-50% clock shifts its crossing. A gated clock is invalid for about RC after start. | `clock_term.ac_coupling` | Xc under 5 ohm at f_clk; corner under f_clk/100 (default); outputs held for 2 RC after start. | None expected. | [AN1051 §2.2 p.7; SCAA112 p.2, 6 to 7; AN-828 p.13 Table 3; SCAA059C p.2]. Duty offset formula DERIVED. |
| CKD-5 PCIe reference clock | HCSL or LP-HCSL termination; 85 or 100 ohm; clock architecture (common, SRNS, SRIS); SSC; jitter against the generation (table 9.2); receiver coupling rules; PERST after REFCLK is stable. | LP-HCSL with an end termination halves the swing; traditional HCSL without 50 ohm does not switch. | `jitter.rss`; `clock_term.termination` | Termination matches the driver; source plus additive jitter (RSS) under the limit. | Additive jitter missing: bench. | [AN-808 p.1 to 2; AN-879 p.1 to 4; AN-891 p.1 to 2; 9QXL2001C p.10, 12, 17; SKY-PCIE p.2 to 5; 683112] |
| CKD-6 Supply for oscillators, buffers and PLLs | Quiet rail (LDO where the part has little PSRR); damped bead or LC filters; bead and inductor current rating; no switching loads on the rail. | See misses 1 and 15. | `calc.lc_tank.lc_filter` (FLT-1, FLT-2) against the part's sensitive offset band; `jitter.spur_to_jitter` | Filter peak at most 6 dB and outside the sensitive band; bead Imax at least 5 x IDD, inductor at least 2 x IDD [AN10006]. | PSRR missing: assume none and require an LDO footprint; bench injection. | [PLUTO-HW; AN10006 p.11 to 14; AN491 p.1 to 6; AN1051 §2.4 p.10] |
| CKD-7 PLL loop filter | Values against Icp, Kvco over the tuning range, N and f_PFD; C0G or film; C3 against the VCO input capacitance; leakage. | Bandwidth moves with Kvco and N. X7R loses capacitance with bias and adds microphonics and dielectric absorption. | `pll.loop_filter_check` (sweep); `pll.loop_filter_design` | Phase margin at least 45 degrees at all Kvco and tolerance corners (default); loop-gain spread within 15% or compensated with Icp; C0G or film; C3 at least 4 x VCO input C. | Kvco range missing: datasheet min and max; else unknown, bench phase noise shows the loop. | [SNAA106C p.143, 287 to 288, 299, 339 to 347; ICS663 p.5] |
| CKD-8 Clipped-sine TCXO and reference inputs | DC-cut cap (inside or outside the TCXO); load (10 kohm and 10 pF typical); amplitude (at least 0.8 Vpp); receiver bias and abs max; slew at the receiver. | Clipped sine into an unbiased CMOS input gives duty distortion or no clock. Slow edges raise additive jitter. Si534x says avoid clipped sine. | `clock_term.ac_coupling` | Per TCXO and receiver datasheets; slew at least 0.6 V/ns at buffer inputs [AN766]. | Receiver bias missing: add external bias. | [TG2520SBN p.1; SNAA411 p.4 to 6; AN766 p.2, 6; AN1051 §2.3.2 p.9; AD9361 p.5; UG-570 p.14 to 15] |
| CKD-9 Crystal drive, load and spec (extends CLK-2, CLK-3) | Drive level with ESR adjusted for C0/CL; part-specific rules (Si534x: no load caps, guard ring not to ground); crystal spec against the transceiver's requirement. | Overdrive ages the crystal. A generic crystal can miss a transceiver's spec (miss 24). | `calc.crystal.drive_level`; `calc.crystal.load_capacitance` | Drive under 80% of rating (as CLK-2); spec meets the chip's crystal table. | Drive current not computable: bench current probe. | [SNAA331 p.2 to 5; AN1051 §2.3.1 p.8; FMC2-HW] |
| CKD-10 Unused outputs and inputs | Unused outputs open or disabled per datasheet; unused inputs biased per datasheet; fail-safe on inputs that can idle. | A floating differential input with no fail-safe oscillates on noise. | None | Per datasheet; fail-safe or offset network on inputs that can idle. | Datasheet silent: one leg up, one down, through 1 kohm. | [SNVA745 p.2 to 9; SLLA082B p.2; SNLA187 p.37; AN-828 p.2 to 3; AN1051 §2.2 p.7 to 8] |
| CKD-11 Spread spectrum | Which clocks have SSC (center or down, depth, rate); every downstream PLL can track it; no SSC on interfaces that forbid it. | A low-bandwidth PLL filters SSC out and loses lock margin. Some oscillator inputs do not support SSC. | `jitter.ssc_emi` | SSC only where every receiver allows it; down spread when the system is at fmax. | SSC on ADC sample clocks and LO references: we expect it to be wrong, but no vendor states it (UNSURE). | [AN10005 p.2, 5, 7; SCAA103 p.3 to 4; QUARTUS-BW; SPRAD21J §6.1.3.1] |
| CKD-12 Jitter budget | Each consumer's jitter need and band; chain from reference to consumer: phase noise, multiplication, buffer additive jitter, spurs. | Budgets that ignore the band or the spurs pass on paper. | `jitter.pn_to_jitter`, `rss`, `multiply`, `spur_to_jitter` | Total under the requirement with 20% margin (default, as `calc.timing.budget`). | Additive jitter missing: bench. | [AN10007 p.3 to 10; AN256 p.1, 4; AN766 p.2 to 3; SNAA106C p.1, 12, 228] |
| CKD-13 VCXO control and range | Control-node noise and filtering; tuning DAC range against the pull range plus aging. | Control-node noise maps straight to phase noise. | `jitter.vc_noise`; `calc.divider` for the range | Control noise contribution 10 dB under the VCXO's own noise (default); DAC range covers pull plus aging. | Kv missing: datasheet pull range over control range. | [WENZEL-VCXO; LIME-MINI2 2v5] |

### 9.1 Output types and standard terminations

| Type | Levels | DC termination | When AC-coupled | Source |
|---|---|---|---|---|
| LVDS | 3.5 mA into 100 ohm = 350 mV; VCM about 1.2 V; receiver threshold 100 mV | 100 ohm across the receiver, or internal | Receiver re-bias if not self-biased (100 ohm plus 10 kohm/10 kohm to 1.65 V) | [SLLA120 p.10 to 11, 16; SNLA187 p.10, 90; SCAA059C p.3 to 8]. TIA/EIA-644 VOD limits: UNSURE. |
| LVPECL 3.3 V | VOH 2.4 V, VOL 1.6 V, VCM 2.0 V | 50 ohm to VCC - 2 V; Thevenin 127 ohm up and 82.5 ohm down; T, Y and PI networks | Pull-downs 140 to 240 ohm (TI 150 ohm); none on Si534x | [SLLA120 p.3 to 5; AN-828 p.3 to 9, 13; SCAA059C p.3 to 4; AN1051 p.4] |
| LVPECL 2.5 V | VCM about 1.2 V | Thevenin 250 ohm up and 62.5 ohm down (249 and 61.9 standard) | Pull-downs 56 to 91 ohm (Renesas); check the driver datasheet | [AN-828 Table 2; AN-953 p.17] |
| HCSL (traditional) | 15 mA, about 0.75 V swing | 49.9 ohm to ground at the source, 0 to 33 ohm series | Needs a DC path | [AN-808 p.1 to 2; AN-879 p.1] |
| LP-HCSL | Push-pull 0 to 0.8 V; about 17 ohm out | Series only (33 ohm for 100 ohm, 27 ohm for 85 ohm) or integrated; no 50 ohm to ground | Per datasheet | [AN-879 p.4; AN-891 p.1 to 2] |
| CML | VOH = VCC, VOL = VCC - 0.4 V, VCM about VCC - 0.2 V | 50 ohm to VCC, often internal | Si534x: 50 ohm at the receiver to VDD - 1.3 V; no pull-ups at the source | [SLLA120 p.13 to 14; AN1051 p.5] |
| HSTL | VOH = VDDQ - 0.4 V, VOL 0.4 V, VREF 0.75 V | Thevenin to 0.75 V: 220/68 ohm (3.3 V), 167/71 ohm (2.5 V), 100/100 ohm (1.5 V) | Per datasheet | [SCAA059C p.3, 6, 9] |
| LVCMOS | Rail to rail | Series Rs = Z0 - Ro at the driver (Ro 7 ohm gives 43 ohm); N outputs tied driving M loads: Rs = Z0 - Ro M/N | 1.8 V into 3.3 V buffers: see SCAA112 | [AN-953 p.1, 5; AN10006 p.18; SCAA112] |
| Clipped sine | At least 0.8 Vpp into 10 kohm and 10 pF | DC-cut cap, 0.01 uF on the Epson part | Receiver must bias itself or be biased | [TG2520SBN p.1; SNAA411 p.4 to 6] |

LVPECL Thevenin values come from `R_up = Z0 VCC / (VCC - 2)` and `R_down = Z0 VCC / 2` (DERIVED;
the printed values in [AN-828 p.3; AN-953 p.17] match).

### 9.2 PCIe reference clock jitter limits (common clock, after the PCIe filters)

| Gen | Limit | Source |
|---|---|---|
| 1 | 86 ps peak to peak | [9QXL2001C p.12 Table 11] |
| 2 | 3.1 ps RMS (3.0 ps in one table) | [9QXL2001C p.12; SKY-PCIE p.4 Table 1]. Which applies: UNSURE, settle with the PCI-SIG CEM spec. |
| 3 | 1.0 ps RMS | same |
| 4 | 0.5 ps RMS | same |
| 5 | 0.15 ps RMS | same |
| 6 | 0.10 ps RMS | [9QXL2001C p.12 notes 6 to 9] |
| 7 | 0.067 ps RMS | same |
| SRIS, SRNS | No spec limit. Common practice divides by sqrt(2): Gen5 106 fs. | [9QXL2001C p.12 note 10; SKY-PCIE p.5 Table 2] |

SSC for PCIe: modulation 30 to 33 kHz, up to 0.5% down spread [SKY-PCIE p.4; 9FGV0231 p.1, 3, 6].

## 10. Calculators (f)

Same style as `calc.crystal`. Argument names carry units. Every function returns a `Result` with a
formula, labeled inputs and outputs, a verdict, a plain summary and key numbers. W numbers point
to the worked examples in 10.7.

### 10.1 jitter (new calc module)

| Function | Formula | Inputs | Outputs | Verdict rule | Source | Tests |
|---|---|---|---|---|---|---|
| `snr_jitter` | SNR_j = -20 log10(2 pi f_in t); t = sqrt(t_clk^2 + t_ap^2); SNR = -10 log10(10^(-SNR_adc/10) + 10^(-SNR_j/10)) | f_in_hz, t_clk_s, t_ap_s, snr_adc_db | snr_j_db, snr_total_db, loss_db | Loss at most 1 dB pass, at most 3 dB marginal, above that fail (defaults) | [MT-008 p.2; AN-501 p.2 eq 5 to 6; SLYT379 AAJ p.6 eq 1] | W1, W2 |
| `pn_to_jitter` | A = integral of 10^(L(f)/10) df, power law between points (straight lines on log-log); sigma_phi = sqrt(2 A); t = sigma_phi/(2 pi f0); optional mask H(f) squared | points (offset_hz, dbc_hz), f1_hz, f2_hz, f0_hz | area_dbc, sigma_rad, jitter_s | Against a limit if given, 20% margin | [MT-008 p.4 eq 2 to 3; AN10007 p.9 eq 3, p.10 eq 4; SNAA106C p.228] | W3 |
| `rss` | sqrt(sum t_i^2) | terms_s, limit_s | total_s | Pass under limit with 20% margin | [AD42 p.4; AN766 p.2] | W4 |
| `multiply` | L_out = L_in + 20 log10(N) | dbc_hz, n | dbc_hz | Info | [SNAA106C p.1, 12] | W5 |
| `spur_to_jitter` | J = 10^(x/20)/(sqrt(2) pi f0) | spur_dbc, f0_hz | jitter_s | Info, feeds `rss` | [AN491 p.6 eq 1]; AN256 p.4 drops the sqrt(2), UNSURE which convention fits a single-sided spur | W6 |
| `spur_transfer` | spur_out = spur_clk + 20 log10(f_in/f_clk) | spur_dbc, f_in_hz, f_clk_hz | spur_out_dbc | Against the spur limit | [AN-756 p.5 eq 12 to 13] | W7 |
| `ripple_sideband` | beta = K_push V_pk / f_m; sideband = 20 log10(beta/2) dBc; valid outside the loop bandwidth | k_push_hz_per_v, v_pk_v, f_m_hz | beta, sideband_dbc | Against the spur limit | DERIVED from [AD45 p.1 to 2; PSMR p.1 to 2] | W8 |
| `vc_noise` | S_phi(fm) = (f0 Kv v_n / fm)^2 | f0_hz, kv_per_v (fractional), vn_v_rthz, fm_hz | s_phi_dbc_hz | Against VCXO phase noise | [WENZEL-VCXO] | W9 |
| `ssc_emi` | Reduction about 10 log10(S f_c / RBW) | spread_frac, f_c_hz, rbw_hz | reduction_db | Info | [AN10005 p.5, 7] | W9 |

### 10.2 clock_term (new calc module)

| Function | Formula | Inputs | Outputs | Verdict rule | Source | Tests |
|---|---|---|---|---|---|---|
| `termination` | Per table 9.1: LVPECL Thevenin R_up = Z0 VCC/(VCC - 2), R_down = Z0 VCC/2; LVCMOS Rs = Z0 - Ro; HCSL 49.9 ohm; LVDS 100 ohm; CML 50 ohm to VCC | standard, vcc_v, z0_ohm, r_out_ohm, fitted values | computed values, error of fitted values | Fitted within 2% (default) | Table 9.1 | W11 |
| `compat` | VOH, VOL, VCM of the driver against VICM range, VID min and abs max of the receiver, at supply corners | driver and receiver digests | margins in V | Pass with positive margin at all corners | [SCAA062; SLLA120; AN-828 p.11 to 12] | W12 |
| `ac_coupling` | f_c = 1/(2 pi R C); Xc = 1/(2 pi f C); dV = (D - 0.5) Vpp; dt = dV/slew; droop = 1 - exp(-t_run/(R C)) | c_f, r_bias_ohm, f_clk_hz, duty, v_pp_v, slew_v_per_s, run_bits, bit_rate_hz | f_c_hz, xc_ohm, dv_v, dt_s, droop | Xc under 5 ohm; f_c under f_clk/100; droop under 1% (defaults) | [AN1051 §2.2 p.7; SCAA112 p.2, 6 to 7]; dV and droop DERIVED | W13 |

### 10.3 pll (new calc module)

| Function | Formula | Inputs | Outputs | Verdict rule | Source | Tests |
|---|---|---|---|---|---|---|
| `loop_filter_check` | G(s) = Icp Kvco Z(s)/(N s); Z of C1 parallel (R2 + C2), plus R3-C3 for 3rd order; fc where abs(G) = 1; PM = 180 + angle G(fc); attenuation at f_PFD; sweep over Kvco range and part tolerance | icp_a, kvco_hz_per_v (min, typ, max), n, f_pfd_hz, r2_ohm, c1_f, c2_f, r3_ohm, c3_f, tolerances | fc_hz, pm_deg per corner, att_pfd_db | PM at least 45 degrees pass, 35 to 45 marginal, under 35 fail (defaults) | [SNAA106C ch. 38 to 39 p.339 to 347] | W20, W21, W23 |
| `loop_filter_design` | 2nd order: T1 = [sqrt((1+g)^2 tan^2 phi + 4 g) - (1+g) tan phi]/(2 wc); T2 = g/(wc^2 T1); A0 = Icp Kvco/(N wc^2) sqrt((1 + wc^2 T2^2)/(1 + wc^2 T1^2)); C1 = A0 T1/T2; C2 = A0 - C1; R2 = T2/C2. 3rd order: T3 = T31 T1, solve phi numerically, then A1, A2, C1, C3, C2, R2, R3 per the book | icp_a, kvco_hz_per_v, n, fc_hz, pm_deg, gamma, t31 | C1, C2, C3, R2, R3 | Info; check the result with `loop_filter_check` | [SNAA106C p.339 to 347]; book eq 38.19 prints C1 = A0 T2/T1, a typo | W19, W22 |

### 10.4 rf (new calc module)

| Function | Formula | Inputs | Outputs | Verdict rule | Source | Tests |
|---|---|---|---|---|---|---|
| `cascade` | F = F1 + (F2 - 1)/G1 + ...; G = product; 1/IIP3 = sum (G before stage i)/IIP3_i in mW; OIP3 = IIP3 + G | stages (gain_db, nf_db, iip3_dbm, p1db_dbm) | gain_db, nf_db, iip3_dbm, oip3_dbm, stage contributions | Against intake requirements | [AN57-1 eq 2-3 p.8; MC-5G; MC-LIN] | W24 |
| `mismatch` | ML = -10 log10(1 - abs(Gamma)^2); VSWR = (1 + abs(Gamma))/(1 - abs(Gamma)) | rl_db or gamma | ml_db, vswr | Info | [BIRD] for the RL sign | W25 |
| `shunt_c` | y = j w C Z0; S11 = -y/(2 + y); S21 = 2/(2 + y) | c_f, f_hz, z0_ohm | rl_db, il_db | RL at least 20 dB and IL at most 0.1 dB (defaults) | DERIVED (two-port) | W26 |
| `peak_voltage` | V_pk = sqrt(2 P Z0)(1 + abs(Gamma)) | p_w, z0_ohm, gamma | v_pk_v | Under the part's working voltage | DERIVED from [TPD1E0B04 §7.2.2] | W27 |
| `dc_block` | S21 = 2 Z0/(2 Z0 + Z_C), Z_C from C, ESL, ESR; corner f = 1/(2 pi C 2 Z0); SRF; PRF from data | c_f, esl_h, esr_ohm, prf_hz, f_min_hz, f_max_hz, z0_ohm | il_min_db, f_c_hz, srf_hz, notch flags | IL at most 0.1 dB at f_min, no SRF or PRF notch in band (defaults) | [ATC; 550L; JTI-SRF] | W28 |
| `pad` | K = 10^(A/20). Pi: shunt Z0(K+1)/(K-1), series Z0(K^2-1)/(2K). T: series Z0(K-1)/(K+1), shunt 2 K Z0/(K^2-1). Check fitted values by ABCD to S. Power per resistor at P_in. | a_db, z0_ohm, topology, fitted values, p_in_w, ratings | values, A and RL as fitted, P per resistor | abs(dA) at most 0.25 dB, RL at least 20 dB, P at most 50% of rating (defaults) | DERIVED; [FRICKEY Table I] for ABCD to S | W29 |
| `stability` | Delta = S11 S22 - S12 S21; K = (1 - abs(S11)^2 - abs(S22)^2 + abs(Delta)^2)/(2 abs(S12 S21)); mu = (1 - abs(S11)^2)/(abs(S22 - Delta conj(S11)) + abs(S12 S21)) | S-parameters at each frequency | K, abs(Delta), mu, mu' per frequency; worst frequency | Pass when K > 1 and abs(Delta) < 1 (or mu > 1) at every frequency | [KS5072 p.3 (fix the printed Delta); AN154 p.19 to 22]; mu from Edwards and Sinsky 1992 (UNSURE, not opened) | W30 |
| `cavity_modes` | f = (c/2) sqrt((m/a)^2 + (n/b)^2 + (p/d)^2), at most one index zero | a_m, b_m, d_m, f_max_hz | lowest modes | Lowest mode above f_max (default) | [ICM] | W31 |
| `element_impedance` | Series R-L-C model of a part, or S2P; abs(Z), Q, SRF | kind, value, esr_ohm, esl_h or srf_hz, f_hz | abs_z_ohm, q, srf_hz | Per caller | [CC671; JTI-SRF; ATC] | W32 |
| `network_impedance` | Parallel branches of `element_impedance`; find peaks | branches, f range | abs(Z) curve, peaks | No peak in listed bands | [CY1032 p.2 to 3] | W32 |
| `match_sweep` | Cascade the match with part tolerance corners and S2P parts; RL at band edges | match topology, parts, tolerances, band | worst RL | RL at least 10 dB (default) | DERIVED | Later |

### 10.5 spur (new calc module)

| Function | Formula | Inputs | Outputs | Verdict rule | Source | Tests |
|---|---|---|---|---|---|---|
| `search` | Harmonics n f_a in each band; mixing abs(m f_LO plus or minus n f_a) in the IF; alias abs(f - k fs) folded into 0 to fs/2 | aggressors_hz, bands, n_max, lo_hz, m_max, fs_hz | list of hits (source, order, frequency, band) | Fail on a hit with no level estimate under the limit; info otherwise | [MT-002 p.5; MT-003 p.2; M1838 p.2] | W33, W34 |
| `frequency_plan` | Image f_RF plus or minus 2 f_IF; half-IF f_LO plus or minus f_IF/2 (on the RF side); per tuning step | rf range, step, f_if_hz, lo_side | image and half-IF bands per step | Against filter rejection data | [AN150 p.11 to 12; M1838 p.2 to 3] | W35 |
| `alias` | fold(f) = abs(f - fs round(f/fs)) | f_hz, fs_hz | f_alias_hz | Info | [MT-002 p.5] | W34 |
| `supply_spur` | spur_dBFS = 20 log10(ripple/full scale) + PSRR_dB | ripple_v_pp, full_scale_v_pp, psrr_db | spur_dbfs | 6 dB under the SFDR target (default) | [MS-2210 p.3] | W36 |

### 10.6 converter (new calc module)

| Function | Formula | Inputs | Outputs | Verdict rule | Source | Tests |
|---|---|---|---|---|---|---|
| `sar_rc` | V_step = 2 pi f V_pk t_conv C_DAC/(C_EXT + C_DAC); N_TC = ln(V_step/V_halfLSB), V_halfLSB = V_REF/2^(N+1); tau = t_ACQ/N_TC; BW = 1/(2 pi tau) | n_bits, v_ref_v, t_acq_s, t_conv_s, c_dac_f, c_ext_f, f_hz, v_pk_v | tau_s, r_max_ohm, bw_hz | Fitted R at most r_max; C_EXT at least 20 C_S | [AD46 p.1 to 2; ADS8910B p.57 to 58] | W37 |
| `jesd_lane_rate` | 8b/10b: M N' (10/8) fs / L. 64b/66b: (M/L) NP (66/64) fs | m, np, l, fs_hz, encoding, limits | lane_bps | Inside both ends' limits; 8b/10b at most 12.5 Gb/s for 204B | [AD9680 p.73; UG-1578 p.58; SBAA402A p.3 to 4] | W38 |
| `sysref` | f_SYSREF = f_bit/(10 F K n) for integer n (204B); LEMC = lane rate/(E 2112) (204C); coupling against mode; HPF corner against f_SYSREF/4 | f_sysref_hz, lane_bps, f, k, mode, coupling, c_f, r_ohm | n, corner_hz | Integer n; coupling allowed for the mode | [SLYT628 p.16 eq 1; ADC12DJ3200 p.43; UG-1578 p.27 to 28] | W39 |

### 10.7 Worked examples for tests

All numbers were computed for this plan and checked by a second method where one exists (closed
form against numeric root finding, or against the source's own example).

| W | Function | Inputs | Expected | Check against |
|---|---|---|---|---|
| W1 | `snr_jitter` | f_in 100 MHz, t_clk 150 fs | SNR_j 80.51 dB. With t_ap 70 fs: 165.5 fs, 79.66 dB. With SNR_adc 75 dB (no t_ap): 73.92 dB, loss 1.08 dB, marginal | [MT-008 p.2] form; agent cross-check 79.7 dB |
| W2 | `snr_jitter` | 1 GHz, 100 fs; and the jitter for 70 dB at 200 MHz | 64.0 dB; 251.6 fs | [MT-008 p.2] |
| W3 | `pn_to_jitter` | f0 100 MHz; points 1 kHz -120, 10 kHz -130, 100 kHz -135, 1 MHz -145, 10 MHz -150, 20 MHz -150 dBc/Hz; 12 kHz to 20 MHz | A = -74.55 dBc; 265 urad; 421.6 fs. Flat -150 dBc/Hz over the same band: -76.99 dBc, 318.2 fs at 100 MHz, 203.7 fs at 156.25 MHz | Flat case closed form sqrt(2 x 10^-15 x 19.988 MHz)/(2 pi f0) |
| W4 | `rss` | 300, 100, 80 fs | 326.2 fs | |
| W5 | `multiply` | -150 dBc/Hz, N = 100 | -110 dBc/Hz | |
| W6 | `spur_to_jitter` | -70 dBc at 100 MHz | 712 fs | [AN491 p.6 eq 1] |
| W7 | `spur_transfer` | -66 dBc, f_in 30.62 MHz, f_clk 78 MHz | -74.1 dBc | [AN-756 p.5] prints this example |
| W8 | `ripple_sideband` | 2 MHz/V, 1 mV peak, 1 MHz; and ADF4350 1 MHz/V, 1 mV, 2 MHz | -60.0 dBc; -72.0 dBc | Narrowband FM sideband beta/2 |
| W9 | `vc_noise`, `ssc_emi` | 10 MHz, 0.5 ppm/V, 100 nV/rtHz, 100 Hz; and 2% at 125 MHz, RBW 100 kHz | -166 dBc/Hz; 14 dB (13 dB measured) | [WENZEL-VCXO]; [AN10005 p.5, 7] |
| W11 | `termination` | LVPECL 3.3 V and 2.5 V, Z0 50 ohm; LVCMOS Ro 7 ohm | 126.9/82.5 ohm; 250/62.5 ohm; Rs 43 ohm | [AN-828 p.3; AN-953 p.1, 17] |
| W12 | `compat` | 3.3 V LVPECL into an LVDS receiver through a 127/52/31 ohm divider | Worst swing 626 mVpp against a 450 mVpp single-ended maximum, both printed in the source; take the verdict from the source's text when writing the test | [AN-828 p.11 Fig 11] |
| W13 | `ac_coupling` | 100 nF into 50 ohm; Xc at 10 MHz for 100 nF and 1 nF; 100 nF into a 5 kohm bias; duty 45%, 3.3 Vpp, 2.64 V/ns; 8b/10b run of 5 at 1.25 Gb/s with RC 5 us | 31.8 kHz; 0.159 ohm pass, 15.9 ohm fail; 318 Hz; dV -0.165 V, dt 62.5 ps per edge (1.25% duty shift at 100 MHz); droop 0.08% | |
| W19 | `loop_filter_design` 2nd | Banerjee: Icp 1 mA, Kvco 60 MHz/V, N 39200, fc 10 kHz, PM 49.2 deg, gamma 1.024 | C1 0.145 nF, C2 0.906 nF, R2 47.78 kohm | [SNAA106C p.342 to 343] prints the same |
| W20 | `loop_filter_design` and check | Icp 5 mA, Kvco 30 MHz/V, N 100, fc 100 kHz, PM 45 deg, gamma 1 | C1 1.574 nF, C2 7.599 nF, R2 505.6 ohm; check returns fc 100.0 kHz, PM 45.0 deg; attenuation at 10 MHz -72.3 dB | Root finding on abs(G) = 1 |
| W21 | `loop_filter_check` | W20 with standard parts 1.5 nF, 8.2 nF, 510 ohm; Kvco 20 and 45 MHz/V; C2 at -30% (X7R at bias) | 101.6 kHz, 47.0 deg; 73.9 kHz, 46.0 deg and 139.3 kHz, 45.2 deg; 40.7 deg (marginal) | |
| W22 | `loop_filter_design` 3rd | W20 inputs, T31 0.4 | C1 713.4 pF, C2 8.732 nF, C3 166.2 pF, R2 447.7 ohm, R3 1.777 kohm; fc 100.0 kHz, PM 45.0 deg, -90.9 dB at 10 MHz | Root finding |
| W23 | `loop_filter_check` 3rd | W20 2nd-order design with R3 1 kohm and C3 157 pF added naively (pole 1.01 MHz) | fc 97.3 kHz, PM 38.1 deg (marginal), -92.3 dB at 10 MHz | Shows why the 3rd order needs its own design |
| W24 | `cascade` | LNA 20 dB, 1 dB, 0 dBm; filter -2 dB, 2 dB, +100 dBm; mixer -7 dB, 7 dB, +15 dBm; IF amp 15 dB, 3 dB, +10 dBm | Gain 26.0 dB, NF 1.48 dB, IIP3 -6.29 dBm, OIP3 19.71 dBm | Hand Friis |
| W25 | `mismatch` | RL 10 dB | ML 0.458 dB | |
| W26 | `shunt_c` | 0.5 pF at 2.45 GHz; 0.2 pF at 2.45 GHz; 1 pF at 5.8 GHz | RL 14.47 dB, IL 0.158 dB; 22.30 dB, 0.026 dB; 3.43 dB, 2.62 dB | Agent cross-check: 1 pF at 6 GHz gives RL 3.3 dB |
| W27 | `peak_voltage` | 200 mW, 50 ohm, matched | 4.47 V peak (3.16 V RMS) against 3.6 V: fail | [TPD1E0B04 §7.2.2] gives the RMS figure |
| W28 | `dc_block` | Ideal C between 50 ohm ports: 1 nF, 10 nF, 100 nF at 1 MHz | IL 5.48, 0.109, 0.0011 dB; corners 1.59 MHz, 159 kHz, 15.9 kHz; C for 0.1 dB at 1 MHz 10.4 nF | 550L "16 kHz (-3 dB)" for 100 nF [550L] |
| W29 | `pad` | Pi and T at 3, 6, 10, 20 dB, 50 ohm; 6 dB pi with 150/37.4 ohm fitted; 1 W into the 6 dB pi | Pi shunt/series 292.4/17.61, 150.5/37.35, 96.25/71.15, 61.11/247.5 ohm; T series/shunt 8.55/141.9, 16.61/66.93, 25.97/35.14, 40.91/10.10 ohm; fitted 6.013 dB, RL 67 dB; power 0.332, 0.333, 0.083 W, output 0.251 W | ABCD round trip |
| W30 | `stability` | S11 0.6 at -60 deg, S21 4 at 100 deg, S22 0.5 at -30 deg; S12 0.05 at 40 deg, then 0.1 at 40 deg | K 1.493, abs(Delta) 0.455, mu 1.392: pass. K 0.993, abs(Delta) 0.636, mu 0.988: fail | K and mu agree on the verdict |
| W31 | `cavity_modes` | 30 x 20 mm; 50 x 40 mm | 9.01 GHz; 4.80 GHz | [ICM] 30 x 20 mm near 9.0 GHz |
| W32 | `network_impedance` | 22 nF (0.4 nH, 20 mohm) parallel 100 pF (0.4 nH, 0.1 ohm) | SRFs 53.7 and 796 MHz; anti-resonance 563 MHz with abs(Z) 16.5 ohm against 1.40 ohm for 22 nF alone | Synthetic; shape matches [CY1032 p.2 to 3] |
| W33 | `search` | Aggressors 2.2 MHz and 25 MHz, n up to 60; RF band 98 to 102 MHz; LO 110.7 MHz; IF 10.6 to 10.8 MHz | RF hits 2.2 MHz x45 = 99.0, x46 = 101.2, 25 MHz x4 = 100.0 MHz; IF hit abs(LO - 4 x 25 MHz) = 10.7 MHz | Brute force |
| W34 | `alias` | fs 61.44 MSPS: 50, 75, 99 MHz; 2.2 MHz x27 = 59.4 MHz | 11.44, 13.56, 23.88 MHz; 2.04 MHz | [MT-002 p.5] |
| W35 | `frequency_plan` | RF 100 MHz, high-side LO 110.7 MHz; and RF 1950, LO 1750, IF 200 MHz | Image 121.4, half-IF 105.35 MHz; half-IF 1850 MHz | [M1838 p.2 to 3] prints the second |
| W36 | `supply_spur` | 10 mVpp ripple, 2 Vpp full scale, PSRR -60 dB | -106 dBFS | [MS-2210 p.3] rule |
| W37 | `sar_rc` | AD7980 example inputs from [AD46 p.1 to 2] | tau 51.16 ns, BW 3.11 MHz, R 18.9 ohm with 2.7 nF | Copy the inputs from AD46 when writing the test |
| W38 | `jesd_lane_rate` | M 2, N' 16, fs 1 GSPS, 8b/10b, L 2 then L 4 | 20 Gb/s fail for 204B; 10 Gb/s pass | |
| W39 | `sysref` | Lane 10 Gb/s, F 2, K 32 | Allowed f_SYSREF = 15.625 MHz/n: 7.8125 MHz pass (n = 2), 10 MHz fail | [SLYT628 p.16 eq 1] |

## 11. Manufacturer models in the sim package (g)

### 11.1 What each tool can do

| Model | Python (`touchstone`, numpy) | LTspice 26.0.2 | ngspice 47 |
|---|---|---|---|
| Touchstone .s2p and .sNp | Main path. Read 1.x and 2.x, cascade, RL and IL, renormalize, stability, passivity. | No import. `.NET` only outputs 2-port parameters inside `.AC`, with 1 ohm terminations unless set [LTSPICE-HELP ".NET"]. | XSPICE `xfer` reads one S_ij from a Touchstone file, AC only, piecewise-linear in frequency [NGSPICE-47 §8.2.19 p.212 to 214]. `.sp` computes S, Y, Z of a circuit, and noise for 2-ports [§11.3.8 p.334]. `wrs2p` writes a 2-port v1 file [§13.5.110]. RF ports keep their series Z0 in every analysis [§4.1.11 p.101]. |
| Frequency-dependent behavior | Rational fit (vector fitting) later | E or G source with `Laplace=`; transient uses an FFT impulse response; must roll off at high frequency [LTSPICE-HELP "E"] | `s_xfer` code model, AC and transient [§8.2.18 p.209] |
| IBIS (clock drivers) | Later: parse I/V and V/T tables for edge and termination checks | None | No IBIS parser in the manual. KiCad 9 runs IBIS pins and writes an ngspice netlist [KICAD-9]. `darter` converts with limits [DARTER]. |
| Vendor SPICE | n/a | Runs PSpice semiconductor and behavioral models; ADI regulator models are native and proprietary [LTSPICE-HELP "Model Compatibility"] | PSpice compatibility modes `ps`, `psa`, and others [§12.11]. No decryption: encrypted LTspice or HSPICE `.PROT` models do not run (UNSURE, settle by test). |

### 11.2 Touchstone reader rules

| Rule | Source |
|---|---|
| Option line `# <unit> <param> <format> R <n>`; defaults GHz, S, MA, 50 ohm; any later option line is ignored; DB means 20 log10; angles in degrees; `!` starts a comment | [TS2.1 p.4, 6 to 8] |
| 2-port order in 1.x is N11 N21 N12 N22; 2.x needs `[Two-Port Data Order]` | [TS2.1 p.9 to 10, 14 to 15] |
| 1.x: at most 4 pairs per line, each matrix row on a new line for 3+ ports. 2.x: parse by count (2n^2 + 1 values per frequency, Full) | [TS2.1 p.14, 18] |
| `[Reference]` takes one real resistance per port | [TS2.1 p.11] |
| 1.x Y and Z data are normalized by R; 2.x are not. Noise Rn normalized in 1.x, ohms in 2.x | [TS2.1 p.25, 29] |
| Noise block: 2-port only, f, NFmin, abs(Gamma_opt), angle, Rn | [TS2.1 p.24 to 26] |
| Cascade with ABCD or T after matching reference impedances. S to ABCD and back per Frickey Table I; keep to real references (complex-reference waves are unconventional there) | [FRICKEY p.205 to 206, Table I, Table VI; MARKS-WILLIAMS] |
| Passivity: max singular value of S at most 1 at every frequency. Row sums alone are not enough. Reciprocity S = S^T for passive parts. | [SHLEPNEV slides 6 to 10] |
| Interpolate real and imaginary parts (or log magnitude and unwrapped phase). Refuse frequencies outside the file. | [SHLEPNEV slides 11 to 14]; refusing extrapolation is our rule |
| A free checker exists for test files: TSCHK | [IBIS-TOOLS] |

### 11.3 Model provenance rules for reviews

| Rule | Source |
|---|---|
| Record whether an S2P is de-embedded to the pins or includes the eval board. Qorvo TQP9111 is de-embedded with tuning parts removed; ADI amplifier files often include the EVB. | [QORVO-FORUM; ADI-FORUM] (forum answers by staff) |
| Murata and TDK data: typical, 20 or 25 C, no DC bias. Use the DC-bias model for MLCCs at voltage. | [MURATA-S; TDK-README] |
| Coilcraft RF inductor S-parameters come from a fitted model (first resonance only); de-embedded SRF reads higher than mounted. | [CC1721] |
| Two bias points mean two files (Qorvo TQL9092 at 5 V and 3.3 V). Match the file to the board's bias. | [QORVO-FORUM] |
| Macromodels do not model every nonlinearity or noise; compare with datasheet curves before trusting them. | [MT-099 p.1 to 2; SBOA027] |
| IBIS covers I/V, V/T, package and C_comp. It has no jitter, phase noise or PLL. Jitter appears only as IBIS-AMI parameters for SerDes. | [IBIS-8.0 §6.1, §10.6] |

## 12. Bench tests (h)

| Test | Checks | Method | Pass | Source |
|---|---|---|---|---|
| VNA return and insertion loss | RF-1, RF-2, RF-9, RF-10, RF-12, RF-14 | Full two-port SOLT calibration (12-term) at the connector plane. Sweep the full tuning range plus margin. Compare with the calculator. | Calculator verdict holds on the measured data. | [AN1287-3] |
| VNA stability sweep | RF-6 | Full two-port cal; compute K and mu over the VNA's full span (TR1108 used 10 MHz to 10 GHz). Set port powers separately for high-gain parts. | K > 1 and abs(Delta) < 1 everywhere. | [KS5072 p.3; TR1108 p.12 to 13]. Spectrum scan with ports open and shorted: no vendor procedure (UNSURE). |
| Noise figure, Y-factor | RF-13 | Y = N_on/N_off; F = ENR/(Y - 1) linear; second-stage correction F1 = F12 - (F2 - 1)/G1. 6 dB ENR source up to about 16 to 18 dB NF, 15 dB above. Shield; no adapters. | NF within the lineup budget. Gain difference on and off under 0.05 dB. | [AN57-1 eq 3-3 to 3-7 p.12 to 13; AN57-2 §2.2.6, §3.1 to 3.6] |
| Two-tone IP3 | RF-13 | TOI = A - d/2 (d in dBc, negative). Change analyzer attenuation to prove the IM is not the analyzer's. | IIP3 meets the lineup. | [AN150 p.56 to 57; MC009 p.6] |
| Spur scan | SPUR-1 to SPUR-6, ADC-10 | RF input terminated. Note RBW (noise moves 10 log10(BW2/BW1)). Use the preamp rule. Change input attenuation: a spur that changes is from the analyzer. Find sources by changing fsw (sync pin), fs, LO, or shielding an inductor. | Every spur in band has a known source and is under the limit. | [AN150 p.47, 49 to 50, 56 to 57; AD51 p.2; SLAA824 p.4] |
| ADC FFT | ADC-1 to ADC-7 | Coherent sampling (prime cycles); Blackman-Harris otherwise. Band-pass filter the source. Measure SNR at low and high f_in to split jitter from other noise. | SNR and SFDR at datasheet values within the calculator's loss. | [AN-835 p.6 to 10; AN-501 p.2 to 3; MT-007 p.6 to 7; SLYT389 AAJ p.6] |
| Supply injection (PSRR, PSMR) | ADC-10, SPUR-4, CKD-6 | Inject ripple through a bias tee or with beads removed; compare the FFT or phase noise spur with the injected level; input grounded for ADCs. | Measured rejection meets the assumption in the calculator. | [AN-835 p.27; MS-2210 p.3 to 4; AN491 p.4 to 5] |
| Phase noise | CKD-6, CKD-7, CKD-12, ADC-1 | Signal source analyzer or spectrum analyzer option. The direct method is valid only if the analyzer's own noise is below the DUT and AM noise is 10 dB below PN. Cross-correlation lowers the floor by sqrt(M). A loop bandwidth shows as the knee of the curve. | Integrated jitter under the budget; no peak at the filter resonance. | [KS-PN p.5, 11; RS-1EF56 p.3; AN10006 p.12 Fig 10] |
| Additive jitter | CKD-12, CKD-8 | Reference 3 to 10 dB cleaner than the DUT; J_buf = sqrt(J_tot^2 - J_src^2). | Under the budget. | [AN766 p.2] |
| Scope jitter (TIE, period) | CKD-5, CKD-12 | Bandwidth at least 3 times signal bandwidth (0.35/tr); 3 samples on the edge; 10k cycles x 25 runs. PCIe: 20 GS/s or more, 100k cycles, PCIe filters. | Under the budget. | [AN10007 p.13 to 14; 9QXL2001C p.12] |
| Clock amplitude and common mode | CKD-1 to CKD-4, CKD-8 | Differential probe for VOD (single-ended pairs lose CMRR with frequency). Bandwidth at least 5 times the clock frequency for amplitude. Short grounds. Two single-ended probes for VCM. | VOD, VCM and crossing inside the receiver's range. | [TEK-PROBES PDF p.8, 10 to 11, 15, 30, 40]. VCM with two probes: no vendor procedure (UNSURE). |
| Crystal drive | CKD-9 | Current probe on the crystal; DL = I_RMS^2 ESR. | Under 80% of rating. | [SNAA331 p.3 to 4] |
| SYSREF and latency | ADC-9 | Repeat power cycles and resyncs; check channel-to-channel phase stays put. | Same phase every cycle. | No vendor procedure found (UNSURE). |

## 13. Eval boards (i)

| Board | Files | Documented issues | Use |
|---|---|---|---|
| HackRF One | KiCad, CERN-OHL-P v2 [HRF-REPO] | Ten revisions, several r9 fixes with commits (sealed; kept out of the repo in evals/hackrf_one/local) | **Held-out.** Review the r9 snapshot. |
| ADALM-PLUTO Rev A to D | Allegro, OrCAD, PDF, Gerbers, BOM; no license stated [PLUTO-HW] | Rev A: oscillator on a noisy 1.8 V digital rail (EVM -32 against -45 dB), supply noise on some PCs (choke added, switchers synchronized), 480 MHz USB noise (choke added). Rev B: R88 on the wrong side of the fuse. Rev D: RF ESD diodes shorted by paste. Oscillator is plus or minus 25 ppm [PLUTO-CAL]. | Dev. Lessons now; scored later if a PDF or Allegro path is built. |
| LimeSDR Mini v1.x and 2.x | Altium; CC BY 3.0 (v1), Solderpad 2.1 (v2) [LIME-MINI; LIME-MINI2] | v1.3 change list (LDO EOL, LMS caps); 2v0 (VCTCXO, tuning DAC 8 to 10 bit, clock buffer VDDO, 3.3 V enable on 1.1 V power-good); 2.x shunt part swap (1.2 pF to 11 pF); 2v3 clock mux; 2v5 work in progress (pull-up domain fix, tuning DAC divider, RF port ESD, VDD_TBB 1.25 to 1.4 V) | Dev. The Altium path works through eda-agent. |
| LimeSDR-USB v1.4 | Altium, CC BY 3.0 [LIME-USB] | Default matching optimized above HF; remove MN18 on RX1_L for HF [LIME-USB-HF] | Dev, small case. |
| AD-FMCOMMS5 Rev B | Rev C design files public; Rev B "may be available" (UNSURE) | ADF5355 AVDD pin floating; balun-to-SMA traces not phase-matched; RF switches not for use above 900 MHz [FMC5-HW] | Dev, small case if Rev B files can be had. |
| AD-FMCOMMS2 | Design files on the product page | Generic TSX-3225 crystal does not meet AD9361 specs; balun rated 2.4 to 2.5 GHz only [FMC2-HW; ADI-CFG] | Dev, small case. |
| bladeRF, KrakenSDR, RTL-SDR Blog | PDF only or none | No formal errata found | Not used. |

Contamination: all these boards are public. Score each review on its derivation (nets, levels,
math), not on whether it names the bug.

## 14. Later items

- Impedance and stackup: controlled impedance, coplanar waveguide, via fence spacing at lambda/20
  with the real dielectric [SNAA408 §3.4.2], ground under RF lines, balun-to-connector phase
  matching (FMCOMMS5 Rev A/B), clock pair length matching.
- IBIS simulation of clock drivers through KiCad and ngspice.
- Monte Carlo matching with vendor S2P parts (`rf.match_sweep`).
- PDF or Allegro schematic intake (needed to score Pluto).
- Antenna tuning, PA thermal, conducted and radiated EMC.

## 15. Not confirmed (UNSURE) and how to settle each

| Item | Settle with |
|---|---|
| AD9361 TX bias through the balun center tap; MAX2837/MAX2839 and LMS7002M RF pin DC needs | UG-570 RF port section; MAX2839 and LMS7002M datasheets |
| Edwards and Sinsky mu paper; Qorvo AN107 sequencing | Open the IEEE paper (T-MTT 40(12) 1992) and AN107 |
| Vendor figure for RL shift against 0402 tolerance | Monte Carlo on vendor S2P data |
| Pi and T pad formulas from a vendor page | A Mini-Circuits or Keysight note; until then the ABCD round trip is the check |
| Shield can land pattern and frame guides | Laird, Wurth or Harwin frame datasheets |
| Shunt inductor as an antenna ESD path | A vendor ESD app note (Infineon AN327 not found) |
| Insertion loss definition page; Pozar Table 4.2 page; IEEE 370 section numbers | Read the documents |
| TIA/EIA-644 VOD limits; 8b/10b run length of 5 | TIA/EIA-644-A; IEEE 802.3 Clause 36 |
| Duty offset from AC coupling (formula DERIVED) | Maxim HFAN-1.1 |
| SSC on ADC sample clocks and LO references | An ADC or RF vendor note |
| X7R DC-bias loss in loop filters; MT-086, ADIsimPLL, AN-1368 | Capacitor DC-bias curves; the ADI documents (analog.com timed out for the clock research) |
| VCO ripple sideband closed form (DERIVED) | A vendor note that prints it |
| Locking switcher sync to the system reference | A vendor note; today it is engineering judgment |
| Stability bench procedure with open and shorted ports; VCM with two single-ended probes; SYSREF latency test | Vendor procedures |
| Converter DDR and SDR output timing | Each part's datasheet timing section |
| AN256 and AN491 differ by sqrt(2) for spur jitter | Derive for single and double sidebands and state which the calculator uses |
| PCIe Gen2 limit 3.1 or 3.0 ps | PCI-SIG CEM specification |
| ngspice and encrypted models; `xfer` outside the table range | Test runs |
| Mini-Circuits and ADI S2P reference planes | Read the file headers |
| NXP i.MX and Microchip PolarFire checklists; AMD XTP427 | Download from vendor sites (login or form) |
| bladeRF errata; KrakenSDR and RTL-SDR Blog files | Vendor support |
| FMCOMMS5 Rev B files; Pluto Rev A downloads (HTTP 206) | Product pages |
| Which LimeSDR Mini 2v5 commit changed the tuning DAC divider | Read the commits listed under LIME-MINI2 2v5 |
| QSPICE Touchstone import | QSPICE release notes |

## 16. Sources

Page and section are given where each source is used. Some ADI PDFs were read through
web.archive.org because analog.com timed out; the URL below is the original.

### 16.1 RF

| Key | Document | Rev or date | URL |
|---|---|---|---|
| AN57-1 | Keysight AN 57-1, Fundamentals of RF and Microwave Noise Figure Measurements, 5952-8255E | 2010-08-05 | https://www.keysight.com/us/en/assets/7018-06808/application-notes/5952-8255.pdf |
| AN57-2 | Agilent AN 57-2, Noise Figure Measurement Accuracy: The Y-Factor Method, 5952-3706E | 2010-05-05 | https://www.keysight.com/find/AN57-2 |
| AN154 | Agilent AN 154, S-Parameter Design, 5952-1087 | 2000-11 | https://ytdp.eie.wits.ac.za/AN154.pdf |
| KS5072 | Agilent, Basics of RF Amplifier Measurements with the E5072A, 5990-9974EN | 2012-03-22 | https://www.keysight.com/kr/ko/assets/7018-03364/application-notes/5990-9974.pdf |
| AN150 | Keysight AN 150, Spectrum Analysis Basics, 5952-0292 | 2014-08-04 | https://xdevs.com/doc/HP_Agilent_Keysight/5952-0292%20English%20_%202014-02-25%20_%20PDF%205.71%20MB%20c20141003%20%5B89%5D.pdf |
| AN1287-3 | HP AN 1287-3, Applying Error Correction to Network Analyzer Measurements, 5965-7709E | 1997-05 | https://www.hpmemoryproject.org/an/pdf/an_1287-3.pdf |
| MC-149 | Mini-Circuits AN-60-149, biasing depletion-mode GaAs and GaN amplifiers | Rev OR, 2025-09-08 | https://www.minicircuits.com/app/AN60-149.pdf |
| MC-063 | Mini-Circuits AN-60-063, PGA-105+ stabilizing network | Rev B, 2015-04-14 | https://www.minicircuits.com/app/AN60-063.pdf |
| MC009 | Mini-Circuits AN-00-009, Understanding Mixers | Rev A, 2015-04-14 | https://www.minicircuits.com/app/AN00-009.pdf |
| MC011 | Mini-Circuits AN-00-011, mixer spurious tables | Rev B, 2015-04 | https://www.minicircuits.com/app/AN00-011.pdf |
| MC-AN20-001 | Mini-Circuits AN-20-001, How RF Transformers Work | Rev B, 2015-04-15 | https://www.minicircuits.com/app/AN20-001.pdf |
| TCM1 | Mini-Circuits TCM1-63AX+ datasheet | Rev C | https://www.minicircuits.com/pdfs/TCM1-63AX+.pdf |
| MC-LIN | Mini-Circuits blog, Linearity: Cascaded P1dB and IP3 for a Simple Microwave Front-End | 2022-09-30 | https://blog.minicircuits.com/linearity-cascaded-p1db-and-ip3-for-a-simple-microwave-front-end/ |
| MC-5G | Mini-Circuits blog, Cascaded P1dB and IP3 in a 26 GHz 5G Front-End | 2022-12-08 | https://blog.minicircuits.com/every-block-covered-cascaded-p1db-and-ip3-in-a-26-ghz-5g-front-end/ |
| TR1108 | Infineon TR1108, BFR380F ISDB-T LNA | Rev 1.0, 2012-07-17 | https://www.infineon.com/assets/row/public/documents/24/57/tr1108.pdf |
| ESD101 | Infineon ESD101-B1-02 datasheet | Rev 1.4, 2017-10-27 | https://www.infineon.com/assets/row/public/documents/24/49/infineon-esd101-b1-datasheet-en.pdf |
| TPD1E0B04 | TI TPD1E0B04 datasheet, SLVSDG9C | 2025-06 | https://www.ti.com/lit/ds/symlink/tpd1e0b04.pdf |
| SWRA730 | TI SWRA730, BOM Tunable PCB Antenna | 2022-02 | https://www.ti.com/lit/an/swra730/swra730.pdf |
| SNAA408 | TI SNAA408, LMK3H0102 layout note | 2025-04 | https://www.ti.com/document-viewer/lit/html/SNAA408/GUID-6EC493B4-E057-431E-A2A3-667FFDFDFEC2 |
| AN27 | pSemi AN27, Using Blocking Capacitors with UltraCMOS Devices, DOC-02181-2 | 2025-09 | https://www.psemi.com/pdf/app_notes/an27.pdf |
| PE42423 | pSemi PE42423 datasheet, DOC-85742-4.02 | 2026-07 | https://www.psemi.com/pdf/datasheets/pe42423ds.pdf |
| AS179 | Skyworks (Alpha) AS179-92 datasheet (copy read) | rev 10/02A | https://pccomponents.com/datasheets/SKYWO-AS179-92.pdf |
| JTI-2450 | Johanson 2450BL15B050 detail spec | 2019-01-18 | https://johansontechnology.com/docs/1024/2450BL15B050_owJMCsz.pdf |
| JTI-1720 | Johanson 1720BL15A0100E-AEC detail spec | 2020-02-21 | https://www.johansontechnology.com/docs/1907/1720BL15A0100E-AEC_4inXfni.pdf |
| JTI-SRF | Johanson, SRF and PRF and Their Relation to RF Capacitor Applications | 1999-01-17 | https://johansontechnology.com/docs/22/srf-and-prf-and-their-relation-to-rf-capacitor-applications.pdf |
| ATC | ATC Circuit Designer's Notebook, Capacitors in Coupling and DC Blocking Applications, 001-927 | Rev E, 2005-01 | https://rfs.kyocera-avx.com/userFiles/uploads/pdfs/capacitors_in_coupling.pdf |
| 550L | Kyocera AVX 550L series page | accessed 2026-10-15 | https://rfs.kyocera-avx.com/550l-series |
| CY1032 | Cypress AN1032, Using Decoupling Capacitors, 001-19299 | Rev *C, 2014-11-03 | https://emcfastpass.com/wp-content/uploads/2017/04/Using_decoupling_caps.pdf |
| CC671 | Coilcraft Doc 671-C, Key Parameters for Selecting RF Inductors | 2021-01-07 | https://www.coilcraft.com/pdfs/doc671_Selecting_RF_Inductors.pdf |
| CC945 | Coilcraft Doc 945, Inductors as RF Chokes | 2017-10-04 | https://www.coilcraft.com/getmedia/7bfb1feb-2a4c-4896-9282-3db23ed33b09/Doc945_Inductors_as_RF_Chokes.pdf |
| CC1193 | Coilcraft Doc 1193, Broadband chokes for bias tees | 2014-05-28 | https://www.coilcraft.com/pdfs/Doc1193_Broadband_chokes_for_bias_tees.pdf |
| VSH | Vishay Doc 60107, Frequency Response of Thin Film Chip Resistors (copy read) | 2009-02-04 | https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/14/freqresp_2D00_1.pdf |
| ADI-CFG | ADI, Configuration Options for AD9361/AD9364 boards | accessed 2026-10-15 | https://developer.analog.com/docs/system-level/solutions/reference-designs/fmcomms2/hardware/configuration_options.html |
| PLUTO-ESD | ADI, PlutoSDR ESD Diode Issue | accessed 2026-10-15; source commit 0536458758 (2026-09-02) | https://developer.analog.com/docs/system-level/solutions/platforms/pluto/setup/esd.html |
| ICM | In Compliance Magazine, Cavity Resonances of Shielding Boxes and Cans (trade press) | 2023-08-01 | https://incompliancemag.com/cavity-resonances-of-shielding-boxes-and-cans/ |
| BIRD | T. S. Bird, Definition and Misuse of Return Loss, IEEE AP Magazine 51(2) pp.166 to 167 (citation only, full text not read) | 2009-04 | https://researchers.mq.edu.au/en/publications/definition-and-misuse-of-return-loss/ |

### 16.2 Data converters and spurs

| Key | Document | Rev or date | URL |
|---|---|---|---|
| MT-002 | ADI MT-002, What the Nyquist Criterion Means | Rev A, 2008-10 | https://www.analog.com/media/en/training-seminars/tutorials/MT-002.pdf |
| MT-003 | ADI MT-003, Understand SINAD, ENOB, SNR, THD, THD+N, SFDR | Rev A, 2008-10 | https://www.analog.com/media/en/training-seminars/tutorials/MT-003.pdf |
| MT-007 | ADI MT-007, Aperture Time, Aperture Jitter, Aperture Delay Time | Rev A, 2008-10 | https://www.analog.com/media/en/training-seminars/tutorials/MT-007.pdf |
| MT-008 | ADI MT-008, Converting Oscillator Phase Noise to Time Jitter | Rev A, 2008-10 | https://www.analog.com/media/en/training-seminars/tutorials/MT-008.pdf |
| MT-031 | ADI MT-031, Grounding Data Converters | Rev A, 2008-10 | https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf |
| MT-080 | ADI MT-080, Mixers and Modulators | Rev 0, 2008-10 | https://www.analog.com/media/en/training-seminars/tutorials/MT-080.pdf |
| MT-200 | ADI MT-200, Minimizing Jitter in ADC Clock Interfaces | Rev 0, 2012-01 | https://www.analog.com/media/en/training-seminars/tutorials/MT-200.pdf |
| AN-501 | ADI AN-501, Aperture Uncertainty and ADC System Performance | Rev A, 2006-03 | https://www.analog.com/media/en/technical-documentation/application-notes/AN-501.pdf |
| AN-756 | ADI AN-756, Sampled Systems and the Effects of Clock Phase Noise and Jitter | Rev 0, 2004-12 | https://www.analog.com/media/en/technical-documentation/application-notes/AN-756.pdf |
| AN-835 | ADI AN-835, Understanding High Speed ADC Testing and Evaluation | Rev B, 2015-03 | https://www.analog.com/media/en/technical-documentation/application-notes/AN-835.pdf |
| AN-742 | ADI AN-742, Frequency Domain Response of Switched-Capacitor ADCs | Rev C, 2018-06 | https://www.analog.com/media/en/technical-documentation/application-notes/AN-742.pdf |
| AN-586 | ADI AN-586, LVDS Data Outputs for High-Speed ADCs | Rev 0, 2002 | https://www.analog.com/media/en/technical-documentation/application-notes/5957542118600205599850975382134073431740717454123180480718AN586.pdf |
| AD42 | ADI Analog Dialogue 42-02, ADC Clock Optimization: A Test Engineering Perspective | 2008-02 | https://www.analog.com/media/en/analog-dialogue/volume-42/number-1/articles/analog-to-digital-converter-clock-optimization.pdf |
| AD46 | ADI Analog Dialogue 46-12, Front-End Amplifier and RC Filter Design for a Precision SAR ADC | 2012-12 | https://www.analog.com/media/en/analog-dialogue/volume-46/number-4/articles/front-end-amp-and-rc-filter-design.pdf |
| AD51 | ADI Analog Dialogue 51-04, Analyzing and Solving Fixed Frequency Spur Issues in High Precision ADC Signal Chains | 2017-04 | https://www.analog.com/media/en/analog-dialogue/volume-51/number-2/articles/analyzing-and-solving-fixed-frequency-spur-issues-in-high-precision-adc-signal-chains.pdf |
| AD45 | ADI Analog Dialogue 45-09, Power Management Design for PLLs | 2011-09 | https://www.analog.com/media/en/analog-dialogue/volume-45/number-3/articles/power-management-design-for-plls.pdf |
| OP1 | ADI Analog Dialogue, Optimizing Power Systems for the Signal Chain, Part 1 | 2021-03 | https://www.analog.com/media/en/analog-dialogue/volume-55/number-1/optimizing-power-systems-for-the-signal-chain-part-1.pdf |
| OP2 | Same series, Part 2 | 2021-04 | https://www.analog.com/media/en/analog-dialogue/volume-55/number-2/optimizing-power-systems-for-the-signal-chain-part-2.pdf (file name UNSURE) |
| OP3 | Same series, Part 3 | 2021-05 | https://www.analog.com/media/en/analog-dialogue/volume-55/number-2/optimizing-power-systems-for-the-signal-chain-part-3.pdf (file name UNSURE) |
| MS-2210 | ADI MS-2210, Designing Power Supplies for High Speed ADC | 2012-02 | https://www.analog.com/media/en/technical-documentation/tech-articles/MS-2210.pdf |
| PSMR | ADI, Power Supply Modulation Ratio Demystified | 2018 | https://www.analog.com/media/en/technical-documentation/tech-articles/Power-Supply-Modulation-Ratio-Demystified-How-Does-PSMR-Differ-from-PSRR.pdf |
| AD9268 | ADI AD9268 datasheet | Rev A, 2009-09 | https://www.analog.com/media/en/technical-documentation/data-sheets/AD9268.pdf |
| AD7980 | ADI AD7980 datasheet | Rev G, 2021-01 | https://www.analog.com/media/en/technical-documentation/data-sheets/AD7980.pdf |
| AD9361 | ADI AD9361 datasheet | Rev F, 2016-11 | https://www.analog.com/media/en/technical-documentation/data-sheets/AD9361.pdf |
| UG-570 | ADI UG-570, AD9361 Reference Manual (also read through a manualslib mirror) | Rev A | https://www.analog.com/media/en/technical-documentation/user-guides/AD9361_Reference_Manual_UG-570.pdf |
| ADF4350 | ADI ADF4350 datasheet | Rev B, 2016-05 | https://www.analog.com/media/en/technical-documentation/data-sheets/ADF4350.pdf |
| SLYT379 | TI SLYT379, Clock jitter analyzed in the time domain, Part 1 | AAJ 3Q 2010 | https://www.ti.com/lit/an/slyt379/slyt379.pdf |
| SLYT389 | TI SLYT389, Part 2 | AAJ 4Q 2010 | https://www.ti.com/lit/an/slyt389/slyt389.pdf |
| SLYT339 | TI SLYT339, How the voltage reference affects ADC performance, Part 2 | AAJ 3Q 2009 | https://www.ti.com/lit/an/slyt339/slyt339.pdf |
| SLYT355 | TI SLYT355, Part 3 | AAJ 4Q 2009 | https://www.ti.com/lit/an/slyt355/slyt355.pdf |
| ADS8910B | TI ADS8910B datasheet, SBAS707B | 2018-01 | https://www.ti.com/lit/ds/symlink/ads8910b.pdf |
| SLAA824 | TI SLAA824, Spurs Analysis in the RF Sampling ADC | 2018-02 | https://www.ti.com/lit/an/slaa824/slaa824.pdf |
| SLYT720 | TI SLYT720, Designing a modern power supply for RF sampling converters | AAJ 2Q 2017 | https://www.ti.com/lit/an/slyt720/slyt720.pdf |
| SLVAEW7 | TI SLVAEW7, Powering Sensitive ADC Designs with the TPS62913 | 2020-09 | https://www.ti.com/lit/an/slvaew7/slvaew7.pdf |
| JESD-SG | ADI JESD204B Survival Guide (printed page = PDF page - 1) | 2014-08 | https://www.analog.com/media/en/technical-documentation/technical-articles/JESD204B-Survival-Guide.pdf |
| AD9680 | ADI AD9680 datasheet | Rev E, 2019-03 | https://www.analog.com/media/en/technical-documentation/data-sheets/AD9680.pdf |
| UG-1578 | ADI UG-1578, AD9081/AD9082 System Development User Guide | Rev 0, 2021-07 | https://www.analog.com/media/en/technical-documentation/user-guides/ad9081-ad9082-ug-1578.pdf |
| SLYT628 | TI SLYT628, JESD204B multi-device synchronization | AAJ 2Q 2015 | https://www.ti.com/lit/an/slyt628/slyt628.pdf |
| SLAP161 | TI SLAP161, JESD204B Overview (slides) | no date printed | https://www.ti.com/lit/ml/slap161/slap161.pdf |
| SBAA402A | TI SBAA402A, Upgrading from JESD204B to JESD204C | 2021-04 | https://www.ti.com/lit/an/sbaa402/sbaa402.pdf |
| LMK04828 | TI LMK04828 datasheet, SNAS605AS | 2020-05 | https://www.ti.com/lit/ds/symlink/lmk04828.pdf |
| ADC12DJ3200 | TI ADC12DJ3200 datasheet, SLVSD97A | 2020-04 | https://www.ti.com/lit/ds/symlink/adc12dj3200.pdf |
| ADC16DX370 | TI ADC16DX370 datasheet, SNVSA18C | 2014-08 | https://www.ti.com/lit/ds/symlink/adc16dx370.pdf |
| ADS54J54 | TI ADS54J54 datasheet, SLASE67A | 2019-08 | https://www.ti.com/lit/ds/symlink/ads54j54.pdf |
| M1838 | Maxim AN1838, Mixer 2x2 Spurious Response and IP2 Relationship | 2003-03 | https://pdfserv.maximintegrated.com/en/an/AN1838.pdf |
| LT8650S | ADI LT8650S datasheet | Rev D | https://www.analog.com/media/en/technical-documentation/data-sheets/LT8650S.pdf |
| TPS62913 | TI TPS62913 datasheet, SLVSFP4B | date not recorded | https://www.ti.com/lit/ds/symlink/tps62913.pdf |
| TPS62840 | TI TPS62840 datasheet, SLVSEC6D, §8.4.1 to 8.4.2 | 2020-03 | https://www.ti.com/document-viewer/lit/html/SLVSEC6D/forced-pwm-mode-operation-x8000 |
| DOSTAL | F. Dostal, Reducing Noise by Synchronizing Switching Regulators, ADI TA23725 | 2022-03 | https://www.analog.com/en/resources/technical-articles/reducing-noise-by-synchronizing-switching-regulators.html |

### 16.3 Clocks

| Key | Document | Rev or date | URL |
|---|---|---|---|
| SCAA059C | TI SCAA059C, AC-Coupling Between Differential LVPECL, LVDS, HSTL, and CML | 2003-03, rev 2007-10 | https://www.ti.com/lit/an/scaa059c/scaa059c.pdf |
| SCAA062 | TI SCAA062, DC-Coupling Between Differential LVPECL, LVDS, HSTL, and CML | 2003-03 | https://www.ti.com/lit/an/scaa062/scaa062.pdf |
| SLLA120 | TI SLLA120, Interfacing Between LVPECL, VML, CML, and LVDS Levels | 2002-12 | https://www.ti.com/lit/an/slla120/slla120.pdf |
| AN-828 | Renesas (IDT) AN-828, Termination: LVPECL | Rev A, 2014-04-30 | https://www.renesas.com/en/document/apn/828-termination-lvpecl |
| AN-953 | Renesas (IDT) AN-953, Quick Guide: Output Terminations | 2017-03-06 | https://www.renesas.com/en/document/apn/quick-guide-output-terminations |
| AN-808 | Renesas (IDT) AN-808, PCI Express/HCSL Termination | Rev A, 2013-12-04 | https://www.renesas.com/en/document/apn/808-pci-expresshcsl-termination |
| AN-879 | Renesas (IDT) AN-879, Low-Power HCSL vs. Traditional HCSL | Rev B, 2015-04-02 | https://www.renesas.com/en/document/apn/879-low-power-hcsl-vs-traditional-hcsl |
| AN-891 | Renesas AN-891, Driving LVPECL, LVDS, CML and SSTL Logic with Universal Low-Power HCSL Outputs | 2023-12-05 | https://www.renesas.com/en/document/apn/891-driving-lvpecl-lvds-cml-and-sstl-logic-universal-low-power-hcsl-outputs |
| 9QXL2001C | Renesas 9QXL2001C datasheet, R31DS0090EU0113 | Rev 1.13, 2026-09-22 | https://www.renesas.com/en/document/dst/9qxl2001c-datasheet |
| 9FGV0231 | Renesas 9FGV0231 datasheet | 2025-12-01 | https://www.renesas.com/en/document/dst/9fgv0231-datasheet |
| SKY-PCIE | Skyworks (Silicon Labs) white paper, Selecting the Optimum PCI Express Clock Source | Rev 2.0, 2021-11-16 | https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/white-papers/PCIe-Clock-Source-Selection.pdf |
| AN1051 | Skyworks AN1051, Si534x/7x/8x/9x Schematic Review Checklist | Rev 0.3, 2021-07-26 | https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/application-notes/AN1051-Si534x-8x-Schematic_Review-Checklist.pdf |
| AN491 | Skyworks AN491, Power Supply Rejection for Low-Jitter Clocks | Rev 0.2, 2021-09-22 | https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/application-notes/AN491.pdf |
| AN256 | Skyworks AN256, Integrated Phase Noise | Rev 0.4, 2021-09-21 | https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/application-notes/AN256.pdf |
| AN766 | Skyworks AN766, Understanding and Optimizing Clock Buffer's Additive Jitter Performance | Rev 0.1, 2021-09-23 | https://www.skyworksinc.com/-/media/Skyworks/SL/documents/public/application-notes/AN766.pdf |
| AN10007 | SiTime AN10007, Clock Jitter Definitions and Measurement Methods | Rev 1.21 | https://www.sitime.com/sites/default/files/hiddenresources/AN10007-Jitter-and-measurement-methods_SIT.pdf |
| AN10005 | SiTime AN10005, Spread Spectrum Clock Oscillators | Rev 1.2 | https://www.sitime.com/sites/default/files/hiddenresources/AN10005-Spread-Spectrum-Clock-Oscillators_SIT.pdf |
| AN10006 | SiTime AN10006, Best Design and Layout Practices for SiTime Timing Devices | Rev 2.9 | https://www.sitime.com/sites/default/files/hiddenresources/AN10006-Best-Design-Layout-Practices_SIT.pdf |
| SNAA106C | TI SNAA106C, D. Banerjee, PLL Performance, Simulation, and Design, 5th ed. (printed page = PDF page - 6) | 2017-05 | https://www.ti.com/lit/ml/snaa106c/snaa106c.pdf |
| SBAA653A | TI SBAA653A, Practical Clocking Considerations for High-Speed Converters | 2024-10, rev 2025-04 | https://www.ti.com/lit/an/sbaa653a/sbaa653a.pdf |
| SNAA331 | TI SNAA331, CDCE6214-Q1 Crystal-Based Oscillator Design | 2019-12 | https://www.ti.com/lit/an/snaa331/snaa331.pdf |
| SCAA119 | TI SCAA119, Crystal Oscillator Performance of the CDCLVC1310 | 2012-09 | https://www.ti.com/lit/an/scaa119/scaa119.pdf |
| TG2520SBN | Epson TG2016SBN/TG2520SBN TCXO datasheet (Epson PDF hosted on TI E2E) | PDF dated 2018-04-03 | https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/166/TG2520SBN_5F00_en.pdf |
| SNAA411 | TI SNAA411, Sine to Square Wave Conversion Using Clock Buffers | 2024-09 | https://www.ti.com/lit/an/snaa411/snaa411.pdf |
| SCAA112 | TI SCAA112, How to Apply 1.8-V Signals to 3.3-V CDCLVC11xx Fanout Clock Buffer | 2010-11 | https://www.ti.com/lit/an/scaa112/scaa112.pdf |
| SNVA745 | TI SNVA745, Clocking Design Guidelines: Unused Pins | 2015-11 | https://www.ti.com/lit/an/snva745/snva745.pdf |
| SLLA082B | TI SLLA082B, Active Fail-Safe in TI's LVDS Receivers | 2001-10 | https://www.ti.com/lit/an/slla082b/slla082b.pdf |
| SNLA187 | TI SNLA187, LVDS Owner's Manual, 4th ed. | 2008 | https://www.ti.com/lit/ug/snla187/snla187.pdf |
| SCAA103 | TI SCAA103, Spread Spectrum Clocking Using the CDCS502/503 | 2009-08 | https://www.ti.com/lit/an/scaa103/scaa103.pdf |
| QUARTUS-BW | Intel Quartus Prime Help 23.3, PLL Bandwidth logic option | v23.3 | https://resources.altera.com/quartushelp/23.3/logicops/logicops/def_pll_bandwidth.htm |
| ICS663 | Renesas (IDT) ICS663 PLL Building Block datasheet | Rev E, 2006-01 | https://www.renesas.com/en/document/dst/663-datasheet |
| WENZEL-VCXO | Wenzel Associates, VCXOs tutorial | undated | https://wenzel.com/library/crystal-oscillator-tutorials/vcxos-voltage-controlled-crystal-oscillators/ |
| KS-PN | Keysight 5990-5729EN, Phase Noise Measurement Solutions Selection Guide (mirror) | 2014-08-03 | https://xdevs.com/doc/HP_Agilent_Keysight/5990-5729EN%20Phase%20Noise%20Measurement%20Solutions%20-%20Selection%20Guide%20c20140918%20%5B24%5D.pdf |
| RS-1EF56 | Rohde & Schwarz 1EF56_0E, Frequency Extension for R&S FSUP and X-Correlation | 2007-01 | https://cdn.rohde-schwarz.com.cn/pws/dl_downloads/dl_application/application_notes/1ef56/1EF56.pdf |
| TEK-PROBES | Tektronix 60W-6053-8, ABCs of Probes (mirror) | 2004-01 | https://xdevs.com/doc/Tektronix/abc_Probes.pdf |
| SPRAD21J | TI SPRAD21J, AM62x family Schematic Design Guidelines and Review Checklist | 2022-05, rev 2026-10 | https://www.ti.com/lit/pdf/sprad21 |
| UG583 | AMD UG583, UltraScale Architecture PCB Design | v1.29, 2025-12-23 | https://docs.amd.com/r/en-US/ug583-ultrascale-pcb-design |
| 683112 | Altera 683112, Agilex 7 Pin Connection Guidelines (F and I series), P-Tile and R-Tile (read from search excerpts; the section pages redirect) | 2025-08-29 | https://www.intel.com/content/www/us/en/docs/programmable/683112 |

### 16.4 Models and simulation

| Key | Document | Rev or date | URL |
|---|---|---|---|
| TS1.1 | IBIS Open Forum, Touchstone File Format Specification Rev 1.1 (draft) | 2002 (footer 2003-10-01) | https://www.ibis.org/connector/touchstone_spec11.pdf |
| TS2.0 | IBIS Open Forum, Touchstone File Format Specification Version 2.0 | ratified 2009-04-24 | https://www.ibis.org/touchstone_ver2.0/touchstone_ver2_0.pdf |
| TS2.1 | IBIS Open Forum, Touchstone File Format Specification Version 2.1 | ratified 2024-01-26 | https://www.ibis.org/touchstone_ver2.1/touchstone_ver2_1.pdf |
| IBIS-8.0 | IBIS Version 8.0 | ratified 2025-12-05 | https://www.ibis.org/ver8.0/ver8_0.pdf |
| IBIS-TOOLS | IBIS Open Forum free tools (TSCHK, IBISCHK) | accessed 2026-10-15 | https://www.ibis.org/tools/ |
| FRICKEY | D. Frickey, Conversions Between S, Z, Y, h, ABCD, and T Parameters, IEEE T-MTT 42(2) pp.205 to 211 | 1994-02 | https://doi.org/10.1109/22.275248 |
| MARKS-WILLIAMS | Marks and Williams, comments on Frickey, IEEE T-MTT 43(4) | 1995-04 | https://doi.org/10.1109/22.375247 |
| KUROKAWA | K. Kurokawa, Power Waves and the Scattering Matrix, IEEE T-MTT 13(2) pp.194 to 202 (abstract only) | 1965-03 | https://ieeexplore.ieee.org/document/1125964 |
| SHLEPNEV | Y. Shlepnev, Quality metrics for S-parameter models, DesignCon IBIS Summit | 2010-02-04 | https://www.ibis.org/summits/feb10/shlepnev.pdf |
| GUSTAVSEN | Gustavsen and Semlyen, vector fitting, IEEE Trans. Power Delivery 14(3) pp.1052 to 1061 | 1999-07 | https://doi.org/10.1109/61.772353 |
| IEEE370 | IEEE 370-2020 (not read; metrics seen in a MathWorks implementation) | 2021-01-08 | https://standards.ieee.org/standard/370-2020.html |
| MURATA-S | Murata S-parameter data pages | updated 2026-09-08 | https://www.murata.com/en-us/tool/data/sparameterdata/sparameter-inductor |
| TDK-README | TDK Equivalent Circuit Model Library readme | 2016-07-15 | https://product.tdk.cn/system/files/dam/tvcl/readme_model_en_v201607.pdf |
| CC1721 | Coilcraft Doc 1721, When to use S-parameters | 2023-01-03 | https://coilcraft.com/getmedia/35dbfd16-8483-4ef7-bb07-9b28a04f6dcc/doc1721_when-to-use-s-parameters.pdf |
| QORVO-FORUM | Qorvo forum staff answers on TQP9111 and TQL9092 S-parameters | 2026-02 | https://forum.qorvo.com/t/tqp9111-s-parameters-file/24911 ; https://forum.qorvo.com/t/tql9092-s-parameter-file-s11-s22/24876 |
| ADI-FORUM | ADI EngineerZone threads 14881 and 103987 on S2P reference planes (search excerpt) | | https://ez.analog.com/ |
| LTSPICE-HELP | LTspice 26.0.2 installed help: .NET, E source, .LIB, Model Compatibility; LTspiceChangeLog.txt | 2026-04-29 | local install, C:\Program Files\ADI\LTspice\LTspiceHelp\ |
| NGSPICE-47 | ngspice-47 manual | 2026-08-11 | https://sourceforge.net/projects/ngspice/files/ng-spice-rework/47/ngspice-47-manual.pdf/download |
| KICAD-9 | KiCad 9 Eeschema manual, Simulator, IBIS models | 9.0 | https://docs.kicad.org/9.0/en/eeschema/eeschema.html |
| DARTER | darter, IBIS to ngspice converter | | https://github.com/russdill/darter |
| MT-099 | ADI MT-099, Analog Circuit Simulation (mirror) | Rev 0, 2009-01 | https://docs.ampnuts.ru/eevblog.docs/_Materials/Analog_Devices/MT-099.pdf |
| SBOA027 | TI SBOA027 (Burr-Brown AB-046), macromodel use | 1993-03 | https://www.ti.com/lit/pdf/sboa027 |

### 16.5 Boards

| Key | Document | Rev or date | URL |
|---|---|---|---|
| HRF-REV | HackRF documentation, List of Hardware Revisions (source commit ed221e65a9) | 2025-12-18 | https://hackrf.readthedocs.io/en/latest/list_of_hardware_revisions.html |
| HRF-REPO | greatscottgadgets/hackrf, hardware/hackrf-one | | https://github.com/greatscottgadgets/hackrf/commits/main/hardware/hackrf-one |
| PLUTO-HW | ADI wiki, ADALM-PLUTO hardware (revisions and design files) | modified 2023-03-21, approved 2024-05-15 | https://wiki.analog.com/university/tools/pluto/hacking/hardware |
| PLUTO-CAL | ADI wiki, ADALM-PLUTO calibration (plus or minus 25 ppm oscillator) | 2021-01-14 | https://wiki.analog.com/university/tools/pluto/users/calibration |
| LIME-USB | myriadrf/LimeSDR-USB | | https://github.com/myriadrf/LimeSDR-USB |
| LIME-USB-HF | Crowd Supply update, Optimising performance on HF (Lime team) | 2017-02-14 | https://www.crowdsupply.com/lime-micro/limesdr/updates/optimising-performance-on-hf |
| LIME-MINI | myriadrf/LimeSDR-Mini, hardware/1v3/LimeSDR_Mini_ChangeList.txt (commit fb012c8db9) | 2020-02-11 | https://github.com/myriadrf/LimeSDR-Mini |
| LIME-MINI2 | myriadrf/LimeSDR-Mini-v2: hardware/2v0 change list (5cb5ccac9d, 2025-01-30); hardware/2v4 change list; docs/v2.2/index.rst (72795ccf52, 2024-12-02); 2v5 commits 8c7fa4e2f8, 18592d4f2c, 268e183eec, ef33ceacfe, 20a9fe973a | 2024 to 2026-10 | https://github.com/myriadrf/LimeSDR-Mini-v2 |
| FMC5-HW | analogdevicesinc/documentation, fmcomms5 hardware.rst (be9146da17) | 2026-06-17 | https://github.com/analogdevicesinc/documentation/blob/main/docs/solutions/reference-designs/fmcomms5/hardware.rst |
| FMC2-HW | analogdevicesinc/documentation, fmcomms2 hardware.rst (b9515ab6c4) | 2026-03-26 | https://github.com/analogdevicesinc/documentation/blob/main/docs/solutions/reference-designs/fmcomms2/hardware/hardware.rst |

## Appendix A. Public review checklists we borrow from

| Checklist | Items worth borrowing | Source |
|---|---|---|
| Skyworks AN1051 (Si534x) | Termination by output format; Xc under 5 ohm; no crystal load caps; avoid clipped sine; beads usually not needed but keep a 0 ohm footprint | [AN1051 §2.1 to 2.4 p.4 to 10] |
| TI SPRAD21J (AM62x) | Crystal load includes PCB capacitance; no DC on XI; no SSC on MCU_OSC0; buffer an oscillator shared with a PHY | [SPRAD21J §6.1.3.1 p.30 to 31] |
| AMD UG583 (RFSoC) | External RF clock P/N skew under 4 ps and 49/51% duty; unused ADC and DAC tie-offs; guard trace about 10 dB isolation | [UG583 v1.29 RFSoC sections] |
| ADI UG-570 (AD9361) | External reference AC-coupled into XTALN, XTALP floating, at most 1.3 Vpp; separate LDO for synthesizer and LO rails | [UG-570 p.14 to 15, 117 to 126] |
| Altera 683112 (Agilex 7) | P-tile HCSL refclk DC-coupled only; R-tile PERST after both refclks are stable | [683112] (search excerpt only) |


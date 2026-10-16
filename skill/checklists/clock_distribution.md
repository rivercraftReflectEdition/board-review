# Clock distribution

Applies to differential clocks, clock buffers, PLLs, VCXOs, TCXOs and reference inputs.
Use [clocks and crystals](clocks_crystals.md) for CLK-1 to CLK-6 as well.
Record the part, output configuration, rail corners, clock rate, receiver and coupling mode for each path.
Missing data follows the not-published rule in [stage 4](../workflow/40_checks.md).

Every numerical pass limit comes from the board requirement or the selected part's datasheet.
If neither gives one, record JUDGMENT, the chosen number and the engineering reason before computing.
No supplied limit means INFO or UNKNOWN, never a pass. Typical networks below identify a starting
topology; the selected part's published circuit takes precedence.

Fetch manufacturer models into the local review folder at review time. Do not collect them in this
skill. For the driver and receiver, request IBIS files for the selected package, output mode, voltage
and temperature corner. For supply filters, request bead R/X curves or S-parameters with the stated
DC current and capacitor data at the operating bias. For PLL or oscillator supply/control behavior,
request the vendor's SPICE model and its supported simulator and operating range. Record filename,
vendor revision, source, model selection, bias, reference plane and validity range. Check whether a
model includes the internal termination and bias. IBIS defines buffer models; passive S-parameters
do not establish oscillator supply pushing or phase noise [IBIS-8.0, 2025-12-05, model sections;
CC1721, 2023-01-03, model-use discussion, page UNSURE]. Missing conditions or coverage mean UNSURE:
record source_unavailable or not published as appropriate, the omitted behavior and the bench test
that settles it. Do not substitute a model from another part. Model section/page details not supplied
in the offline plan need confirmation against the fetched files.

## CKD-1 Driver and receiver pairing
- Check: identify the actual output circuit and receiver limits, including coupling permission.
  Distinguish traditional HCSL from LP-HCSL. Record complementary VOH/VOL corner pairs, common-mode
  range, differential magnitude limits, pin abs max and any internal bias or termination.
- Why: the name HCSL does not identify the termination circuit. A source and sink can require
  opposite coupling modes [AN-879 Rev B, 2015-04-02, p.1 to 4; AN1051 Rev 0.3, 2021-07-26,
  sec.2.1 p.5]. Agilex P-tile DC-only coupling is UNSURE here: the plan has search excerpts only
  [683112, 2025-08-29, P-Tile section, page UNSURE]. Fetch the exact device guideline before judgment.
- Compute: `calc.clock_term.compat` for each supply, load, bias and temperature corner. For a divider,
  supply its Thevenin resistance and voltage, including receiver loading. Its VID is differential
  magnitude, equal to the peak-to-peak swing of one complementary leg. It is half the differential
  peak-to-peak swing. This conversion follows the complementary waveform definition [SLLA120,
  2002-12, p.3 to 5, 10 to 11; DERIVED].
  W12 quotes 626 mVpp per leg against a 450 mVpp maximum, a negative 176 mV swing margin.
  The arithmetic exceeds that stated maximum. UNSURE: the 127/52/31 ohm divider connectivity and
  the source's qualification or conclusion must be checked in AN-828 Rev A, 2014-04-30, p.11 Fig.11.
- Pass: every receiver datasheet common-mode, differential magnitude and pin-voltage limit holds
  at all corners, and both ends explicitly allow the chosen coupling. Record bounds that the
  calculator lacks as UNKNOWN; arithmetic does not establish coupling permission.
- Not published: request the missing receiver limits or coupling rule. Keep bias and coupling
  options reviewable and require a receiver-pin waveform test at supply corners.
- Example: [oscillator output domain](../lessons/oscillator-output-domain.md).

## CKD-2 Termination values and location
- Check: use the selected driver's network, including internal resistors. Locate series resistors
  at the source and receiver termination as the part requires [AN-953, 2017-03-06, p.1, 5 to 7, 17, 20].
- Why: loading changes both common mode and swing [SCAA062, 2003-03, Table 3 p.3;
  SLLA120, 2002-12, p.3 to 16]. Generic starting circuits are:

  | Output | Network | Source |
  |---|---|---|
  | LVPECL | Each leg sees Z0 to VCC minus 2 V, often a Thevenin pair | AN-828 Rev A, 2014-04-30, p.3 to 9 |
  | LVDS | 100 ohm across a 100 ohm differential receiver path, external or internal | SLLA120, 2002-12, p.10 to 11, 16 |
  | Traditional HCSL | About 49.9 ohm to ground per leg; series values per the part | AN-808 Rev A, 2013-12-04, p.1 to 2 |
  | LP-HCSL | Source series termination or integrated equivalent; no added end load | AN-879 Rev B, 2015-04-02, p.3 to 4; AN-891, 2023-12-05, p.1 to 2 |
  | CML | 50 ohm to VCC per leg, often internal; vendor exceptions apply | SLLA120, 2002-12, p.13 to 14; AN1051 Rev 0.3, 2021-07-26, p.5 |
  | LVCMOS | Source series resistance Z0 minus driver output resistance | AN-953, 2017-03-06, p.1, 5 |

- Compute: `calc.clock_term.termination`. Z0 is single-ended, so LVDS uses 2 Z0 across the pair.
  Supply effective driver resistance for LVCMOS and LP-HCSL. Supply `vendor_values_ohm` when the
  device requires a different circuit. The resistor keys are `r_up`, `r_down`, `r_diff`, `r_shunt`
  and `r_series`. Supply all fitted values and `error_limit_frac`; no tolerance is built in.
  W11 gives 126.9/82.5 ohm at 3.3 V and 250/62.5 ohm at 2.5 V for 50 ohm LVPECL.
  A 7 ohm LVCMOS driver needs 43 ohm in series for a 50 ohm source match
  [AN-828 Rev A, 2014-04-30, p.3; AN-953, 2017-03-06, p.1, 17; DERIVED].
- Pass: topology follows the driver and receiver datasheets. Fitted values, including tolerances,
  satisfy their permitted error. If no error is specified, choose and justify a numerical JUDGMENT
  limit based on the resulting swing and common-mode margin.
- Not published: request output resistance or the family termination note. A series value computed
  from assumed output resistance remains UNSURE until an IBIS or bench waveform check settles it.

## CKD-3 AC coupling and receiver re-bias
- Check: verify the driver's DC current path before each capacitor and the receiver's bias after
  it. Include internal bias, source termination and device-specific exceptions.
- Why: conventional emitter-follower LVPECL needs pull-down current even with AC coupling.
  Pull-downs vary by driver, including 140 to 240 ohm examples at 3.3 V. Si534x LVPECL instead
  requires no source pull-downs; its HCSL mode requires AC coupling and a divider, without 50 ohm
  source shunts [AN-828 Rev A, 2014-04-30, p.9, 13; SLLA120, 2002-12, p.13;
  AN1051 Rev 0.3, 2021-07-26, sec.2.1 p.4 to 6].
- Compute: `calc.clock_term.termination` with `topology="pull_down"` only for a conventional
  LVPECL emitter follower. Supply the datasheet average common mode and pull-down current per leg,
  or use the vendor's specified resistor values. Use `calc.clock_term.compat` with AC coupling
  and the receiver's Thevenin bias. Sweep resistor, leakage and supply corners externally.
- Pass: the driver datasheet DC path exists and the receiver datasheet bias and swing limits hold.
  A family label alone cannot override a part-specific circuit.
- Not published: request the family interface note and receiver bias impedance. Keep the check
  UNKNOWN and measure startup and receiver-pin common mode, including an interrupted clock.

## CKD-4 Coupling capacitance, duty and stopped clocks
- Check: capacitance at tolerance and bias, source resistance, full bias/load resistance, clock
  rate, duty range, bias offset, crossing slew and longest uninterrupted level or stopped interval.
- Why: the capacitor and bias network form a high-pass. Baseline shift moves the crossings, and
  restarting requires a transient check [SCAA059C, revised 2007-10, p.2;
  SCAA112, 2010-11, p.2, 6 to 7; AN-828 Rev A, 2014-04-30, p.13 Table 3].
- Compute: `calc.clock_term.ac_coupling`. Reduce the network per leg, including the differential
  resistor's equivalent load. Supply reactance, corner, fractional droop and per-edge timing limits.
  Its curves show high-pass gain and constant-level decay. The duty-offset and equal-slope timing
  estimates are DERIVED, valid for a repetitive two-level waveform with RC much longer than a period.
  Use the source waveform or a transient model for clipped sine, missing crossings and restart edges.
  W13: 100 nF and 50 ohm give 31.8 kHz. At 10 MHz, 100 nF gives 0.159 ohm and 1 nF gives
  15.9 ohm; compare with an explicitly selected 5 ohm limit. A 5 kohm bias gives 318 Hz. At 45% duty,
  3.3 Vpp and 2.64 V/ns, the ideal-source estimate is -165 mV and 62.5 ps per edge, or 1.25% of a
  period in high-time shift at 100 MHz. A five-bit run at 1.25 Gb/s with RC of 5 us loses 0.080%
  [AN1051 Rev 0.3, 2021-07-26, p.7; SCAA112, 2010-11, p.2, 6 to 7; DERIVED].
- Pass: use the receiver's amplitude, duty and timing requirement to set all four limits. AN1051
  suggests reactance below 5 ohm at the clock as a starting point for its devices, not a universal
  limit [AN1051 Rev 0.3, 2021-07-26, sec.2.2 p.7]. A generic corner ratio, droop percentage or
  startup hold time requires an explicit numerical JUDGMENT and reason. Check validity during
  the required observation window after enable; a fixed number of RC is not proof of a valid clock.
- Not published: request the permitted start/stop behavior and bias circuit. Require a scope test
  at the longest stopped interval and worst initial capacitor charge.

## CKD-5 PCIe reference clock
- Check: identify the PCIe generation, common-clock, SRNS or SRIS architecture, SSC configuration,
  filtered jitter metric, differential impedance and both ends' coupling rules. Verify REFCLK
  stability before reset release against the endpoint guideline.
- Why: traditional HCSL needs its DC shunts; adding end termination to LP-HCSL reduces swing
  [AN-808 Rev A, 2013-12-04, p.1 to 2; AN-879 Rev B, 2015-04-02, p.1 to 4]. The Si534x/Agilex
  coupling conflict in CKD-1 needs resolution before selecting a source.
- Compute: `calc.clock_term.termination`, `calc.clock_term.compat` and `jitter.rss`. Use the generation's
  PCIe filters; an unfiltered RMS integration is a different measurement [9QXL2001C R31DS0090EU0113,
  Rev 1.13, 2026-09-22, p.10, 12, 17; SKY-PCIE Rev 2.0, 2021-11-16, p.2 to 5].
- Pass: topology, 85 or 100 ohm target and timing follow the selected driver, receiver and PCIe
  architecture requirement. Datasheet common-clock comparison values after the PCIe filters are:

  | Generation | Reference value | Source |
  |---|---|---|
  | 1 | 86 ps peak to peak | 9QXL2001C Rev 1.13, 2026-09-22, p.12 Table 11 |
  | 2 | 3.1 ps RMS; 3.0 ps also appears, UNSURE | 9QXL2001C Rev 1.13, p.12; SKY-PCIE Rev 2.0, p.4 Table 1 |
  | 3 | 1.0 ps RMS | Same documents and pages |
  | 4 | 0.5 ps RMS | Same documents and pages |
  | 5 | 0.15 ps RMS | Same documents and pages |
  | 6 | 0.10 ps RMS | 9QXL2001C Rev 1.13, 2026-09-22, p.12 notes 6 to 9 |
  | 7 | 0.067 ps RMS | Same document and page |

  Confirm the applicable PCI-SIG requirement before using these as limits. Do not convert Gen 1
  peak-to-peak to RMS without a jitter model. Dividing by sqrt(2) for SRIS/SRNS is a documented
  allocation practice, not a universal specification [9QXL2001C Rev 1.13, p.12 note 10;
  SKY-PCIE Rev 2.0, p.5 Table 2]. SSC examples use 30 to 33 kHz and up to 0.5% down spread;
  check allowance in the selected architecture [SKY-PCIE Rev 2.0, p.4; 9FGV0231, 2025-12-01, p.1, 3, 6].
- Not published: obtain architecture-specific limits, filters and additive jitter. Keep the budget
  UNKNOWN and measure with the applicable filters. Gen 2 discrepancy needs the applicable CEM specification.

## CKD-6 Oscillator, buffer, PLL, VCXO and TCXO supplies
- Check: rail noise and part PSRR over sensitive offsets, switched loads, bead/inductor current
  rating at DC bias, effective capacitance and damping. Include control and analog supplies.
- Why: a bead plus capacitors can amplify supply noise and raise phase noise around 10 to 30 kHz
  offsets [AN10006 Rev 2.9, p.11 to 14]. Pluto's oscillator supply was changed to an ADM7160 LDO
  after degraded EVM [PLUTO-HW, modified 2023-03-21, approved 2024-05-15, Rev A narrative,
  unpaginated]. This is a supply-path warning, not a guaranteed improvement for every oscillator.
- Compute: `calc.lc_tank.lc_filter` using manufacturer data at operating bias. Set `peak_limit_db`
  explicitly from the allowed supply-noise transfer, then assess the full sensitive offset band,
  not only switcher harmonics. Use `jitter.spur_to_jitter` for measured supply-induced sidebands.
- Pass: rail noise and resulting phase noise meet the board requirement over the sensitive band.
  Any peaking allowance without a part limit is JUDGMENT with a stated number and reason.
  AN10006's bead rating of at least five times IDD and inductor rating of at least twice IDD are
  vendor guidance to assess for the selected device, not universal margins [AN10006 Rev 2.9,
  p.11 to 14]. AN1051 says beads are usually unnecessary for its parts and suggests a zero-ohm
  option [AN1051 Rev 0.3, 2021-07-26, sec.2.4 p.10].
- Not published: do not infer PSRR from decoupling. Record it missing, retain a quiet-supply or
  damping option as JUDGMENT, and inject ripple while measuring phase-noise sidebands
  [AN491 Rev 0.2, 2021-09-22, p.1 to 6].

## CKD-7 PLL loop filter
- Check: filter topology, Icp, N, PFD rate, Kvco range, tolerance and voltage corners, capacitor
  dielectric, leakage and VCO input capacitance.
- Why: loop bandwidth changes with Kvco and N. Dielectric absorption and microphonics are reasons
  to avoid X7R in the loop filter [ICS663 Rev E, 2006-01, p.5;
  SNAA106C, 2017-05, printed p.143, 287 to 288, 299].
- Compute: `pll.loop_filter_check` for every corner, and `pll.loop_filter_design` for candidate
  values. Confirm modeled control-node loading against the actual part [SNAA106C, 2017-05,
  printed p.339 to 347].
- Pass: bandwidth, phase margin, settling and spur rejection meet the board or PLL datasheet
  requirement at every corner. If none is specified, choose numerical JUDGMENT limits and explain
  the settling/peaking tradeoff. Use the device's dielectric and input-loading guidance; do not
  make the plan's 45 degree, 15% or four-times-C recommendations universal thresholds.
- Not published: request Kvco limits, leakage and input capacitance. Typical-only analysis stays
  UNKNOWN; bench lock transients and phase noise across tuning range settle it.

## CKD-8 Clipped-sine TCXO and reference inputs
- Check: internal/external DC-cut capacitor, receiver bias, source load, amplitude at corners,
  pin abs max and slew at the actual receiver crossing.
- Why: a clipped-sine source needs the load and bias intended by both ends. Slow crossings can
  increase buffer additive jitter; Si534x guidance says to avoid clipped sine
  [TG2520SBN, PDF 2018-04-03, p.1; SNAA411, 2024-09, p.4 to 6;
  AN766 Rev 0.1, 2021-09-23, p.2, 6; AN1051 Rev 0.3, 2021-07-26, sec.2.3.2 p.9].
- Compute: `calc.clock_term.ac_coupling` for corner and reactance only. Do not use its two-level
  duty-offset estimate as a clipped-sine waveform model. Measure or model receiver threshold
  crossings and use `calc.clock_term.compat` only where complementary level assumptions apply.
- Pass: source load and receiver swing, bias, slew and timing meet their datasheets. The Epson
  example specifies at least 0.8 Vpp into 10 kohm and 10 pF with a DC-cut capacitor; it is not a
  generic TCXO limit [TG2520SBN, PDF 2018-04-03, p.1]. AN766's 0.6 V/ns guidance applies to its
  buffer context [AN766 Rev 0.1, 2021-09-23, p.2, 6]. AD9361 external reference needs its own
  AC-coupled XTALN connection and amplitude limit [AD9361 Rev F, 2016-11, p.5;
  UG-570 Rev A, p.14 to 15].
- Not published: request receiver bias, threshold and slew limits. Require a buffer/bias option
  and measure duty and jitter at the receiver, including enable and cold startup.

## CKD-9 Crystal drive, load and part specification
- Check: extend CLK-2 and CLK-3 with drive power, crystal C0/CL and ESR definition, load and
  temperature/aging limits. Compare the exact crystal ordering code against the consumer's table.
- Why: drive and load are part-specific. A generic TSX-3225 40 MHz crystal on FMCOMMS2 is documented
  as not meeting AD9361 requirements [SNAA331, 2019-12, p.2 to 5; FMC2-HW, commit b9515ab6c4,
  2026-03-26, crystal discussion, unpaginated]. Si534x guidance has no external load caps and its
  own crystal guard-ring connection [AN1051 Rev 0.3, 2021-07-26, sec.2.3.1 p.8].
- Compute: `calc.crystal.drive_level` and `calc.crystal.load_capacitance`. Before using I squared R,
  establish whether the supplied ESR/current is motional or loaded; apply only the consumer's
  documented C0/CL correction. A missing definition is UNSURE. The existing calculator does not
  perform that correction automatically [SNAA331, 2019-12, p.2 to 5].
- Pass: actual drive is below the crystal datasheet maximum and frequency/load specs meet the
  consumer requirement. Any additional derating, including 80%, must be an explicit numerical
  JUDGMENT with a reason. Existing calculator classifications do not replace that documented limit.
- Not published: request ESR definition and maximum drive. Measure oscillator current with a
  suitable probe and account for probe loading; keep an assumed drive calculation UNKNOWN.

## CKD-10 Unused outputs, unused inputs and idle behavior
- Check: each unused output's disable/open/termination instruction, unused input bias, OE default
  and fail-safe behavior during stopped clocks or disconnected sources.
- Why: floating differential inputs without fail-safe can respond to noise; unused output rules
  vary by device [SNVA745, 2015-11, p.2 to 9; SLLA082B, 2001-10, p.2;
  SNLA187, 4th ed., 2008, p.37; AN-828 Rev A, 2014-04-30, p.2 to 3].
- Compute: digest pin instructions; `calc.clock_term.compat` for deliberate bias networks.
  Include leakage and internal pulls in worst-case bias values.
- Pass: selected-mode datasheet tie-offs hold. A fail-safe or offset network has a documented
  receiver threshold margin and permitted pin current. Do not apply generic 1 kohm pulls without
  checking the part [AN1051 Rev 0.3, 2021-07-26, sec.2.2 p.7 to 8].
- Not published: request unused-pin and fail-safe guidance. Choose any proposed network as
  JUDGMENT with explicit voltage/current limits; test disconnected and stopped-source behavior.

## CKD-11 Spread spectrum through the clock tree
- Check: center/down spread, depth, rate, extrema and every downstream PLL's tracking bandwidth
  and receiver permission. Include oscillator bypass inputs and SSC defaults.
- Why: receiver tracking and frequency range constrain SSC. Some oscillator inputs forbid it
  [AN10005 Rev 1.2, p.2, 5, 7; SCAA103, 2009-08, p.3 to 4;
  QUARTUS-BW v23.3, PLL Bandwidth option, unpaginated;
  SPRAD21J, revised 2026-10, sec.6.1.3.1 p.30 to 31].
- Compute: `jitter.ssc_emi` for an EMI estimate, plus explicit minimum/maximum frequency and PLL
  tracking checks against each consumer's datasheet. EMI reduction does not establish compatibility.
- Pass: every receiver explicitly permits the chosen spread, tracks it and stays within its
  required frequency range. Select down spread at a frequency ceiling only if the consumer allows it.
- Not published: SSC permission on ADC sample clocks or LO references is UNSURE. Obtain a vendor
  statement or measure the signal-chain impact; do not infer permission from a digital clock input.

## CKD-12 Jitter budget at each consumer
- Check: consumer jitter requirement, integration band and metric. Trace reference phase noise,
  multiplication, PLL transfer, buffer additive jitter and discrete spurs to the receiver.
- Why: phase-noise integration depends on the band. Buffer additive jitter and discrete spurs
  need their own entries [AN10007 Rev 1.21, p.3 to 10; AN256 Rev 0.4, 2021-09-21, p.1, 4;
  AN766 Rev 0.1, 2021-09-23, p.2 to 3; SNAA106C, 2017-05, printed p.1, 12, 228].
- Compute: `jitter.pn_to_jitter`, `jitter.multiply`, `jitter.spur_to_jitter` and `jitter.rss`.
  Record bands and independence assumptions; do not blindly RSS correlated terms. Validate the
  single-sided spur convention: the plan flags differing AN491/AN256 formulas as UNSURE
  [AN491 Rev 0.2, 2021-09-22, p.6 eq.1; AN256 Rev 0.4, 2021-09-21, p.4].
- Pass: total jitter meets the consumer requirement using its band and metric. Any reserved
  margin, including the plan's 20%, is a separately stated numerical JUDGMENT with a reason.
- Not published: request phase noise, integration band or additive jitter. Keep the affected budget
  UNKNOWN and measure at the receiver with the required filter and band.

## CKD-13 VCXO control noise and usable tuning range
- Check: DAC extrema, divider and buffer headroom, VCXO control limits, pull range, temperature
  and aging allowance, control-node filtering, noise and tuning sensitivity.
- Why: control noise becomes phase noise. A divider can prevent reaching the available pull
  range, as the LimeSDR Mini 2v5 tuning-DAC divider change documents
  [WENZEL-VCXO, undated, control-noise discussion, unpaginated;
  LIME-MINI2, 2v5 commits listed in the plan, 2024 to 2026, tuning-DAC change, unpaginated].
- Compute: `jitter.vc_noise`; `calc.divider.divider_output` for the DAC endpoints, with leakage,
  resistor and supply corners. Compare achieved control voltage with the required pull range.
- Pass: the datasheet control range and board frequency/aging requirement are covered at all
  corners. Control-noise contribution meets the allocated phase-noise requirement. If no allocation
  exists, choose a numerical JUDGMENT limit and explain its effect; 10 dB separation is not automatic.
- Not published: request Kv and noise data. A sensitivity estimated from pull divided by control
  range is typical-only and UNSURE until tuning/noise measurements establish the corners.
